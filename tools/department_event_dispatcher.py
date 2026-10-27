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
import stat
import resource
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
    intake = rc.received_notification(root, record)
    if intake is not None:
        return value, rc.frozen_notification_route(root,record)['target_department'], True
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
        self.db.execute('''CREATE TABLE IF NOT EXISTS activation_recovery (
            event_key TEXT PRIMARY KEY, native_message_id TEXT, owner TEXT NOT NULL,
            status TEXT NOT NULL, detail TEXT NOT NULL, intent_json TEXT, updated_at TEXT NOT NULL)''')
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
        old = self.db.execute('SELECT * FROM wakeups WHERE event_key=?',(event,)).fetchone()
        if old and old['state']==state and old['detail']==detail and (turn_id is None or old['turn_id']==turn_id) and (native_message_id is None or old['native_message_id']==native_message_id):
            return False
        self.db.execute('UPDATE wakeups SET state=?,detail=?,turn_id=COALESCE(?,turn_id),native_message_id=COALESCE(?,native_message_id),updated_at=? WHERE event_key=?',
                        (state, detail, turn_id, native_message_id, now(), event))
        self.db.commit()
        return True

    def changed_summary(self, payload, name='last_summary'):
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoints(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        value = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        old = self.db.execute('SELECT value FROM checkpoints WHERE name=?',(name,)).fetchone()
        if old and old[0]==value:
            return False
        self.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',(name,value));self.db.commit()
        return True

    def checkpoint_value(self, name):
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoints(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        row = self.db.execute('SELECT value FROM checkpoints WHERE name=?',(name,)).fetchone()
        return row[0] if row else None

    def activation_state(self, row, status, detail):
        old = self.db.execute('SELECT * FROM activation_recovery WHERE event_key=?',(row['event_key'],)).fetchone()
        if old and old['status']==status and old['detail']==detail:
            return False
        self.db.execute('INSERT INTO activation_recovery VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_key) DO UPDATE SET status=excluded.status,detail=excluded.detail,updated_at=excluded.updated_at',
            (row['event_key'],row['native_message_id'],'operations',status,detail,None,now()))
        self.db.commit()
        return True

    def activation_intent(self, event):
        row = self.db.execute('SELECT intent_json FROM activation_recovery WHERE event_key=?',(event,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def reserve_activation(self, row, plan):
        # Original queue ID and one HQ owner survive duplicate events/restarts.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM activation_recovery WHERE event_key=?',(row['event_key'],)).fetchone()
            if old and old['intent_json']:
                result = {'state':'existing_single_recovery_intent','intent':json.loads(old['intent_json']),
                          'message_sent':False,'duplicate_ignored':True}
            else:
                if old and old['native_message_id'] not in {None,plan['original_message_id']}:
                    raise DispatchError('original native queue ID differs; never replace recovery intent')
                self.db.execute('INSERT INTO activation_recovery VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_key) DO UPDATE SET native_message_id=excluded.native_message_id,status=excluded.status,intent_json=excluded.intent_json,updated_at=excluded.updated_at',
                    (row['event_key'],plan['original_message_id'],'operations','reserved_not_sent','normal HQ policy/send still required',json.dumps(plan,ensure_ascii=False,sort_keys=True),now()))
                result = {**plan,'message_sent':False,'permission_issued':False}
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def rows(self):
        return [dict(v) for v in self.db.execute('SELECT * FROM wakeups ORDER BY updated_at,event_key')]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


LOGIN_LABEL = 'com.flashcast.department-event-dispatcher'


def service_python(root):
    """Pinned existing local interpreter; this binding grants no OS consent."""
    path = root / CONFIG
    config = json.loads(path.read_text()) if path.is_file() else {}
    runtime = config.get('service_runtime')
    if runtime is None:
        return sys.executable
    if not isinstance(runtime, dict) or runtime.get('schema') != 'existing-local-python-service-runtime/v1':
        raise DispatchError('exact existing service runtime binding required')
    binary = runtime.get('binary', {})
    executable = Path(binary.get('path', ''))
    if not executable.is_absolute() or not re.fullmatch(r'python3(?:\.[0-9]+)?', executable.name):
        raise DispatchError('exact pinned local Python executable required')
    resolved = executable.resolve()
    if str(resolved) != binary.get('real_path') or not resolved.is_file():
        raise DispatchError('existing service interpreter path drift; preserve current runtime')
    observed = resolved.stat()
    if (observed.st_uid != binary.get('uid') or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != binary.get('mode')
            or observed.st_mode & 0o022 or not os.access(resolved, os.X_OK)
            or hashlib.sha256(resolved.read_bytes()).hexdigest() != binary.get('sha256')):
        raise DispatchError('existing service interpreter bytes/owner/mode drift; rebind exact real source')
    return str(executable)


def _login_expected(root):
    """Read-only description of this user's one actual project entry."""
    if Path(root).resolve() != ROOT.resolve():
        raise DispatchError('only this actual project login service is supported')
    return {'Label': LOGIN_LABEL,
            'ProgramArguments': [service_python(root), '-u', '-B', str(root / 'tools/department_event_dispatcher.py'), 'serve-queue'],
            'WorkingDirectory': str(root), 'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False},
            'ThrottleInterval': 10, 'ProcessType': 'Background',
            # launchd cannot pre-open these Desktop logs in this user session.
            # The same Python entry opens its owned project logs after spawn.
            'StandardOutPath': '/dev/null', 'StandardErrorPath': '/dev/null'}



def configure_login_stdio(root):
    """Open project logs inside the actual original LaunchAgent process.

    The service label selects logging only, never identity or execution authority.
    Manual service startup retains its existing parent-opened log descriptors.
    """
    if os.environ.get('XPC_SERVICE_NAME') != LOGIN_LABEL:
        return False
    if Path(root).resolve() != ROOT.resolve():
        raise DispatchError('only the owned project login log directory is supported')
    directory = root / STATE
    if directory.is_symlink() or not directory.resolve().is_relative_to(Path(root).resolve()):
        raise DispatchError('project log directory must not escape through a symlink')
    directory.mkdir(parents=True, exist_ok=True)
    if directory.stat().st_uid != os.getuid():
        raise DispatchError('actual user-owned project log directory required')
    descriptors = []
    try:
        for name in ('app-background.stdout.jsonl', 'app-background.stderr.log'):
            path = directory / name
            descriptor = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
            descriptors.append(descriptor)
            observed = os.fstat(descriptor)
            if not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.getuid():
                raise DispatchError('only regular current-user project logs may receive service output')
        for descriptor, stream in zip(descriptors, (1, 2)):
            os.dup2(descriptor, stream)
        (directory / 'login-stdio-readback.json').write_text(json.dumps({
            'pid': os.getpid(), 'uid': os.getuid(), 'project_root': str(root),
            'service_label': LOGIN_LABEL, 'initialized_at': now(),
            'stdout': str(directory / 'app-background.stdout.jsonl'),
            'stderr': str(directory / 'app-background.stderr.log'),
            'security_settings_changed': False}, sort_keys=True) + '\n')
        return True
    except (OSError, DispatchError) as error:
        import syslog
        syslog.syslog(syslog.LOG_ERR, 'FLASH CAST original login stdio initialization failed: '
                      + type(error).__name__ + ' errno=' + str(getattr(error, 'errno', None)))
        raise
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def login_plan(root):
    native_queue_capability(root)
    return _login_expected(root)

def login_status(root):
    import plistlib
    path = Path.home() / 'Library/LaunchAgents' / (LOGIN_LABEL + '.plist')
    expected = _login_expected(root)
    installed = False
    if path.is_file() and not path.is_symlink():
        try:
            installed = plistlib.loads(path.read_bytes()) == expected
        except (ValueError, OSError, plistlib.InvalidFileException):
            pass
    observed = subprocess.run(['/bin/launchctl','print','gui/' + str(os.getuid()) + '/' + LOGIN_LABEL],
                              capture_output=True,text=True)
    found=re.search(r'(?m)^\s*pid = (\d+)\s*$',observed.stdout)
    owned = _owned_service_status(root)
    ready_path=root/STATE/'service-ready.json'
    try:
        ready=json.loads(ready_path.read_text()) if ready_path.is_file() else {}
    except (OSError,ValueError):
        ready={}
    activated=bool(installed and observed.returncode==0 and found and owned.get('running')
        and int(found[1])==owned.get('pid')==ready.get('pid')
        and ready.get('uid')==os.getuid() and ready.get('project_root')==str(root)
        and ready.get('native_transport_ready') is True)
    return {'label':LOGIN_LABEL,'plist_path':str(path),'exact_plist_installed':installed,
            'launchd_pid':int(found[1]) if found else None,
            'loaded_in_current_user_domain':installed and observed.returncode==0,
            'login_autostart_enabled':installed and observed.returncode==0,
            'activation_proven':activated,'owned_process_ready':activated,
            'actual_launchctl_exit_code':observed.returncode,
            'actual_launchctl_error':observed.stderr.strip(),
            'OS_restart_tested':False,'user_login_cycle_tested':False}


def install_login(root):
    """Actual activation, no sudo/TCC bypass. Existing foreign plists fail closed."""
    import plistlib
    import tempfile
    path = Path.home() / 'Library/LaunchAgents' / (LOGIN_LABEL + '.plist')
    expected = plistlib.dumps(login_plan(root),fmt=plistlib.FMT_XML,sort_keys=True)
    directory = root / STATE
    directory.mkdir(parents=True,exist_ok=True)
    previous_status=login_status(root)
    before = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    if path.is_symlink() or path.exists() and before != expected:
        raise DispatchError('existing login service differs; preserve it and require exact reviewed CAS successor')
    journal = directory / 'login-activation-journal.json'
    if before is None:
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.flashcast-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(expected);stream.flush();os.fsync(stream.fileno())
            if path.exists():
                raise DispatchError('late login plist CAS drift; no replacement')
            os.link(temporary,path)
        finally:
            os.unlink(temporary)
    result=subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(path)],
                          capture_output=True,text=True)
    status=login_status(root)
    service=background_status(root)
    ready_path=directory/'service-ready.json'
    ready=json.loads(ready_path.read_text()) if ready_path.is_file() else {}
    actual_ready=bool(service.get('running') and service.get('pid')==status.get('launchd_pid')
        and ready.get('pid')==service.get('pid') and ready.get('uid')==os.getuid()
        and ready.get('project_root')==str(root) and ready.get('native_transport_ready') is True)
    record={'schema':'project-user-login-activation/v1','project_root':str(root),'uid':os.getuid(),
            'label':LOGIN_LABEL,'plist_path':str(path),'before':'ABSENT' if before is None else 'EXACT_EXISTING',
            'plist_sha256':hashlib.sha256(expected).hexdigest(),'previous_loaded':previous_status['loaded_in_current_user_domain'],'bootstrap_exit_code':result.returncode,
            'bootstrap_error':result.stderr.strip(),'status':status,
            'launchd_loaded_proven':status['login_autostart_enabled'],'activation_proven':actual_ready,
            'owned_process_ready':actual_ready,'service':service,
            'next_owner':None if actual_ready else ('system-development' if status['login_autostart_enabled']
                else 'current macOS user / platform service custodian'),
            'unblock_action':None if actual_ready else ('Read login-status after the exact owned service-ready event; do not reinstall or duplicate the service'
                if status['login_autostart_enabled'] else
                'Resolve the recorded actual launchctl error in this user session; retry only this activation and preserve system protection'),
            'OS_restart_tested':False,'account_or_production_permission_issued':False}
    if journal.exists():
        import uuid
        journal=directory/('login-activation-attempt-'+str(uuid.uuid4())+'.json')
    journal.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    return record


def rollback_login(root):
    """Undo only this exact actually installed plist; never touch foreign agents."""
    path = root / STATE / 'login-activation-journal.json'
    if not path.is_file():
        raise DispatchError('actual exact login activation journal required')
    record = json.loads(path.read_text());target=Path(record['plist_path'])
    if (record.get('project_root')!=str(root) or record.get('uid')!=os.getuid()
            or target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest()!=record.get('plist_sha256')):
        raise DispatchError('exact current user/project/plist rollback CAS required')
    if record.get('previous_loaded') is True:
        return {'state':'preexisting_exact_loaded_login_service_preserved','unrelated_agents_changed':False}
    result=subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid())+'/'+LOGIN_LABEL],
                          capture_output=True,text=True)
    if result.returncode!=0 and login_status(root)['loaded_in_current_user_domain']:
        raise DispatchError('login service is still loaded; preserve actual failed rollback')
    retained=root/STATE/'preserved-login-plist-after-rollback.plist'
    if retained.exists():
        raise DispatchError('existing retained plist must not be overwritten')
    if record['before']=='ABSENT':
        os.replace(target,retained)
    return {'state':'exact_login_activation_rolled_back','previous_exact_plist_preserved':str(retained),
            'previously_existing_exact_plist_retained':record['before']!='ABSENT',
            'unrelated_agents_changed':False,'OS_restart_tested':False}

