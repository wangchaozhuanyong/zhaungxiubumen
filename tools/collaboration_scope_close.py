"""Reuse an exact independent release acceptance from an actual fenced intake.

Read-only validation; this does not confer permissions, repeat a push, update a
workflow snapshot, or close its parent. Actor metadata alone is not authority.
The caller retains its existing coordination lease and workflow append lock.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

SOURCE_PINS = ("collaboration", "native_transport", "result_receipt", "result", "visible_reply", "native_result")
PROOF_MODE = "prior_fenced_intake_exact_acceptance"
VERDICT = "PASS_ACTUAL_PUSH_AND_PUBLIC_RELEASE_SCOPE"


def _w():
    import workflow_control
    return workflow_control


def _fail(message):
    raise _w().WorkflowError(message)


def _pin(root, pin):
    if not isinstance(pin, dict) or _w().file_digest(root, pin.get("path", "")) != pin:
        _fail("collaboration scope closure requires unchanged exact frozen proof pins")
    document = _w().read_json(_w().safe_path(root, pin["path"]))
    if not isinstance(document, dict):
        _fail("collaboration scope proof must be a structured frozen object")
    return document


def _time(value):
    parsed = _w()._parse_observed_at(value)
    if parsed is None or parsed > dt.datetime.now(dt.timezone.utc):
        _fail("actual timezone-aware nonfuture collaboration proof time required")
    return parsed


def _committed_prior_intake(root, identity, intake, acceptance):
    """Check committed effect/native readback and its original role/owner/fence.

    Never instantiate CoordinationStore here: even its constructor writes.
    The existing global audit hash chain is read for structural integrity only;
    only this exact result's claim/reservation/commit is interpreted or returned.
    Lease tokens are neither selected nor copied to any output.
    """
    import result_coordination as c
    path = _w().safe_path(root, str(c.DATABASE))
    if not path.is_file():
        _fail("prior fenced intake coordination database missing")
    effect = c._sha(["controller_received", intake.get("idempotency_key")])
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            reservation = conn.execute(
                "SELECT status,payload_json,native_record_json FROM reservations WHERE result_key=? AND effect_key=?",
                (c._key(identity), effect)).fetchone()
            if reservation is None or reservation["status"] != "committed":
                _fail("exact prior intake effect has no committed native readback")
            native = json.loads(reservation["native_record_json"])
            if native != intake:
                _fail("prior intake native ledger differs from committed coordination readback")
            payload = json.loads(reservation["payload_json"])
            request, pins = payload["request"], payload["pins"]
            if (any(request.get(k) != v for k, v in identity.items())
                    or request.get("event") != "controller_received"
                    or request.get("idempotency_key") != intake.get("idempotency_key")
                    or any(request.get(key) != intake.get(key) for key in (
                        "action_id", "scope", "collaboration_source", "source_mode", "intake_mode",
                        "source_reply_sha256", "source_thread_id", "reply_observed_at"))
                    or request.get("outbox_path") != intake.get("outbox", {}).get("path")
                    or pins.get("outbox") != intake.get("outbox")
                    or pins.get("evidence") != intake.get("evidence")
                    or acceptance not in pins.get("evidence", [])):
                _fail("reserved prior intake must freeze the exact independent acceptance and original source")
            previous, selected = "", []
            for row in conn.execute("SELECT seq,payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq"):
                value = json.loads(row["payload_json"])
                if row["previous_hash"] != previous or row["record_hash"] != c._sha([previous, value]):
                    _fail("prior fenced intake coordination audit integrity failed")
                previous = row["record_hash"]
                if value.get("identity") == identity:
                    selected.append({**value, "seq": row["seq"]})
    except (sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        _fail("prior fenced intake coordination proof unreadable: " + type(exc).__name__)
    commits = [x for x in selected if x.get("event") == "effect_readback_committed"
               and x.get("details", {}).get("effect_key") == effect
               and x["details"].get("native_record_id") == intake["record_id"]]
    if not commits:
        _fail("prior fenced intake lacks the exact effect commit audit")
    commit = commits[0]
    reserved = [x for x in selected if x.get("event") == "effect_reserved"
                and x.get("details", {}).get("effect_key") == effect and x["seq"] < commit["seq"]]
    if len(reserved) != 1:
        _fail("one original exact intake reservation audit required")
    reservation = reserved[0]
    claims = [x for x in selected if x.get("event") in {"claim", "recover_expired"}
              and x["seq"] < reservation["seq"]]
    if not claims:
        _fail("original intake claim audit missing")
    claim = claims[-1]
    expected = {"role": intake.get("coordinator_role"), "owner": intake.get("coordinator_owner")}
    if (any(claim.get("details", {}).get(k) != v or reservation.get("details", {}).get(k) != v
            for k, v in expected.items())
            or type(intake.get("coordination_fence")) is not int or intake["coordination_fence"] < 1
            or claim["details"].get("fence") != intake["coordination_fence"]
            or not expected["owner"]
            or not (claim["at"] <= reservation["at"] <= commit["at"] <= dt.datetime.now(dt.timezone.utc).timestamp())
            or any(x.get("event") in {"release", "claim", "recover_expired"}
                   and claim["seq"] < x["seq"] < commit["seq"] for x in selected)
            or _time(intake.get("created_at")).timestamp() > commit["at"]
            or _time(intake.get("reply_observed_at")).timestamp() > commit["at"]):
        _fail("prior committed intake must match the original assigned actor, active fence and actual timing")
    return {"effect_key": effect, "claim_seq": claim["seq"], "reservation_seq": reservation["seq"],
            "commit_seq": commit["seq"], "coordination_fence": intake["coordination_fence"]}


def verify_collaboration_scope_close(root, request, source, evidence, prior_rows=None):
    """Return bounded close metadata, never derive acceptance from delivery."""
    root = Path(root).resolve()
    w = _w()
    import result_coordination as c
    identity = c.exact_identity(request)
    if (request.get("event") != "controller_decision" or request.get("decision") != "close_scope"
            or request.get("collaboration_acceptance_mode") != PROOF_MODE
            or source.get("source_mode") != "collaboration"
            or source.get("status") != "completed"
            or source.get("task_id") != identity["task_id"]
            or source.get("department") != identity["sender_department"]
            or source.get("candidate_version") != identity["candidate_version"]
            or source.get("result", {}).get("sha256") != identity["result_sha256"]):
        _fail("exact original collaboration result and prior independent acceptance mode required")
    goal = c._goal_actor(root, identity, source["responsible_assistant"])
    role = source["responsible_assistant"]
    scope, state = source["scope"], source["state"]
    if (not goal or goal.get("acceptance_capability") != "release_result"
            or role not in c.coordinator_roles(root, task_id=identity["task_id"])
            or goal.get("responsible_assistant") != role
            or request.get("coordinator_role") != role or request.get("next_owner") != role
            or request.get("acceptance_scope") != scope or request.get("scope") != scope
            or request.get("action_id") != state["action_id"] or scope not in goal["authorized_scope"]
            or not isinstance(request.get("next_action"), str) or not request["next_action"].strip()
            or role == identity["sender_department"] or role in goal["producer_departments"]
            or request.get("qa_status") != "pass"
            or request.get("execution_status") != "EXECUTION_VERIFIED"
            or request.get("public_postcheck_status") != "pass"
            or request.get("business_goal_closed", False) is not False
            or request.get("external_permission_issued", False) is not False):
        _fail("only assigned independent release_result reviewer may close the exact authorized source scope")
    if w.validate_workflow_events(root, identity["task_id"]) or w._validate_receipt_chain(root, identity["task_id"])[1]:
        _fail("collaboration scope closure requires intact original workflow and receipt chains")
    required = [state[k] for k in SOURCE_PINS]
    for pin in required:
        if pin not in evidence or w.file_digest(root, pin["path"]) != pin:
            _fail("scope closure must preserve all original actual sent and result pins")
    acceptance_pin = request.get("collaboration_acceptance")
    accepted = _pin(root, acceptance_pin)
    if acceptance_pin not in evidence:
        _fail("independent acceptance must be included in exact close evidence")
    if (any(accepted.get(k) != v for k, v in {
            "task_id": identity["task_id"], "candidate_version": identity["candidate_version"],
            "reviewer": role, "capability": "release_result", "sole_final_reviewer": True,
            "verdict": VERDICT, "scope_accepted": True, "actual_normal_push": True,
            "remote_blobs_sha256_and_bytes_match": True, "source_mapping_and_version_preserved": True,
            "actual_new_push": 0, "actual_new_deployment": 0, "parent_goal_closed": False}.items())
            or not isinstance(accepted.get("scope_closure"), str) or not accepted["scope_closure"].strip()
            or accepted.get("acceptance_scope", scope) != scope):
        _fail("independent acceptance must retain exact reviewer, capability, version and finite scope verdict")
    acceptance_evidence = accepted.get("evidence")
    if not isinstance(acceptance_evidence, list) or not acceptance_evidence or source["result"] not in acceptance_evidence:
        _fail("independent acceptance must bind the original result bytes")
    for pin in acceptance_evidence:
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            _fail("original independent acceptance evidence changed")
    rows = w._result_handoff_rows(root, identity["task_id"]) if prior_rows is None else prior_rows
    intakes = [row for row in rows if row.get("event") == "controller_received"
               and row.get("record_id") == request.get("acceptance_intake_record_id")
               and all(row.get(k) == v for k, v in identity.items())]
    if len(intakes) != 1:
        _fail("one exact original independent assistant formal intake required")
    intake = intakes[0]
    if (any(intake.get(k) != v for k, v in {
            "source_mode": "collaboration", "scope": scope, "action_id": state["action_id"],
            "coordinator_role": role, "decision_actor": role, "responsible_assistant": role,
            "collaboration_source": state["result_receipt"], "outbox": source["result"],
            "source_thread_id": source["fixed_chat_task_id"], "source_reply_sha256": state["visible_reply"]["sha256"],
            "intake_mode": "collaboration", "business_goal_closed": False, "external_permission_issued": False}.items())
            or acceptance_pin not in intake.get("evidence", [])
            or any(pin not in intake.get("evidence", []) for pin in required)
            or _time(accepted.get("observed_at")) > _time(intake.get("reply_observed_at"))):
        _fail("original assigned assistant intake must already freeze this exact acceptance before close")
    audit = _committed_prior_intake(root, identity, intake, acceptance_pin)
    outcome_pin, remote_pin, manifest_pin = (request.get(k) for k in
        ("collaboration_release_outcome", "collaboration_remote_readback", "collaboration_public_manifest"))
    if any(pin not in acceptance_evidence or pin not in evidence for pin in (outcome_pin, remote_pin, manifest_pin)):
        _fail("scope close outcome must be the exact source outcome already independently accepted")
    outcome, remote, manifest = (_pin(root, pin) for pin in (outcome_pin, remote_pin, manifest_pin))
    sha = accepted.get("actual_main_sha")
    if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or any(outcome.get(k) != v for k, v in {
                "task_id": identity["task_id"], "candidate_version": identity["candidate_version"], "scope": scope,
                "parent_task_id": goal.get("parent_task_id"), "fixed_chat_task_id": source["fixed_chat_task_id"],
                "status": "completed", "status_scope": "actual_normal_source_push_and_remote_exact_readback",
                "normal_push": True, "force_push": False, "branch": "main", "remoteSHA": sha,
                "localSHA": sha, "trackingSHA": sha, "remote_exact244_bytes": "PASS",
                "business_parent_closed": False, "website_deployment_performed": False,
                "CMS_Ads_Maps_writes": False, "automations_modified": False}.items())
            or remote.get("status") != "PASS_REMOTE_MAIN_SAME_SHA_AND_EXACT_PUBLIC_TREE"
            or any(remote.get(k) != sha for k in ("remote_SHA", "local_SHA", "tracking_SHA"))
            or _time(outcome.get("observed_at")) > _time(accepted.get("observed_at"))
            or _time(remote.get("observed_at")) > _time(accepted.get("observed_at"))):
        _fail("accepted exact original normal push and same-SHA remote outcome required")
    ls = remote.get("remote_ls_command", {})
    if (ls.get("returncode") != 0 or ls.get("argv") != ["git", "ls-remote", "origin", "refs/heads/main"]
            or ls.get("stdout", "").strip() != sha + "\trefs/heads/main"):
        _fail("actual successful remote main SHA readback required")
    files, readback = manifest.get("files"), remote.get("remote_file_readback")
    if (not isinstance(files, list) or not files or not isinstance(readback, list)
            or any(not isinstance(x, dict) or not isinstance(x.get("path"), str)
                   or not re.fullmatch(r"[0-9a-f]{64}", str(x.get("release_sha256", "")))
                   or type(x.get("bytes")) is not int or x["bytes"] < 0 for x in files)
            or any(not isinstance(x, dict) or not isinstance(x.get("path"), str) for x in readback)):
        _fail("accepted public payload and actual remote file readback required")
    expected = [{"path": x["path"], "sha256": x["release_sha256"], "bytes": x["bytes"]} for x in files]
    expected.append({"path": "release-manifest.json", "sha256": manifest_pin["sha256"], "bytes": manifest_pin["size"]})
    if (len({x["path"] for x in expected}) != len(expected)
            or len(readback) != len(expected) or len({x.get("path") for x in readback}) != len(readback)
            or sorted(readback, key=lambda x: x["path"]) != sorted(expected, key=lambda x: x["path"])
            or accepted.get("remote_file_count") != len(readback) or remote.get("file_count") != len(readback)
            or outcome.get("remote_tracked_count_with_manifest") != len(readback)
            or accepted.get("payload_file_count") != len(files) or outcome.get("public_payload_count") != len(files)
            or outcome.get("public_manifest_fingerprint") != manifest.get("fingerprint")
            or remote.get("manifest_fingerprint") != manifest.get("fingerprint")
            or remote.get("release_version") != manifest.get("version")
            or not isinstance(accepted.get("current_public_fingerprint"), str)
            or len(accepted["current_public_fingerprint"]) < 8
            or not manifest.get("fingerprint", "").startswith(accepted["current_public_fingerprint"])):
        _fail("accepted public manifest and all actual remote blob SHA/bytes must exactly correspond")
    return {"acceptance_scope": scope, "qa_status": "pass", "execution_status": "EXECUTION_VERIFIED",
            "public_postcheck_status": "pass", "independent_acceptance_verdict": VERDICT,
            "collaboration_acceptance_mode": PROOF_MODE, "collaboration_acceptance": acceptance_pin,
            "acceptance_intake_record_id": intake["record_id"], "acceptance_intake_audit": audit,
            "collaboration_release_outcome": outcome_pin, "collaboration_remote_readback": remote_pin,
            "collaboration_public_manifest": manifest_pin, "accepted_actual_main_sha": sha,
            "closed_collaboration_scope": scope, "parent_goal_closed": False,
            "business_goal_closed": False, "external_permission_issued": False}


def readback_collaboration_scope_close(root, decision, prior_rows=None):
    """Pending may consume only stored, still-valid exact closure metadata."""
    from goal_delivery_runtime import collaboration_result_source
    source = collaboration_result_source(root, decision)
    metadata = verify_collaboration_scope_close(root, decision, source, decision.get("evidence", []), prior_rows)
    if any(decision.get(key) != value for key, value in metadata.items()):
        _fail("stored collaboration closure metadata differs from exact accepted scope proof")
    return metadata
