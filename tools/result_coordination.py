"""Exact-result coordination for the real native result-handoff entry.

Actor/owner strings are audit metadata, not authentication. This module grants
no external permission and never executes a message, decision, or publication.
Lock order is coordination flock -> SQLite transaction -> native workflow lock;
SQLite transactions finish before invoking the native handoff append.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import uuid

COORDINATION_LOCK = Path("logs/.result-coordination.lock")
DATABASE = Path("logs/result-coordination.sqlite3")
ROLES = {"operations", "operations-assistant"}
FINAL_EVENTS = {"controller_received", "controller_decision", "controller_followthrough"}
REPORT_STATES = {"completed", "partial", "qa_rework", "external_blocked", "queue_failed", "failed"}
IDENTITY_FIELDS = ("task_id", "sender_department", "candidate_version", "result_sha256")
COORDINATOR_FIELDS = {"coordinator_role", "coordinator_owner", "coordination_claim"}


def _w():
    import workflow_control
    return workflow_control


def _fail(message):
    raise _w().WorkflowError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def exact_identity(request):
    identity = {key: request.get(key) for key in IDENTITY_FIELDS}
    if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
        _fail("exact original result identity required")
    _w().validate_task_id(identity["task_id"])
    if not re.fullmatch(r"[0-9a-f]{64}", identity["result_sha256"]):
        _fail("final outbox SHA-256 required")
    return identity


def _key(identity):
    return _sha([identity[name] for name in IDENTITY_FIELDS])


@contextmanager
def coordination_lock(root):
    root = Path(root).resolve()
    path = _w().safe_path(root, str(COORDINATION_LOCK))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_queued(root, identity):
    """Claims apply only to an existing exact native queue; no historical scan."""
    w = _w()
    registry = w.department_registry(root)
    sender = identity["sender_department"]
    if sender == "operations" or sender not in registry:
        _fail("registered result sender required")
    rows = w._result_handoff_rows(root, identity["task_id"])
    current = [row for row in rows if w._result_identity(row) ==
               (sender, identity["candidate_version"], identity["result_sha256"])]
    queued = [row for row in current if row.get("event") == "notification_queued"]
    if len(queued) != 1:
        _fail("claim requires one existing exact native queued result")
    pin = queued[0].get("outbox")
    if not isinstance(pin, dict) or w.file_digest(root, str(pin.get("path") or "")) != pin:
        _fail("queued frozen outbox bytes changed")
    w.validate_outbox(root, [pin], sender, identity["task_id"])
    box = w.read_json(w.safe_path(root, pin["path"]))
    fixed = registry[sender].get("chat_binding", {}).get("task_id")
    if (box.get("task_id") != identity["task_id"] or box.get("department") != sender
            or box.get("candidate_version") != identity["candidate_version"]
            or not fixed or box.get("fixed_chat_task_id", box.get("chat_task_id")) != fixed):
        _fail("queued outbox original task/version/registered chat mismatch")
    if pin["sha256"] != identity["result_sha256"]:
        _fail("queued result hash mismatch")
    return box


def _role(root, role, owner):
    if role not in ROLES or role not in _w().department_registry(root):
        _fail("registered coordinator role required")
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
        _fail("nonempty coordinator owner audit metadata required")


class CoordinationStore:
    """One connection per caller; all public mutations use shared flock."""

    def __init__(self, root, clock=None):
        self.root = Path(root).resolve()
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        path = _w().safe_path(self.root, str(DATABASE))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
          CREATE TABLE IF NOT EXISTS claims (
            result_key TEXT PRIMARY KEY, identity_json TEXT NOT NULL,
            role TEXT NOT NULL, owner TEXT NOT NULL, token TEXT NOT NULL,
            fence INTEGER NOT NULL, expires REAL NOT NULL, request_id TEXT NOT NULL,
            precheck_json TEXT
          );
          CREATE TABLE IF NOT EXISTS reservations (
            result_key TEXT NOT NULL, effect_key TEXT NOT NULL, payload_json TEXT NOT NULL,
            status TEXT NOT NULL, native_record_json TEXT,
            PRIMARY KEY(result_key,effect_key)
          );
          CREATE TABLE IF NOT EXISTS coordination_audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL
          );
        """)

    def close(self):
        self.conn.close()

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            _fail("timezone-aware coordination clock required")
        return value.timestamp()

    def _audit(self, identity, event, details):
        previous = self.conn.execute("SELECT record_hash FROM coordination_audit ORDER BY seq DESC LIMIT 1").fetchone()
        prior = previous[0] if previous else ""
        payload = {"identity": identity, "event": event, "details": details, "at": self._now()}
        self.conn.execute("INSERT INTO coordination_audit(payload_json,previous_hash,record_hash) VALUES(?,?,?)",
                          (_canonical(payload), prior, _sha([prior, payload])))

    def _begin(self):
        self.conn.execute("BEGIN IMMEDIATE")
        previous = ""
        try:
            for row in self.conn.execute("SELECT * FROM coordination_audit ORDER BY seq"):
                payload = json.loads(row["payload_json"])
                if row["previous_hash"] != previous or row["record_hash"] != _sha([previous, payload]):
                    _fail("coordination audit changed; explicit reconciliation required")
                previous = row["record_hash"]
        except BaseException:
            self.conn.rollback()
            raise

    def _row(self, identity):
        return self.conn.execute("SELECT * FROM claims WHERE result_key=?", (_key(identity),)).fetchone()

    @staticmethod
    def _view(row, duplicate=False):
        if row is None:
            return {"claimed": False, "external_permission_issued": False}
        return {name: row[name] for name in ("result_key", "role", "owner", "token", "fence", "expires")} | {
            "claimed": bool(row["owner"]), "duplicate": duplicate, "external_permission_issued": False,
            "actor_metadata_is_authentication": False,
            "precheck": json.loads(row["precheck_json"]) if row["precheck_json"] else None}

    def _lease(self, identity, role, owner, claim):
        _role(self.root, role, owner)
        row = self._row(identity)
        if (not isinstance(claim, dict) or not row or row["role"] != role or row["owner"] != owner
                or claim.get("result_key") != _key(identity) or claim.get("token") != row["token"]
                or type(claim.get("fence")) is not int or claim["fence"] != row["fence"]
                or row["expires"] <= self._now()):
            _fail("stale, expired or foreign coordination claim")
        return row

    def readback(self, identity):
        identity = exact_identity(identity)
        with coordination_lock(self.root):
            _validate_queued(self.root, identity)
            self._begin()
            try:
                result = self._view(self._row(identity))
                self.conn.commit()
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def claim(self, identity, role, owner, request_id, ttl_seconds=900, recovery_reason=""):
        identity = exact_identity(identity)
        _role(self.root, role, owner)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("claim request id and TTL 1..900 seconds required")
        with coordination_lock(self.root):
            _validate_queued(self.root, identity)
            self._begin()
            try:
                old = self._row(identity)
                if old and old["owner"] and old["expires"] > self._now():
                    if (old["owner"], old["role"], old["request_id"]) == (owner, role, request_id):
                        self.conn.commit()
                        return self._view(old, True)
                    _fail("result already claimed; explicit release/transfer required")
                if old and old["owner"] and not recovery_reason.strip():
                    _fail("expired/interrupted claim requires explicit recovery reason")
                fence = old["fence"] + 1 if old else 1
                self.conn.execute("""INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,NULL)
                  ON CONFLICT(result_key) DO UPDATE SET role=excluded.role,owner=excluded.owner,
                  token=excluded.token,fence=excluded.fence,expires=excluded.expires,
                  request_id=excluded.request_id,precheck_json=NULL""",
                  (_key(identity), _canonical(identity), role, owner, uuid.uuid4().hex,
                   fence, self._now() + ttl_seconds, request_id))
                self._audit(identity, "recover_expired" if old and old["owner"] else "claim",
                            {"role": role, "owner": owner, "fence": fence, "reason": recovery_reason})
                result = self._view(self._row(identity))
                self.conn.commit()
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def recover(self, identity, role, owner, request_id, reason, ttl_seconds=900):
        if not isinstance(reason, str) or not reason.strip():
            _fail("explicit interruption recovery reason required")
        return self.claim(identity, role, owner, request_id, ttl_seconds, reason)

    def _change(self, identity, role, owner, claim, event, mutate):
        identity = exact_identity(identity)
        with coordination_lock(self.root):
            box = _validate_queued(self.root, identity)
            self._begin()
            try:
                row = self._lease(identity, role, owner, claim)
                details = mutate(row, box)
                self._audit(identity, event, details)
                result = self._view(self._row(identity))
                self.conn.commit()
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def renew(self, identity, role, owner, claim, ttl_seconds=900):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            _fail("lease TTL must be 1..900 seconds")
        def mutate(row, box):
            self.conn.execute("UPDATE claims SET expires=? WHERE result_key=?", (self._now()+ttl_seconds, row["result_key"]))
            return {"fence": row["fence"], "ttl_seconds": ttl_seconds}
        return self._change(identity, role, owner, claim, "renew", mutate)

    def release(self, identity, role, owner, claim, reason):
        if not isinstance(reason, str) or not reason.strip():
            _fail("release reason required")
        def mutate(row, box):
            self.conn.execute("UPDATE claims SET role='',owner='',token='',expires=0,fence=fence+1 WHERE result_key=?", (row["result_key"],))
            return {"previous_owner": owner, "reason": reason}
        return self._change(identity, role, owner, claim, "release", mutate)

    def transfer(self, identity, role, owner, claim, target_role, target_owner, request_id, ttl_seconds=900):
        _role(self.root, target_role, target_owner)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("transfer request id and TTL 1..900 seconds required")
        def mutate(row, box):
            if not row["precheck_json"]:
                _fail("precheck and unfinished scope required before explicit transfer")
            self.conn.execute("UPDATE claims SET role=?,owner=?,token=?,fence=fence+1,expires=?,request_id=? WHERE result_key=?",
                              (target_role, target_owner, uuid.uuid4().hex, self._now()+ttl_seconds, request_id, row["result_key"]))
            return {"previous_owner": owner, "target_role": target_role, "target_owner": target_owner}
        return self._change(identity, role, owner, claim, "transfer", mutate)

    def precheck(self, identity, role, owner, claim, status, next_owner, next_action, unblock_condition, scope=""):
        if status not in REPORT_STATES or any(not isinstance(value, str) or not value.strip()
                                             for value in (next_owner, next_action, unblock_condition)):
            _fail("actual status, next owner/action and unblock condition required")
        def mutate(row, box):
            if scope and (not box.get("scope") or scope != box["scope"]):
                _fail("precheck scope must already exist in exact frozen outbox")
            draft = {"status": status, "next_owner": next_owner, "next_action": next_action,
                     "unblock_condition": unblock_condition, "scope": scope, "fence": row["fence"],
                     "draft_only": True, "controller_decision_recorded": False,
                     "external_permission_issued": False}
            self.conn.execute("UPDATE claims SET precheck_json=? WHERE result_key=?", (_canonical(draft), row["result_key"]))
            return draft
        return self._change(identity, role, owner, claim, "precheck_draft", mutate)