def _owned_service_status(root):
    pid_path = root / STATE / 'service.pid'
    if not pid_path.exists():
        return {'running': False}
    try:
        pid = int(pid_path.read_text().strip())
        if pid <= 1:
            raise ValueError('invalid owned service PID')
    except (OSError, ValueError):
        return {'running': False, 'pid_source_invalid': True}
    observed = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'uid=,pid=,ppid=,etime=,command='],
                              capture_output=True, text=True)
    columns=observed.stdout.strip().split(None,4)
    # ps renders an unquoted pathname (the project may contain spaces). Require
    # the actual Python executable and exact script/command suffix, never a
    # shell containing these words. PID/UID alone cannot authorize a signal.
    script = str(root / 'tools/department_event_dispatcher.py')
    command = columns[4] if len(columns) == 5 else ''
    suffix = script + ' serve-queue'
    prefix = command[:-len(suffix)].strip() if command.endswith(suffix) else ''
    parts = prefix.split()
    owned_python = bool(parts and re.fullmatch(r'python(?:3(?:\.[0-9]+)?)?', Path(parts[0]).name, re.I)
                        and all(flag in {'-u', '-B'} for flag in parts[1:]))
    running = (observed.returncode == 0 and len(columns)==5 and columns[0]==str(os.getuid())
               and owned_python)
    return {'running': running, 'pid': pid, 'actual_process': observed.stdout.strip()}


def service_source_hashes(root):
    names = ("department_event_dispatcher", "result_coordination", "workflow_control",
             "readonly_work_view_cache", "department_autonomy", "goal_continuity", "goal_source_recovery",
             "flashcast_ops", "goal_delivery_runtime", "department_rotation",
             "professional_web_execution", "professional_web_increment",
             "professional_cms_execution", "professional_cms_integration",
             "professional_cms_channel", "professional_cms_issuer", "chief_assistant_coordination",
             "original_production_delivery")
    values = {"tools/" + name + ".py": hashlib.sha256((root / "tools" / (name + ".py")).read_bytes()).hexdigest()
              for name in names}
    if (root / CONFIG).is_file():
        values[str(CONFIG)] = hashlib.sha256((root / CONFIG).read_bytes()).hexdigest()
    return values


def background_status(root):
    owned = _owned_service_status(root)
    try:
        ready = json.loads((root / STATE / 'service-ready.json').read_text())
    except (OSError, ValueError):
        ready = {}
    current = bool(owned['running'] and ready.get('pid') == owned.get('pid')
                   and ready.get('uid') == os.getuid() and ready.get('project_root') == str(root)
                   and ready.get('loaded_sources') == service_source_hashes(root)
                   and ready.get('python_real_path') == str(Path(service_python(root)).resolve()))
    try:
        scan = json.loads((root / STATE / 'service-scan-readback.json').read_text())
    except (OSError, ValueError):
        scan = {}
    scanned = bool(current and scan.get('pid') == owned.get('pid') and scan.get('uid') == os.getuid()
                   and scan.get('project_root') == str(root) and scan.get('loaded_sources') == service_source_hashes(root))
    return {**owned, 'current_source_ready':current, 'current_scan_completed':scanned,
            'last_completed_scan_at':scan.get('scan_completed_at') if scanned else None,
            'login_autostart_enabled':login_status(root)['login_autostart_enabled']}


