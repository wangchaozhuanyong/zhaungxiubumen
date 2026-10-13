"""Small project-local source transaction; no dispatch, QA or platform permission.

Run expensive review/tests before calling apply. The short workflow lock only
protects exact file comparisons, backups and atomic replacements. An unrelated
result queue update is not a source conflict. This is an execution journal,
never a fabricated assistant verdict or a claim that business work is complete.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile
import uuid

import workflow_control as w


def _file(root, relative):
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise w.WorkflowError("source transaction requires a project-relative path")
    target = w.safe_path(root, relative)
    unresolved = Path(root) / raw
    if any(p.is_symlink() for p in [unresolved, *unresolved.parents] if p != Path(root).parent):
        raise w.WorkflowError("source transaction cannot traverse symlinks")
    return target


def fingerprint(root, relative):
    path = _file(root, relative)
    if not path.is_file():
        raise w.WorkflowError("existing exact source file required: " + relative)
    raw = path.read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw), "mode": stat.S_IMODE(path.stat().st_mode)}


def _replace(path, raw, mode):
    fd, temporary = tempfile.mkstemp(prefix=".source-cas-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare(root, changes):
    """Read/compile all changed files before entering the short write lock."""
    if not isinstance(changes, list) or not changes or len(changes) > 100:
        raise w.WorkflowError("bounded nonempty source change list required")
    prepared, seen = [], set()
    for row in changes:
        target = row.get("path", "")
        if not target.startswith("tools/") or target in seen:
            raise w.WorkflowError("unique tools source files required")
        seen.add(target)
        expected = row.get("before")
        if fingerprint(root, target) != expected:
            raise w.WorkflowError("current source changed; preserve newer work: " + target)
        candidate = fingerprint(root, row.get("candidate", ""))
        raw = _file(root, candidate["path"]).read_bytes()
        if target.endswith(".py"):
            compile(raw, target, "exec")
        prepared.append({"path": target, "before": expected, "candidate": candidate,
                         "after": {"path": target, "sha256": candidate["sha256"],
                                   "size": candidate["size"], "mode": expected["mode"]},
                         "bytes": raw})
    return prepared


def apply(root, prepared, backup_directory, *, task_id, executor="operations"):
    root = Path(root).resolve()
    backup = _file(root, backup_directory)
    if not backup_directory.startswith("backups/") or backup.exists():
        raise w.WorkflowError("new project-owned backup directory required")
    execution_id = str(uuid.uuid4())
    journal = {"schema": "project-source-transaction/v1", "task_id": task_id,
               "executor": executor, "execution_id": execution_id, "state": "prepared",
               "started_at": w.utc_timestamp(), "external_writes": 0,
               "assistant_verdict_created": False, "business_goal_closed": False,
               "source_operations": []}
    journal_relative = str((backup / "journal.json").relative_to(root))
    with w.workflow_lock(root):
        # Recheck only these files. No recursive native reader or global queue
        # fingerprint belongs in this short write transaction.
        for row in prepared:
            if (fingerprint(root, row["path"]) != row["before"]
                    or fingerprint(root, row["candidate"]["path"]) != row["candidate"]
                    or hashlib.sha256(row["bytes"]).hexdigest() != row["after"]["sha256"]):
                raise w.WorkflowError("protected source changed before apply: " + row["path"])
        backup.mkdir(parents=True)
        journal_path = backup / "journal.json"
        try:
            for row in prepared:
                original = _file(root, row["path"])
                if fingerprint(root, row["path"]) != row["before"]:
                    raise w.WorkflowError("source changed before replacement: " + row["path"])
                saved = backup / row["path"]
                saved.parent.mkdir(parents=True, exist_ok=True)
                _replace(saved, original.read_bytes(), row["before"]["mode"])
                operation = {k: row[k] for k in ("path", "before", "after")}
                operation.update(backup=fingerprint(root, str(saved.relative_to(root))), applied=False)
                journal["source_operations"].append(operation)
                w.atomic_write_json(journal_path, journal)
                _replace(original, row["bytes"], row["before"]["mode"])
                operation["applied"] = True
                if fingerprint(root, row["path"]) != row["after"]:
                    raise w.WorkflowError("after-source readback mismatch: " + row["path"])
                w.atomic_write_json(journal_path, journal)
        except Exception as exc:
            conflicts = []
            for operation in reversed(journal["source_operations"]):
                if not operation["applied"]:
                    continue
                if fingerprint(root, operation["path"]) != operation["after"]:
                    conflicts.append(operation["path"])
                    continue
                saved = _file(root, operation["backup"]["path"])
                _replace(_file(root, operation["path"]), saved.read_bytes(), operation["before"]["mode"])
                operation["restored"] = True
            journal.update(state="rollback_conflict" if conflicts else "rolled_back",
                           failure=str(exc), conflicts=conflicts, completed_at=w.utc_timestamp())
            w.atomic_write_json(journal_path, journal)
            raise
        journal.update(state="adopted", completed_at=w.utc_timestamp())
        w.atomic_write_json(journal_path, journal)
    return {"journal": w.file_digest(root, journal_relative), "state": "adopted",
            "execution_id": execution_id, "files": len(prepared), "external_writes": 0}


def readback(root, journal_pin):
    if w.file_digest(root, journal_pin.get("path", "")) != journal_pin:
        raise w.WorkflowError("exact source execution journal changed")
    journal = w.read_json(_file(root, journal_pin["path"]))
    if journal.get("state") != "adopted" or journal.get("external_writes") != 0:
        raise w.WorkflowError("actual completed project source adoption required")
    for row in journal.get("source_operations", []):
        if (fingerprint(root, row["path"]) != row["after"]
                or fingerprint(root, row["backup"]["path"]) != row["backup"]
                or {k: row["backup"][k] for k in ("sha256", "size", "mode")}
                   != {k: row["before"][k] for k in ("sha256", "size", "mode")}):
            raise w.WorkflowError("adopted file or rollback bytes changed: " + row["path"])
    return {"state": "adopted", "source_readback_passed": True,
            "files": len(journal["source_operations"]), "business_goal_closed": False}
