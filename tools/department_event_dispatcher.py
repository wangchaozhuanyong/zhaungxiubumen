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
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path('data/department-event-dispatcher.json')
STATE = Path('logs/department-event-dispatcher')
HISTORY_STATES = {'native_queue_accepted','resolved_by_original_intake','wake_acknowledged'}
HISTORY_CHECKPOINT = 'dispatcher-bounded-history-sweep-v1'
HISTORY_CONTINUE = 'dispatcher-history-scan-continue'
HISTORY_MAX_ROWS = 4
HISTORY_SOFT_SECONDS = 2.0
INPUT_CONTINUE = 'dispatcher-current-notification-input-continue'
INPUT_MAX_ROWS = 1
INPUT_SOFT_SECONDS = 2.0
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

    def reserve_receiver(self, row):
        name='current-receiver-inflight:'+row['target']
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoints(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT value FROM checkpoints WHERE name=?',(name,)).fetchone()
            allowed=not old or old[0]==row['event_key']
            if allowed:self.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',(name,row['event_key']))
            self.db.commit()
            return allowed
        except Exception:
            self.db.rollback();raise

    def release_receiver(self, row, *, received=False, pre_send_failure=False):
        # An unknown/sent/accepted effect never releases its receiver slot.
        if not received and not pre_send_failure:return False
        current=self.db.execute('SELECT state FROM wakeups WHERE event_key=?',(row['event_key'],)).fetchone()
        if not received and (not current or current[0]!='waiting_policy_or_source'):return False
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoints(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',('current-receiver-inflight:'+row['target'],row['event_key']))
        self.db.commit();return True

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
             "qa_review_plan", "controller_progress", "controller_event_state",
             "professional_web_execution", "professional_web_increment",
             "professional_cms_execution", "professional_cms_integration",
             "professional_cms_channel", "professional_cms_issuer", "professional_cms_single_field_pending", "chief_assistant_coordination",
             "original_production_delivery", "builtin_wardrobe_current_binding", "r3_platform_binding_transport",
             "receipt_obligation_consumer")
    if (Path(root)/'tools/publication_deadline_runtime.py').is_file():
        names += ('publication_deadline_runtime',)  # optional separately adopted capability
    if (Path(root)/'tools/hq_bounded_web_admission.py').is_file():
        names += ('hq_bounded_web_admission',)
    if (Path(root)/'tools/hq_singlefield_test_successor.py').is_file():
        names += ('hq_singlefield_test_successor',)  # exact optional adopted source
    for name in ('hq_en2_readonly_source', 'hq_web_health_probe', 'hq_pub_health_probe', 'direct_handoff_readback',
                 'professional_cms_single_field_admission', 'professional_cms_singlefield_provider',
                 'professional_cms_singlefield_operator', 'professional_cms_singlefield_continuation'):
        if (Path(root)/('tools/'+name+'.py')).is_file():
            names += (name,)  # only actually adopted original PUB capability
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
            'loaded_module_bytes_verified':False,
            'source_ready_interpretation':'recorded startup source hashes match current files; not independent in-memory byte verification',
            'last_completed_handoff_scan':scan.get('handoff_scan') if scanned else None,
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
        self.notification_counts = {}
        self.notification_lock = threading.Lock()
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

    def count_notification(self, method):
        if not hasattr(self,'notification_lock'):
            self.notification_lock=threading.Lock();self.notification_counts={}
        key=method if isinstance(method,str) and method in NON_WORK_RPC_NOTIFICATIONS|KNOWN_WORK_RPC_NOTIFICATIONS|{'connection_closed'} else 'other_notification'
        with self.notification_lock:self.notification_counts[key]=self.notification_counts.get(key,0)+1

    def notification_snapshot(self):
        if not hasattr(self,'notification_lock'):return {}
        with self.notification_lock:return dict(self.notification_counts)

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
                    method=value.get('method')
                    self.count_notification(method)
                    if not isinstance(method,str) or method not in NON_WORK_RPC_NOTIFICATIONS:
                        self.events.put(value)
                        self.notify()
        finally:
            self.count_notification('connection_closed')
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



# Suppress only known non-work metrics. Unknown notifications remain wake-ups.
NON_WORK_RPC_NOTIFICATIONS = frozenset({'account/rateLimits/updated','thread/tokenUsage/updated'})
KNOWN_WORK_RPC_NOTIFICATIONS = frozenset({'turn/completed','turn/started','thread/status/changed',
    'thread/started','thread/archived','thread/unarchived','thread/name/updated','account/updated','error'})
WORK_VIEW_STATES = frozenset({'later_received_completed_owner_report',
    'historical_accepted_source_rejected','source_rejected_transport_unverified',
    'unknown_effect_readback_required','historical_source_read_only','later_original_owner_report',
    'later_received_original_owner_report','original_task_paused'})


def archived_queue_acceptance(root, record):
    """Validate an original archived receipt for display only; no send authority."""
    import result_coordination as rc
    import workflow_control as w
    value = rc.exact_identity(record.get('identity', {}))
    rc.frozen_notification_route(root, record)
    exact = record['delivery_identity']; q = record.get('native_queue_transport') or {}
    payload = q.get('payload') or {}; path = inside(root, payload.get('path', ''))
    if (q.get('state') != 'accepted' or q.get('event_key') != key(value)
            or q.get('thread_id') != exact['target_thread_id']
            or w.file_digest(root, payload['path']) != payload
            or q.get('payload_sha256') != payload.get('sha256')):
        raise DispatchError('archived accepted identity/payload/recipient differs')
    directory = path.parent
    receipt_path = directory/'native-queue-result.json'
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise DispatchError('original archived receipt file required')
    candidates = [directory/name for name in ('actual-prepare-request.json','actual-normal-prepare-request.json')
                  if (directory/name).is_file() and not (directory/name).is_symlink()]
    if len(candidates) != 1:
        raise DispatchError('one original archived normal preparation required')
    request = w.read_json(candidates[0]); result = w.read_json(directory/'native-queue-result.json')
    policies = [p for p in w.read_jsonl(root/w.POLICY_DECISIONS)
                if p.get('decision_id') == q.get('policy_decision_id')]
    message = q.get('native_message_id')
    if (not isinstance(message,str) or not re.fullmatch(r'[0-9a-f-]{36}',message)
            or result.get('exit_code') != 0 or result.get('stderr')
            or result.get('stdout','').strip() != 'Queued message '+message+' for thread '+q['thread_id']+'.'
            or any(result.get(k) != q.get(k) for k in ('thread_id','payload_sha256','policy_decision_id','started_at'))
            or request.get('result_notification') != value or request.get('payload') != payload
            or request.get('task_id') != value['task_id'] or request.get('sender_department') != value['sender_department']
            or request.get('delivery_mode') != 'official_native_queue'
            or request.get('target_thread_id') != q['thread_id'] or len(policies) != 1):
        raise DispatchError('archived original queue result differs')
    expected = {'status':'allow','action_class':'thread_message','department':value['sender_department'],
                'task_id':value['task_id'],'payload_sha256':payload['sha256'],
                'target_department':exact['target_department'],'target_thread_id':q['thread_id'],
                'scope':'department_result:'+value['task_id']+':'+value['sender_department']}
    if any(policies[0].get(k) != v for k,v in expected.items()):
        raise DispatchError('archived original normal policy differs')
    return {'state':'accepted','native_message_id':message,'target_thread_id':q['thread_id'],
            'payload_sha256':payload['sha256'],'read_only_historical_effect':True,
            'business_intake_proven':False,'new_send_allowed':False}


def notification_work_view(root, record, *, boundary=None, source_rejected=False):
    """Rebuildable independent transport/source facts; never permission or intake."""
    import workflow_control as w
    value = identity(record['identity']); q = record.get('native_queue_transport') or {}
    view = {'event_key':key(value),'identity':value,'original_notification_state':record.get('state'),
            'original_record_unchanged':True,'actionable':False,'new_send_allowed':False,
            'business_intake_proven':False,'source_boundary':(boundary or {}).get('state','source_rejected')}
    if record.get('state') in {'sending','uncertain'} or q.get('state') in {'sending','uncertain'}:
        return {**view,'state':'unknown_effect_readback_required','transport_state':'unknown',
                'original_effect_readback_required':True,'replay_allowed':False}
    if (boundary or {}).get('state') == 'later_received_completed_owner_report' and q.get('state') != 'accepted':
        return {**view,**boundary,'new_send_allowed':False,'actionable':False,
                'transport_state':'original_unsent_predecessor','business_intake_proven':False}
    if q.get('state') == 'accepted':
        try:
            effect = archived_queue_acceptance(root, record)
            return {**view,'state':'historical_accepted_source_rejected','transport_state':'accepted',
                    'historical_acceptance':effect,'source_status':'historical_read_only'
                    if (boundary or {}).get('state') == 'historical_assistant_transport' else 'not_admitted_for_new_send'}
        except (w.WorkflowError,ValueError,OSError,KeyError,TypeError) as exc:
            return {**view,'state':'source_rejected_transport_unverified','transport_state':'unverified_accepted_record',
                    'transport_validation_error_type':type(exc).__name__}
    if (boundary or {}).get('state') in {'later_original_owner_report','later_received_original_owner_report','original_task_paused'}:
        return {**view,**boundary,'actionable':False,'new_send_allowed':False,
                'business_intake_proven':False,'original_record_unchanged':True,
                'transport_state':'no_verified_acceptance',
                'original_intake_or_business_completion_inferred':False}
    return {**view,'state':'historical_source_read_only','transport_state':'no_verified_acceptance',
            'source_status':'rejected' if source_rejected else 'not_admitted_for_new_send'}


def remember_work_view(store, value, view):
    views = getattr(store,'notification_views',None)
    if views is None:store.notification_views = views = {}
    views[key(value)] = view
    found=store.db.execute('SELECT * FROM wakeups WHERE event_key=?',(key(value),)).fetchone()
    row=dict(found) if found is not None else None
    if row is not None:  # Never create a new wakeup from a historical display.
        store.activation_state(row,view['state'],json.dumps(view,sort_keys=True))


def forget_work_view(store, value):
    event=key(value)
    getattr(store,'notification_views',{}).pop(event,None)
    old=store.db.execute('SELECT status FROM activation_recovery WHERE event_key=?',(event,)).fetchone()
    row=store.db.execute('SELECT * FROM wakeups WHERE event_key=?',(event,)).fetchone()
    if old and row and old[0] in WORK_VIEW_STATES:
        store.activation_state(dict(row),'current_source_revalidated_checks_pending',
            json.dumps({'new_send_permission_issued':False,'original_transport_state':row['state'],
                        'ordinary_policy_and_effect_checks_still_required':True},sort_keys=True))


def record_source_block(store, row, state, detail):
    view = getattr(store,'notification_views',{}).get(row['event_key'])
    if view is not None:
        store.activation_state(row,view['state'],json.dumps(view,sort_keys=True))
    else:store.activation_state(row,state,detail)


class ScanObservations:
    """Best-effort phase-boundary metrics, no polling, bodies, tokens or authority."""
    PHASES = {'registration','ingest','pump','prepare','history','wait','root_observer','root_guard','publication_serial','receipt_consumer','receipt_row','publication_consumer'}
    def __init__(self, root, rpc=None, clock=time.monotonic, *, loaded_sources=None):
        self.path = Path(root)/STATE/'service-observation-readback.json'
        self.rpc,self.clock = rpc,clock
        self.loaded_sources={k:v for k,v in (loaded_sources or {}).items()
            if isinstance(k,str) and (k.startswith('tools/') and k.endswith('.py') or k==str(CONFIG))
            and '..' not in Path(k).parts and isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v)}
        self.number=0;self.stack=[];self.seconds={};self.counts={};self.errors={};self.slow={}
        self.trigger=[];self.write_errors=0;self.completed_at=None;self.result_counts={};self.slow_history={}
    def rpc_counts(self):
        reader=getattr(self.rpc,'notification_snapshot',None)
        try:data=reader() if callable(reader) else {}
        except Exception:
            self.write_errors+=1;return {}
        allowed=NON_WORK_RPC_NOTIFICATIONS|KNOWN_WORK_RPC_NOTIFICATIONS|{'other_notification','connection_closed'}
        return {k:v for k,v in data.items() if k in allowed and type(v)is int and v>=0} if isinstance(data,dict) else {}
    def save(self):
        try:
            import workflow_control as w
            top=self.stack[-1] if self.stack else None
            data={'schema':'dispatcher-phase-observation/v1','pid':os.getpid(),'at':now(),
                  'scan_number':self.number,'trigger_categories':self.trigger,'loaded_sources':self.loaded_sources,
                  'current_phase':top[0] if top else 'between_phases','current_event_hash':top[1] if top else None,
                  'phase_started_monotonic':top[2] if top else None,'phase_seconds_inclusive':dict(self.seconds),
                  'phase_calls':dict(self.counts),'phase_error_types':dict(self.errors),
                  'slow_prepare_events':sorted(self.slow.items(),key=lambda x:x[1],reverse=True)[:5],
                  'slow_history_events':sorted(self.slow_history.items(),key=lambda x:x[1],reverse=True)[:5],
                  'RPC_notification_counts':self.rpc_counts(),'scan_completed_at':self.completed_at,
                  'result_counts':self.result_counts,'observation_write_errors':self.write_errors,
                  'observation_is_permission':False}
            w.atomic_write_json(self.path,data)
        except Exception:self.write_errors+=1  # Observation is never a gate.
    def begin(self, triggers):
        self.number+=1;self.seconds={};self.counts={};self.errors={};self.slow={};self.slow_history={};self.completed_at=None
        self.trigger=sorted(set(triggers)&{'startup','file_change','rpc_signal','native_completion','grace_deadline','watch_event','receipt_continuation','history_continuation'})
        self.save()
    @contextmanager
    def phase(self, name, event=None):
        if name not in self.PHASES:raise ValueError('known observation phase required')
        safe=event if isinstance(event,str)and re.fullmatch('[0-9a-f]{64}',event) else hashlib.sha256(str(event).encode()).hexdigest() if event is not None else None
        started=self.clock();self.stack.append((name,safe,started));self.counts[name]=self.counts.get(name,0)+1;self.save()
        try:yield
        except BaseException as exc:
            kind=type(exc).__name__;self.errors[kind]=self.errors.get(kind,0)+1;raise
        finally:
            elapsed=max(0,self.clock()-started);self.seconds[name]=self.seconds.get(name,0)+elapsed
            if name=='prepare' and safe:self.slow[safe]=max(self.slow.get(safe,0),elapsed)
            if len(self.slow)>5:self.slow=dict(sorted(self.slow.items(),key=lambda x:x[1],reverse=True)[:5])
            if name=='history' and safe:self.slow_history[safe]=max(self.slow_history.get(safe,0),elapsed)
            if len(self.slow_history)>5:self.slow_history=dict(sorted(self.slow_history.items(),key=lambda x:x[1],reverse=True)[:5])
            self.stack.pop();self.save()
    def finish(self, counts):
        self.completed_at=now();self.result_counts={k:int(v)for k,v in counts.items()};self.save()