def background_start(root):
    directory=root/STATE;directory.mkdir(parents=True,exist_ok=True)
    with (directory/'startup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _background_start_locked(root)


def _background_start_locked(root):
    native_queue_capability(root)
    status = background_status(root)
    if status['running']:
        return {**status, 'duplicate_start_ignored': True}
    login=login_status(root)
    if login['loaded_in_current_user_domain']:
        result=subprocess.run(['/bin/launchctl','kickstart','gui/'+str(os.getuid())+'/'+LOGIN_LABEL],
                              capture_output=True,text=True)
        return {'launchd_restart_requested':result.returncode==0,'actual_exit_code':result.returncode,
                'actual_error':result.stderr.strip(),'readback_required':True,
                'login_autostart_enabled':True,'duplicate_manual_daemon_started':False}
    directory = root / STATE
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'app-background.stdout.jsonl').open('a') as out, \
            (directory / 'app-background.stderr.log').open('a') as err:
        child = subprocess.Popen([service_python(root), '-u', '-B', str(root / 'tools/department_event_dispatcher.py'), 'serve-queue'],
                                 cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                 start_new_session=True, close_fds=True)
    (directory / 'service.pid').write_text(str(child.pid) + '\n')
    return {'started_pid': child.pid, 'readback_required': True, 'login_autostart_enabled': login_status(root)['login_autostart_enabled']}


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
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.stderr_tail = ''
        self.stderr_lock = threading.Lock()
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.stderr_reader.start()
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

    def _read_stderr(self):
        for chunk in iter(lambda: self.proc.stderr.read(1024), ''):
            with self.stderr_lock:
                self.stderr_tail = (self.stderr_tail + chunk)[-4096:]

    def disconnect_details(self):
        # Only bounded diagnostics; never persist credentials from an error.
        self.stderr_reader.join(timeout=0.1)
        with self.stderr_lock:
            tail = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[=:]\s*)[^\s,;]+',
                          r'\1[REDACTED]', self.stderr_tail)
            tail = re.sub(r'\bsk-[A-Za-z0-9_-]{8,}\b', '[REDACTED]', tail)
        return {'exit_code': self.proc.poll(), 'stderr_tail': tail,
                'fallback_started': False}

    def disconnected_error(self):
        details = self.disconnect_details()
        return {'message': 'shared transport disconnected: ' + json.dumps(details, ensure_ascii=False),
                'transport_diagnostic': details}

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
            failure = self.disconnected_error()
            for waiting in list(self.pending.values()):
                waiting.put({'error': failure})
            self.notify()

    def call(self, method, params, timeout=20):
        if self.closed:
            error = self.disconnected_error()
            exc = DispatchError(error['message'])
            exc.transport_diagnostic = error['transport_diagnostic']
            raise exc
        self.counter += 1
        number = self.counter
        waiting = queue.Queue()
        self.pending[number] = waiting
        try:
            self.send({'id': number, 'method': method, 'params': params})
            value = waiting.get(timeout=timeout)
            if 'error' in value:
                exc = DispatchError(str(value['error'].get('message', 'RPC error')))
                exc.transport_diagnostic = value['error'].get('transport_diagnostic')
                raise exc
            return value['result']
        except queue.Empty as exc:
            raise DispatchError('RPC response uncertain: ' + method) from exc
        except (BrokenPipeError, OSError) as error:
            failure = self.disconnected_error()
            exc = DispatchError(failure['message'])
            exc.transport_diagnostic = failure['transport_diagnostic']
            raise exc from error
        finally:
            self.pending.pop(number, None)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.stderr_reader.join(timeout=0.2)


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

    def pump(self, valid_events=None, only_events=None):
        import workflow_control as w
        for row in self.store.rows():
            from department_autonomy import ASSISTANTS,current_mode
            if current_mode(self.store.root) and row.get('target') in ASSISTANTS:
                continue  # preserve frozen record; no new assistant activation
            if only_events is not None and row['event_key'] not in only_events:
                continue
            if row['state'] in {'native_queue_accepted', 'resolved_by_original_intake'}:
                if valid_events is not None and row['event_key'] not in valid_events:
                    self.store.activation_state(row,'source_or_effect_blocked','original source is invalid; inspect exact effect before recovery')
                    continue
                try:
                    activation_probe(self.store, row)
                except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
                    self.store.activation_state(row, 'source_or_effect_blocked', str(exc))
                continue
            if row['state'] == 'wake_acknowledged':
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
                    try:
                        turn = self.transport.recover(row['target'], row['event_key'], json.loads(row['identity_json']))
                    except Exception as error:
                        self.store.set(row['event_key'],'uncertain',str(error))
                        continue
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
                + '\n沿原任务恢复：从现有结果队列实际收取准确成果。operations只知悉和协调依赖；专业协作结果归原主负责人继续自检与授权执行，不派助理审批，复用原已验结果。'
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


def resume_registered_results(root, store, transport):
    """Reconcile exact pending READY requests on existing source/event changes.

    Source history is read-only. Actual result admission still goes through
    record_result_handoff and the original notification/idempotency store.
    An uncertain/committed original effect is never turned into a new result.
    """
    import workflow_control as w
    import goal_continuity as gc
    import result_coordination as rc
    if not isinstance(transport,OfficialQueueTransport): return []
    events = w.read_jsonl(root/w.WORKFLOW_EVENTS)
    pending = [e for e in events if e.get('details', {}).get('original_result_registration_pending')]
    outcomes = []
    for event in pending:
        item = event['details']['original_result_registration_pending']
        fingerprint, name = None, None
        try:
            value = rc.exact_identity(item['identity']); task = value['task_id']
            if event.get('task_id') != task: raise DispatchError('pending source task differs from its event')
            request = gc.pin_document(root,item['original_request'])
            if rc.exact_identity(request) != value or request.get('event') != 'notification_queued':
                raise DispatchError('exact original READY identity/request required')
            effect = [r for r in w._result_handoff_rows(root,task)
                      if r.get('event') == 'notification_queued' and rc.exact_identity(r) == value]
            if effect:
                if len(effect) != 1: raise DispatchError('ambiguous original notification effect')
                continue  # Already registered: ingest/pump owns its one transport.
            versions = [w.file_digest(root,str(w.receipts_path(root,task).relative_to(root))),
                        w.file_digest(root,'data/department-registry.json'),
                        w.file_digest(root,'data/department-current-assignment.json')]
            task_events = [e for e in events if e.get('task_id') == task]
            fingerprint = {'input':item,'versions':versions,
                           'task_event':task_events[-1].get('event_hash') if task_events else None,
                           'native_turn_event':store.checkpoint_value('native-complete:'+value['sender_department'])}
            name = 'source-registration:'+w.sha256_value(value)
            digest = hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
            if store.checkpoint_value(name) == digest: continue
            snapshot = gc._task(root,task)
            if snapshot.get('current_state') in w.TERMINAL_STATES:
                raise DispatchError('closed source cannot create a new notification')
            rows = w.read_jsonl(w.receipts_path(root,task))
            if not any(r.get('receipt_type') == 'chat_ack' and r.get('department') == value['sender_department']
                       and r.get('ack_nonempty') is True for r in rows):
                outcomes.append({'identity':value,'state':'await_actual_ACK_registration','next_owner':value['sender_department']})
                store.changed_summary(fingerprint,name)
                continue
            role = value['sender_department']; fixed = binding(root,role)
            base = transport._read(role)  # Canonical persisted identity only.
            native_page = transport.history.call('thread/turns/list',{'threadId':fixed['task_id'],
                'limit':20,'sortDirection':'desc','itemsView':'full'})
            turns = [t for t in native_page.get('data',[]) if t.get('id') == request.get('source_turn_id')]
            if len(turns) != 1: raise DispatchError('exact source turn not present in the bounded official history read')
            native = {**base,'turns':turns,'raw_turns_response':native_page}
            directory = root/STATE/'prepared'/('source-registration-'+w.sha256_value(value))
            directory.mkdir(parents=True,exist_ok=True)
            native_path = directory/('actual-native-'+w.sha256_value(native)+'.json')
            if not native_path.exists(): w.atomic_write_json(native_path,native)
            observation = {'schema':'original-result-registration-observation/v1',
                'original_request':item['original_request'],
                'native_observation':w.file_digest(root,str(native_path.relative_to(root)))}
            observation_path = directory/('observation-'+w.sha256_value(observation)+'.json')
            if not observation_path.exists(): w.atomic_write_json(observation_path,observation)
            gc.observe_result_registration(root,str(observation_path.relative_to(root)))
            # Fresh normal source, SQL/native and idempotency checks, no direct
            # ledger/notification writes and no bypass of original action gates.
            result,_ = w.record_result_handoff(root,request)
            outcomes.append({'identity':value,'state':'original_request_registered',
                             'record_id':result['record_id'],'native_send_claimed':False})
            store.changed_summary(fingerprint,name)
        except (w.WorkflowError,DispatchError,OSError,ValueError,TypeError,KeyError) as exc:
            outcomes.append({'event_id':event.get('event_id'),'state':'source_registration_blocked',
                'reason':str(exc),'next_owner':'system-development','blocks_other_pending_results':False})
            # Record only a changed input/error. Never mark an unattempted effect
            # committed before executing it; crashes reconcile original effects.
            if fingerprint is not None and name is not None: store.changed_summary(fingerprint,name)
    return outcomes


def _received_notice_paths(root, value, rows):
    """Only canonical names from the real queued role and trusted rotation."""
    import result_coordination as rc
    import workflow_control as w
    queued = [r for r in rows if r.get('event') == 'notification_queued' and rc.exact_identity(r) == value]
    if len(queued) != 1:
        raise DispatchError('one original queued source required for frozen intake')
    role = queued[0].get('target_department') or queued[0].get('responsible_assistant')
    current = w.department_registry(root).get(role, {}).get('chat_binding', {})
    if not current.get('task_id'):
        raise DispatchError('original queued recipient role required')
    threads = {current['task_id']}
    from department_rotation import _records, _id
    for rotation in _records(root):
        if (rotation.get('role') == role and _id(rotation['new_binding']) == current['task_id']
                and all(rotation[k].get('cwd') == str(root.resolve()) for k in ('old_binding', 'new_binding'))):
            threads.add(_id(rotation['old_binding']))
    base = root / 'logs/result-notifications'
    names = {rc._key(value) + '.json'}
    for thread in threads:
        for purpose in rc.DELIVERY_PURPOSES:
            exact = {**value, 'target_department': role, 'target_thread_id': thread, 'purpose': purpose}
            names.add(rc._delivery_key(exact).split(':', 1)[1] + '.json')
    return [base / name for name in sorted(names) if (base / name).is_file()]


