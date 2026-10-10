"""Exact-result coordination for the real native result-handoff entry.

Actor/owner strings are audit metadata, not authentication. This module grants
no external permission and never executes a message, decision, or publication.
Lock order is coordination flock -> SQLite transaction -> native workflow lock;
transfers hold workflow lock before the SQL transaction through assignment apply.
SQLite transactions finish before invoking the native handoff append.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, TypedDict
import uuid

COORDINATION_LOCK = Path("logs/.result-coordination.lock")
DATABASE = Path("logs/result-coordination.sqlite3")
ROLES = {"operations", "operations-assistant"}
FINAL_EVENTS = {"controller_received", "controller_decision", "controller_followthrough"}
REPORT_STATES = {"completed", "partial", "qa_rework", "external_blocked", "queue_failed", "failed"}
IDENTITY_FIELDS = ("task_id", "sender_department", "candidate_version", "result_sha256")
COORDINATOR_FIELDS = {"coordinator_role", "coordinator_owner", "coordination_claim"}


class NotificationAttempt(TypedDict):
    """Internal call reservation; never a provider event or execution receipt."""
    sequence: int
    attempt_id: str
    previous_attempt_id: str
    identity: dict[str, str]
    tool: str
    target_thread_id: str
    payload: dict[str, Any]
    claim: dict[str, Any]
    call_started_at: str


def goal_delivery_enabled(root):
    """The global switch alone does not migrate an existing task."""
    config = _w().read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {})
    return (isinstance(config, dict) and config.get("model") == "goal_delivery_assistant_v1"
            and config.get("assistant_decisions_enabled") is True)


def goal_delivery(root, task_id=None, snapshot=None):
    if not goal_delivery_enabled(root):
        return None
    if snapshot is None:
        snapshot = _w().read_json(_w().snapshot_path(Path(root), task_id))
    goal = snapshot.get("goal_delivery") if isinstance(snapshot, dict) else None
    return goal if isinstance(goal, dict) else None


def coordinator_roles(root, *, task_id=None):
    registry = _w().department_registry(root)
    if not goal_delivery_enabled(root) or (task_id is not None and goal_delivery(root, task_id) is None):
        return ROLES & registry.keys()
    return {role for role, item in registry.items()
            if item.get("coordination_authority", {}).get("routine_decisions") is True
            and item.get("new_dispatch_enabled") is not False} | ({"operations"} & registry.keys())


def review_capabilities(root, role):
    authority = _w().department_registry(root).get(role, {}).get("coordination_authority", {})
    values = authority.get("review_capabilities", [])
    return {value for value in values if isinstance(value, str) and value.strip()} if isinstance(values, list) else set()


def _goal_actor(root, identity, role, *, assigned=True):
    """Check routine responsibility without interpreting actor metadata as auth."""
    source = _collaboration_source(root, identity)
    if source is not None and role != source['responsible_assistant']:
        _fail('only original responsible assistant may handle this collaboration result')
    goal = goal_delivery(root, identity["task_id"])
    if goal is None:
        route = result_lane(root, identity)
        if route.get('source_mode') == 'scheduled_run' and role != route.get('target_department'):
            _fail('only exact scheduled source responsible assistant may handle this result')
        return goal
    if role == "operations":
        return goal
    producers = goal.get("producer_departments", [])
    if role == identity["sender_department"] or role in producers:
        _fail("independent assistant required; self review rejected")
    if assigned and role != goal.get("responsible_assistant"):
        _fail("only assigned responsible assistant may handle this result; explicit transfer required")
    capability = goal.get("acceptance_capability")
    if not isinstance(capability, str) or capability not in review_capabilities(root, role):
        _fail("assistant lacks the task acceptance capability")
    return goal


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


def _collaboration_source(root, identity):
    """A declared fixed collaborator is a distinct source, never a department alias."""
    if identity['sender_department'] in _w().department_registry(root):
        return None
    from goal_delivery_runtime import collaboration_result_source
    return collaboration_result_source(root, identity)


def _validate_queued(root, identity):
    """Claim one exact native queue or strict declared collaboration return."""
    w = _w()
    registry = w.department_registry(root)
    sender = identity["sender_department"]
    collaboration = _collaboration_source(root, identity)
    if collaboration is not None:
        return collaboration
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


def _role(root, role, owner, identity=None):
    scheduled_target = (result_lane(root, identity).get('target_department')
                        if identity and goal_delivery(root, identity['task_id']) is None else None)
    if role not in coordinator_roles(root, task_id=identity["task_id"] if identity else None) and role != scheduled_target:
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
        _role(self.root, role, owner, identity)
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
        _role(self.root, role, owner, identity)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("claim request id and TTL 1..900 seconds required")
        with coordination_lock(self.root):
            _goal_actor(self.root, identity, role)
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

    def _change(self, identity, role, owner, claim, event, mutate, after_commit=None,
                lock_workflow=False):
        identity = exact_identity(identity)
        with coordination_lock(self.root), (_w().workflow_lock(self.root) if lock_workflow else nullcontext()):
            box = _validate_queued(self.root, identity)
            self._begin()
            try:
                row = self._lease(identity, role, owner, claim)
                details = mutate(row, box)
                self._audit(identity, event, details)
                result = self._view(self._row(identity))
                self.conn.commit()
                if after_commit is not None:
                    result.update(after_commit(result))
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

    def transfer(self, identity, role, owner, claim, target_role, target_owner, request_id, ttl_seconds=900,
                 review_plan_path=""):
        identity = exact_identity(identity)
        _role(self.root, target_role, target_owner, identity)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("transfer request id and TTL 1..900 seconds required")
        assignment = {}
        def mutate(row, box):
            if not row["precheck_json"]:
                _fail("precheck and unfinished scope required before explicit transfer")
            goal = _goal_actor(self.root, identity, role)
            if goal is not None:
                _goal_actor(self.root, identity, target_role, assigned=False)
                capability = goal.get("acceptance_capability")
                if (target_role == "operations" or capability not in review_capabilities(self.root, target_role)
                        or (role != "operations" and capability not in review_capabilities(self.root, role))
                        or (role == "operations" and target_role != goal.get("responsible_assistant"))):
                    _fail("explicit transfer requires the same task review capability")
                assignment.update(previous_assistant=goal["responsible_assistant"], target_assistant=target_role,
                                  result_identity=identity, fence=row["fence"] + 1, snapshot_binding_required=True)
                from qa_review_plan import _binding, transfer_plan
                snapshot = _w().read_json(_w().snapshot_path(self.root, identity["task_id"]))
                if _binding(self.root, snapshot) is not None and target_role != goal["responsible_assistant"]:
                    if not isinstance(review_plan_path, str) or not review_plan_path.strip():
                        _fail("new frozen review plan required before assignment transfer")
                    assignment["review_plan_transfer"] = transfer_plan(self.root, task_id=identity["task_id"],
                        plan_path=review_plan_path, target_role=target_role, prepare_only=True)
                from goal_delivery_runtime import prepare_assignment_transfer
                prepare_assignment_transfer(self.root, identity, assignment)
            self.conn.execute("UPDATE claims SET role=?,owner=?,token=?,fence=fence+1,expires=?,request_id=? WHERE result_key=?",
                              (target_role, target_owner, uuid.uuid4().hex, self._now()+ttl_seconds, request_id, row["result_key"]))
            return {"previous_owner": owner, "previous_role": role, "target_role": target_role,
                    "target_owner": target_owner, "acceptance_capability": goal.get("acceptance_capability") if goal else None,
                    "assignment_change": assignment or None}
        def after_commit(result):
            if not assignment:
                return {}
            from goal_delivery_runtime import record_assignment_transfer
            applied = record_assignment_transfer(self.root, identity, assignment, _workflow_locked=True)
            return {"responsible_assistant": target_role, "assignment_change": assignment,
                    "assignment_receipt": applied}
        return self._change(identity, role, owner, claim, "transfer", mutate, after_commit,
                            lock_workflow=True)

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
    identity = exact_identity(request)
    route = result_lane(root, identity)
    modern = (goal_delivery(root, identity["task_id"]) is not None
              or route.get('source_mode') == 'scheduled_run')
    if route['lane'] == 'HQ_knowledge' and (role != 'operations' or request['event'] == 'controller_decision'):
        _fail('HQ knowledge only; no self review or HQ second acceptance')
    if not modern and role != "operations":
        _fail("assistant precheck cannot record final controller events")
    with coordination_lock(root):
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if modern:
                _goal_actor(root, identity, role)
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
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
    root = Path(root).resolve()
    identity = exact_identity(request)
    role = request.get("coordinator_role", "operations")
    route = result_lane(root, identity)
    modern = (goal_delivery(root, identity["task_id"]) is not None
              or route.get('source_mode') == 'scheduled_run')
    if route['lane'] == 'HQ_knowledge' and (role != 'operations' or request['event'] == 'controller_decision'):
        _fail('HQ knowledge only; no self review or HQ second acceptance')
    if not modern and role != "operations":
        _fail("assistant cannot recover final controller effects")
    with coordination_lock(root):
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if modern:
                _goal_actor(root, identity, role)
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            if row and row["owner"]:
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
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



def result_lane(root, identity, *, source=None):
    """Read current evidence; assistant summaries never enter their own review."""
    identity = exact_identity(identity)
    collaboration = _collaboration_source(root, identity)
    if collaboration is not None:
        return {'lane': 'professional_acceptance',
                'target_department': collaboration['responsible_assistant'],
                'source_mode': 'collaboration', 'acceptance_proven': False,
                'HQ_second_review_required': False}
    goal = goal_delivery(root, identity['task_id'])
    sender = identity['sender_department']
    if goal:
        assistant = goal['responsible_assistant']
        if sender == assistant:
            rows, invalid = _w()._validate_receipt_chain(root, identity['task_id'])
            accepted = [r for r in rows if r.get('receipt_type') == 'qa_verdict'
                        and r.get('department') == assistant]
            latest = accepted[-1] if accepted else {}
            from qa_review_plan import _binding
            snapshot = _w().read_json(_w().snapshot_path(root, identity['task_id']))
            binding = _binding(root, snapshot) or {}
            summaries = []
            for pin in latest.get('evidence', []):
                if pin.get('sha256') != identity['result_sha256'] or _w().file_digest(root, pin.get('path', '')) != pin:
                    continue
                box = _w().read_json(_w().safe_path(root, pin['path']))
                if all(box.get(k) == v for k, v in {'task_id':identity['task_id'],
                        'department':sender, 'candidate_version':identity['candidate_version']}.items()) and (
                            box.get('qa_verdict') == 'pass'
                            and box.get('goal_acceptance', {}).get('responsible_assistant') == assistant
                            and binding.get('pin') in box.get('evidence', [])):
                    summaries.append(pin)
            accepted_exact = (not invalid and latest.get('verdict') == 'pass' and len(summaries) == 1
                              and binding.get('reviewer_department') == assistant)
            return {'lane': 'HQ_knowledge', 'target_department': 'operations',
                    'acceptance_proven': accepted_exact, 'HQ_second_review_required': False,
                    'reason': 'accepted_exact_assistant_summary' if accepted_exact
                              else 'assistant_summary_exact_acceptance_not_proven'}
        if sender in goal.get('producer_departments', []):
            return {'lane': 'professional_acceptance', 'target_department': assistant,
                    'acceptance_proven': False, 'HQ_second_review_required': False}
        return {'lane': 'legacy_unmapped', 'target_department': None,
                'reason': 'sender_not_bound_to_current_goal'}
    rows = _w()._result_handoff_rows(root, identity['task_id'])
    queued = [r for r in rows if _w()._result_identity(r) == tuple(identity[k] for k in IDENTITY_FIELDS[1:])
              and r.get('event') == 'notification_queued']
    if not queued and isinstance(source, dict):
        # The native admission caller has already verified these source pins;
        # this preview classifies routing and never grants claim/admission.
        queued = [source]
    routes = _w().read_json(Path(root) / 'data/task-contract.json').get('result_handoff_contract', {}).get('scheduled_daily_sources', [])
    matches = [route for route in routes if isinstance(route, dict)
               and route.get('department') == sender
               and re.fullmatch(route.get('task_id_pattern', '(?!)'), identity['task_id'])
               and len(queued) == 1 and queued[0].get('source_mode') == 'scheduled_run'
               and queued[0].get('source_automation_id') == route.get('automation_id')
               and queued[0].get('source_thread_id') == _w().department_registry(root).get(sender, {}).get('chat_binding', {}).get('task_id')]
    if len(matches) == 1 and matches[0].get('responsible_assistant') in coordinator_roles(root):
        return {'lane': 'professional_acceptance', 'target_department': matches[0]['responsible_assistant'],
                'source_mode': 'scheduled_run', 'HQ_second_review_required': False}
    return {'lane': 'legacy_unmapped', 'target_department': None,
            'reason': 'original_evidence_mapping_required_no_redispatch'}


def _notification_path(root, identity):
    return _w().safe_path(root, 'logs/result-notifications/' + _key(identity) + '.json')


def notification_enqueue(root, identity, *, _coordination_locked=False):
    """Durable delivery intent, never a native send receipt or a new reviewer."""
    identity = exact_identity(identity)
    with (nullcontext() if _coordination_locked else coordination_lock(root)):
        source = _validate_queued(root, identity)
        if source.get('source_mode') == 'collaboration':
            _fail('formal collaboration return does not create an ordinary notification queue')
        route = result_lane(root, identity)
        path = _notification_path(root, identity)
        old = _w().read_json(path)
        if old:
            if old.get('identity') != identity or old.get('route') != route:
                _fail('frozen notification identity/routing changed; exact reconciliation required')
            return old
        payload = {'schema_version': '1.0', 'identity': identity, 'route': route,
                   'dedupe_key': _key(identity), 'state': 'queued', 'delivered': False,
                   'recovery_owner': route.get('target_department'),
                   'defer_reason': 'fresh_actual_target_idle_or_completion_event_required',
                   'recovery_condition': 'read native fixed target status; send exact prepared notification once when idle',
                   'native_wakeup_guaranteed': False, 'queued_at': _w().utc_timestamp(),
                   'attempts': []}
        _w().atomic_write_json(path, payload)
        return payload


def notification_plan(root, role=None):
    records = [_w().read_json(path) for path in (Path(root) / 'logs/result-notifications').glob('*.json')]
    pending = [r for r in records if not r.get('delivered') and
               (role is None or r.get('route', {}).get('target_department') == role)]
    received = []
    for record in list(pending):
        identity = record['identity']
        if any(row.get('event') == 'controller_received'
               and _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])
               for row in _w()._result_handoff_rows(root, identity['task_id'])):
            pending.remove(record)
            received.append({'identity': identity, 'resolution': 'actual_queue_intake_already_recorded',
                             'native_notification_sent': record.get('delivered', False)})
    return {'notifications': pending, 'pending_count': len(pending),
            'resolved_by_actual_intake': received,
            'native_entry': 'mcp__codex_app__list_threads then notification_claim; execute returned send only if ready',
            'ended_chat_recovery_owner': role or 'operations',
            'native_wakeup_guaranteed': False, 'queue_is_delivery': False,
            'no_new_polling_or_automation': True}


def notification_claim(root, identity, role, owner, request_id, live_identity, payload, *, recovery_reason=''):
    """Existing exact-result lease fences preparation; Python never calls native tools."""
    identity = exact_identity(identity)
    if any(row.get('event') == 'controller_received'
           and _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])
           for row in _w()._result_handoff_rows(root, identity['task_id'])):
        _fail('actual result already received; do not send an old notification')
    queued = notification_enqueue(root, identity)
    if queued.get('delivered'):
        return {'result': 'duplicate_ignored', 'delivered': True, 'native_transport': queued['native_transport']}
    route = result_lane(root, identity)
    if route.get('target_department') != role or route['lane'] == 'legacy_unmapped':
        _fail('exact current notification receiver required; legacy mapping is not a send')
    if route['lane'] == 'HQ_knowledge' and not route.get('acceptance_proven'):
        _fail('assistant summary exact acceptance required before HQ knowledge delivery')
    w = _w()
    if (not isinstance(live_identity, dict) or w.file_digest(root, live_identity.get('path', '')) != live_identity
            or not isinstance(payload, dict) or w.file_digest(root, payload.get('path', '')) != payload):
        _fail('frozen native live identity and exact message bytes required')
    live = w.read_json(w.safe_path(root, live_identity['path']))
    observed = w._parse_observed_at(live.get('observed_at'))
    native_pin = live.get('actual_native_observation')
    from goal_delivery_runtime import _collaboration_native
    if not isinstance(native_pin, dict) or w.file_digest(root, native_pin.get('path', '')) != native_pin:
        _fail('original actual native observation pin required')
    native = _collaboration_native(root, native_pin)
    binding = w.department_registry(root).get(role, {}).get('chat_binding', {})
    threads = [*native.get('threads', []), *native.get('pinnedThreads', [])]
    target = [r for r in threads if r.get('id') == binding.get('task_id')]
    if (observed is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300
            or len(target) != 1 or any(target[0].get(k) != binding.get(v) for k,v in
                 {'projectId':'project_id','title':'title','cwd':'cwd'}.items())):
        _fail('fresh exact actual native fixed target identity required')
    with coordination_lock(root):
        current = w.read_json(_notification_path(root, identity))
        # Delivery effects outrank target availability. A busy observation cannot
        # erase an in-flight call and make its unknown effect retryable later.
        rows = [row for row in w._result_handoff_rows(root, identity['task_id'])
                if w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if any(row.get('event') == 'controller_received' for row in rows):
            _fail('actual result already received; do not send an old notification')
        if current.get('delivered'):
            return {'result': 'duplicate_ignored', 'delivered': True,
                    'native_transport': current['native_transport']}
        if current.get('state') == 'sent' or any(row.get('event') == 'notification_sent' for row in rows):
            _fail('native notification already sent; recover its actual receipt before retry')
        if current.get('state') == 'sending':
            if target[0].get('status') != 'idle':
                current.update(live_identity=live_identity,
                    waiting_for_target_idle=True,
                    recovery_condition='read actual send receipt first; unknown is never permission to resend')
                w.atomic_write_json(_notification_path(root, identity), current)
            _fail('native send effect uncertain; recover actual receipt before retry')
        if current.get('state') == 'failed' or current.get('effect_observation') == 'absent':
            _validate_absent_notification_failure(root, current, current.get('actual_native_failure'))
        if current.get('payload') and current['payload'] != payload:
            _fail('prepared notification exact message cannot be replaced')
        if target[0].get('status') != 'idle':
            current.update(state='deferred', defer_reason='actual_target_busy', live_identity=live_identity,
                           recovery_condition='actual fixed target completed/idle; re-read fresh native state then claim once')
            w.atomic_write_json(_notification_path(root, identity), current)
            return {'result': 'deferred', 'delivered': False, 'interrupts_active_thread': False,
                    'recovery_owner': role, 'target_thread_id': binding.get('task_id')}
    store = CoordinationStore(root)
    try:
        claim = store.claim(identity, role, owner, request_id, recovery_reason=recovery_reason)
    finally:
        store.close()
    with coordination_lock(root):
        current = w.read_json(_notification_path(root, identity))
        if any(row.get('event') == 'controller_received'
               and w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])
               for row in w._result_handoff_rows(root, identity['task_id'])):
            _fail('actual result already received; do not send an old notification')
        if current.get('delivered'):
            return {'result': 'duplicate_ignored', 'delivered': True, 'native_transport': current['native_transport']}
        if current.get('state') == 'sending':
            _fail('native send effect uncertain; recover actual receipt before retry')
        if current.get('state') == 'prepared' and current.get('payload') != payload:
            _fail('prepared notification exact message cannot be replaced')
        current.update(state='prepared', live_identity=live_identity, payload=payload,
                       claim=claim, coordinator_owner=owner, target_thread_id=binding['task_id'], defer_reason='',
                       waiting_for_target_idle=False)
        w.atomic_write_json(_notification_path(root, identity), current)
    source = w.department_registry(root).get(identity['sender_department'], {}).get('chat_binding', {})
    return {'result': 'ready', 'identity': identity, 'claim': claim, 'payload': payload,
            'tool': 'mcp__codex_app__send_message_to_thread', 'threadId': binding['task_id'],
            'action_id': 'notify-result-' + _key(identity), 'action_class': 'thread_message',
            'scope': 'department_result:' + identity['task_id'] + ':' + identity['sender_department'],
            'department': identity['sender_department'], 'task_id': identity['task_id'],
            'source_project_id': source.get('project_id'), 'target_department': role,
            'target_project_id': binding.get('project_id'), 'target_thread_id': binding.get('task_id'),
            'target_thread_title': binding.get('title'), 'target_cwd': binding.get('cwd'),
            'target_sidebar_section_id': binding.get('sidebar_section_id'),
            'payload_sha256': payload['sha256'],
            'delivered': False, 'requires_existing_exact_message_policy': True}


def _notification_attempts(current) -> list[NotificationAttempt]:
    """Read the append-only local reservation chain without repairing old data."""
    attempts = current.get('attempts', [])
    if not isinstance(attempts, list):
        _fail('exact internal notification attempt history required')
    previous = ''
    for sequence, attempt in enumerate(attempts, 1):
        if (not isinstance(attempt, dict) or set(attempt) != set(NotificationAttempt.__annotations__)
                or type(attempt.get('sequence')) is not int or attempt['sequence'] != sequence
                or attempt.get('previous_attempt_id') != previous
                or attempt.get('identity') != current.get('identity')
                or attempt.get('tool') != 'mcp__codex_app__send_message_to_thread'
                or attempt.get('target_thread_id') != current.get('target_thread_id')
                or attempt.get('payload') != current.get('payload')
                or _w()._parse_observed_at(attempt.get('call_started_at')) is None):
            _fail('exact internal notification attempt history required; no historical backfill')
        lease = attempt.get('claim')
        if (not isinstance(lease, dict)
                or set(lease) != {'result_key', 'role', 'owner', 'token', 'fence', 'expires'}
                or lease.get('result_key') != _key(current['identity'])
                or type(lease.get('fence')) is not int or lease['fence'] < 1
                or any(not isinstance(lease.get(key), str) or not lease[key]
                       for key in ('role', 'owner', 'token'))):
            _fail('exact original notification attempt lease snapshot required')
        unsigned = {key: value for key, value in attempt.items() if key != 'attempt_id'}
        if attempt.get('attempt_id') != _sha(unsigned):
            _fail('internal notification attempt event changed')
        previous = attempt['attempt_id']
    if current.get('active_attempt_id', '') != previous:
        _fail('exact current internal notification attempt required')
    return attempts


def notification_send_started(root, identity, claim):
    """Reserve before the native call, so interruption never silently re-sends."""
    identity = exact_identity(identity)
    with coordination_lock(root):
        current = _w().read_json(_notification_path(root, identity))
        rows = [row for row in _w()._result_handoff_rows(root, identity['task_id'])
                if _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if any(row.get('event') == 'controller_received' for row in rows):
            _fail('actual result already received; do not send an old notification')
        if (current.get('delivered')
                or any(row.get('event') == 'notification_sent' for row in rows)):
            _fail('native notification already sent; recover its actual receipt before retry')
        if (current.get('state') != 'prepared' or not isinstance(claim, dict)
                or any(current.get('claim', {}).get(key) != claim.get(key)
                       for key in ('result_key', 'role', 'owner', 'token', 'fence'))):
            _fail('exact prepared existing lease required before native send')
        if current.get('effect_observation') == 'absent' or current.get('actual_native_failure'):
            _validate_absent_notification_failure(root, current, current.get('actual_native_failure'))
        store = CoordinationStore(root)
        try:
            lease = store._lease(identity, current['route']['target_department'], current['coordinator_owner'], claim)
        finally:
            store.close()
        payload = current.get('payload')
        if (not isinstance(payload, dict)
                or _w().file_digest(root, payload.get('path', '')) != payload):
            _fail('frozen exact notification payload required before native call reservation')
        attempts = _notification_attempts(current)
        if attempts or 'call_started_at' in current:
            _fail('native send effect uncertain; original started call requires actual effect readback, no attempt backfill')
        started_at = _w().utc_timestamp()
        attempt: NotificationAttempt = {
            'sequence': len(attempts) + 1,
            'previous_attempt_id': attempts[-1]['attempt_id'] if attempts else '',
            'identity': identity,
            'tool': 'mcp__codex_app__send_message_to_thread',
            'target_thread_id': current['target_thread_id'],
            'payload': dict(payload),
            'claim': {key: lease[key]
                      for key in ('result_key', 'role', 'owner', 'token', 'fence', 'expires')},
            'call_started_at': started_at,
            'attempt_id': '',
        }
        attempt['attempt_id'] = _sha({key: value for key, value in attempt.items() if key != 'attempt_id'})
        current.update(state='sending', call_started_at=started_at,
                       active_attempt_id=attempt['attempt_id'], attempts=[*attempts, attempt],
                       effect_observation='unknown')
        _w().atomic_write_json(_notification_path(root, identity), current)
        return current


def notification_record(root, identity, request, *, _coordination_locked=False):
    """Commit only an original pinned successful native send plus exact policy."""
    identity = exact_identity(identity)
    with (nullcontext() if _coordination_locked else coordination_lock(root)):
        w = _w(); current = w.read_json(_notification_path(root, identity))
        native_pin = request.get('actual_native_transport')
        if not isinstance(native_pin, dict) or w.file_digest(root, native_pin.get('path', '')) != native_pin:
            _fail('original actual native send pin required; no missing-pin fallback')
        from goal_delivery_runtime import _collaboration_native
        native = _collaboration_native(root, native_pin)
        sent = native.get('actual_native_send', native)
        if (sent.get('threadId') != current.get('target_thread_id') or sent.get('isError') is True
                or ('status' in sent and sent['status'] not in {'sent', 'queued', 'running'})):
            _fail('successful exact native send target receipt required')
        rows = [row for row in w._result_handoff_rows(root, identity['task_id'])
                if w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if any(row.get('event') == 'controller_received' for row in rows):
            _fail('actual result already received; do not commit a late old notification')
        prior_sent = [row for row in rows if row.get('event') == 'notification_sent']
        if prior_sent and (len(prior_sent) != 1 or prior_sent[0].get('actual_native_transport') != native_pin):
            _fail('existing notification send cannot replace its exact original transport')
        if current.get('delivered'):
            if current.get('native_transport') != native_pin:
                _fail('already delivered notification cannot replace actual transport')
            return current
        if current.get('state') not in {'prepared', 'sending'}:
            _fail('exact prepared original notification required')
        message_ref = request.get('message_ref')
        if (not isinstance(message_ref, str) or not message_ref
                or w.safe_path(root, message_ref.split('#', 1)[0]) != w.safe_path(root, native_pin['path'])):
            _fail('native send reference must point to its original frozen transport file')
        store = CoordinationStore(root)
        try:
            claim = request.get('coordination_claim', current.get('claim'))
            store._lease(identity, current['route']['target_department'], current['coordinator_owner'], claim)
        finally:
            store.close()
        payload = current.get('payload', {})
        if w.file_digest(root, payload.get('path', '')) != payload or request.get('message_sha256') != payload.get('sha256'):
            _fail('frozen exact notification message bytes required')
        decisions = [r for r in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                     if r.get('decision_id') == request.get('policy_decision_id')]
        if len(decisions) != 1 or any(decisions[0].get(k) != v for k,v in
                {'status':'allow','routing_status':'routing_allowed','task_id':identity['task_id'],
                 'department':identity['sender_department'], 'action_id':'notify-result-' + _key(identity),
                 'scope':'department_result:' + identity['task_id'] + ':' + identity['sender_department'],
                 'action_class':'thread_message','target_department':current['route']['target_department'],
                 'target_thread_id':current['target_thread_id'],'payload_sha256':payload['sha256']}.items()):
            _fail('exact existing permitted native notification policy required')
        current.update(state='sent', delivered=True, native_transport=native_pin, claim=claim,
                       native_receipt_ref=request.get('message_ref'), policy_decision_id=request['policy_decision_id'],
                       sent_at=w.utc_timestamp(), queue_is_delivery=False)
        w.atomic_write_json(_notification_path(root, identity), current)
        return current


def _validate_absent_notification_failure(root, current, actual_native_failure):
    """No observed native failure format currently proves call-specific absence.

    A digest pins bytes, and the internal reservation identifies a local start.
    Neither authenticates a provider event or proves that dispatch had no effect.
    Do not infer absence from isError, timing, copied files, or caller labels.
    """
    if (not isinstance(actual_native_failure, dict)
            or _w().file_digest(root, actual_native_failure.get('path', '')) != actual_native_failure):
        _fail('original exact native failure pin required to prove send absent')
    attempts = _notification_attempts(current)
    if not attempts:
        _fail('current call has no original internal attempt; native absence contract missing, no backfill')
    _fail('verified call-specific native no-effect contract missing; errors or attempt labels cannot prove absent')


def notification_failed(root, identity, reason, effect='unknown', actual_native_failure=None):
    identity = exact_identity(identity)
    if not isinstance(reason, str) or not reason.strip() or effect not in {'absent', 'unknown'}:
        _fail('actual failure reason and explicit effect required')
    with coordination_lock(root):
        current = _w().read_json(_notification_path(root, identity))
        rows = [row for row in _w()._result_handoff_rows(root, identity['task_id'])
                if _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if (current.get('delivered') or current.get('state') == 'sent'
                or any(row.get('event') in {'notification_sent', 'controller_received'} for row in rows)):
            _fail('delivered effect cannot become failed')
        if effect == 'absent':
            _validate_absent_notification_failure(root, current, actual_native_failure)
            current['actual_native_failure'] = actual_native_failure
        current.update(state='failed' if effect == 'absent' else 'sending', defer_reason=reason,
                       effect_observation=effect, recovery_condition='read actual send receipt first; unknown is never permission to resend')
        _w().atomic_write_json(_notification_path(root, identity), current)
        return current


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("claim", "readback", "renew", "release", "transfer", "recover", "precheck", "recover-reservation", 'notification-enqueue', 'notification-plan', 'notification-claim', 'notification-call-start', 'notification-record', 'notification-failed'))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    request = json.loads(args.input.read_text(encoding="utf-8"))
    if args.command.startswith('notification-'):
        functions = {'notification-enqueue': notification_enqueue, 'notification-plan': notification_plan,
                     'notification-claim': notification_claim, 'notification-call-start': notification_send_started,
                     'notification-record': notification_record, 'notification-failed': notification_failed}
        result = functions[args.command](args.root, **request)
    elif args.command == "recover-reservation":
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