@contextmanager
def observed_phase(store, phase, event=None):
    observation=getattr(store,'observations',None)
    if observation is None:yield
    else:
        with observation.phase(phase,event):yield


class InputSlice:
    """Owned scheduling hints only; no permission, source PASS or effect cache."""
    def __init__(self, store, stage, entries, *, priority=(), continuation=False, exact=False):
        self.store,self.stage,self.exact=store,stage,exact
        self.name='dispatcher-bounded-'+stage+'-inputs-v1'
        self.started=time.monotonic();self.examined=0;self.available=dict(entries)
        if len(self.available)!=len(entries):raise DispatchError('one original input per cursor key required')
        self.plan={'schema':self.name,'known':{},'pending':[],'urgent':[],'prefer_urgent':True}
        if exact:
            self.selected=list(self.available)[:INPUT_MAX_ROWS]
            return
        raw=store.checkpoint_value(self.name)
        if raw:self.plan=json.loads(raw)
        p=self.plan
        if (not isinstance(p,dict) or set(p)!={'schema','known','pending','urgent','prefer_urgent'}
                or p['schema']!=self.name or not isinstance(p['known'],dict) or type(p['prefer_urgent']) is not bool
                or any(not isinstance(k,str) or not k or any(c in k for c in '\x00\n\r')
                       or not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for k,v in p['known'].items())
                or any(not isinstance(p[k],list) or len(p[k])!=len(set(p[k]))
                       or any(v not in p['known'] for v in p[k]) for k in ('pending','urgent'))
                or not set(p['urgent'])<=set(p['pending'])):
            raise DispatchError('intact owned input cursor required; no silent reset')
        for name,version in entries:
            if p['known'].get(name)!=version:
                p['known'][name]=version
                if name not in p['pending']:p['pending'].append(name)
                if name not in p['urgent']:p['urgent'].append(name)
        if not continuation:
            p['pending'] += [name for name,_ in entries if name not in p['pending']]
            # Current file/native events may retry the newest exact input, but
            # alternate with the retained old order; internal slices do not.
            if priority:
                name=next((v for v in priority if v in self.available),None)
                if name is not None and name not in p['urgent']:p['urgent'].append(name)
        preferred=[v for v in priority if v in p['urgent']]
        p['urgent']=preferred+[v for v in p['urgent'] if v not in set(preferred)]
        first='urgent' if p['prefer_urgent'] else 'pending';second='pending' if first=='urgent' else 'urgent'
        picked=next((v for k in (first,second) for v in p[k] if v in self.available),None)
        self.selected=[picked] if picked is not None else []
        self._save()

    def _save(self):
        if self.exact:return
        self.store.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',
            (self.name,json.dumps(self.plan,sort_keys=True,separators=(',',':'))))
        self.store.db.commit()

    @contextmanager
    def attempt(self, name):
        # A crash/interrupt keeps this original key. A handled failed attempt
        # moves only the inspection cursor, never marks its business completed.
        yield
        self.examined+=1
        if not self.exact:
            for field in ('pending','urgent'):
                if name in self.plan[field]:self.plan[field].remove(name)
            self.plan['prefer_urgent']=not self.plan['prefer_urgent'];self._save()

    def progress(self):
        remaining=[v for v in self.plan['pending'] if v in self.available] if not self.exact else []
        value={'schema':'bounded-current-notification-input-progress/v1','stage':self.stage,
            'examined_rows':self.examined,'remaining_runnable':len(remaining),
            'deferred_missing':len(self.plan['pending'])-len(remaining) if not self.exact else 0,
            'max_rows':INPUT_MAX_ROWS,'soft_seconds':INPUT_SOFT_SECONDS,
            'elapsed_seconds':round(time.monotonic()-self.started,6),
            'continuation_ready':bool(not self.exact and self.examined and remaining),
            'next_input':remaining[0] if remaining else None,'cursor':None if self.exact else self.name,
            'permission_cached':False,'business_completed':False,'soft_budget_does_not_interrupt_a_row':True}
        setattr(self.store,self.stage+'_scan_progress',value)
        return value