def _activation_record(root, value):
    import result_coordination as rc
    import workflow_control as w
    value = rc.exact_identity(value)
    # An existing committed intake is a historical effect, not a fresh route.
    # Validate its frozen recipient and SQL/native chain before later HQ sources.
    from readonly_work_view_cache import inventory_handoff_rows
    rows = inventory_handoff_rows(root, value['task_id'])
    if any(r.get('event') == 'controller_received' and rc.exact_identity(r) == value for r in rows):
        found = []
        for path in _received_notice_paths(root, value, rows):
            if path.is_symlink():
                continue
            try:
                record = w.read_json(path)
            except (ValueError, OSError):
                continue
            if record.get('identity') != value:
                continue
            exact = record.get('delivery_identity', {})
            rc.frozen_notification_route(root, record)
            canonical = rc._delivery_key(exact).split(':', 1)[1] + '.json'
            if path.name not in {canonical, rc._key(value) + '.json'}:
                raise DispatchError('original notification filename differs from frozen delivery identity')
            if rc.received_notification(root, record) is None:
                raise DispatchError('existing intake requires exact SQL/native commit')
            found.append(record)
        if len(found) != 1:
            raise DispatchError('one authentic frozen received notification required')
        return found[0]
    record = w.read_json(rc._notification_path(root, value))
    if record.get('identity') != identity(value):
        raise DispatchError('exact original notification required')
    return record


def _accepted_queue(root, value):
    """Read original acceptance, not a new notification or an editable label."""
    import result_coordination as rc
    import workflow_control as w
    record = _activation_record(root, value)
    received = rc.received_notification(root, record)
    if received:
        return record, received
    rc._validate_queued(root, value)
    route = rc.result_lane(root, value)
    exact = rc.delivery_identity(root, value, route=route)
    if record.get('delivery_identity') != exact:
        raise DispatchError('original queue recipient changed; no recovery to another thread')
    _original_queue_acceptance(root, value, record)
    return record, None


def _original_queue_acceptance(root, value, record):
    """Read an existing exact transport; never authorize another send."""
    import workflow_control as w
    import result_coordination as rc
    if record.get('identity') != identity(value):
        raise DispatchError('original exact queued identity required')
    rc.frozen_notification_route(root, record)
    exact = record['delivery_identity']
    q = record.get('native_queue_transport', {})
    payload = q.get('payload', {})
    path = inside(root, payload.get('path', ''))
    expected_dir = root / STATE / 'prepared' / key(value)
    if (q.get('state') != 'accepted' or q.get('event_key') != key(value)
            or path.parent != expected_dir or w.file_digest(root, payload['path']) != payload
            or q.get('payload_sha256') != payload.get('sha256')
            or q.get('thread_id') != exact['target_thread_id']):
        raise DispatchError('one exact accepted original queue transport required')
    result = w.read_json(expected_dir / 'native-queue-result.json')
    request = w.read_json(expected_dir / 'actual-prepare-request.json')
    policies = [p for p in w.read_jsonl(root / w.POLICY_DECISIONS)
                if p.get('decision_id') == q.get('policy_decision_id')]
    message = q.get('native_message_id')
    if (not isinstance(message, str) or not re.fullmatch(r'[0-9a-f-]{36}', message)
            or result.get('exit_code') != 0 or result.get('stderr')
            or result.get('stdout', '').strip() != 'Queued message ' + message + ' for thread ' + q['thread_id'] + '.'
            or any(result.get(k) != q.get(k) for k in ('thread_id', 'payload_sha256', 'policy_decision_id', 'started_at'))
            or request.get('result_notification') != identity(value) or request.get('payload') != payload
            or request.get('target_thread_id') != q['thread_id']
            or len(policies) != 1 or policies[0].get('status') != 'allow'
            or policies[0].get('department') != value['sender_department']
            or policies[0].get('task_id') != value['task_id']
            or policies[0].get('payload_sha256') != payload['sha256']
            or policies[0].get('target_department') != exact['target_department']
            or policies[0].get('target_thread_id') != exact['target_thread_id']):
        raise DispatchError('original normal policy, payload and actual queue success differ')
    return q


def _handoff_effect(root, record, intake):
    """Read append-only committed updates; intake remains terminal for transport."""
    import result_coordination as rc
    import workflow_control as w
    value = identity(record['identity']); target = record['route']['target_department']
    rows = w._result_handoff_rows(root, value['task_id'])
    same = [p for p in rows if all(p.get(k) == v for k, v in value.items())]
    received = [p for p in same if p.get('event') == 'controller_received']
    if len(received) != 1 or received[0] != intake:
        raise DispatchError('one exact original committed intake required')
    def committed(row):
        if (row.get('outbox') != intake.get('outbox')
                or row.get('coordinator_role', row.get('responsible_assistant')) != target):
            raise DispatchError('original responsible role/outbox differs')
        rc._committed_result(root, row)
        actor, owner = rc._committed_intake_actor(root, row)
        if actor != target or row.get('coordinator_owner', owner) != owner:
            raise DispatchError('actual original committed actor/owner differs')
    committed(intake)
    decisions = [p for p in same if p.get('event') == 'controller_decision']
    actions = [p for p in same if p.get('event') == 'controller_followthrough']
    if len(decisions) > 1 or (actions and len(decisions) != 1):
        raise DispatchError('ambiguous original decision for next action')
    decision = decisions[0] if decisions else None
    prior_time = w._parse_observed_at(intake.get('created_at'))
    if decision:
        committed(decision)
        at = w._parse_observed_at(decision.get('created_at'))
        if (rows.index(decision) <= rows.index(intake) or prior_time is None or at is None
                or not prior_time <= at <= dt.datetime.now(dt.timezone.utc)):
            raise DispatchError('original decision must follow actual intake')
        prior_time = at
    if actions and decision.get('decision') == 'close_scope':
        raise DispatchError('closed original decision cannot append a next action')
    prior = None; seen_ids = set(); seen_keys = set()
    for action in actions:  # native hash-chain order, never timestamp sorting
        committed(action)
        at = w._parse_observed_at(action.get('created_at'))
        if (rows.index(action) <= rows.index(decision) or at is None or prior_time is None
                or not prior_time <= at <= dt.datetime.now(dt.timezone.utc)
                or action.get('record_id') in seen_ids or action.get('idempotency_key') in seen_keys
                or action.get('decision_record_id', decision['record_id']) != decision['record_id']
                or action.get('remaining_requirement_id') != decision.get('remaining_requirement_id')):
            raise DispatchError('next-action identity, decision linkage or order differs')
        if prior:
            if (prior.get('followthrough_status') not in {'external_wait_registered', 'blocked_with_owner'}
                    or prior.get('evidence') == action.get('evidence')):
                raise DispatchError('only a waiting next action may receive new committed evidence')
            if prior.get('followthrough_status') == action.get('followthrough_status'):
                before = w._parse_observed_at(prior.get('next_check_at'))
                after = w._parse_observed_at(action.get('next_check_at'))
                if before is None or after is None or after <= before:
                    raise DispatchError('continued wait must advance the original recheck time')
            old_fence, new_fence = prior.get('coordination_fence'), action.get('coordination_fence')
            if type(old_fence) is int and type(new_fence) is int and new_fence < old_fence:
                raise DispatchError('original coordinator fence moved backwards')
        seen_ids.add(action.get('record_id')); seen_keys.add(action.get('idempotency_key'))
        prior, prior_time = action, at
    latest = actions[-1] if actions else None
    return {'state': 'received_next_step_recorded' if latest else 'received_awaiting_next_action',
            'intake_record_id': intake['record_id'],
            'decision_record_id': decision['record_id'] if decision else None,
            'next_action_record_id': latest['record_id'] if latest else None,
            'next_action_history': [p['record_id'] for p in actions],
            'next_step_status': latest.get('followthrough_status') if latest else None,
            'next_owner': (latest.get('next_owner') if latest else None) or (decision.get('next_owner') if decision else target),
            'unblock_condition': latest.get('unblock_condition') if latest else None,
            'next_check_at': latest.get('next_check_at') if latest else None,
            'transport_resolved_by_actual_intake': True,
            'adoption_or_business_effect_requires_normal_proof': True,
            'handoff_closed': False, 'business_goal_closed': False}


