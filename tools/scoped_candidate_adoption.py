"""Read exact independently accepted/adopted source before the F4 native trial.

Candidate acceptance is not the final goal verdict. This reader performs no
adoption, tool call, lease change or write, and never creates permissions.
"""
from __future__ import annotations

import hashlib
import difflib
import json
import re
import sqlite3
from pathlib import Path, PurePosixPath

import workflow_control as w

TASK = "fc-20261010-system-flow-throughput-and-ledger-close-v1"
ROLE = "operations-assistant-2"
PRODUCER = "system-development"
SCOPE = "project:flashcast:system-flow-throughput-ledger-cleanup:v1"
VERSION = "system-flow-throughput-ledger-cleanup-v4"
PIN_FIELDS = ("candidate_review", "candidate_review_outbox", "candidate_manifest",
              "producer_outbox", "review_plan", "adoption_journal", "postapply", "rollback_preflight")


def _fail(message):
    raise w.WorkflowError("scoped candidate adoption: " + message)


def _pin(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, str(pin.get("path") or "")) != pin:
        _fail("exact frozen evidence bytes required")
    return pin


def _doc(root, pin):
    _pin(root, pin)
    value = w.read_json(w.safe_path(root, pin["path"]))
    if not isinstance(value, dict):
        _fail("object evidence required")
    if any(value.get(key) is True for key in ("fixture_only", "simulation", "simulated",
            "production_write_allowed", "production_permission_issued", "external_permission_issued")):
        _fail("actual internal evidence required; no simulated adoption or permissions")
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _receipts(root, task):
    # Check the original byte/hash chain without recursively revalidating a
    # later final verdict that itself consumes this pre-trial evidence.
    rows = []
    previous = ""
    try:
        for line in w.receipts_path(root, task).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (not isinstance(row, dict) or row.get("task_id") != task
                    or row.get("previous_hash") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                _fail("original receipt chain changed")
            previous = row["receipt_hash"]
            rows.append(row)
    except (OSError, ValueError, TypeError) as exc:
        _fail("strict original receipts required: " + str(exc))
    return rows


def _native_review(root, box, references):
    import goal_delivery_runtime as g
    document = g._collaboration_native(root, box.get("actual_native_reply"))
    binding = w.department_registry(root)[ROLE]["chat_binding"]
    thread = document.get("thread", {})
    if (thread.get("id") != binding["task_id"]
            or not w._same_resolved_path(str(thread.get("cwd") or ""), str(Path(root).resolve()))
            or box.get("fixed_chat_task_id") != binding["task_id"]
            or box.get("department") != ROLE or box.get("task_id") != TASK
            or box.get("candidate_version") != VERSION or box.get("status") != "partial"
            or box.get("chat_reply", {}).get("nonempty") is not True
            or box.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True
            or box.get("qa_verdict") == "pass" or box.get("goal_acceptance")):
        _fail("independent bounded A2 reply required; never full goal PASS")
    reply = _pin(root, box.get("visible_reply"))
    raw = w.safe_path(root, reply["path"]).read_bytes()
    matches = []
    turns = [turn for turn in document.get("turns", []) if turn.get("id") == box.get("source_turn_id")]
    if len(turns) != 1:
        _fail("one unambiguous original independent review turn required")
    for turn in turns:
        started = turn.get("startedAt")
        if (turn.get("status") not in {"completed", "inProgress"}
                or type(started) not in {int, float} or started < 0
                or started > w.dt.datetime.now(w.dt.timezone.utc).timestamp()):
            _fail("actual original native review turn and nonfuture time required")
        for item in turn.get("items", []):
            if (item.get("type") == "agentMessage" and item.get("id") == box.get("source_message_id")
                    and item.get("phase") in {"commentary", "final_answer"}
                    and isinstance(item.get("text"), str) and item["text"].strip()
                    and item["text"].encode("utf-8") == raw):
                matches.append(item)
    if len(matches) != 1 or box.get("source_reply_sha256") != reply["sha256"]:
        _fail("one actual original A2 turn/message and exact UTF-8 reply required")
    text = matches[0]["text"]
    def mentioned(value):
        choices = [value, str(w.safe_path(root, value))] if "/" in value else [value]
        return any(re.search(r"(?<![A-Za-z0-9_./:-])" + re.escape(choice)
                             + r"(?![A-Za-z0-9_./:-])", text) for choice in choices)
    if any(not mentioned(value) for value in references):
        _fail("native bounded acceptance must identify original task/version/source/manifest/review")
    observed = w._parse_observed_at(box.get("reply_observed_at"))
    if (observed is None or observed.timestamp() < started
            or observed > w.dt.datetime.now(w.dt.timezone.utc)):
        _fail("actual original independent reply observation time required")
    return observed


def _report(root, pin, journal, manifest_pin, stage):
    report = _doc(root, pin)
    if (report.get("task_id") != TASK or report.get("candidate_version") != VERSION
            or report.get("actor") != ROLE or report.get("execution_id") != journal["execution_id"]
            or report.get("candidate_manifest") != manifest_pin or report.get("exit_code") != 0
            or report.get("actual_execution") is not True or report.get("stage") != stage
            or report.get("external_writes") != 0):
        _fail("actual exact postapply/rollback rehearsal execution required")
    output = _pin(root, report.get("output"))
    started = w._parse_observed_at(report.get("started_at"))
    completed = w._parse_observed_at(report.get("completed_at"))
    adopted = w._parse_observed_at(journal.get("completed_at"))
    if (started is None or completed is None or adopted is None
            or not adopted <= started <= completed <= w.dt.datetime.now(w.dt.timezone.utc)):
        _fail("actual checks must follow completed exact source adoption")
    raw = w.safe_path(root, output["path"]).read_text(encoding="utf-8")
    if stage == "postapply":
        tests = report.get("tests", {})
        if (type(tests.get("run")) is not int or tests["run"] < 1
                or tests.get("errors") != 0 or tests.get("failures") != 0
                or not re.search(r"Ran\s+" + str(tests["run"]) + r"\s+tests?\b", raw)
                or not re.search(r"(?m)^OK\s*$", raw)):
            _fail("actual successful postapply test output required")
    elif (report.get("read_only") is not True or report.get("actual_rollback") is not False
            or report.get("source_paths") != [x["path"] for x in journal["source_operations"]]
            or report.get("field_operations") != journal.get("field_operations", [])
            or json.loads(raw) != {"source_paths": report["source_paths"],
                                  "field_operations": report["field_operations"], "result": "PASS"}):
        _fail("actual read-only reverse CAS/diff rehearsal output required")
    return report


def validate_adoption(root, parent, proof):
    """Consume bounded candidate QA + actual exact CAS, without final goal PASS."""
    import qa_review_plan as q
    import goal_delivery_runtime as g
    root = Path(root).resolve()
    goal = g.restore_goal(root, parent).get("goal_delivery", {})
    if (parent.get("task_id") != TASK or goal.get("primary_owner") != PRODUCER
            or goal.get("producer_departments") != [PRODUCER] or goal.get("responsible_assistant") != ROLE
            or goal.get("acceptance_capability") != "development" or goal.get("authorized_scope") != [SCOPE]
            or goal.get("required_execution_actions") or goal.get("source_mode") != "approved_dispatch"):
        _fail("exact original F4 owner/assistant/contract/scope required")
    if (not isinstance(proof, dict) or set(proof) != {"mode", *PIN_FIELDS}
            or proof.get("mode") != "scoped_candidate_actual_adoption"):
        _fail("bounded candidate acceptance/adoption proof required before first trial")
    documents = {key: _doc(root, proof[key]) for key in PIN_FIELDS}
    review, box, manifest, producer, plan, journal = [documents[key] for key in PIN_FIELDS[:6]]
    expected = {"task_id": TASK, "candidate_version": VERSION, "scope": SCOPE}
    if any(any(doc.get(key) != value for key, value in expected.items())
           for doc in (review, manifest, journal)):
        _fail("original exact task/version/scope must match every candidate/adoption stage")
    payload = {key: manifest.get(key) for key in ("task_id", "scope", "changes", "field_changes")}
    fingerprint = _hash(payload)
    if (manifest.get("candidate_fingerprint") != fingerprint or manifest.get("external_writes") is not False
            or manifest.get("primary_owner") != PRODUCER or manifest.get("responsible_assistant") != ROLE
            or any(doc.get("candidate_fingerprint") != fingerprint for doc in (review, journal))):
        _fail("exact independently reviewed manifest fingerprint required")
    expected_review = {"reviewer": ROLE, "producer_department": PRODUCER, "acceptance_capability": "development",
        "phase": "candidate_source_only", "verdict": "PASS_CANDIDATE_SCOPE_ONLY",
        "goal_completion_claimed": False, "final_goal_verdict": False, "pilot_complete": False,
        "candidate_manifest": proof["candidate_manifest"], "producer_outbox": proof["producer_outbox"],
        "review_plan": proof["review_plan"], "human_authorization": goal.get("authorization_pin"),
        "goal_contract": parent.get("goal_contract")}
    if any(review.get(key) != value for key, value in expected_review.items()):
        _fail("independent candidate-only acceptance cannot replace or preclaim full-goal PASS")
    evidence = review.get("independent_evidence", [])
    if not isinstance(evidence, list) or not evidence:
        _fail("actual independent candidate review evidence required")
    for pin in evidence:
        _pin(root, pin)
    _pin(root, parent.get("goal_contract")); _pin(root, goal.get("authorization_pin"))
    q.validate_plan(root, parent, plan)
    binding = parent.get("qa_review_plan", {})
    receipts = _receipts(root, TASK)
    source_receipts = [row for row in receipts if row.get("receipt_type") == "outbox_received"
                       and row.get("department") == PRODUCER and proof["producer_outbox"] in row.get("evidence", [])]
    if len(source_receipts) != 1:
        _fail("one actual exact original v3 producer outbox receipt required")
    if (binding.get("pin") != proof["review_plan"] or plan.get("candidate_version") != VERSION
            or plan.get("reviewer_department") != ROLE or plan.get("producer_department") != PRODUCER
            or plan.get("scope") != SCOPE or not plan.get("native_multi_goal_review")
            or q._assigned_review_round(root, parent, receipts, plan) is None
            or not q._producer_candidate_bound(root, plan, proof["producer_outbox"], producer)):
        _fail("actual original native responsibility and exact bound plan required")
    w.validate_outbox(root, [proof["producer_outbox"]], PRODUCER, TASK)
    w.validate_outbox(root, [proof["candidate_review_outbox"]], ROLE, TASK)
    if (proof["candidate_manifest"] not in list(q._evidence_pins(producer.get("evidence", [])))
            or proof["candidate_review"] not in list(q._evidence_pins(box.get("evidence", [])))
            or producer.get("candidate_version") != VERSION):
        _fail("original producer/reviewer outbox must freeze this manifest/acceptance")
    reviewed_at = _native_review(root, box, (TASK, VERSION, proof["producer_outbox"]["sha256"], fingerprint,
                              proof["candidate_review"]["path"], proof["candidate_review"]["sha256"]))
    producer_at = w._parse_observed_at(source_receipts[0].get("created_at"))
    if producer_at is None or producer_at > reviewed_at:
        _fail("actual original producer receipt must precede independent bounded acceptance")
    if (journal.get("actor") != ROLE or journal.get("state") != "adopted"
            or not re.fullmatch(r"[0-9a-f-]{36}", str(journal.get("execution_id") or ""))
            or journal.get("independent_review") != proof["candidate_review"]
            or journal.get("review_outbox") != proof["candidate_review_outbox"]
            or journal.get("authorized_source") != goal["authorization_pin"]
            or journal.get("external_writes") != 0 or journal.get("permissions_issued") is not False):
        _fail("actual independent A2 CAS journal and original human authority required")
    times = [w._parse_observed_at(journal.get(key)) for key in ("started_at", "completed_at")]
    if any(value is None for value in times) or not reviewed_at <= times[0] <= times[1] <= w.dt.datetime.now(w.dt.timezone.utc):
        _fail("actual adoption timestamps required")
    changes = manifest.get("changes", [])
    operations = journal.get("source_operations", [])
    paths = [entry.get("path") for entry in changes if isinstance(entry, dict)]
    if (not paths or len(paths) != len(changes) or len(set(paths)) != len(paths)
            or any(not isinstance(path, str) or not path.startswith(("tools/", "departments/"))
                   or "\\" in path or ".." in PurePosixPath(path).parts
                   or str(PurePosixPath(path)) != path
                   or str(w.safe_path(root, path).relative_to(root)) != path for path in paths)
            or [entry.get("path") for entry in operations] != paths):
        _fail("exact reviewed source CAS target set required")
    current = []
    for entry, operation in zip(changes, operations):
        candidate = _pin(root, entry.get("candidate")); _pin(root, entry.get("diff"))
        actual = w.file_digest(root, entry["path"])
        if (actual["sha256"] != candidate["sha256"] or actual["size"] != candidate["size"]
                or operation.get("after_sha256") != candidate["sha256"]):
            _fail("actual current source differs from reviewed adopted bytes")
        expected_source = entry.get("expected_source")
        before = b""
        if expected_source == "ABSENT":
            if operation.get("before_sha256") != "ABSENT" or operation.get("backup") is not None:
                _fail("new source must retain exact absent baseline")
        else:
            baseline = _pin(root, entry.get("baseline")); backup = _pin(root, operation.get("backup"))
            before = w.safe_path(root, baseline["path"]).read_bytes()
            if (expected_source != {"sha256": baseline["sha256"], "size": baseline["size"]}
                    or operation.get("before_sha256") != baseline["sha256"]
                    or (backup["sha256"], backup["size"]) != (baseline["sha256"], baseline["size"])):
                _fail("exact baseline CAS and recoverable original source backup required")
        expected_diff = "".join(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),
            w.safe_path(root, candidate["path"]).read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile="/dev/null" if expected_source == "ABSENT" else "a/" + entry["path"],
            tofile="b/" + entry["path"])).encode("utf-8")
        if w.safe_path(root, entry["diff"]["path"]).read_bytes() != expected_diff:
            _fail("exact reversible source diff must cover reviewed before/after bytes")
        current.append(actual)
    field_operations = []
    for migration_pin in manifest.get("field_changes", []):
        migration = _doc(root, migration_pin)
        if (migration.get("source_registry") != "data/department-registry.json"
                or migration.get("mode") != "field_CAS_only" or migration.get("preserve_all_other_fields") is not True):
            _fail("separate exact registry field CAS required")
        registry = w.department_registry(root)
        for change in migration.get("changes", []):
            if (change.get("department_id") != "operations-assistant-3"
                    or change.get("field") not in {"approved_subskills", "approved_subskill_paths", "coordination_authority"}
                    or _hash(change.get("expected")) != change.get("expected_sha256")
                    or registry.get(change["department_id"], {}).get(change["field"]) != change.get("replacement")):
                _fail("actual current exact reviewed field differs")
            field_operations.append({"department_id": change["department_id"], "field": change["field"],
                "before": change["expected"], "after": change["replacement"]})
    if journal.get("field_operations", []) != field_operations:
        _fail("adoption journal must cover every exact field CAS")
    if len({(entry["department_id"], entry["field"]) for entry in field_operations}) != len(field_operations):
        _fail("one unique operation per exact reviewed field required")
    if field_operations:
        before = _doc(root, journal.get("registry_before")); after = _doc(root, journal.get("registry_after"))
        expected_registry = json.loads(json.dumps(before))
        for operation in field_operations:
            found = [row for row in expected_registry.get("departments", []) if row.get("id") == operation["department_id"]]
            if len(found) != 1 or found[0].get(operation["field"]) != operation["before"]:
                _fail("original field baseline CAS backup required")
            found[0][operation["field"]] = operation["after"]
        if expected_registry != after:
            _fail("adoption changed fields outside exact reviewed field CAS")
    _report(root, proof["postapply"], journal, proof["candidate_manifest"], "postapply")
    _report(root, proof["rollback_preflight"], journal, proof["candidate_manifest"], "rollback_preflight")
    return {"control_qa": proof["candidate_review_outbox"], "control_applied_proof": proof["adoption_journal"],
        "control_candidate_version": VERSION, "adoption_stage": "scoped_candidate_actual_adoption",
        "required_evidence": [proof[name] for name in PIN_FIELDS], "applied_files": current,
        "final_goal_pass": False, "external_authority_granted": False, "business_goal_closed": False}