def notification_paths(root, store, only_events=None):
    """Directory/stat and original identity are locators, never admission."""
    paths=sorted(p for p in (root/'logs/result-notifications').glob('*.json') if not p.is_symlink())
    if only_events is None:return paths
    selected=[]
    # Derive possible opaque filenames from stored identity/current binding
    # metadata only. Never expand a source/route merely to locate its file.
    import result_coordination as rc
    import workflow_control as workflow
    for event in only_events:
        row=store.db.execute('SELECT identity_json,target FROM wakeups WHERE event_key=?',(event,)).fetchone()
        if row:
            try:
                value=json.loads(row[0]);fixed=binding(root,row[1])
                candidates=[root/'logs/result-notifications'/(rc._key(value)+'.json')]
                for purpose in rc.DELIVERY_PURPOSES:
                    locator={**value,'target_department':row[1],'target_thread_id':fixed['task_id'],'purpose':purpose}
                    candidates.append(root/'logs/result-notifications'/(rc._delivery_key(locator).split(':',1)[1]+'.json'))
                selected += [path for path in candidates if path in paths and key(json.loads(path.read_text()).get('identity'))==event]
            except (workflow.WorkflowError,DispatchError,ValueError,OSError,KeyError,TypeError,AttributeError):pass
    # Exact lookup may inspect editable metadata; the selected notice still
    # runs all original admitted/source/target/UNKNOWN gates below.
    for path in sorted(paths,key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            if key(json.loads(path.read_text()).get('identity')) in only_events:selected.append(path)
        except (ValueError,OSError,KeyError,TypeError):continue
    return sorted(set(selected))


def input_slice(store, stage, entries, **options):
    try:return InputSlice(store,stage,entries,**options)
    except (DispatchError,ValueError,OSError,KeyError,TypeError,sqlite3.Error) as error:
        setattr(store,stage+'_scan_progress',{'schema':'bounded-current-notification-input-progress/v1',
            'stage':stage,'state':'input_cursor_or_locator_blocked','owner':'system-development',
            'reason':str(error),'continuation_ready':False,'permission_cached':False,'business_completed':False})
        return None



class Dispatcher:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport

    def _reconcile_readonly_row(self, row, valid_events=None):
        import workflow_control as w
        from department_autonomy import ASSISTANTS,current_mode
        chief_row=current_mode(self.store.root) and row.get('target') in ASSISTANTS
        if chief_row and row.get('target')!='operations-assistant':
            return True  # retired rows were reconciled in ingest; no current-role probe
        if chief_row:
            import result_coordination as rc
            from chief_assistant_coordination import notification_boundary
            try:
                # Bound reuse to one frozen row; validators still run and
                # no authorization, effect, or policy crosses rows.
                with w.request_validation_context():
                    record=_activation_record(self.store.root,json.loads(row['identity_json']))
                    boundary=notification_boundary(self.store.root,record)
                if boundary['state']=='committed_original_intake':
                    tracked=self.store.db.execute('SELECT 1 FROM activation_recovery WHERE event_key=?',(row['event_key'],)).fetchone()
                    owned=self.store.checkpoint_value('current-receiver-inflight:'+row['target'])==row['event_key']
                    self.store.set(row['event_key'],'resolved_by_original_intake','original responsible intake already committed')
                    self.store.release_receiver(row,received=True)
                    if tracked or owned or row['state']!='resolved_by_original_intake':
                        activation_probe(self.store,row)
                    return True
                if not boundary['new_dispatch_allowed']:
                    # Never overwrite accepted/uncertain history or label an
                    # old notification as actually received.
                    self.store.activation_state(row,boundary['state'],json.dumps(boundary,sort_keys=True))
                    return True
                if row['target']!='operations-assistant':
                    return True
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError) as exc:
                record_source_block(self.store,row,'source_or_effect_blocked',str(exc))
                return True
        if row['state'] in {'native_queue_accepted', 'resolved_by_original_intake'}:
            if valid_events is not None and row['event_key'] not in valid_events:
                record_source_block(self.store,row,'source_or_effect_blocked','original source is invalid; inspect exact effect before recovery')
                return True
            try:
                activation_probe(self.store, row)
            except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
                self.store.activation_state(row, 'source_or_effect_blocked', str(exc))
            return True
        return False

    def _reconcile_history(self, valid_events=None, only_events=None):
        # Reuse only version-checked historical ledger INPUTS in this read-only
        # pass. Never carry a policy/claim/allow result into actual preparation.
        from readonly_work_view_cache import inventory_session
        handled = set()
        import workflow_control as w
        with w.request_validation_context(), inventory_session(self.store.root):
            for row in self.store.rows():
                if only_events is not None and row['event_key'] not in only_events:
                    continue
                if row['state'] in {'sending','uncertain'}:
                    continue  # Unknown-effect recovery always runs uncached.
                with observed_phase(self.store, 'history', row['event_key']):
                    if self._reconcile_readonly_row(row, valid_events):
                        handled.add(row['event_key'])
        return handled

    def _bounded_history(self, valid_events=None, only_events=None, *, continuation=False):
        """Fair cursor over original history, never a permission/effect cache.

        Only row boundaries observe soft budgets. Missing/inflight keys remain
        deferred; an attempted failed row is not a completed business result.
        """
        import workflow_control as w
        from readonly_work_view_cache import inventory_session
        started=time.monotonic();examined=0;handled=set();errors=[]
        try:
            raw=self.store.checkpoint_value(HISTORY_CHECKPOINT)
            plan=json.loads(raw) if raw else {'schema':HISTORY_CHECKPOINT,'known':[],'pending':[]}
            if (not isinstance(plan,dict) or set(plan)!={'schema','known','pending'} or plan['schema']!=HISTORY_CHECKPOINT
                    or any(not isinstance(plan[k],list) or len(plan[k])!=len(set(plan[k]))
                           or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in plan[k])
                           for k in ('known','pending')) or not set(plan['pending'])<=set(plan['known'])):
                raise DispatchError('intact original bounded-history cursor required; no silent reset')
            rows=self.store.rows();by_key={row['event_key']:row for row in rows}
            if len(by_key)!=len(rows):raise DispatchError('one original historical row per event key required')
            eligible=[row['event_key'] for row in rows if row['state'] in HISTORY_STATES]
            if not plan['pending'] and not continuation and only_events is None:
                plan={'schema':HISTORY_CHECKPOINT,'known':[],'pending':[]}
            known=set(plan['known'])
            for key in eligible:
                if key not in known:
                    plan['known'].append(key);known.add(key);plan['pending'].append(key)
            if only_events is None and not continuation:
                # A real watch/source event requests fresh examination again,
                # behind unfinished keys. A missing old row cannot suppress all
                # other history forever; internal continuations never reopen it.
                plan['pending'] += [key for key in eligible if key not in plan['pending']]
            if only_events is not None and not continuation:
                preferred=[key for key in eligible if key in only_events]
                plan['pending']=preferred+[key for key in plan['pending'] if key not in set(preferred)]
            def checkpoint():
                self.store.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',
                    (HISTORY_CHECKPOINT,json.dumps(plan,sort_keys=True,separators=(',',':'))))
                self.store.db.commit()
            checkpoint()
            selected=set(eligible)  # historical reads only; exact due keys were prioritized above
            with w.request_validation_context(), inventory_session(self.store.root):
                for key in list(plan['pending']):
                    if key not in selected:continue
                    if examined>=HISTORY_MAX_ROWS or examined and time.monotonic()-started>=HISTORY_SOFT_SECONDS:break
                    # Consumers ran first. Re-read current row; no stale accepted
                    # label may reinterpret a now-sending/UNKNOWN original key.
                    fresh={row['event_key']:row for row in self.store.rows()}.get(key)
                    if fresh is None or fresh['state'] not in HISTORY_STATES:continue
                    examined+=1
                    try:
                        with observed_phase(self.store,'history',key):
                            if self._reconcile_readonly_row(fresh,valid_events):handled.add(key)
                    except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError,RuntimeError) as error:
                        errors.append({'event_key':key,'error_type':type(error).__name__})
                        self.store.activation_state(fresh,'history_source_read_blocked',str(error))
                    # Only a finished row attempt moves the cursor. SIGTERM,
                    # process death or failed checkpoint preserves original work.
                    plan['pending'].remove(key);checkpoint()
            current={row['event_key']:row for row in self.store.rows()}
            runnable=[key for key in plan['pending'] if key in current and current[key]['state'] in HISTORY_STATES]
            self.store.history_scan_progress={'schema':'bounded-original-history-progress/v1',
                'examined_rows':examined,'read_blocked_rows':errors,'elapsed_seconds':round(time.monotonic()-started,6),
                'max_rows':HISTORY_MAX_ROWS,'soft_seconds':HISTORY_SOFT_SECONDS,'remaining_rows':len(plan['pending']),
                'deferred_missing_or_inflight_rows':len(plan['pending'])-len(runnable),
                'next_event_key':runnable[0] if runnable else None,'sweep_examination_complete':not plan['pending'],
                'continuation_ready':bool(examined and runnable),'cursor_checkpoint':HISTORY_CHECKPOINT,
                'permission_cached':False,'business_goal_closed':False,'soft_budget_does_not_interrupt_an_inflight_row':True}
        except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
            self.store.history_scan_progress={'schema':'bounded-original-history-progress/v1',
                'state':'history_cursor_or_source_read_blocked','owner':'system-development',
                'reason':str(error),'examined_rows':examined,'continuation_ready':False,
                'sweep_examination_complete':False,'permission_cached':False,'business_goal_closed':False}
        return handled

    def _current_source(self,row,valid_events):
        # A bounded ingest set is not a global invalid set. This selected old
        # row must independently pass the same normal admission before new send.
        if valid_events is not None and row['event_key'] in valid_events:return True
        _,allowed=load_pilot(self.store.root)
        try:valid,errors=ingest(self.store.root,self.store,allowed,only_events={row['event_key']})
        except (DispatchError,ValueError,OSError,KeyError,TypeError,AttributeError,RuntimeError) as error:
            self.store.activation_state(row,'notification_source_DATA_MISSING',str(error));return False
        if row['event_key'] in valid:return True
        view=getattr(self.store,'notification_views',{}).get(row['event_key'])
        self.store.activation_state(row,view['state'] if view else 'notification_source_DATA_MISSING',
            json.dumps(view,sort_keys=True) if view else 'exact original notice not yet authenticated; unvisited inputs are not invalid/completed')
        return False

    def _notification_guard(self,row):
        from receipt_obligation_consumer import notification_queue_admission
        try:
            guard=notification_queue_admission(self.store.root,json.loads(row['identity_json']),row['target'],
                self.transport,actual_active_observation=getattr(self.transport,'notification_runtime_observation',None))
            self.notification_serial_guard=guard
            return guard.get('queue_allowed') is True
        except (DispatchError,ValueError,OSError,KeyError,TypeError,AttributeError,RuntimeError) as error:
            self.notification_serial_guard={'state':'notification_capacity_DATA_MISSING','queue_allowed':False,'reason':str(error)}
            return False

    def _notification_budget_blocked(self):
        # An authenticated already-active queue is not a new-window activation.
        occupied = self.activation_attempted or getattr(self,'publication_serial_pending',None) is not None
        return occupied and getattr(self,'notification_serial_guard',{}).get('requires_reservation') is not False

    def _consume_current(self, only_events=None, *, notification_only=False, guard_only=False):
        import workflow_control as w
        if notification_only:
            self.receipt_obligation_outcomes=[];self.publication_deadline_outcomes=[]
            self.publication_serial_pending=None
            return
        from receipt_obligation_consumer import pump as consume_received_obligations, shared_serial_guard, observe_root_serial
        from direct_handoff_readback import observe as observe_direct_handoff
        with observed_phase(self.store, 'root_observer'):
            self.root_serial_observation = observe_root_serial(self.store.root,self.transport,store=self.store) if self.transport else {
                'state':'DATA_MISSING_existing_readonly_transport','root_release_recorded':False}
        with observed_phase(self.store, 'root_guard'):
            self.root_serial_guard = shared_serial_guard(self.store.root,transport=self.transport)
            self.direct_handoff = observe_direct_handoff(
                self.store.root, self.root_serial_guard.get('assigned_next_original_window'),
                getattr(self.transport, 'history', None))
        # A direct delivery may be executing before it has a formal receipt.
        # Keep consuming existing effects, but let that original window finish
        # before the dispatcher starts a second recovery.
        if ((self.direct_handoff or {}).get('turn_status') == 'inProgress'
                and self.direct_handoff.get('state') in {'direct_input_observed', 'direct_reply_in_progress'}):
            self.activation_attempted = True
        publication = publication_deadline_runtime(self.store.root)
        serial_ready = publication is None or callable(getattr(publication,'serial_pending',None))
        publication_pending = None
        if publication is not None and serial_ready:
            try:
                with observed_phase(self.store, 'publication_serial'):
                    publication_pending = publication.serial_pending(self.store.root)
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
                publication_pending = {'state':'publication_original_slot_readback_blocked',
                    'owner':'system-development','reason':str(error),'new_activation_allowed':False}
        elif publication is not None:
            publication_pending = {'state':'publication_serial_interface_not_adopted',
                'owner':'system-development','new_activation_allowed':False}
        self.publication_serial_pending = publication_pending
        self.activation_attempted = self.activation_attempted or bool(self.store.checkpoint_value('current-receipt-followthrough-inflight'))
        if guard_only:
            # Fresh safety observations precede queue effects. Historical receipt
            # work may be slow; it must not hold a newly committed result behind
            # unrelated old rows. The effect consumers run after this queue pass
            # with the same (never reset) one-new-window activation budget.
            self.receipt_obligation_outcomes=[];self.publication_deadline_outcomes=[]
            return
        from receipt_obligation_consumer import SCAN_CONTINUE
        history_continuation=only_events is not None and (HISTORY_CONTINUE in only_events or INPUT_CONTINUE in only_events)
        receipt_events={SCAN_CONTINUE} if history_continuation else only_events
        with observed_phase(self.store, 'receipt_consumer'):
            self.receipt_obligation_outcomes = consume_received_obligations(
                self.store.root, self.store, self.transport, only_events=receipt_events,
                allow_new=not self.activation_attempted and publication_pending is None and self.root_serial_guard.get('new_activation_allowed') is True)
        self.activation_attempted = self.activation_attempted or any(item.get('message_sent') or item.get('effect_unknown') for item in self.receipt_obligation_outcomes) or bool(self.store.checkpoint_value('current-receipt-followthrough-inflight'))
        available = (self.transport if not self.activation_attempted and serial_ready and self.root_serial_guard.get('new_activation_allowed') is True and not self.store.checkpoint_value('current-receipt-followthrough-inflight')
            and not any(item.get('message_sent') for item in self.receipt_obligation_outcomes) else None)
        with observed_phase(self.store, 'publication_consumer'):
            self.publication_deadline_outcomes = (publication.consume_due(self.store.root, available)
                if publication is not None and serial_ready else [])
        self.publication_serial_pending = publication_pending
        # Consume the cached absolute alarm exactly once. The next wait computes
        # a fresh future deadline; an already-overdue source never spins at 0s.
        self.store.publication_wait_deadline = None
        self.activation_attempted = self.activation_attempted or any(item.get('message_sent') or item.get('effect_unknown') for item in self.publication_deadline_outcomes)

    def pump(self, valid_events=None, only_events=None, *, notification_only=False):
        import workflow_control as w
        from readonly_work_view_cache import inventory_active
        if inventory_active(self.store.root):
            raise DispatchError('transport pump requires an uncached caller context')
        # New/unknown work retains fresh normal gates but no longer waits behind
        # the full already-accepted/received history. History still runs below.
        self.activation_attempted=False
        source_continuation=only_events is not None and INPUT_CONTINUE in only_events
        history_continuation=only_events is not None and HISTORY_CONTINUE in only_events
        self._consume_current(only_events,notification_only=notification_only,guard_only=True)
        selected = [row for row in self.store.rows()
                    if only_events is None or source_continuation or row['event_key'] in only_events]
        historical = {row['event_key'] for row in selected
                      if row['state'] in {'native_queue_accepted','resolved_by_original_intake','wake_acknowledged'}}
        work = {row['event_key'] for row in selected} - historical
        entries=[(row['event_key'],hashlib.sha256(row['identity_json'].encode()).hexdigest()) for row in selected if row['event_key'] in work]
        priority=[row['event_key'] for row in selected if row['state'] in {'sending','uncertain'}]
        priority += [row['event_key'] for row in selected if valid_events is not None and row['event_key'] in valid_events]
        cursor=input_slice(self.store,'pending',entries,priority=priority,
            continuation=source_continuation or history_continuation,
            exact=only_events is not None and not source_continuation and not history_continuation)
        sent_receivers=set()
        for event in (cursor.selected if cursor else []):
            row=next((r for r in self.store.rows() if r['event_key']==event and r['state'] not in HISTORY_STATES),None)
            if row is None:continue
            with cursor.attempt(event):
                # Pending/unknown work rechecks the original source outside any
                # historical inventory session before normal policy/effect paths.
                if self._reconcile_readonly_row(row, valid_events):
                    continue
                from department_autonomy import ASSISTANTS,current_mode
                chief_row=current_mode(self.store.root) and row.get('target') in ASSISTANTS
                if row['state'] == 'wake_acknowledged':
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
                    if not self._notification_guard(row) or self._notification_budget_blocked():
                        self.store.activation_state(row,'waiting_original_serial_boundary',json.dumps(getattr(self,'notification_serial_guard',{}),sort_keys=True)+'; an ACK alone does not release the previous window')
                        continue
                    if not self._current_source(row,valid_events):continue
                    value = json.loads(row['identity_json'])
                    if chief_row and (row['target'] in sent_receivers or not self.store.reserve_receiver(row)):
                        self.store.activation_state(row,'waiting_receiver_safe_boundary','another exact original result owns the current receiver slot; no batch activation')
                        continue
                    try:
                        with observed_phase(self.store,'prepare',row['event_key']):
                            prepared = self.transport.prepare(row['target'], row['event_key'], value)
                    except Exception as exc:
                        self.store.set(row['event_key'], 'waiting_policy_or_source', str(exc))
                        if chief_row:self.store.release_receiver(row,pre_send_failure=True)
                        continue
                    if not self._notification_guard(row) or self._notification_budget_blocked():
                        self.store.set(row['event_key'],'waiting_policy_or_source','fresh original serial boundary or activation budget changed before enqueue; no effect started')
                        if chief_row:self.store.release_receiver(row,pre_send_failure=True)
                        continue
                    try:
                        from receipt_obligation_consumer import reserve_notification_serial
                        capacity=reserve_notification_serial(self.store.root,value,prepared,self.transport,
                            actual_active_observation=getattr(self.transport,'notification_runtime_observation',None),
                            allow_new_capacity=not self.activation_attempted)
                        if not isinstance(capacity,dict) or capacity.get('queue_allowed') is not True:
                            raise DispatchError('normal notification capacity did not authorize this exact queue commit')
                    except Exception as exc:
                        self.store.set(row['event_key'],'waiting_policy_or_source','normal notification capacity reservation: '+str(exc))
                        if chief_row:self.store.release_receiver(row,pre_send_failure=True)
                        continue
                    self.store.set(row['event_key'], 'sending')
                    try:
                        self.activation_attempted=self.activation_attempted or capacity.get('requires_reservation') is not False
                        receipt = self.transport.enqueue(prepared)
                    except Exception as exc:
                        self.store.set(row['event_key'], 'uncertain', str(exc))
                    else:
                        self.store.set(row['event_key'], 'native_queue_accepted',
                                       'official queue acknowledged; recipient intake not claimed',
                                       native_message_id=receipt['message_id'])
                    if chief_row:sent_receivers.add(row['target'])
                    continue
                if row['state'] in {'sending', 'uncertain'}:
                    turn = self.transport.recover(row['target'], row['event_key'], json.loads(row['identity_json']))
                    self.store.set(row['event_key'], 'wake_acknowledged' if turn else 'uncertain',
                                   'recovered exact native effect' if turn else 'read exact native effect; no blind resend', turn)
                    continue
                if not self._notification_guard(row) or self._notification_budget_blocked():
                    self.store.activation_state(row,'waiting_original_serial_boundary',json.dumps(getattr(self,'notification_serial_guard',{}),sort_keys=True))
                    continue
                if not self._current_source(row,valid_events):continue
                self.store.activation_state(row,'shared_wake_capacity_adapter_DATA_MISSING',
                    'legacy shared toolOutput new wake has no normal result-notification capacity carrier; original effect recovery remains available')
                continue

        # No permission cache reaches the effect tail. Preserve every selected
        # historical proof check after pending/unknown work; normal failures do
        # not authorize a replay and SIGTERM is never delayed by a finally scan.
        # Outside the read-only inventory context: actual next-obligation effects
        # use their own normal preparation/policy and durable original intent.
        # Original result consumers always run before old accepted history.
        if cursor:cursor.progress()
        from receipt_obligation_consumer import SCAN_CONTINUE
        if not notification_only:
            self._consume_current(only_events)
            self._bounded_history(None,only_events,continuation=(source_continuation or history_continuation or
                only_events is not None and SCAN_CONTINUE in only_events))