def _received_effect_or_block(root, record, intake):
    import workflow_control as w
    try:
        return _handoff_effect(root, record, intake)
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as error:
        return {'state': 'received_next_step_read_blocked', 'intake_record_id': intake['record_id'],
                'transport_resolved_by_actual_intake': True, 'next_action_source_error': str(error),
                'source_repair_owner': 'system-development', 'handoff_closed': False,
                'business_goal_closed': False, 'original_queue_replay_allowed': False}


def activation_recovery_view(root, record):
    """Existing notification inventory exposes the one HQ owner, not a new queue."""
    import workflow_control as w
    event = key(record['identity'])
    path = Path(root) / STATE / 'transport.sqlite3'
    current = None
    if path.is_file():
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='activation_recovery'").fetchone():
                row = db.execute('SELECT status,detail,intent_json FROM activation_recovery WHERE event_key=?', (event,)).fetchone()
                if row:
                    current = {'status': row[0], 'detail': row[1], 'intent_reserved': bool(row[2])}
        finally:
            db.close()
    return {'event_key': event, 'recovery_owner': 'operations',
            'original_message_id': record.get('native_queue_transport', {}).get('native_message_id'),
            'state': current or {'status': 'awaiting_actual_receiver_observation'},
            'headless_activation_capability': 'DATA_MISSING',
            'official_owner_entry': [sys.executable, str(Path(root) / 'tools/department_event_dispatcher.py'),
                'activation-plan', '--event', event, '--desktop-proof', '<fresh-native-observation.json>'],
            'trigger': 'original receiver completion, receipt, source/config change or owned process startup',
            'ordinary_send_entry': 'goal_source_recovery.prepare_message then original HQ codex_app.send_message_to_thread only if ready_to_send',
            'acceptance_is_activation': False, 'no_result_replay': True,
            'unverified_app_server_start_allowed': False}


def activation_probe(store, row):
    import workflow_control as w
    try:
        return _activation_probe(store, row)
    except (w.WorkflowError, ValueError, KeyError, OSError, TypeError) as exc:
        store.activation_state(row, 'source_or_effect_blocked', str(exc))


def queue_grace_deadline(record):
    """Schedule a check only; this timestamp never grants a send or permission."""
    value = record.get('native_queue_transport', {})
    if value.get('state') != 'accepted':
        return None
    stamp = value.get('updated_at') or value.get('started_at')
    try:
        return dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')) + dt.timedelta(seconds=900)
    except (ValueError, TypeError, AttributeError):
        return None


def activation_wait_deadline(store, at=None):
    """Read the existing recovery view; one due event, never periodic polling."""
    at = at or dt.datetime.now(dt.timezone.utc)
    due, pending = set(), []
    for row in store.db.execute("SELECT event_key,detail FROM activation_recovery WHERE status='requires_official_HQ_observation'"):
        try:
            detail = json.loads(row['detail'])
            if detail.get('deadline_checked') or not detail.get('grace_deadline'):
                continue
            deadline = dt.datetime.fromisoformat(detail['grace_deadline'])
            if deadline.tzinfo is None:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        seconds = (deadline - at).total_seconds()
        if seconds <= 0:
            due.add(row['event_key'])
        else:
            pending.append(seconds)
    return (0.0 if due else min(pending) if pending else None), due