def _committed(root, record):
    import result_coordination as c
    database = w.safe_path(root, str(c.DATABASE))
    if not database.is_file():
        _fail("actual committed original coordination required")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT status,payload_json,native_record_json FROM reservations WHERE result_key=? AND effect_key=?",
            (c._key(c.exact_identity(record)), c._sha([record["event"], record["idempotency_key"]]))).fetchone()
    finally:
        connection.close()
    if (not row or row[0] != "committed" or json.loads(row[2] or "null") != record
            or c._native_readback(root, json.loads(row[1])) != record):
        _fail("exact original fenced committed native readback required")


def validate_final_goal_pass(root, parent, box):
    """F4 full PASS follows real native trial; candidate acceptance cannot close it."""
    completion = box.get("system_goal_completion", {})
    if not isinstance(completion, dict):
        _fail("actual native trial completion proof required for full-goal PASS")
    adoption = completion.get("scoped_adoption")
    validate_adoption(root, parent, adoption)
    rows = w._result_handoff_rows(root, TASK)
    matches = [row for row in rows if row.get("record_id") == completion.get("pilot_followthrough_record_id")
               and row.get("event") == "controller_followthrough"]
    if len(matches) != 1:
        _fail("actual subsequent read-only child followthrough required for full-goal PASS")
    follow = matches[0]
    decisions = [row for row in rows[:rows.index(follow)] if row.get("event") == "controller_decision"]
    decision = decisions[-1] if decisions else {}
    if (follow.get("coordinator_role") != ROLE or follow.get("followthrough_status") != "subsequent_action_verified"
            or follow.get("business_goal_closed") is not False
            or decision.get("initial_dispatch", {}).get("adoption") != adoption
            or follow.get("candidate_version") != VERSION):
        _fail("exact original adopted version/parent/assistant next-task trial required")
    import parent_initial_dispatch as initial
    action = {**decision["initial_dispatch"]["action"], "decision_record_id": decision["record_id"],
              "parent_initial_dispatch": decision["initial_dispatch"]}
    initial._fenced_decision(root, parent, action, "sent")
    initial._context(root, parent, decision["initial_dispatch"], "sent")
    _committed(root, follow)
    w._verify_inflight_followthrough(root, follow, decision)
    child = follow["linked_task_id"]
    child_box = _doc(root, follow["linked_outbox"])
    if child_box.get("status") != "completed" or child_box.get("parent_task_id") != TASK:
        _fail("actual completed original read-only child outbox required")
    child_rows = w._result_handoff_rows(root, child)
    queued = [row for row in child_rows if row.get("event") == "notification_queued"
              and row.get("outbox") == follow["linked_outbox"]]
    intakes = [row for row in child_rows if row.get("event") == "controller_received"
               and row.get("outbox") == follow["linked_outbox"] and row.get("coordinator_role") == ROLE]
    if len(queued) != 1 or len(intakes) != 1:
        _fail("real child native completion and unique original assistant intake required")
    fixed = w.department_registry(root)[PRODUCER]["chat_binding"]["task_id"]
    w._validate_goal_completed_result(root, queued[0], fixed)
    _committed(root, intakes[0])
    snapshot = w.read_json(w.snapshot_path(root, child))
    receipts, invalid = w._validate_receipt_chain(root, child)
    verdicts = [row for row in receipts if row.get("receipt_type") == "qa_verdict"]
    if (invalid or not verdicts or verdicts[-1].get("department") != ROLE
            or verdicts[-1].get("verdict") != "pass" or snapshot.get("current_state") != "closed"):
        _fail("original child must complete its own independent formal PASS and closed scope")
    import qa_review_plan as q
    plan = q.load_plan(root, snapshot)
    if (not isinstance(plan, dict) or not plan.get("parent_initial_child_review")
            or plan["candidate_version"] != child_box["candidate_version"]
            or plan["parent_initial_child_review"].get("producer_outbox") != follow["linked_outbox"]):
        _fail("closed child review must retain the exact initial parent source and current producer result")
    return {"actual_native_trial_verified": True, "external_authority_granted": False}