def _scan_continuation_events(store):
    from receipt_obligation_consumer import SCAN_CONTINUE
    if any(getattr(store,name+'_scan_progress',{}).get('continuation_ready') is True for name in ('registration','ingest','pending')):
        return {INPUT_CONTINUE}
    if getattr(store,'receipt_scan_progress',{}).get('continuation_ready') is True:return {SCAN_CONTINUE}
    if getattr(store,'history_scan_progress',{}).get('continuation_ready') is True:return {HISTORY_CONTINUE}
    return None


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


def resume_registered_results(root, store, transport, *, only_events=None, continuation=False):
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
    pending=[];locator_errors=[]
    for event in events:
        item=event.get('details',{}).get('original_result_registration_pending')
        if not item:continue
        try:
            if not isinstance(event.get('event_id'),str) or not event['event_id'] or not isinstance(item,dict):
                raise DispatchError('original registration event/identity locator DATA_MISSING')
            hint=key(item.get('identity'))
        except (DispatchError,ValueError,TypeError,KeyError) as error:
            locator_errors.append({'event_id':event.get('event_id'),'state':'registration_locator_DATA_MISSING',
                'reason':str(error),'next_owner':'system-development','blocks_other_pending_results':False})
            continue
        if only_events is None or hint in only_events:pending.append(event)
    entries=[(e['event_id'],w.sha256_value(e)) for e in pending]
    cursor=input_slice(store,'registration',entries,priority=[e['event_id'] for e in reversed(pending)],
                      continuation=continuation,exact=only_events is not None)
    outcomes = locator_errors
    if cursor is None:return [*outcomes,{'state':'source_registration_cursor_blocked','next_owner':'system-development'}]
    for event in pending:
        if event['event_id'] not in cursor.selected:continue
        with cursor.attempt(event['event_id']):
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
    cursor.progress()
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
    """One request-local read context; never cache transport state across rows."""
    import workflow_control as w
    with w.request_validation_context():
        return _activation_record_uncached(root, value)