def _activation_probe(store, row):
    """Changed inputs only. Read-only history is not evidence that desktop is idle."""
    import workflow_control as w
    root = store.root
    value = json.loads(row['identity_json'])
    record = _activation_record(root, value)
    deadline = queue_grace_deadline(record)
    expired = deadline is not None and dt.datetime.now(dt.timezone.utc) >= deadline
    # All intake/queue/identity sources remain fresh in ingest. This fingerprint
    # only suppresses repeated recovery work, never caches policy or permission.
    observed = {'record': record, 'grace_expired': expired, 'binding': binding(root, row['target']),
                'completion_hint': store.checkpoint_value('native-complete:' + row['target']),
                'receipt_head': w.file_digest(root, str(w.result_handoff_path(root, value['task_id']).relative_to(root)))
                    if hasattr(w, 'result_handoff_path') else
                    [(p.name, p.stat().st_size, p.stat().st_mtime_ns)
                     for p in (root / 'logs/result-handoffs').glob(value['task_id'] + '*.jsonl')]}
    previous = None
    if getattr(store, 'db', None) is not None:
        found = store.db.execute('SELECT status FROM activation_recovery WHERE event_key=?', (row['event_key'],)).fetchone()
        previous = found[0] if found else None
    if previous in {'source_or_effect_blocked', 'received_next_step_read_blocked'}:
        # A repaired SQL/audit source can change without appending the native
        # message. Only failed projections depend on this repair epoch.
        observed['SQL_repair_epoch'] = [(str(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in (root / 'logs/result-coordination.sqlite3', root / 'logs/result-coordination.sqlite3-wal') if p.exists()]
    if not store.changed_summary(observed, 'activation-input:' + row['event_key']):
        return
    try:
        record, intake = _accepted_queue(root, value)
        if intake:
            store.set(row['event_key'], 'resolved_by_original_intake', 'original responsible intake already committed')
            effect = _received_effect_or_block(root, record, intake)
            store.activation_state(row, effect['state'], json.dumps(effect, sort_keys=True))
            if effect['state'] == 'received_next_step_read_blocked':
                observed['SQL_repair_epoch'] = [(str(p), p.stat().st_size, p.stat().st_mtime_ns)
                    for p in (root / 'logs/result-coordination.sqlite3', root / 'logs/result-coordination.sqlite3-wal') if p.exists()]
                store.changed_summary(observed, 'activation-input:' + row['event_key'])
            elif 'SQL_repair_epoch' in observed:
                observed.pop('SQL_repair_epoch')
                store.changed_summary(observed, 'activation-input:' + row['event_key'])
        else:
            store.activation_state(row, 'requires_official_HQ_observation',
                json.dumps({'reason': 'official queue accepted; verified headless activation unavailable',
                    'recovery_owner': 'operations', 'original_message_id': record['native_queue_transport']['native_message_id'],
                    'grace_deadline': deadline.isoformat() if deadline else None,
                    'deadline_checked': expired,
                    'trigger': 'actual receiver completion/intake, dependency/configuration change, service startup or one grace expiry',
                    'next_entry': 'original active HQ reads actual desktop then uses activation-plan; no second result package',
                    'automatic_activation_proven': False}, sort_keys=True))
    except (w.WorkflowError, ValueError, KeyError, OSError, TypeError) as exc:
        store.activation_state(row, 'source_or_effect_blocked', str(exc))


def _autonomous_activation_context(root, snapshot, value, record, row):
    """Authenticate the frozen professional task and original delivery, never retarget it."""
    import workflow_control as w
    import result_coordination as rc
    import department_autonomy as autonomous
    frozen = autonomous.document(root, snapshot['goal_contract'])
    goal = snapshot['goal_delivery']
    if (not autonomous.autonomous_goal(frozen) or not autonomous.autonomous_goal(goal)
            or frozen.get('task_id') != value['task_id']
            or any(goal.get(k) != frozen.get(k) for k in (
                'delivery_model', 'primary_owner', 'producer_departments', 'authorized_scope',
                'human_authorization', 'collaboration_scopes', 'parent_task_id'))
            or goal.get('source_mode') != frozen.get('source_mode', 'approved_dispatch')
            or frozen.get('authorization_pin') is not None
               and goal.get('authorization_pin') != frozen['authorization_pin']):
        raise DispatchError('unchanged frozen autonomous owner/producer/scope/authority required')
    expected = autonomous._autonomous_result_current_owner(root, snapshot, value)
    if expected == value['sender_department'] == frozen['primary_owner']:
        expected = 'operations'
    route = rc.frozen_notification_route(root, record)
    exact = record['delivery_identity']
    if expected=='operations' and route.get('target_department')=='operations-assistant':
        from chief_assistant_coordination import default_receiver,SOURCE as routine_SOURCE
        original_queue=rc._validate_queued(root,value)
        if original_queue.get('routine_route_authorization')==routine_SOURCE:expected=default_receiver(root,expected)
    lane = 'HQ_knowledge' if expected in {'operations','operations-assistant'} else 'professional_acceptance'
    if (row['target'] != expected or route['target_department'] != expected
            or route['lane'] != lane or exact['target_department'] != expected
            or exact['target_thread_id'] != binding(root, expected)['task_id']):
        raise DispatchError('original frozen professional/HQ result route required; no retarget')
    queued = rc._validate_queued(root, value)
    outbox = autonomous.document(root, queued['outbox'])
    scope = outbox.get('scope')
    if scope is None and len(frozen.get('authorized_scope', [])) == 1:
        scope = frozen['authorized_scope'][0]
    if (scope not in frozen.get('authorized_scope', [])
            or queued['outbox']['sha256'] != value['result_sha256']
            or outbox.get('task_id') != value['task_id']
            or outbox.get('department') != value['sender_department']
            or outbox.get('candidate_version') != value['candidate_version']):
        raise DispatchError('exact frozen result task/producer/version/SHA/scope required')
    # The receiver is not a new reviewer. The original professional producer
    # and owner retain their actual task responsibility/ACK (or human-direct source).
    for role in dict.fromkeys((frozen['primary_owner'], value['sender_department'])):
        autonomous.original_assignment_ready(root, snapshot, role)
    return {'scope': scope, 'sender_department': value['sender_department']
            if expected in {'operations','operations-assistant'} else 'operations',
            'delivery_model': autonomous.MODE, 'goal_contract': snapshot['goal_contract'],
            'original_owner': frozen['primary_owner'], 'original_producer': value['sender_department'],
            'frozen_recipient': expected, 'original_outbox': queued['outbox']}


def activation_plan(root, store, event, proof_pin):
    """Only produce/reserve an exact normal HQ request; never activate or adopt."""
    import workflow_control as w
    import result_coordination as rc
    from goal_delivery_runtime import restore_goal, _collaboration_native
    from goal_source_recovery import _native_container_valid
    rows = [p for p in store.rows() if p['event_key'] == event]
    if len(rows) != 1:
        raise DispatchError('one original enrolled transport required')
    row = rows[0]; value = json.loads(row['identity_json'])
    record, intake = _accepted_queue(root, value)
    if intake:
        store.set(row['event_key'], 'resolved_by_original_intake', 'original responsible intake already committed')
        effect = _received_effect_or_block(root, record, intake)
        store.activation_state(row, effect['state'], json.dumps(effect, sort_keys=True))
        return {**effect, 'message_sent': False}
    if store.activation_intent(event) is not None:
        return {'state': 'existing_single_recovery_intent', 'recovery_owner': 'operations',
                'intent': store.activation_intent(event), 'next_action': 'read original exact effect; never resend', 'message_sent': False}
    observation = w.read_json(inside(root, proof_pin['path']))
    if w.file_digest(root, proof_pin['path']) != proof_pin:
        raise DispatchError('exact current desktop proof bytes required')
    when = w._parse_observed_at(observation.get('observed_at'))
    if when is None or not 0 <= (dt.datetime.now(dt.timezone.utc) - when).total_seconds() <= 300:
        raise DispatchError('fresh actual desktop read required')
    page = _collaboration_native(root, observation.get('actual_native_target_turn'))
    target = binding(root, row['target']); source = binding(root, 'operations')
    SharedTransport._identity({**page.get('thread', {}), 'name': page.get('thread', {}).get('title')}, target)
    if (page.get('source_transport') == 'official_app_server_readonly_history'
            or not _native_container_valid(page) or not page.get('turns')
            or page['thread'].get('projectId') not in {None, target['project_id']}
            or page['thread'].get('archived') is True):
        raise DispatchError('actual non-archived desktop receiver observation required; readonly app-server status is insufficient')
    turn = page['turns'][0]
    if turn.get('status') in {'inProgress', 'pending'}:
        store.activation_state(row, 'receiver_active_original_queue_retained', 'busy receiver; no interruption or recovery intent')
        return {'state': 'waiting_receiver_completion', 'recovery_owner': 'operations', 'message_sent': False}
    if turn.get('status') not in {'completed', 'interrupted', 'failed'}:
        raise DispatchError('real ended receiver turn required; notLoaded alone is insufficient')
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, value['task_id'])))
    goal = snapshot.get('goal_delivery', {}); contract = snapshot.get('goal_contract')
    receipts, bad = w._validate_receipt_chain(root, value['task_id'])
    if (bad or snapshot.get('current_state') in w.TERMINAL_STATES or not contract
            or w.file_digest(root, contract['path']) != contract):
        raise DispatchError('active exact original goal, contract and receipt chain required')
    import department_autonomy as autonomous
    frozen = w.read_json(inside(root, contract['path']))
    autonomous_source = None
    if frozen.get('delivery_model') == autonomous.MODE:
        autonomous_source = _autonomous_activation_context(root, snapshot, value, record, row)
        scope = autonomous_source['scope']
        sender = autonomous_source['sender_department']
        source = binding(root, sender)
        action = 'resume-original-queue:' + record['native_queue_transport']['native_message_id']
        directory = root / STATE / 'prepared' / event / 'activation'
        directory.mkdir(parents=True, exist_ok=True)
        body = ('task_id=' + value['task_id'] + '\n' + 'scope=' + scope
                + '\nsender_department=' + sender + '\ntarget_department=' + row['target']
                + '\n原合同=' + contract['path']
                + '\n仅接续原已接受消息=' + record['native_queue_transport']['native_message_id']
                + '\n准确原成果=' + json.dumps(value, ensure_ascii=False, sort_keys=True)
                + '\n原成果路径=' + autonomous_source['original_outbox']['path']
                + '\n保留当前及暂停位置；忙时保留原队列。未收沿原入口实收并执行已授权下一动作；'
                  '已收不重收、不重复自检，只接原剩余动作。不复制原成果包，不新增任务、'
                  '账号、费用、网站/CMS/Ads、Git或生产权限。\n')
        body_path = directory / 'professional-exact-resume.txt'
        if body_path.exists():
            if body_path.read_text() != body:
                raise DispatchError('original autonomous recovery payload is immutable')
        else:
            body_path.write_text(body)
        payload = w.file_digest(root, str(body_path.relative_to(root)))
        mode = 'ordinary_original_professional_result_resume'
    else:
        if (frozen.get('delivery_model') not in {None, 'goal_delivery_assistant_v1'}
                or goal.get('delivery_model') not in {None, 'goal_delivery_assistant_v1'}
                or goal.get('responsible_assistant') != row['target']
                or len(goal.get('authorized_scope', [])) != 1):
            raise DispatchError('original historical assistant contract and sole binding required')
        sender = 'operations'
        scope = goal['authorized_scope'][0]
        sent = [p for p in receipts if p.get('receipt_type') == 'dispatch_sent' and p.get('department') == row['target']]
        paired = [(p, a) for p in sent for a in receipts if a.get('receipt_type') == 'chat_ack'
                  and a.get('department') == row['target'] and a.get('action_id') == p.get('action_id')
                  and a.get('ack_nonempty') is True and receipts.index(p) < receipts.index(a)]
        directory = root / STATE / 'prepared' / event / 'activation'
        directory.mkdir(parents=True, exist_ok=True)
        if not paired:
            if sent:
                return {'state': 'initial_responsibility_ACK_effect_required', 'recovery_owner': 'operations',
                        'next_action': 'read and recover the actual original initial dispatch/ACK; never resend it', 'message_sent': False}
            intents = [p['details']['initial_responsibility_message'] for p in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                       if p.get('task_id') == value['task_id'] and p.get('details', {}).get('initial_responsibility_message')]
            if len(intents) != 1:
                return {'state': 'original_initial_responsibility_source_required', 'recovery_owner': 'operations',
                        'next_action': 'use original contract-linked assign-goal-review entry, then recover actual dispatch/ACK', 'message_sent': False}
            payload = intents[0]['payload']
            if (w.file_digest(root, payload['path']) != payload or intents[0].get('goal_contract') != contract
                    or intents[0].get('sender_department') != 'operations' or intents[0].get('target_department') != row['target']
                    or intents[0].get('scope') != scope):
                raise DispatchError('original initial responsibility source differs')
            action = 'assign-goal-review:' + value['task_id']
            prior_policy = [p for p in w.read_jsonl(root / w.POLICY_DECISIONS) if p.get('task_id') == value['task_id']
                            and p.get('action_id') == action and p.get('status') == 'allow']
            if prior_policy:
                return {'state': 'original_initial_send_effect_unknown', 'recovery_owner': 'operations',
                        'next_action': 'read original HQ invocation and original queued assignment; use recover-queued-assignment with actual receiver ACK',
                        'initial_action': action, 'message_sent': False}
            mode = 'original_initial_responsibility'
        else:
            action = 'resume-original-queue:' + record['native_queue_transport']['native_message_id']
            body = ('原任务 ' + value['task_id'] + '\nscope=' + scope + '\n原合同=' + contract['path']
                    + '\n仅恢复已接受原消息 ' + record['native_queue_transport']['native_message_id']
                    + '\n准确原结果=' + json.dumps(value, ensure_ascii=False, sort_keys=True)
                    + '\n保留当前及暂停工作；沿原正常入口实收后执行已授权下一动作。已收取不重收，不复制结果包。'
                      '本通知不授账号、费用、网站/CMS/Ads、Git或生产许可。\n')
            body_path = directory / 'HQ-exact-resume.txt'
            if body_path.exists() and body_path.read_text() != body:
                raise DispatchError('original recovery payload is immutable')
            body_path.write_text(body)
            payload = w.file_digest(root, str(body_path.relative_to(root)))
            mode = 'ordinary_original_responsibility_resume'
    request = {'task_id': value['task_id'], 'sender_department': sender, 'scope': scope,
               'action_id': action, 'action_class': 'thread_message', 'source_project_id': source['project_id'],
               'target_department': row['target'], 'target_project_id': target['project_id'],
               'target_thread_id': target['task_id'], 'target_thread_title': target['title'],
               'target_cwd': target['cwd'], 'target_sidebar_section_id': target['sidebar_section_id'],
               'payload': payload, 'payload_sha256': payload['sha256'],
               'actual_target_state': observation['actual_native_target_turn'],
               'assignment_record_required': mode == 'original_initial_responsibility', 'authorization_changes': []}
    if autonomous_source is not None:
        # Same normal authorization reader used by prepare-message; no assistant
        # plan/ACK projection and no new policy/send before the durable intent.
        from goal_delivery_runtime import authorization_precheck
        checked = authorization_precheck(root, value['task_id'], request)
        reasons = [] if checked.get('status') == 'within_original_authorization' else checked.get('reasons') or ['normal_autonomous_authorization_required']
    else:
        reasons = w._ordinary_thread_dispatch_precheck(root, snapshot=snapshot, task_id=value['task_id'],
            target_department=row['target'], target_thread_id=target['task_id'], action_id=action,
            scope=scope, sender_department=sender, payload_sha256=payload['sha256'])
    if reasons:
        return {'state': 'normal_original_source_blocked', 'reasons': reasons, 'recovery_owner': 'operations',
                'mode': mode, 'message_sent': False}
    # A receipt may arrive or the role may rotate while the plan is being built.
    _, intake = _accepted_queue(root, value)
    if intake or binding(root, row['target']) != target:
        return {'state': 'source_changed_before_intent', 'message_sent': False}
    plan = {'event_key': event, 'original_message_id': record['native_queue_transport']['native_message_id'],
            'owner': 'operations', 'mode': mode, 'request': request, 'desktop_observation': proof_pin,
            'original_professional_source': autonomous_source,
            'state': 'reserved_not_sent', 'headless_activation_capability': 'DATA_MISSING',
            'before_actual_send': 'original HQ re-reads desktop; busy means retain this intent without sending. Normal fresh prepare/policy must allow. Unknown effect: read exact original request in target native history, never send twice.',
            'send_api': 'actual request sender uses codex_app.send_message_to_thread on original fixed recipient only after normal prepare; never impersonate another role or use independent app-server start'}
    return store.reserve_activation(row, plan)



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
    from readonly_work_view_cache import inventory_session
    with workflow.request_validation_context(), inventory_session(root):
        return _ingest_view(root,store,allowed)


