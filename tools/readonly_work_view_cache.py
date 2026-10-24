"""Rebuildable historical inventory cache. Never used by a permission consumer."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
from urllib.parse import unquote, urlsplit

CACHE_REL = 'logs/handoffs/2026-10-22-department-flow-congestion-optimization-v1/runtime-view-cache'
SCHEMA = 'historical-inventory-cache/v2'
_SESSION = ContextVar('flashcast_inventory_session', default=None)
_TRACE = ContextVar('flashcast_inventory_dependency_trace', default=None)
_NAMESPACES = {'historical-assignment-view', 'historical-intake-route', 'dispatcher-source-error'}


class CachedReadError(ValueError):
    pass


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _stat(path):
    try:
        s = path.stat()
        return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
    except FileNotFoundError:
        return None


def _audit(event, args):
    trace = _TRACE.get()
    if trace is None:
        return
    if event in {'open', 'os.scandir', 'os.listdir', 'sqlite3.connect'} and args:
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            value = os.fsdecode(value)
            if event == 'sqlite3.connect' and value.startswith('file:'):
                value = unquote(urlsplit(value).path)
            path = Path(value).absolute()
            root, directory, paths, versions = trace
            if path.is_relative_to(root) and not path.is_relative_to(directory):
                paths.add(str(path))
                paths.add(str(path.parent))
                if str(path) not in versions:versions[str(path)] = _stat(path)
                if str(path.parent) not in versions:versions[str(path.parent)] = _stat(path.parent)
                if event == 'sqlite3.connect':
                    paths.add(str(path) + '-wal')
                    if str(path) + '-wal' not in versions:
                        versions[str(path) + '-wal'] = _stat(Path(str(path) + '-wal'))


sys.addaudithook(_audit)


def note_read(path):
    """Also observe cached/absent request reads; no behavior outside inventory."""
    if _TRACE.get() is not None:
        _audit('open', (os.fspath(path),))


class Session:
    def __init__(self, root, directory):
        self.root = Path(root).resolve()
        self.directory = Path(directory).resolve()
        if not self.directory.is_relative_to(self.root):
            raise ValueError('project-owned inventory cache required')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fingerprints = {}
        self.hits = self.misses = self.invalidated = 0
        self.source_generation = None
        self.source_paths = set()
        self.native_rows = {}

    def fingerprint(self, path):
        path = Path(path)
        version = _stat(path)
        key = (str(path), tuple(version) if version else None)
        if key not in self.fingerprints:
            token = _TRACE.set(None)
            try:
                if path.is_symlink():
                    raise ValueError('symlink dependencies are not cached')
                elif version is None:
                    value = {'kind': 'absent'}
                elif path.is_dir():
                    value = {'kind': 'directory', 'names': sorted(os.listdir(path))}
                else:
                    raw = path.read_bytes()
                    if _stat(path) != version:
                        raise ValueError('inventory dependency changed while reading')
                    value = {'kind': 'file', 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
                self.fingerprints[key] = value
            finally:
                _TRACE.reset(token)
        return self.fingerprints[key]


@contextmanager
def inventory_session(root, *, directory=None):
    root = Path(root).resolve()
    existing = _SESSION.get()
    if existing is not None and existing.root == root:
        yield existing
        return
    value = Session(root, directory or root / CACHE_REL)
    token = _SESSION.set(value)
    try:
        yield value
    finally:
        _SESSION.reset(token)


def inventory_active(root):
    value = _SESSION.get()
    return value is not None and value.root == Path(root).resolve()


def inventory_handoff_rows(root, task_id):
    """One fresh validated ledger per read-only request, never a disk cache.

    These private rows are only read by inventory consumers. Outside an active
    inventory the normal native reader is used, including execution guards.
    """
    import workflow_control as w
    session = _SESSION.get()
    if session is None or session.root != Path(root).resolve():
        return w._result_handoff_rows(root, task_id)
    path = w.result_handoff_path(root, task_id)
    note_read(path)
    stamp = _stat(path)
    cached = session.native_rows.get(str(path))
    if cached is None or cached[0] != stamp:
        rows = w._result_handoff_rows(root, task_id)
        if _stat(path) != stamp:
            raise w.WorkflowError('native ledger changed during inventory; retry fresh read')
        cached = (stamp, rows)
        session.native_rows[str(path)] = cached
    return cached[1]


def _safe(value):
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if lowered in {'token', 'claim', 'coordination_claim', 'delivery_claim', 'cookie',
                           'api_key', 'password', 'secret', 'authorization_header'}:
                return False
            if not _safe(item):
                return False
    elif isinstance(value, list):
        return all(_safe(item) for item in value)
    return True


def _mandatory(root, required):
    files = {root / 'data/department-registry.json', root / 'data/task-contract.json',
             root / 'data/department-current-assignment.json', Path(__file__).resolve()}
    files.update(Path(p).resolve() for p in required)
    # Logic changes invalidate old derived views, including already-loaded helpers.
    session = _SESSION.get()
    generation = len(sys.modules)
    if session is not None and session.source_generation == generation:
        files.update(session.source_paths)
    else:
        sources = set()
        prefix = str(root) + os.sep
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name and str(name).startswith(prefix) and str(name).endswith('.py'):
                sources.add(Path(name).absolute())
        if session is not None:
            session.source_generation, session.source_paths = generation, sources
        files.update(sources)
    return {str(p) for p in files if p.is_relative_to(root)}


def _propagate(paths):
    # A nested hit must contribute its original dependencies to the caller's
    # trace. Reading only the disposable cache filename would hide source drift.
    trace = _TRACE.get()
    if trace is not None:
        root, directory, outer, versions = trace
        for path in paths:
            p = Path(path)
            if p.is_relative_to(root) and not p.is_relative_to(directory):
                outer.add(path)
                versions.setdefault(path, _stat(p))


def memoized_view(root, namespace, key, compute, *, required=(), failures_only=False):
    """Display/error projection only. Never cache claims, policy, permits or CAS."""
    if namespace not in _NAMESPACES:
        raise ValueError('permission or arbitrary function caching is prohibited')
    from workflow_control import WorkflowError
    with inventory_session(root) as session:
        mandatory = _mandatory(session.root, required)
        identity = [SCHEMA, str(session.root), namespace, key]
        name = session.directory / (_sha(identity) + '.json')
        entry = None
        try:
            candidate = json.loads(name.read_text())
            deps = candidate['dependencies']
            if (candidate.get('identity') == identity
                    and candidate.get('outcome_sha256') == _sha(candidate['outcome'])
                    and mandatory.issubset(deps)
                    and all(Path(p).is_relative_to(session.root) and session.fingerprint(p) == value
                            for p, value in deps.items())):
                entry = candidate
            else:
                session.invalidated += 1
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if entry is not None:
            session.hits += 1
            _propagate(entry['dependencies'])
            outcome = entry['outcome']
            if 'error' in outcome:
                raise CachedReadError(outcome['error'])
            return outcome['value']
        session.misses += 1
        paths = set(mandatory)
        versions = {p: _stat(Path(p)) for p in paths}
        token = _TRACE.set((session.root, session.directory, paths, versions))
        error = None
        try:
            value = compute()
            outcome = {'value': value}
        except (WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            error = exc
            outcome = {'error': str(exc), 'error_type': type(exc).__name__}
        finally:
            _TRACE.reset(token)
        unchanged = all(_stat(Path(p)) == version for p, version in versions.items())
        _propagate(paths)
        if unchanged and (not failures_only or error is not None) and _safe(outcome):
            try:
                paths.update(_mandatory(session.root, required))
                deps = {p: session.fingerprint(p) for p in sorted(paths)}
                entry = {'identity': identity, 'dependencies': deps, 'outcome': outcome,
                         'outcome_sha256': _sha(outcome), 'inventory_is_permission': False}
                session.directory.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix='.view-', dir=session.directory)
                try:
                    with os.fdopen(fd, 'w') as stream:
                        json.dump(entry, stream, ensure_ascii=False, sort_keys=True)
                        stream.flush(); os.fsync(stream.fileno())
                    os.replace(temporary, name)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            except (OSError, ValueError, TypeError):
                pass  # A disposable view cache never blocks the normal reader.
        if error is not None:
            raise error
        return value