def _activation_record_uncached(root, value):
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
    intake_actor, intake_owner = rc._committed_intake_actor(root, intake)
    def committed(row):
        if row.get('outbox') != intake.get('outbox') or row.get('target_department',target) != target:
            raise DispatchError('original frozen responsible receiver/outbox differs')
        rc._committed_result(root, row)
        actor, owner = rc._committed_intake_actor(root, row)
        if (actor != intake_actor or owner != intake_owner
                or row.get('coordinator_role',row.get('responsible_assistant',target)) != actor
                or row.get('coordinator_owner',owner) != owner):
            raise DispatchError('actual original committed actor/owner differs')
        if actor != target:
            from chief_assistant_coordination import receiver_context
            receiver_context(root,row,target)  # authenticate real delegation; never relabel HQ as A1
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
        # Reuse only version-checked inputs within this one original event.
        # Each effect, recipient, source and recovery guard still runs.
        with w.request_validation_context():
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


def publication_deadline_runtime(root):
    if not (Path(root)/'tools/publication_deadline_runtime.py').is_file():
        return None  # adoption is explicit; no new background runtime is created
    import publication_deadline_runtime as runtime
    return runtime


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
    receipt_deadline = getattr(store,'receipt_wait_deadline',None)
    if receipt_deadline is not None:
        if receipt_deadline <= at:due.add('receipt-obligation-due')
        else:pending.append((receipt_deadline-at).total_seconds())
    publication = publication_deadline_runtime(store.root)
    if publication:
        cached = getattr(store,'publication_wait_deadline',None)
        if cached is not None and cached <= at:
            due.add('publication-deadline-due')
        else:
            value = publication.next_deadline(store.root,at)
            stamp = dt.datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
            if stamp is not None:
                if stamp.tzinfo is None:
                    raise DispatchError('publication deadline must retain UTC timezone')
                store.publication_wait_deadline = stamp
                if stamp <= at:due.add('publication-deadline-due')
                else:pending.append((stamp-at).total_seconds())
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


def _scheduled_queue_context(root, value, record, row):
    """Authenticate an existing admitted daily result, never manufacture a goal."""
    import workflow_control as w
    import result_coordination as rc
    import department_autonomy as a
    from chief_assistant_coordination import notification_boundary
    daily = a.scheduled_delivery_source(root, value)
    if daily is None:
        return None
    # Preserve the original SYS v2 successor's receipt-chain safety check.
    # A legitimately empty daily chain needs no fabricated goal or receipt;
    # a damaged existing chain cannot authorize even metadata continuation.
    _receipts, receipt_errors = w._validate_receipt_chain(root, value['task_id'])
    if receipt_errors:
        raise DispatchError('original daily receipt chain is invalid; no metadata continuation')
    queued = rc._validate_queued(root, value)
    if (queued.get('source_mode') != 'scheduled_run'
            or queued.get('source_automation_id') != daily.get('automation_id')
            or queued.get('mode_authorization') != a.OWNER):
        raise DispatchError('original declared daily queue/automation authority required')
    # Reuse normal source admission: exact native READY, outbox, automation and
    # declared report scope. No invented business snapshot or completion proof.
    native = a.native_result(root, queued, binding(root, value['sender_department'])['task_id'])
    if w.file_digest(root, queued.get('outbox', {}).get('path', '')) != queued.get('outbox'):
        raise DispatchError('exact original daily outbox bytes required')
    box = w.read_json(inside(root, queued['outbox']['path']))
    if (queued['outbox']['sha256'] != value['result_sha256']
            or any(box.get(k) != value[v] for k, v in
                   {'task_id':'task_id','department':'sender_department','candidate_version':'candidate_version'}.items())):
        raise DispatchError('original daily result identity must remain exact')
    route = rc.frozen_notification_route(root, record)
    exact = rc.delivery_identity(root, value, route=route)
    if (route.get('lane') != 'HQ_knowledge'
            or route.get('target_department') not in {'operations', 'operations-assistant'}
            or record.get('delivery_identity') != exact
            or row.get('target') != exact['target_department']
            or exact['target_thread_id'] != binding(root, row['target'])['task_id']
            or row.get('state') != 'native_queue_accepted'
            or row.get('native_message_id') != record['native_queue_transport'].get('native_message_id')):
        raise DispatchError('same accepted original daily message and frozen recipient required')
    boundary = notification_boundary(root, record)
    if not boundary.get('new_dispatch_allowed'):
        raise DispatchError('daily result is historical, superseded or source-blocked: ' + str(boundary.get('state')))
    sender = 'operations' if row['target'] != 'operations' else value['sender_department']
    a.authority(root)  # Existing real owner delegation, not a caller flag.
    if sender == 'operations' and row['target'] == 'operations-assistant':
        from chief_assistant_coordination import actor_allowed
        if not actor_allowed(root, value, row['target'], sender):
            raise DispatchError('current original coordinator delegation required for daily queue resume')
    for role in (sender, row['target']):
        role_row = w.department_registry(root).get(role, {})
        fixed = role_row.get('chat_binding', {})
        if (role_row.get('new_dispatch_enabled') is not True
                or fixed.get('project_id') != a.PROJECT
                or Path(fixed.get('cwd', '')).resolve() != Path(root).resolve()
                or not w._chat_binding_healthy(fixed, verification_ttl_hours=26)):
            raise DispatchError('current exact daily recovery sender/receiver identity and health required')
    return {'source_mode': 'scheduled_run', 'source_automation_id': daily['automation_id'],
            'sender_department': sender, 'frozen_recipient': row['target'],
            'scope': 'department_result:' + value['task_id'] + ':' + value['sender_department'],
            'original_outbox': queued['outbox'], 'identity': identity(value),
            'original_message_id': row['native_message_id'], 'delivery_identity': exact,
            'source_fingerprint': w.sha256_value([daily, queued, native, a.OWNER]),
            'external_permission_issued': False}