def _ingest_view(root, store, allowed):
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
        try:
            import result_coordination as rc
            intake = rc.received_notification(root,record)
            if intake is not None:
                target = rc.frozen_notification_route(root,record)['target_department']
                event = store.put(value,target)
                store.set(event,'resolved_by_original_intake','original responsible intake already committed')
                valid.add(event)
                continue
            from department_autonomy import ASSISTANTS,current_mode
            from chief_assistant_coordination import authority as routine_authority
            active_chief=(record.get('route',{}).get('target_department')=='operations-assistant' and routine_authority(root) is not None
                and rc._validate_queued(root,value).get('routine_route_authorization')==__import__('chief_assistant_coordination').SOURCE)
            if current_mode(root) and record.get('route',{}).get('target_department') in ASSISTANTS and not active_chief:
                continue  # preserve the original transport; never wake a retired assistant
            if record.get('delivered'):
                continue
            def validate_unreceived():
                if not admitted_result(root,record,allowed):
                    return None
                return validate_notification(root,record)
            from readonly_work_view_cache import memoized_view
            result = memoized_view(root,'dispatcher-source-error',
                [str(path.relative_to(root)),record],validate_unreceived,
                required=[path,root/CONFIG],failures_only=True)
            if result is None:
                continue
            value, target, received = result
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append({'event_key': key(value), 'file': str(path.relative_to(root)),
                           'reason': str(exc), 'blocks_other_events': False})
            continue
        event = store.put(value, target)
        if received:
            store.set(event, 'resolved_by_original_intake', 'original responsible intake already committed')
        elif record.get('native_queue_transport', {}).get('state') == 'accepted':
            try:
                _accepted_queue(root, value)
            except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
                errors.append({'event_key':event,'file':str(path.relative_to(root)),
                               'reason':str(exc),'blocks_other_events':False})
                continue
            store.set(event, 'native_queue_accepted', 'official queue acknowledged; recipient intake not claimed',
                      native_message_id=record['native_queue_transport']['native_message_id'])
        elif record.get('native_queue_transport', {}).get('state') in {'sending', 'uncertain'}:
            store.set(event, 'uncertain', 'original queue owns unknown effect; inspect before any recovery')
        valid.add(event)
    return valid, errors


class NativeCompletionHints:
    """App-owned append-only session hints; only official history confirms them."""
    def __init__(self, path):
        self.path = Path(path)
        self.offset = self.path.stat().st_size
        self.tail = b''
        self.inode = self.path.stat().st_ino

    def read(self):
        try:
            current = self.path.stat()
            if current.st_ino != self.inode or current.st_size < self.offset:
                # Replaced/archived/history files never replay old completions.
                self.inode, self.offset, self.tail = current.st_ino, current.st_size, b''
                return []
            with self.path.open('rb') as stream:
                stream.seek(self.offset)
                raw = stream.read(4 * 1024 * 1024 + 1)
                self.offset = stream.tell()
            if len(raw) > 4 * 1024 * 1024:
                self.offset, self.tail = current.st_size, b''
                return []
            lines = (self.tail + raw).split(b'\n')
            self.tail = lines.pop()
            completed = []
            for line in lines:
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                payload = value.get('payload', {})
                turn = payload.get('turn_id')
                if (value.get('type') == 'event_msg' and payload.get('type') == 'task_complete'
                        and isinstance(turn, str) and re.fullmatch(r'[0-9a-f-]{36}', turn)):
                    completed.append(turn)
            return completed
        except OSError:
            return []


def attach_completion_events(watcher, transport, store):
    if not isinstance(transport, OfficialQueueTransport):
        return
    registry = json.loads((watcher.root / 'data/department-registry.json').read_text())
    for role in registry['departments']:
        if not role.get('new_dispatch_enabled'):
            continue
        try:
            native = transport._read(role['id'])
            path = Path(native['thread']['path'])
            fixed = role['chat_binding']['task_id']
            # The API supplies the actual current role path. No history globbing,
            # thread resume, arbitrary caller path or old archived binding.
            if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                    or not path.name.endswith(fixed + '.jsonl')):
                continue
            watcher.attach_native(path, role['id'], transport, store)
        except (DispatchError, KeyError, OSError, ValueError):
            continue


def ensure_descriptor_capacity(additional):
    """Match this process's soft limit to real watch demand; preserve hard/system limits."""
    if type(additional) is not int or additional < 0:
        raise DispatchError('nonnegative actual descriptor demand required')
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    opened = len(os.listdir('/dev/fd'))
    required = opened + additional + 64  # bounded RPC/SQLite/stdout headroom
    if soft != resource.RLIM_INFINITY and soft < required:
        if hard != resource.RLIM_INFINITY and required > hard:
            raise DispatchError('owned watcher needs ' + str(required) + ' descriptors; process hard limit is ' + str(hard))
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (required, hard))
        except (OSError, ValueError) as error:
            raise DispatchError('cannot set owned process soft descriptor limit: ' + str(error)) from error
    actual_soft, actual_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if actual_hard != hard or actual_soft != resource.RLIM_INFINITY and actual_soft < required:
        raise DispatchError('owned descriptor capacity readback differs; hard limit must remain unchanged')
    return {'before_soft':soft, 'current_soft':actual_soft, 'hard':hard,
            'actual_open_count':opened, 'additional_watch_count':additional,
            'required_with_headroom':required, 'hard_or_system_limit_changed':False}