def _payload(root, request):
    """Freeze all request semantics plus exact bytes used by native append."""
    w = _w()
    raw = {key: value for key, value in request.items() if key not in COORDINATOR_FIELDS}
    paths = raw.get("evidence_paths") or []
    if not isinstance(paths, list):
        _fail("native evidence_paths must be an array")
    pins = {"outbox": w.file_digest(root, str(raw.get("outbox_path") or "")),
            "evidence": [w.file_digest(root, str(path)) for path in paths]}
    if raw.get("linked_outbox_path"):
        pins["linked_outbox"] = w.file_digest(root, raw["linked_outbox_path"])
    return {"request": raw, "pins": pins}


def _native_readback(root, payload):
    w = _w()
    request, pins = payload["request"], payload["pins"]
    rows = w._result_handoff_rows(root, request["task_id"])
    matches = [row for row in rows if row.get("idempotency_key") == request.get("idempotency_key")]
    if not matches:
        return None
    if len(matches) != 1:
        _fail("native idempotency key is ambiguous")
    row = matches[0]
    expected = {key: request.get(key) for key in (*IDENTITY_FIELDS, "event", "idempotency_key")}
    expected.update(pins)
    # All native preserved request fields are compared; path inputs map to pins.
    skipped = {"evidence_paths", "outbox_path", "linked_outbox_path", *IDENTITY_FIELDS, "event", "idempotency_key"}
    # The native operations verifier converts this path input into a digest.
    # Compare the same frozen bytes, rather than a path string with a pin dict.
    if "control_applied_proof" in request and "control_applied_proof" in row:
        expected["control_applied_proof"] = w.file_digest(root, request["control_applied_proof"])
        skipped.add("control_applied_proof")
    for key, value in request.items():
        if key not in skipped and key in row:
            expected[key] = value
    defaults = {"qa_status": "NOT_VERIFIED", "execution_status": "NOT_EXECUTED",
                "public_postcheck_status": "NOT_VERIFIED"}
    event = request.get("event")
    required_fields = {
        "controller_received": ("intake_mode", "source_reply_sha256", "source_thread_id", "reply_observed_at"),
        "controller_decision": ("decision", "next_owner", "next_action"),
        "controller_followthrough": ("followthrough_status",),
    }
    expected.update({key: str(request.get(key) or "") for key in required_fields[event]})
    if event == "controller_received":
        expected["source_reply_sha256"] = expected["source_reply_sha256"].lower()
        if request.get("intake_mode") == "fallback":
            expected["fallback_reason"] = str(request.get("fallback_reason") or "")
    if event == "controller_decision":
        expected.update({key: request.get(key) or value for key, value in defaults.items()})
        if request.get("decision") == "wait_external":
            expected["unblock_condition"] = str(request.get("unblock_condition") or "")
        if request.get("decision") == "close_scope":
            expected["acceptance_scope"] = str(request.get("acceptance_scope") or "")
    if event == "controller_followthrough":
        status = request.get("followthrough_status")
        if status in {"external_wait_registered", "blocked_with_owner"}:
            expected.update({key: str(request.get(key) or "") for key in ("next_check_at", "unblock_condition")})
        elif status in {"dispatch_sent", "execution_verified", "prior_action_verified", "inflight_result_verified"}:
            expected.update({key: str(request.get(key) or "") for key in ("linked_task_id", "action_receipt_id")})
            if status == "inflight_result_verified":
                expected["linked_dispatch_receipt_id"] = str(request.get("linked_dispatch_receipt_id") or "")
        elif status == "dependency_resolved":
            expected["resolution_record_id"] = str(request.get("resolution_record_id") or "")
        else:
            expected["action_reference"] = str(request.get("action_reference") or "")
    if any(row.get(key) != value for key, value in expected.items()):
        _fail("native readback payload/evidence differs from reserved effect")
    return row