def _scheduled_desktop(root, observation_pin, sender, target_role):
    """Normal fresh actual desktop + scoped sidebar evidence, no health writes."""
    import workflow_control as w
    from goal_delivery_runtime import _collaboration_native
    from goal_source_recovery import _native_container_valid
    if not isinstance(observation_pin, dict) or w.file_digest(root, observation_pin.get('path', '')) != observation_pin:
        raise DispatchError('exact daily activation desktop observation pin required')
    observed = w.read_json(inside(root, observation_pin['path']))
    at = w._parse_observed_at(observed.get('observed_at'))
    if at is None or not 0 <= (dt.datetime.now(dt.timezone.utc) - at).total_seconds() <= 300:
        raise DispatchError('fresh actual daily recovery desktop observation required')
    native_pin = observed.get('actual_native_target_turn')
    page = _collaboration_native(root, native_pin)
    target = binding(root, target_role)
    SharedTransport._identity({**page.get('thread', {}), 'name': page.get('thread', {}).get('title')}, target)
    if (page.get('source_transport') == 'official_app_server_readonly_history'
            or not _native_container_valid(page)
            or page.get('thread', {}).get('archived') is True
            or page.get('thread', {}).get('projectId') not in {None, target['project_id']}
            or page.get('page', {}).get('order') != 'newest_first'
            or not page.get('turns')):
        raise DispatchError('actual current non-archived daily receiver desktop read required')
    turn = page['turns'][0]
    if turn.get('status') in {'inProgress', 'pending'}:
        return {'state': 'waiting_receiver_completion', 'message_sent': False}
    if turn.get('status') not in {'completed', 'interrupted', 'failed'}:
        raise DispatchError('actual ended receiver turn required; notLoaded alone is insufficient')
    inventory_pin = observed.get('actual_live_inventory')
    if not isinstance(inventory_pin, dict) or w.file_digest(root, inventory_pin.get('path', '')) != inventory_pin:
        raise DispatchError('fresh actual scoped sender/receiver inventory required')
    live_at = w._parse_observed_at(observed.get('live_observed_at'))
    if live_at is None or not 0 <= (dt.datetime.now(dt.timezone.utc) - live_at).total_seconds() <= 300:
        raise DispatchError('fresh actual fixed daily recovery memberships required')
    inventory = _collaboration_native(root, inventory_pin)
    for role in dict.fromkeys((sender, target_role)):
        fixed = binding(root, role)
        rows = [p for p in inventory.get('threads', []) + inventory.get('pinnedThreads', [])
                if p.get('id') == fixed['task_id']]
        memberships = [p['sectionId'] for p in inventory.get('sections', [])
                       if 'codex:thread:' + fixed['host_id'] + ':' + fixed['task_id'] in p.get('itemKeys', [])]
        if (len(rows) != 1 or rows[0].get('archived') is True
                or memberships != [fixed['sidebar_section_id']]
                or any(rows[0].get(k) != fixed[v] for k, v in
                       {'id':'task_id', 'title':'title', 'cwd':'cwd', 'projectId':'project_id', 'hostId':'host_id'}.items())):
            raise DispatchError('actual exact daily recovery sender/receiver identity or sidebar differs')
    return {'state': 'actual_ended_receiver_verified', 'actual_target_state': native_pin,
            'observation': observation_pin, 'inventory': inventory_pin,
            'observed_at': observed['observed_at']}


def _daily_resume_body(value, source):
    return ('task_id=' + value['task_id'] + '\nscope=' + source['scope']
            + '\n仅激活已接受原消息=' + source['original_message_id']
            + '\n原结果身份=' + json.dumps(identity(value), ensure_ascii=False, sort_keys=True)
            + '\n原成果路径=' + source['original_outbox']['path']
            + '\n从原队列读取原包，不复制或重发结果；保留当前及暂停工作。'
              '已实收不重收；本次恢复仅限原报告接收、登记和读回。'
              '读回后仅报告接收事实及准确待办，不执行或触发业务下一动作。'
              '禁止实际执行或触发真实 EN2、生产执行/Save/发布、HQ 索引合并、'
              '新增或扩展业务/收件部门、付款及凭据/安全权限变更。'
              '原发送、实收或外部执行效果未知时仅对账，禁止重放、重发、清槽或绕过现有门禁。'
              '本消息不创建业务任务、许可、账号、费用或生产权限；'
              '其他任务不能据本恢复指令接续执行。\n')


def _daily_serial_boundary(row, slot):
    # A current assistant queue already owns its exact serial slot. Missing
    # ownership is not proof that an accepted/unknown message may be replaced.
    if row['target'] == 'operations-assistant':
        return slot == row['event_key']
    return slot in {None, row['event_key']}


def _plan_scheduled_activation(root, store, row, value, record, proof_pin, source):
    import workflow_control as w
    slot = store.checkpoint_value('current-receiver-inflight:' + row['target'])
    if not _daily_serial_boundary(row, slot):
        return {'state': 'waiting_receiver_safe_boundary', 'message_sent': False}
    desktop = _scheduled_desktop(root, proof_pin, source['sender_department'], row['target'])
    if desktop['state'] != 'actual_ended_receiver_verified':
        return desktop
    directory = root / STATE / 'prepared' / row['event_key'] / 'activation'
    directory.mkdir(parents=True, exist_ok=True)
    body = _daily_resume_body(value, source)
    path = directory / 'declared-daily-exact-resume.txt'
    if path.exists() and path.read_text() != body:
        raise DispatchError('original daily recovery payload is immutable')
    if not path.exists():
        path.write_text(body)
    payload = w.file_digest(root, str(path.relative_to(root)))
    sender, target = binding(root, source['sender_department']), binding(root, row['target'])
    request = {'task_id': value['task_id'], 'sender_department': source['sender_department'],
               'scope': source['scope'], 'action_id': 'resume-original-queue:' + source['original_message_id'],
               'action_class': 'thread_message', 'source_project_id': sender['project_id'],
               'target_project_id': target['project_id'], 'target_department': row['target'],
               'target_thread_id': target['task_id'], 'target_thread_title': target['title'],
               'target_cwd': target['cwd'], 'target_sidebar_section_id': target['sidebar_section_id'],
               'payload': payload, 'payload_sha256': payload['sha256'],
               'actual_target_state': desktop['actual_target_state'], 'delivery_mode': 'mcp_direct_send',
               'scheduled_queue_resume': {'event_key': row['event_key'], 'original_message_id': source['original_message_id']},
               'scheduled_activation_observation': proof_pin, 'authorization_changes': []}
    plan = {'event_key': row['event_key'], 'original_message_id': source['original_message_id'],
            'owner': 'operations', 'mode': 'declared_daily_accepted_queue_resume',
            'state': 'reserved_not_sent', 'request': request, 'original_daily_source': source,
            'desktop_observation': proof_pin, 'headless_activation_capability': 'DATA_MISSING',
            'before_actual_send': 'Actual sender refreshes desktop and runs normal prepare/policy once. Unknown effects never replay.',
            'send_api': 'actual request sender uses codex_app.send_message_to_thread only after normal ready_to_send'}
    # Re-read real source and occupancy immediately before the one durable intent.
    latest_record, intake = _accepted_queue(root, value)
    if intake or _scheduled_queue_context(root, value, latest_record, row) != source:
        return {'state': 'source_changed_before_intent', 'message_sent': False}
    if not _daily_serial_boundary(row, store.checkpoint_value('current-receiver-inflight:' + row['target'])):
        return {'state': 'waiting_receiver_safe_boundary', 'message_sent': False}
    return store.reserve_activation(row, plan)