class VnodeEvents:
    """macOS kqueue: block on file/native events, never a timed chat poll."""
    def __init__(self, paths, root=None):
        self.root = Path(root or ROOT)
        self.native = {}
        if not hasattr(select, 'kqueue'):
            raise DispatchError('kqueue is required on this local macOS host')
        self.queue = select.kqueue()
        self.fds = {}
        self.paths = [Path(v) for v in paths]
        self.fd_capacity_changes = []
        try:
            self.refresh()
        except BaseException:
            self.close()
            raise

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
        pending = [path for path in current if path not in self.fds and path.exists() and not path.is_symlink()]
        capacity = ensure_descriptor_capacity(len(pending))
        if capacity['before_soft'] != capacity['current_soft']:
            self.fd_capacity_changes.append(capacity)
        for path in pending:
            if path not in self.fds and path.exists() and not path.is_symlink():
                fd = os.open(path, os.O_RDONLY)
                self.fds[path] = fd
                self.queue.control([select.kevent(fd, filter=select.KQ_FILTER_VNODE,
                    flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                    fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_RENAME | select.KQ_NOTE_DELETE)], 0, 0)

    def add_readable(self, fd):
        self.queue.control([select.kevent(fd, filter=select.KQ_FILTER_READ,
                            flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR)], 0, 0)

    def attach_native(self, path, role, transport, store):
        path = Path(path)
        if path not in self.native:
            self.native[path] = (role, NativeCompletionHints(path), transport, store)
            self.paths.append(path)
            self.refresh()

    def wait(self, timeout=None):
        rows = self.queue.control([], 32, timeout)
        if not rows:
            return False
        native_fds = {self.fds[p]:item for p,item in self.native.items() if p in self.fds}
        relevant = any(row.ident not in native_fds for row in rows)
        for row in rows:
            if row.ident not in native_fds:
                continue
            role, hints, transport, store = native_fds[row.ident]
            for turn in hints.read():
                try:
                    expected = binding(transport.root,role)
                    latest = transport.history.call('thread/turns/list',{'threadId':expected['task_id'],
                        'limit':1,'sortDirection':'desc','itemsView':'notLoaded'})['data']
                    if (latest and latest[0].get('id')==turn and latest[0].get('status')=='completed'
                            and not latest[0].get('error') and store.changed_summary(
                                {'turn_id':turn,'fixed_thread_id':expected['task_id']},'native-complete:'+role)):
                        relevant = True
                except (DispatchError,ValueError,OSError,KeyError):
                    pass
        self.refresh()
        return relevant

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.queue.close()


def main():
    def terminate_owned_service(signum,frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate_owned_service)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage-once', 'observe', 'serve', 'queue-once', 'serve-queue', 'status', 'probe',
                                          'start-background', 'background-status', 'stop-background', 'login-plan', 'login-status', 'install-login', 'rollback-login', 'activation-plan'])
    parser.add_argument('--desktop-proof', help='project-relative fresh native ACTIVE observation')
    parser.add_argument('--event', help='exact original event key for HQ activation recovery')
    args = parser.parse_args()
    if args.command == 'serve-queue':
        chosen = service_python(ROOT)
        if Path(sys.executable).resolve() != Path(chosen).resolve():
            os.execv(chosen, [chosen, '-u', '-B', str(ROOT/'tools/department_event_dispatcher.py'), 'serve-queue'])
        configure_login_stdio(ROOT)
    if args.command == 'activation-plan':
        if not args.event or not args.desktop_proof:
            raise DispatchError('exact original event and fresh pinned desktop observation required')
        import workflow_control as workflow
        store = Store(ROOT)
        try:
            result = activation_plan(ROOT, store, args.event,
                workflow.file_digest(ROOT, args.desktop_proof))
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:
            store.close()
        return 0
    config, allowed = load_pilot(ROOT)
    if args.command in {'login-plan','login-status','install-login','rollback-login'}:
        handler={'login-plan':login_plan,'login-status':login_status,'install-login':install_login,'rollback-login':rollback_login}[args.command]
        print(json.dumps(handler(ROOT),ensure_ascii=False));return 0
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
                              'transport_diagnostic': getattr(exc, 'transport_diagnostic', None),
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
            if args.command=='serve-queue':
                (ROOT/STATE/'service.pid').write_text(str(os.getpid())+'\n')
                (ROOT/STATE/'service-started.json').write_text(json.dumps({'pid':os.getpid(),'uid':os.getuid(),
                    'project_root':str(ROOT),'mode':'serve-queue','started_at':now()},sort_keys=True)+'\n')
            watcher = VnodeEvents([ROOT / 'logs/result-notifications', ROOT / 'logs/result-handoffs',
                                   ROOT / 'logs/receipts', ROOT / 'data/workflows', ROOT / 'logs',
                                   ROOT / 'logs/result-coordination.sqlite3', ROOT / 'logs/result-coordination.sqlite3-wal',
                                   ROOT / 'data/department-current-assignment.json', ROOT / 'data/task-contract.json',
                                   ROOT / CONFIG, ROOT / 'data/department-registry.json', ROOT / 'tools'],root=ROOT) \
                if args.command in {'observe', 'serve', 'serve-queue'} else None
            rpc, transport, signal_read, signal_write = None, None, None, None
            try:
                def signal_event():
                    if signal_write is not None:
                        try:signal_write.send(b'E')
                        except (BlockingIOError,OSError):pass
                if args.command in {'serve','serve-queue'}:
                    signal_read,signal_write=socket.socketpair()
                    signal_read.setblocking(False);signal_write.setblocking(False)
                    watcher.add_readable(signal_read.fileno())
                if args.command in {'queue-once', 'serve-queue'}:
                    cli = native_queue_capability(ROOT)
                    # This connection reads persisted identities only. No resume,
                    # turn/start or false busy/idle inference is permitted here.
                    rpc = RPC([cli, 'app-server', '--listen', 'stdio://'],notify=signal_event)
                    transport = OfficialQueueTransport(ROOT, rpc)
                    if watcher is not None:
                        attach_completion_events(watcher,transport,store)
                if args.command == 'serve':
                    if not args.desktop_proof:
                        raise DispatchError('live service requires fresh independent desktop proof')
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
                if args.command=='serve-queue':
                    (ROOT/STATE/'service-ready.json').write_text(json.dumps({'pid':os.getpid(),'uid':os.getuid(),
                        'project_root':str(ROOT),'native_transport_ready':isinstance(transport,OfficialQueueTransport),
                        'native_readonly_child_pid':rpc.proc.pid if rpc else None,
                        'descriptor_capacity_changes':watcher.fd_capacity_changes if watcher else [],'loaded_sources':service_source_hashes(ROOT),'python_executable':sys.executable,'python_real_path':str(Path(sys.executable).resolve()),'ready_at':now()},sort_keys=True)+'\n')
                registry_version=(ROOT/'data/department-registry.json').stat().st_mtime_ns
                code_sources=service_source_hashes(ROOT)
                deadline_only = None
                while True:
                    if service_source_hashes(ROOT)!=code_sources:
                        # Same owned entry, same durable transport store. exec closes
                        # non-inheritable locks/DBs and reloads adopted code, not a new runtime.
                        (ROOT/STATE/'source-restart-request.json').write_text(json.dumps({
                            'pid':os.getpid(),'uid':os.getuid(),'project_root':str(ROOT),
                            'before':code_sources,'after':service_source_hashes(ROOT),'at':now(),
                            'transport_ids_retained':True})+'\n')
                        os.execv(service_python(ROOT),[service_python(ROOT),'-u','-B',str(ROOT/'tools/department_event_dispatcher.py'),'serve-queue'])
                    changed=(ROOT/'data/department-registry.json').stat().st_mtime_ns
                    if watcher and changed!=registry_version:
                        attach_completion_events(watcher,transport,store);registry_version=changed
                    if rpc and rpc.closed:
                        raise DispatchError('shared connection lost; retained outbox requires reconnection')
                    config, allowed = load_pilot(ROOT)
                    if deadline_only is None:
                        registration_outcomes = resume_registered_results(ROOT,store,transport) if transport else []
                        valid, errors = ingest(ROOT, store, allowed)
                    Dispatcher(store, transport).pump(valid_events=valid, only_events=deadline_only)
                    summary = {'enrolled_results_found': len(valid), 'isolated_source_errors': errors,
                               'original_source_registration': registration_outcomes,
                               'headless_receiver_activation': 'DATA_MISSING; original operations activation-plan entry required',
                               'mode': 'official_native_queue' if getattr(transport,'queues_busy_recipient',False)
                                       else 'verified_shared_transport' if transport else 'observer_only',
                               'wakeups': [{k:row[k] for k in ['event_key','target','state','turn_id','native_message_id']}
                                           for row in store.rows()]}
                    if args.command == 'serve-queue':
                        # One compact owned readback, including unchanged scans;
                        # no business receipt, second ledger or periodic polling.
                        (ROOT/STATE/'service-scan-readback.json').write_text(json.dumps({
                            'pid':os.getpid(),'uid':os.getuid(),'project_root':str(ROOT),
                            'loaded_sources':code_sources,'scan_completed_at':now(),
                            'enrolled_results_found':len(valid),'isolated_source_error_count':len(errors),
                            'transport_rows':len(store.rows()),'descriptor_capacity_changes':watcher.fd_capacity_changes if watcher else [],'transport_ids_retained':True},sort_keys=True)+'\n')
                    if store.changed_summary(summary):
                        print(json.dumps({'observed_at':now(),**summary}),flush=True)
                    if watcher is None:
                        break
                    while True:
                        timeout, _ = activation_wait_deadline(store)
                        if watcher.wait(timeout):
                            deadline_only = None
                            break
                        _, due = activation_wait_deadline(store)
                        if due:
                            deadline_only = due
                            break
                        if rpc and rpc.closed:
                            raise DispatchError('native connection closed; preserve effects and restart owned service')
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