class HandoffAdmission:
    def __init__(self, store, identity, effect, payload, replay_record=None):
        self.store, self.identity, self.effect, self.payload = store, identity, effect, payload
        self.replay_record = replay_record
        self.completed = replay_record is not None

    def complete(self, record):
        if self.store is None:
            return
        native = _native_readback(self.store.root, self.payload)
        if native is None or native.get("record_id") != record.get("record_id"):
            _fail("native append readback missing or mismatched")
        self.store._begin()
        try:
            self.store.conn.execute("UPDATE reservations SET status='committed',native_record_json=? WHERE result_key=? AND effect_key=?",
                                    (_canonical(native), _key(self.identity), self.effect))
            self.store._audit(self.identity, "effect_readback_committed", {"effect_key": self.effect, "native_record_id": native["record_id"]})
            self.store.conn.commit()
            self.completed = True
        except BaseException:
            self.store.conn.rollback()
            raise


@contextmanager
def handoff_guard(root, request):
    """Native wrapper guard. Exceptions retain uncertain intent until readback."""
    if not isinstance(request, dict) or request.get("event") not in FINAL_EVENTS:
        yield HandoffAdmission(None, None, None, None)
        return
    root = Path(root).resolve()
    role = request.get("coordinator_role", "operations")
    if role != "operations":
        _fail("assistant precheck cannot record final controller events")
    identity = exact_identity(request)
    with coordination_lock(root):
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if row and row["owner"]:
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            elif request.get("coordination_claim"):
                _fail("claim was released or does not own this exact result")
            payload = _payload(root, request)
            effect = _sha([request["event"], request.get("idempotency_key")])
            store._begin()
            reservation = store.conn.execute("SELECT * FROM reservations WHERE result_key=? AND effect_key=?", (_key(identity), effect)).fetchone()
            if reservation and json.loads(reservation["payload_json"]) != payload:
                store.conn.rollback()
                _fail("reserved effect already binds different semantic payload/evidence")
            native = _native_readback(root, payload)
            if reservation and reservation["status"] == "committed" and native is None:
                store.conn.rollback()
                _fail("committed native effect is missing; reconcile")
            if reservation and reservation["status"] == "uncertain" and native is None:
                store.conn.rollback()
                _fail("uncertain native effect absent; explicit recover_reservation required before retry")
            if not reservation:
                store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)", (_key(identity), effect, _canonical(payload)))
                store._audit(identity, "effect_reserved", {"effect_key": effect, "role": role,
                             "owner": request.get("coordinator_owner", "legacy-operations")})
            elif reservation["status"] == "retry_ready":
                store.conn.execute("UPDATE reservations SET status='uncertain' WHERE result_key=? AND effect_key=?", (_key(identity), effect))
            store.conn.commit()
            admission = HandoffAdmission(store, identity, effect, payload, native)
            if native:
                admission.complete(native)
            try:
                yield admission
            except _w().WorkflowError:
                # A native validation refusal is recoverable without changing
                # legacy caller behavior, but only after exact append readback
                # proves this effect is absent. Crashes and divergent records
                # keep their uncertain reservation and require reconciliation.
                if _native_readback(root, payload) is None:
                    store._begin()
                    store.conn.execute("DELETE FROM reservations WHERE result_key=? AND effect_key=?",
                                       (_key(identity), effect))
                    store._audit(identity, "native_validation_refused_append_absent", {"effect_key": effect})
                    store.conn.commit()
                raise
        finally:
            if store.conn.in_transaction:
                store.conn.rollback()
            store.close()