def _activation_snapshot(root, event):
    """Read the original durable intent without constructing a writable Store."""
    path = Path(root) / STATE / 'transport.sqlite3'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise DispatchError('bounded existing activation SQL required')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-journal')):
        raise DispatchError('activation SQL is changing; read back, never guess')
    before = path.stat(); raw = path.read_bytes(); after = path.stat()
    if ((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-journal'))):
        raise DispatchError('activation SQL changed during read')
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(raw); db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM wakeups WHERE event_key=?', (event,)).fetchone()
        intent = db.execute('SELECT * FROM activation_recovery WHERE event_key=?', (event,)).fetchone()
        if row is None or intent is None or not intent['intent_json']:
            raise DispatchError('one existing original daily activation intent required')
        row, intent = dict(row), dict(intent)
        slot = db.execute('SELECT value FROM checkpoints WHERE name=?',
                          ('current-receiver-inflight:' + row['target'],)).fetchone()
        return row, intent, slot[0] if slot else None
    except sqlite3.Error as exc:
        raise DispatchError('original activation SQL snapshot invalid; no recovery permission') from exc
    finally:
        db.close()


def validate_scheduled_activation(root, request):
    """Exact normal daily-resume source preflight, not an allow-result cache."""
    import workflow_control as w
    from readonly_work_view_cache import inventory_active
    if inventory_active(root):
        raise DispatchError('daily activation requires an uncached normal caller')
    keys = {'task_id','sender_department','scope','action_id','action_class','source_project_id',
            'target_project_id','target_department','target_thread_id','target_thread_title','target_cwd',
            'target_sidebar_section_id','payload','payload_sha256','actual_target_state','delivery_mode',
            'scheduled_queue_resume','scheduled_activation_observation','authorization_changes'}
    if not isinstance(request, dict) or set(request) != keys or request['authorization_changes'] != []:
        raise DispatchError('exact transport-only daily recovery request fields required')
    marker = request.get('scheduled_queue_resume')
    if (not isinstance(marker, dict) or set(marker) != {'event_key','original_message_id'}
            or not re.fullmatch('[0-9a-f]{64}', str(marker['event_key']))):
        raise DispatchError('one original daily event/message marker required')
    row, intent, slot = _activation_snapshot(root, marker['event_key'])
    plan = json.loads(intent['intent_json'])
    if (row['state'] != 'native_queue_accepted'
            or any(word in str(intent['status']).lower() for word in ('unknown', 'uncertain'))
            or plan.get('owner') != 'operations' or plan.get('mode') != 'declared_daily_accepted_queue_resume'
            or plan.get('state') != 'reserved_not_sent'
            or intent.get('owner') != 'operations'
            or intent.get('native_message_id') != marker['original_message_id']
            or row.get('native_message_id') != marker['original_message_id']
            or plan.get('original_message_id') != marker['original_message_id']
            or not _daily_serial_boundary(row, slot)):
        raise DispatchError('accepted original message, known intent and serial boundary required')
    value = identity(json.loads(row['identity_json']))
    record, intake = _accepted_queue(root, value)
    if intake:
        raise DispatchError('original daily report already received; no late recovery')
    source = _scheduled_queue_context(root, value, record, row)
    if source is None or source != plan.get('original_daily_source'):
        raise DispatchError('unchanged original admitted daily source required')
    original = plan.get('request', {})
    observation_fields = {'scheduled_activation_observation','actual_target_state'}
    if set(original) != keys or any(request[k] != original[k] for k in keys - observation_fields):
        raise DispatchError('original daily task/action/recipient/payload identity is immutable')
    if (request['delivery_mode'] != 'mcp_direct_send' or request['action_class'] != 'thread_message'
            or request['task_id'] != value['task_id'] or request['scope'] != source['scope']
            or request['sender_department'] != source['sender_department']
            or request['action_id'] != 'resume-original-queue:' + source['original_message_id']
            or w.file_digest(root, request['payload'].get('path', '')) != request['payload']
            or request['payload_sha256'] != request['payload']['sha256']
            or inside(root, request['payload']['path']).read_text() != _daily_resume_body(value, source)):
        raise DispatchError('same original report activation payload and ordinary mode required')
    sender, target = binding(root, source['sender_department']), binding(root, row['target'])
    expected = {'source_project_id':sender['project_id'], 'target_project_id':target['project_id'],
                'target_department':row['target'], 'target_thread_id':target['task_id'],
                'target_thread_title':target['title'], 'target_cwd':target['cwd'],
                'target_sidebar_section_id':target['sidebar_section_id']}
    if any(request[k] != v for k, v in expected.items()):
        raise DispatchError('current exact daily recovery recipient required')
    desktop = _scheduled_desktop(root, request['scheduled_activation_observation'], source['sender_department'], row['target'])
    if desktop['state'] != 'actual_ended_receiver_verified':
        raise DispatchError('receiver is active; preserve the original queue and intent')
    if desktop['actual_target_state'] != request['actual_target_state']:
        raise DispatchError('exact fresh native receiver proof required')
    return {'schema':'declared-daily-original-queue-resume-precheck/v1',
            'status':'within_original_authorization', 'original_daily_source':source,
            'event_key':row['event_key'], 'original_message_id':source['original_message_id'],
            'desktop_observation':request['scheduled_activation_observation'],
            'writes_performed':False, 'external_permission_issued':False, 'actual_action_allowed':False}


def scheduled_activation_policy(root, request):
    """Normal policy log: one exact metadata-only recovery, never an execution permit."""
    import workflow_control as w
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    fields = ('task_id','action_id','action_class','scope','source_project_id','target_project_id',
              'target_department','target_thread_id','target_thread_title','target_cwd',
              'target_sidebar_section_id','payload_sha256')
    with w.workflow_lock(root):
        source = validate_scheduled_activation(root, request)
        previous = [p for p in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if p.get('task_id') == request['task_id'] and p.get('action_id') == request['action_id']]
        if previous:
            return {'status':'blocked', 'reason':['existing_single_recovery_policy_effect_readback_required'],
                    'original_message_id':source['original_message_id'], 'message_sent':False,
                    'external_permission_issued':False}
        value = {k:request[k] for k in fields}
        value.update(department=request['sender_department'], status='allow',
                     approval_basis='declared_daily_original_queue_resume_v1', checked_at=w.utc_timestamp(),
                     approval_id='', consume_approval=False, routing_status='routing_allowed',
                     delivery_mode='mcp_direct_send', original_daily_activation=source,
                     reason=['exact_admitted_daily_queue_and_single_intent'],
                     external_permission_issued=False)
        value['decision_id'] = 'pol-' + w.sha256_value(value)[:20]
        if validate_scheduled_activation(root, request) != source:
            raise DispatchError('daily recovery source changed before policy append')
        w.append_jsonl_locked(root / w.POLICY_DECISIONS, value)
        return value


def prepare_scheduled_activation(root, request):
    import workflow_control as w
    checked = validate_scheduled_activation(root, request)
    fields = ('task_id','action_id','action_class','scope','source_project_id','target_project_id',
              'target_department','target_thread_id','target_thread_title','target_cwd',
              'target_sidebar_section_id','payload_sha256')
    policy, _ = w.policy_check(root, department=request['sender_department'],
                               **{k:request[k] for k in fields},
                               delivery_mode='mcp_direct_send', original_message=request)
    return {'status':'ready_to_send' if policy['status'] == 'allow' else 'blocked',
            'authorization_precheck':checked, 'policy_decision':policy,
            'payload':request['payload'], 'message_sent':False,
            'external_permission_issued':False, 'original_queue_replay_allowed':False}


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
    daily_source = _scheduled_queue_context(root, value, record, row)
    if daily_source is not None:
        return _plan_scheduled_activation(root, store, row, value, record, proof_pin, daily_source)
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


def remember_verified_intake(store, event, intake):
    """Project only the actual receipt already authenticated by received_notification.

    Receiver occupancy must not wait behind a full historical pump. This does
    not infer a next action, business completion, or a fresh permission.
    """
    import workflow_control as w
    if not isinstance(intake,dict) or not isinstance(intake.get('record_id'),str) or not intake['record_id']:
        raise w.WorkflowError('authenticated nonempty intake record required for receipt projection')
    current=store.db.execute('SELECT * FROM wakeups WHERE event_key=?',(event,)).fetchone()
    if current is None:
        raise w.WorkflowError('existing exact transport row required for receipt projection')
    row=dict(current)
    store.set(event,'resolved_by_original_intake','original responsible intake already committed')
    store.release_receiver(row,received=True)
    previous=store.db.execute('SELECT status,intent_json FROM activation_recovery WHERE event_key=?',(event,)).fetchone()
    if previous is None or not previous['status'].startswith('received_'):
        detail={'intake_record_id':intake['record_id'],'transport_resolved_by_actual_intake':True,
                'next_action_source_checked':False,'handoff_closed':False,'business_goal_closed':False,
                'original_queue_replay_allowed':False,'activation_intent_preserved':bool(previous and previous['intent_json'])}
        store.activation_state(row,'received_next_action_check_pending',json.dumps(detail,sort_keys=True))


def ingest(root, store, allowed, *, only_events=None, continuation=False):
    import workflow_control as workflow
    from readonly_work_view_cache import inventory_session
    store.notification_views = {}
    paths=notification_paths(root,store,only_events)
    entries=[];by_name={};stamps={};versions={}
    for path in paths:
        try:
            st=path.stat();name=str(path.relative_to(root))
            if only_events is not None:
                event=key(json.loads(path.read_text()).get('identity'))
                if event not in only_events:continue
                name=event
            version=workflow.sha256_value([str(path.relative_to(root)),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns])
        except (ValueError,OSError,KeyError,TypeError):continue
        by_name.setdefault(name,[]).append(path);versions.setdefault(name,[]).append(version)
        stamps[name]=max(stamps.get(name,0),st.st_mtime_ns)
    entries=[(name,workflow.sha256_value(version)) for name,version in versions.items()]
    cursor=input_slice(store,'ingest',entries,priority=sorted(stamps,key=stamps.get,reverse=True),
                      continuation=continuation,exact=only_events is not None)
    valid,errors=set(),[]
    if cursor is None:return valid,[{'state':'notification_input_cursor_blocked','next_owner':'system-development','blocks_other_events':False}]
    for name in cursor.selected:
        with cursor.attempt(name):
            with workflow.request_validation_context(),inventory_session(root):
                selected,blocked=_ingest_view(root,store,allowed,paths=by_name[name],only_events=only_events)
                valid.update(selected);errors.extend(blocked)
    cursor.progress()
    return valid,errors


def _ingest_view(root, store, allowed, *, paths=None, only_events=None):
    import workflow_control as workflow
    valid, errors = set(), []
    for path in (paths if paths is not None else sorted((root / 'logs/result-notifications').glob('*.json'))):
        if path.is_symlink():
            continue
        try:
            record = json.loads(path.read_text())
        except (ValueError, OSError):
            continue  # unrelated corrupt records cannot disable enrolled work
        value = record.get('identity')
        if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k] for k in IDENTITY):
            continue
        if only_events is not None and key(value) not in only_events:continue
        try:
            import result_coordination as rc
            intake = rc.received_notification(root,record)
            if intake is not None:
                forget_work_view(store,value)
                target = rc.frozen_notification_route(root,record)['target_department']
                event = store.put(value,target)
                remember_verified_intake(store,event,intake)
                valid.add(event)
                continue
            from chief_assistant_coordination import notification_boundary
            boundary=notification_boundary(root,record)
            if not boundary['new_dispatch_allowed']:
                # Read-only work projection; never alter the original notice/lease.
                if key(value) not in valid:
                    remember_work_view(store,value,notification_work_view(root,record,boundary=boundary))
                continue
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
            if key(value) not in valid:
                remember_work_view(store,value,notification_work_view(root,record,source_rejected=True))
            errors.append({'event_key': key(value), 'file': str(path.relative_to(root)),
                           'reason': str(exc), 'blocks_other_events': False})
            continue
        forget_work_view(store,value)
        event = store.put(value, target)
        if received:
            store.set(event, 'resolved_by_original_intake', 'original responsible intake already committed')
        elif record.get('native_queue_transport', {}).get('state') == 'accepted':
            try:
                _accepted_queue(root, value)
            except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
                remember_work_view(store,value,notification_work_view(root,record,source_rejected=True))
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


def root_serial_watch_paths(root):
    """Observe the existing serial release and its atomic-replacement parent.

    These are ordinary file events in the owned watcher, never permissions or
    a new timer. The next normal scan still rechecks every admission gate.
    """
    from receipt_obligation_consumer import ROOT_SERIAL_PATH
    path = inside(Path(root), ROOT_SERIAL_PATH)
    return [path.parent, path]


class VnodeEvents:
    """macOS kqueue: block on file/native events, never a timed chat poll."""
    def __init__(self, paths, root=None):
        self.root = Path(root or ROOT)
        self.native = {}
        self.readable_fds = set()
        self.last_event_categories = []
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
        self.readable_fds.add(fd)
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
        categories={'rpc_signal' if row.ident in getattr(self,'readable_fds',set()) else 'file_change'
                    for row in rows if row.ident not in native_fds}
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
                        categories.add('native_completion')
                except (DispatchError,ValueError,OSError,KeyError):
                    pass
        self.last_event_categories=sorted(categories)
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
    parser.add_argument('--event', help='exact original notification event for queue-once, or HQ activation recovery')
    args = parser.parse_args()
    if args.event and args.command not in {'queue-once','activation-plan'}:
        raise DispatchError('--event is supported only by exact queue-once or activation-plan')
    if args.command=='queue-once' and args.event and not re.fullmatch('[0-9a-f]{64}',args.event):
        raise DispatchError('one existing original 64-hex notification event required')
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
                                   ROOT / CONFIG, ROOT / 'data/department-registry.json', ROOT / 'tools',
                                   *root_serial_watch_paths(ROOT)],root=ROOT) \
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
                    if args.desktop_proof:
                        import workflow_control as workflow
                        # Optional actual first-party input, never a caller active flag.
                        # Missing/stale/contradictory proof follows normal capacity.
                        transport.notification_runtime_observation=workflow.file_digest(ROOT,args.desktop_proof)
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
                store.observations=ScanObservations(ROOT,rpc,loaded_sources=code_sources) if args.command=='serve-queue' else None
                trigger_categories=['startup']
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
                    if store.observations:store.observations.begin(trigger_categories)
                    exact_events={args.event} if args.command=='queue-once' and args.event else None
                    source_tick=deadline_only is None or INPUT_CONTINUE in deadline_only
                    continuation=deadline_only is not None
                    registration_outcomes=[];valid=set();errors=[]
                    if source_tick:
                        if exact_events is not None:
                            with observed_phase(store,'registration'):
                                registration_outcomes=resume_registered_results(ROOT,store,transport,only_events=exact_events) if transport else []
                        with observed_phase(store,'ingest'):
                            valid, errors = ingest(ROOT, store, allowed,only_events=exact_events,continuation=continuation)
                    with observed_phase(store,'pump'):
                        dispatcher = Dispatcher(store, transport)
                        dispatcher.pump(valid_events=valid, only_events=exact_events or deadline_only,
                                        notification_only=exact_events is not None)
                    # Current exact notifications get a normal bounded consume
                    # opportunity before any old READY registration expansion.
                    if source_tick and exact_events is None:
                        with observed_phase(store,'registration'):
                            registration_outcomes=resume_registered_results(ROOT,store,transport,continuation=continuation) if transport else []
                    summary = {'enrolled_results_found': len(valid), 'isolated_source_errors': errors,
                               'receipt_next_obligations':getattr(dispatcher,'receipt_obligation_outcomes',[]),
                               'receipt_bounded_scan':getattr(store,'receipt_scan_progress',{}),
                               'source_input_slices':{name:getattr(store,name+'_scan_progress',{}) for name in ('registration','ingest','pending')},
                               'source_scope':'only this bounded slice; unvisited is not invalid/completed',
                               'history_bounded_scan':getattr(store,'history_scan_progress',{}),
                               'publication_deadline_obligations':getattr(dispatcher,'publication_deadline_outcomes',[]),
                               'publication_serial_pending':getattr(dispatcher,'publication_serial_pending',None),
                               'root_serial_guard':getattr(dispatcher,'root_serial_guard',None),
                               'root_serial_observation':getattr(dispatcher,'root_serial_observation',None),
                               'notification_serial_guard':getattr(dispatcher,'notification_serial_guard',None),
                               'activation_attempted_this_pump':getattr(dispatcher,'activation_attempted',False),
                               'original_source_registration': registration_outcomes,
                               'headless_receiver_activation': 'DATA_MISSING; original operations activation-plan entry required',
                               'mode': 'official_native_queue' if getattr(transport,'queues_busy_recipient',False)
                                       else 'verified_shared_transport' if transport else 'observer_only',
                               'wakeups': [{k:row[k] for k in ['event_key','target','state','turn_id','native_message_id']}
                                           for row in store.rows()]}
                    if args.command == 'serve-queue':
                        guard = summary['root_serial_guard'] or {}
                        observation = summary['root_serial_observation'] or {}
                        publication_wait = summary['publication_serial_pending'] or {}
                        handoff_scan = {
                            'original_window': guard.get('current_active_original_window'),
                            'original_turn': guard.get('current_active_turn'),
                            'serial_state': guard.get('current_state'),
                            'release_check': observation.get('state'),
                            'release_recorded_this_scan': observation.get('root_release_recorded', False),
                            'release_blocker': observation.get('reason'),
                            'activation_guard': guard.get('state'),
                            'guard_reasons': guard.get('reasons', []),
                            'publication_wait_task': publication_wait.get('task_id'),
                            'publication_wait_state': publication_wait.get('state'),
                            'direct_handoff': getattr(dispatcher, 'direct_handoff', None),
                        }
                        # One compact owned readback, including unchanged scans;
                        # no business receipt, second ledger or periodic polling.
                        (ROOT/STATE/'service-scan-readback.json').write_text(json.dumps({
                            'pid':os.getpid(),'uid':os.getuid(),'project_root':str(ROOT),
                            'loaded_sources':code_sources,'scan_completed_at':now(),
                            'enrolled_results_found':len(valid),'isolated_source_error_count':len(errors),
                            'handoff_scan':handoff_scan,
                            'transport_rows':len(store.rows()),'receipt_bounded_scan':getattr(store,'receipt_scan_progress',{}),
                            'history_bounded_scan':getattr(store,'history_scan_progress',{}),
                            'descriptor_capacity_changes':watcher.fd_capacity_changes if watcher else [],'transport_ids_retained':True},sort_keys=True)+'\n')
                    if store.observations:store.observations.finish({'valid_events':len(valid),'source_errors':len(errors),'transport_rows':len(store.rows())})
                    if store.changed_summary(summary):
                        print(json.dumps({'observed_at':now(),**summary}),flush=True)
                    if watcher is None:
                        break
                    while True:
                        timeout, _ = activation_wait_deadline(store)
                        continuation_events=_scan_continuation_events(store)
                        if continuation_events:timeout=0.0
                        # Existing watch events and due original deadlines take
                        # priority over cooperative finite history continuations.
                        with observed_phase(store,'wait'):
                            changed=watcher.wait(timeout)
                        if changed:
                            trigger_categories=getattr(watcher,'last_event_categories',[]) or ['watch_event']
                            deadline_only=None
                            break
                        _,due=activation_wait_deadline(store)
                        if due:
                            trigger_categories=['grace_deadline'];deadline_only=due
                            break
                        if continuation_events:
                            trigger_categories=['source_continuation' if INPUT_CONTINUE in continuation_events else 'history_continuation' if HISTORY_CONTINUE in continuation_events else 'receipt_continuation']
                            deadline_only=continuation_events
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