def recover_reservation(root, request, reason):
    """Explicitly reconcile an uncertain append, never execute its side effect."""
    if not isinstance(reason, str) or not reason.strip() or request.get("event") not in FINAL_EVENTS:
        _fail("explicit uncertain-effect recovery reason required")
    if request.get("coordinator_role", "operations") != "operations":
        _fail("assistant cannot recover final controller effects")
    root = Path(root).resolve()
    identity = exact_identity(request)
    with coordination_lock(root):
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if row and row["owner"]:
                _validate_queued(root, identity)
                store._lease(identity, "operations", request.get("coordinator_owner"), request.get("coordination_claim"))
            payload = _payload(root, request)
            effect = _sha([request["event"], request.get("idempotency_key")])
            store._begin()
            reserved = store.conn.execute("SELECT * FROM reservations WHERE result_key=? AND effect_key=?", (_key(identity), effect)).fetchone()
            if not reserved or json.loads(reserved["payload_json"]) != payload:
                _fail("exact existing reservation required for recovery")
            native = _native_readback(root, payload)
            if reserved["status"] == "committed" and native is None:
                _fail("committed native effect is missing; reconcile")
            status = "committed" if native else "retry_ready"
            store.conn.execute("UPDATE reservations SET status=?,native_record_json=? WHERE result_key=? AND effect_key=?",
                               (status, _canonical(native) if native else None, _key(identity), effect))
            store._audit(identity, "effect_recovery_readback", {"effect_key": effect, "status": status, "reason": reason})
            store.conn.commit()
            return {"status": status, "native_record": native, "side_effect_executed": False}
        finally:
            if store.conn.in_transaction:
                store.conn.rollback()
            store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("claim", "readback", "renew", "release", "transfer", "recover", "precheck", "recover-reservation"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    request = json.loads(args.input.read_text(encoding="utf-8"))
    if args.command == "recover-reservation":
        result = recover_reservation(args.root, request["handoff_request"], request["reason"])
    else:
        store = CoordinationStore(args.root)
        try:
            result = getattr(store, args.command)(**request)
        finally:
            store.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
