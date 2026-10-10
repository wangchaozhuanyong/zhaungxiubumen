"""Read the original T3 candidate acceptance; never issue permission or a goal PASS.

The three tuples come from the original publisher, not a generic scope alias.
An independent native V2 and a committed continue are necessary even when the
producer has a full-goal verdict. Production preflight remains a separate gate.
"""
from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import re
import subprocess
from pathlib import Path

import workflow_control as w

TASK = "fc-20261010-paid-three-page-exact-publication-followthrough-v1"
SCOPE = "project:flashcast:paid-three-page-original-publication-followthrough:v1"
VERSION = "paid-three-page-exact-native-diff-v1-20261010"
ROLLBACK_VERSION = VERSION + "-rollback-v1"
ROLE = "operations-assistant-2"
PRODUCER = "publishing"
MODEL = "paid_three_page_bounded_cms_candidate_v1"
BASE = f"drafts/publishing/{TASK}"
ROWS = (("builtin", "b401a610-a4dc-4a0b-a7e0-efcac6c81d71", ("content_zh",)),
        ("kitchen", "ce4156db-9034-42c8-ba29-b35724ea7d6d", ("title_zh", "excerpt_zh")),
        ("renovation", "0d947129-0595-43ef-baa1-0fd9d8b870e6", ("title_zh", "excerpt_zh")))
SOURCES = ("tools/paid_three_page_bounded_cms.py", "tools/qa_review_plan.py",
           "tools/managed_cms_permit_issuer.py", "tools/goal_delivery_runtime.py",
           "tools/workflow_control.py")
FLAGS = ("production_write_allowed", "production_release_eligible", "external_permission_issued")
WEBSITE = Path("<WEBSITE_PROJECT_ROOT>")
DEPLOYMENT_EVIDENCE = "reports/paid-three-page-exact-entry-repair-20261010/production-closeout-20261010"
WEBSITE_SOURCE_VERSION = "paid-three-page-exact-entry-source-v3-20261010"
WORKFLOW_CLI = (".github/workflows/content-publish-approved.yml",
                "scripts/managed-cms-targets-paid-three-page-v1.mjs",
                "scripts/publish-content-trust-fixes.mjs")


def require(condition, message):
    if not condition:
        raise w.WorkflowError("bounded T3 CMS: " + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def strict(reader):
    @functools.wraps(reader)
    def read(*args, **kwargs):
        try:
            return reader(*args, **kwargs)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration) as error:
            raise w.WorkflowError("bounded T3 CMS: malformed or changed exact evidence: " + str(error)) from error
    return read


def pin(root, value):
    require(isinstance(value, dict), "frozen pin required")
    # Original publisher pins use absolute paths and bytes. Read those exact
    # bytes, but return the company's canonical pin; never rewrite the source.
    path = Path(str(value.get("path", "")))
    if path.is_absolute():
        require(path.resolve().is_relative_to(Path(root).resolve()), "evidence must belong to this project")
        path = path.resolve().relative_to(Path(root).resolve())
    actual = w.file_digest(root, str(path))
    require(actual["sha256"] == value.get("sha256")
            and actual["size"] == value.get("size", value.get("bytes")), "frozen source bytes changed")
    return actual


def doc(root, value):
    value = pin(root, value)
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result, "unambiguous frozen JSON fields required")
            result[key] = item
        return result
    result = json.loads(w.safe_path(root, value["path"]).read_bytes(), object_pairs_hook=unique)
    require(isinstance(result, dict), "object evidence required")
    require(not any(result.get(key) is True for key in
            ("fixture_only", "simulation", "simulated", *FLAGS)), "actual evidence without production permission required")
    return result


def exact_tuple(task, action, scope, department, action_class="cms_write"):
    return task == TASK and department == PRODUCER and action_class == "cms_write" and any(
        action in {f"paid-three-page-{slug}-exact-fields-v1", f"rollback-{VERSION}"}
        and scope == f"flashcast.com.my:services/{record}:{','.join(fields)}"
        for slug, record, fields in ROWS)


def _rows(root, current):
    """Recompute all 90 values; preserve both publisher and website digests."""
    original = doc(root, current["evidence"]["original_V2"])
    bindings_pin = pin(root, original["evidence"]["bindings"])
    bindings = doc(root, bindings_pin)
    require(bindings.get("task_id") == TASK and bindings.get("candidate_version") == VERSION
            and bindings.get("delta_count") == 5 and len(bindings.get("records", [])) == 3,
            "original three-row/five-field bindings required")
    manifest_pin = pin(root, current["evidence"]["manifest"])
    manifest = doc(root, manifest_pin)
    require(manifest.get("task_id") == TASK and manifest.get("candidate_version") == VERSION,
            "current producer source manifest required")
    legacy = "artifact_pins" in manifest or "fresh_backup_pins" in manifest
    modern = "artifacts" in manifest or "backups" in manifest
    require(legacy != modern, "one unambiguous producer manifest pin shape required")
    artifacts_key, backups_key = (("artifact_pins", "fresh_backup_pins") if legacy else ("artifacts", "backups"))
    require(isinstance(manifest.get(artifacts_key), list) and isinstance(manifest.get(backups_key), list),
            "complete current producer artifact/backup pins required")
    artifacts = [pin(root, frozen) for frozen in manifest[artifacts_key]]
    backups = [pin(root, frozen) for frozen in manifest[backups_key]]
    checks = doc(root, current["evidence"]["fresh_CAS_input_checks"])
    require(checks.get("task_id") == TASK and checks.get("candidate_version") == VERSION
            and len(checks.get("records", [])) == 3, "current exact producer row checks required")
    if modern:
        require(manifest.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
                and manifest.get("records") == checks["records"], "V4 manifest must freeze the same three current row checks")
    results = []
    for (slug, record, fields), binding, fresh in zip(ROWS, bindings["records"], checks["records"]):
        identity = {"taskId": TASK, "actionId": f"paid-three-page-{slug}-exact-fields-v1",
                    "operation": "publish", "scope": f"flashcast.com.my:services/{record}:{','.join(fields)}",
                    "candidateVersion": VERSION}
        require(binding.get("slug") == fresh.get("slug") == slug
                and binding.get("record_id") == fresh.get("record_id") == record
                and binding.get("proposed_target_identity") == identity
                and binding.get("changed_fields") == fresh.get("changed_fields") == list(fields),
                "original row/action/scope/field identity changed")
        backup_pin, candidate_pin = pin(root, binding["backup"]), pin(root, binding["candidate"])
        before, after = doc(root, backup_pin), doc(root, candidate_pin)
        require(set(before) == set(after) and len(before) == 30 and before.get("id") == after.get("id") == record,
                "exact full native row required")
        changes = {key for key in before if before[key] != after[key]}
        require(changes == set(fields), "sixth field or retained value changed")
        retained = {key: value for key, value in before.items() if key not in fields}
        website_retained = {key: value for key, value in retained.items() if key not in {"updated_at", "version"}}
        require(digest(before) == binding["before_full_fields_sha256"]
                and digest(after) == binding["after_full_fields_sha256"]
                and digest(retained) == binding["retained_fields_sha256"]
                and len(retained) == binding["retained_field_count"], "original native digests changed")
        fresh_backup, typed_pin = pin(root, fresh["backup"]), pin(root, fresh["typed_preview"])
        require(backups.count(fresh_backup) == 1 and artifacts.count(typed_pin) == 1,
                "current source manifest must freeze each row input")
        typed = doc(root, typed_pin)
        request = typed.get("request", {})
        require(doc(root, fresh_backup) == before
                and fresh.get("raw_updated_at") == binding["raw_updated_at"] == before["updated_at"]
                and fresh.get("native_version") == binding["version"] == before["version"]
                and request.get("mode") == "dry-run" and request.get("contentType") == "service"
                and request.get("expectedUpdatedAt") == before["updated_at"]
                and request.get("managedCandidate") == identity and request.get("record") == after,
                "current raw CAS/typed request differs from original exact candidate")
        results.append({"slug": slug, "record_id": record, "action_id": identity["actionId"],
            "scope": identity["scope"], "changed_fields": list(fields), "raw_updated_at": before["updated_at"],
            "native_version": before["version"], "baseline_sha256": digest(before), "desired_sha256": digest(after),
            "retained_sha256": digest(retained), "retained_count": len(retained),
            "website_retained_sha256": digest(website_retained), "website_retained_count": len(website_retained),
            "candidate": candidate_pin, "backup": fresh_backup, "typed_preview": typed_pin})
    return results, bindings_pin, manifest_pin


def _machine_sources(root, current):
    """Original authority and current preview are separately pinned provenance."""
    evidence = current["evidence"]
    actual = evidence.get("actual_machine_identity_and_preview_facts")
    if actual is None:
        return {"original_machine_source": pin(root, evidence["original_authority_review_machine_channel"])}
    previous = doc(root, evidence["original_V3"])
    require(previous.get("task_id") == TASK and previous.get("candidate_version") == VERSION
            and pin(root, previous["evidence"]["original_V2"]) == pin(root, evidence["original_V2"]),
            "current V4 must retain original V3/V2 authority provenance")
    original = pin(root, previous["evidence"]["original_authority_review_machine_channel"])
    require(evidence.get("original_authority_review_machine_channel") is None
            or pin(root, evidence["original_authority_review_machine_channel"]) == original,
            "conflicting original machine source forbidden")
    actual_pin = pin(root, actual)
    facts = doc(root, actual_pin)
    require(facts.get("task_id") == TASK and facts.get("candidate_version") == VERSION
            and len(facts.get("records", [])) == 3
            and [x.get("slug") for x in facts["records"]] == [r[0] for r in ROWS]
            and re.fullmatch(r"[0-9a-f]{40}", str(facts.get("machine_workflow_sha", "")))
            and re.fullmatch(r"[0-9a-f]{40}", str(facts.get("native_frontend_loaded_sha", "")))
            and facts.get("website_deployed_source_candidate_version") == WEBSITE_SOURCE_VERSION
            and facts.get("new_account_permission") is False and facts.get("cms_save") == 0
            and facts.get("signing_authority", {}).get("new_single_use_CMS_permits_issued") == 0,
            "actual current V4 machine facts required")
    return {"original_machine_source": original, "actual_machine_source": actual_pin}


def _producer_native(root, current_pin):
    import goal_delivery_runtime as g
    from scoped_candidate_adoption import _committed
    rows = [r for r in w._result_handoff_rows(root, TASK) if r.get("event") == "controller_received"
            and r.get("outbox") == current_pin and r.get("coordinator_role") == ROLE]
    require(len(rows) == 1, "one actual current producer native intake required")
    row = rows[0]
    _committed(root, row)
    native = g._collaboration_native(root, row.get("actual_native_completion"))
    fixed = w.department_registry(root)[PRODUCER]["chat_binding"]
    require(native.get("thread", {}).get("id") == fixed["task_id"] == row.get("source_thread_id")
            and w._same_resolved_path(str(native.get("thread", {}).get("cwd", "")), str(Path(root).resolve())),
            "current producer original fixed chat required")
    visible = pin(root, row.get("visible_reply"))
    raw = w.safe_path(root, visible["path"]).read_bytes()
    message = g._collaboration_final_message(native, fixed["task_id"])
    require(message.get("turnId") == row.get("source_turn_id")
            and message.get("phase") == "final_answer" and isinstance(message.get("text"), str)
            and message["text"].strip() and message["text"].encode("utf-8") == raw
            and row.get("source_reply_sha256") == visible["sha256"],
            "exact current producer completed UTF-8 required")


def _current(root, snapshot):
    import goal_delivery_runtime as g
    import qa_review_plan as q
    snapshot = g.restore_goal(root, q._review_context(root, snapshot))
    require(snapshot.get("task_id") == TASK and g.enabled(root, snapshot)
            and snapshot.get("current_state") not in w.TERMINAL_STATES, "active original modern T3 required")
    goal = snapshot["goal_delivery"]
    g.validate_goal(root, goal)
    require(goal.get("source_mode") == "owner_direct" and goal.get("primary_owner") == PRODUCER
            and goal.get("producer_departments") == [PRODUCER] and goal.get("authorized_scope") == [SCOPE]
            and goal.get("acceptance_capability") == "cms" and q._goal_reviewer(root, snapshot) == ROLE,
            "original publisher-only authority and sole independent A2 required")
    origin = q.owner_direct_review_context(root, snapshot)
    require(isinstance(origin, dict) and origin.get("prepared_only") is True,
            "original adopted owner-direct review provenance required")
    plan_pin = q._binding(root, snapshot)["pin"]
    receipts, invalid = w._validate_receipt_chain(root, TASK)
    require(not invalid and not w.validate_workflow_events(root, TASK), "valid original receipt/event chains required")
    received = [row for row in receipts if row.get("receipt_type") == "outbox_received" and row.get("department") == PRODUCER]
    require(bool(received), "current publishing result required")
    current_pin = next((p for p in received[-1].get("evidence", []) if str(p.get("path", "")).endswith(".json")), None)
    current = doc(root, current_pin)
    w.validate_outbox(root, [current_pin], PRODUCER, TASK)
    require(current.get("task_id") == TASK and current.get("candidate_version") == VERSION
            and current.get("evidence", {}).get("original_V2") == origin["proof"]["producer_outbox"],
            "latest producer must retain original source/version")
    _producer_native(root, current_pin)
    rows, bindings, manifest = _rows(root, current)
    return snapshot, origin, plan_pin, current_pin, rows, bindings, manifest


@strict
def targets(root):
    """Expose only the original proposed tuples; registration is not admission."""
    snapshot = w.read_json(w.snapshot_path(root, TASK))
    if not snapshot or not isinstance(snapshot.get("goal_delivery"), dict):
        return {}
    _, _, _, _, rows, _, _ = _current(root, snapshot)
    return {f"paid-three-page-{row['slug']}-exact-fields-v1": {
        "task_id": TASK, "action_id": row["action_id"], "scope": row["scope"], "candidate_version": VERSION,
        "execution_owner": PRODUCER, "record_id": row["record_id"], "slug": row["slug"],
        "candidate_shape": MODEL, "changed_fields": row["changed_fields"], "evidence_root": str(Path(root).resolve()),
        "candidate": (row["candidate"]["path"], row["candidate"]["sha256"]),
        "rollback": (row["backup"]["path"], row["backup"]["sha256"]), "rollback_allowed": True,
        "bounded_row": row} for row in rows}


def _native(root, box, references):
    import goal_delivery_runtime as g
    fixed = w.department_registry(root)[ROLE]["chat_binding"]
    require(w._chat_binding_healthy(fixed, verification_ttl_hours=26), "current independent reviewer binding health required")
    native = g._collaboration_native(root, box.get("actual_native_reply"))
    thread = native.get("thread", {})
    reply = pin(root, box.get("visible_reply"))
    raw = w.safe_path(root, reply["path"]).read_bytes()
    turns = [turn for turn in native.get("turns", []) if turn.get("id") == box.get("source_turn_id")]
    require(thread.get("id") == box.get("fixed_chat_task_id") == fixed["task_id"]
            and w._same_resolved_path(str(thread.get("cwd", "")), str(Path(root).resolve()))
            and len(turns) == 1 and turns[0].get("status") in {"inProgress", "completed"}, "actual original A2 native turn required")
    messages = [item for item in turns[0].get("items", []) if item.get("type") == "agentMessage"
                and item.get("id") == box.get("source_message_id") and item.get("phase") in {"commentary", "final_answer"}
                and isinstance(item.get("text"), str) and item["text"].strip() and item["text"].encode("utf-8") == raw]
    reply_meta = box.get("chat_reply", {})
    require(len(messages) == 1 and box.get("source_reply_sha256") == reply["sha256"]
            and reply_meta.get("nonempty") is True and reply_meta.get("in_current_fixed_department_chat") is True
            and reply_meta.get("message_sha256") == reply["sha256"] and reply_meta.get("utf8_bytes") == len(raw)
            and reply_meta.get("source_turn_id") == box["source_turn_id"]
            and reply_meta.get("source_message_id") == box["source_message_id"], "one exact nonempty A2 UTF-8 message required")
    text = messages[0]["text"]
    require(all(re.search(r"(?<![A-Za-z0-9_./:-])" + re.escape(str(value))
                         + r"(?![A-Za-z0-9_./:-])", text) for value in references),
            "native candidate result must identify its exact source and bounded verdict")
    observed = w._parse_observed_at(box.get("reply_observed_at"))
    created = w._parse_observed_at(box.get("created_at"))
    started = turns[0].get("startedAt")
    require(type(started) in {int, float} and observed is not None and created is not None
            and 0 <= started <= observed.timestamp() and observed <= created <= dt.datetime.now(dt.timezone.utc),
            "ordered nonfuture actual review times required")


def _review_box(root, current_pin, kind):
    handoffs = w._result_handoff_rows(root, TASK)
    decisions = [row for row in handoffs if row.get("event") == "controller_decision"
                 and row.get("sender_department") == PRODUCER and row.get("outbox") == current_pin]
    require(bool(decisions), "actual current producer continuation required")
    decision = decisions[-1]
    require(decision.get("decision") == "continue" and decision.get("coordinator_role") == ROLE
            and decision.get("decision_actor") == ROLE and decision.get("responsible_assistant") == ROLE
            and type(decision.get("coordination_fence")) is int and decision["coordination_fence"] > 0
            and decision.get("next_owner") == PRODUCER and decision.get("candidate_version") == VERSION
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual fenced bounded continue required; full-goal PASS cannot substitute")
    from scoped_candidate_adoption import _committed
    _committed(root, decision)
    candidates = [(p, doc(root, p)) for p in decision.get("evidence", []) if str(p.get("path", "")).endswith(".json")]
    candidates = [(p, box) for p, box in candidates if isinstance(box.get(kind), dict)]
    require(len(candidates) == 1, "one real A2 bounded V2 required in committed continue evidence")
    box_pin, box = candidates[0]
    w.validate_outbox(root, [box_pin], ROLE, TASK)
    proof = box[kind]
    return decision, box_pin, box, proof


@strict
def acceptance(root, snapshot, target, operation="publish"):
    if operation == "rollback":
        return rollback_acceptance(root, snapshot, target)
    require(operation == "publish", "known exact operation required")
    snapshot, origin, plan_pin, current_pin, rows, bindings, manifest = _current(root, snapshot)
    require(exact_tuple(target.get("task_id"), target.get("action_id"), target.get("scope"), target.get("execution_owner"))
            and target.get("candidate_version") == VERSION and target.get("candidate_shape") == MODEL,
            "only original exact T3 tuple allowed")
    decision, box_pin, box, proof = _review_box(root, current_pin, "cms_candidate_acceptance")
    require(box.get("schema_version") == "2.0" and box.get("task_id") == TASK and box.get("department") == ROLE
            and box.get("candidate_version") == VERSION and box.get("status") == "partial"
            and box.get("qa_verdict") != "pass" and not box.get("goal_acceptance")
            and all(box.get(key) is False and proof.get(key) is False for key in FLAGS), "independent bounded V2 only; no production/full-goal PASS")
    expected = {"schema": MODEL, "task_id": TASK, "candidate_version": VERSION, "reviewer": ROLE,
                "producer": PRODUCER, "verdict": "PASS_CANDIDATE_ONLY", "project_scope": SCOPE,
                "authority": snapshot["goal_delivery"]["authorization_pin"], "goal_contract": snapshot["goal_contract"],
                "review_plan": plan_pin, "original_producer": origin["proof"]["producer_outbox"],
                "current_producer": current_pin, "bindings": bindings, "source_manifest": manifest, "rows": rows,
                **_machine_sources(root, doc(root, current_pin)),
                "remaining_actions": ["exact_Save_and_SavedCAS", "public_desktop_mobile_noJS_verification"]}
    require(all(proof.get(key) == value for key, value in expected.items()), "bounded review differs from original/current authority, sources or rows")
    source_pins = proof.get("consumer_sources", [])
    require(isinstance(source_pins, list) and all(isinstance(p, dict) for p in source_pins)
            and sorted(p.get("path", "") for p in source_pins) == sorted(SOURCES),
            "current adopted consumer source versions required")
    for source in source_pins:
        pin(root, source)
    frozen = [plan_pin, current_pin, bindings, manifest, *source_pins]
    if "actual_machine_source" in expected:
        frozen += [expected["original_machine_source"], expected["actual_machine_source"]]
    require(all(p in box.get("evidence", []) for p in frozen), "bounded V2 must freeze all current evidence")
    _native(root, box, [TASK, VERSION, current_pin["sha256"], "PASS_CANDIDATE_ONLY"])
    reviewed = w._parse_observed_at(box.get("created_at"))
    continued = w._parse_observed_at(decision.get("created_at"))
    require(reviewed is not None and continued is not None and reviewed <= continued <= dt.datetime.now(dt.timezone.utc),
            "candidate review must precede committed continue")
    matching = [item for item in rows if all(target.get(k) == item[k] for k in ("record_id", "action_id", "scope", "slug"))]
    require(len(matching) == 1, "target record must match its original action/scope")
    row = matching[0]
    require(target.get("bounded_row") == row and target.get("changed_fields") == row["changed_fields"]
            and list(target.get("candidate", ())) == [row["candidate"]["path"], row["candidate"]["sha256"]]
            and list(target.get("rollback", ())) == [row["backup"]["path"], row["backup"]["sha256"]], "current exact target source required")
    return {"task_id": TASK, "scope": row["scope"], "acceptance_model": MODEL, "verdict": "pass_candidate_only", "operation": "publish", "candidate_version": VERSION,
            "candidate_acceptance_record_id": decision["record_id"], "candidate_acceptance_record_hash": decision["record_hash"],
            "created_at": box["created_at"], "responsible_assistant": ROLE, "risk_level": "R3",
            "review_outbox": box_pin, "review_plan": plan_pin, "candidate": row["candidate"],
            "authorization_pin": expected["authority"], "current_producer": current_pin, "row": row,
            **{k: expected[k] for k in ("original_machine_source", "actual_machine_source") if k in expected},
            "consumer_sources": source_pins,
            "preflights": proof.get("execution_preflights", []), "business_goal_closed": False,
            "production_write_allowed": False}


@strict
def rollback_acceptance(root, snapshot, target):
    """A distinct independent review follows a real Save and fresh Saved CAS."""
    snapshot, origin, plan_pin, current_pin, rows, bindings, manifest = _current(root, snapshot)
    matching = [r for r in rows if all(target.get(k) == r[k] for k in ("record_id", "action_id", "scope", "slug"))]
    require(len(matching) == 1 and target.get("candidate_shape") == MODEL
            and target.get("task_id") == TASK and target.get("candidate_version") == VERSION
            and target.get("execution_owner") == PRODUCER
            and target.get("rollback_allowed") is True, "only the original three-row recovery namespace allowed")
    row = matching[0]
    require(target.get("bounded_row") == row and target.get("changed_fields") == row["changed_fields"]
            and list(target.get("candidate", ())) == [row["candidate"]["path"], row["candidate"]["sha256"]]
            and list(target.get("rollback", ())) == [row["backup"]["path"], row["backup"]["sha256"]],
            "rollback target must retain original fields and backup")
    continued, review_pin, box, proof = _review_box(root, current_pin, "cms_rollback_acceptance")
    require(box.get("schema_version") == "2.0" and box.get("task_id") == TASK and box.get("department") == ROLE
            and box.get("candidate_version") == ROLLBACK_VERSION and box.get("status") == "partial"
            and box.get("qa_verdict") != "pass" and not box.get("goal_acceptance")
            and all(box.get(k) is False and proof.get(k) is False for k in FLAGS),
            "new independent rollback result required; publish PASS cannot authorize recovery")
    expected = {"schema": MODEL + "_rollback", "task_id": TASK, "candidate_version": ROLLBACK_VERSION,
        "operation": "rollback", "reviewer": ROLE, "producer": PRODUCER, "project_scope": SCOPE,
        "verdict": "PASS_ROLLBACK_CANDIDATE_ONLY", "row": row, "authority": snapshot["goal_delivery"]["authorization_pin"],
        "goal_contract": snapshot["goal_contract"], "review_plan": plan_pin,
        "original_producer": origin["proof"]["producer_outbox"], "current_producer": current_pin,
        "bindings": bindings, "source_manifest": manifest,
        **_machine_sources(root, doc(root, current_pin)),
        "remaining_actions": ["distinct_single_use_rollback", "restored_public_verification"]}
    require(all(proof.get(k) == v for k, v in expected.items()), "rollback authority/source/row/version differs")
    sources = proof.get("consumer_sources", [])
    require(isinstance(sources, list) and all(isinstance(p, dict) for p in sources)
            and sorted(p.get("path", "") for p in sources) == sorted(SOURCES), "current recovery consumer source pins required")
    for frozen in sources:
        pin(root, frozen)
    publish_pin = pin(root, proof.get("publish_review_outbox"))
    publish_box = doc(root, publish_pin)
    published_review = publish_box.get("cms_candidate_acceptance", {})
    require(published_review.get("schema") == MODEL and published_review.get("verdict") == "PASS_CANDIDATE_ONLY"
            and published_review.get("rows") == rows and published_review.get("authority") == expected["authority"]
            and published_review.get("goal_contract") == expected["goal_contract"]
            and published_review.get("original_producer") == expected["original_producer"]
            and publish_box.get("department") == ROLE and publish_box.get("task_id") == TASK
            and publish_box.get("candidate_version") == VERSION and not publish_box.get("goal_acceptance")
            and all(publish_box.get(k) is False and published_review.get(k) is False for k in FLAGS)
            and published_review.get("current_producer") != current_pin,
            "original independent publish review and subsequent real Save result required")
    _native(root, publish_box, [TASK, VERSION, published_review["current_producer"]["sha256"], "PASS_CANDIDATE_ONLY"])
    parent_rows = [r for r in w._result_handoff_rows(root, TASK) if r.get("record_id") == proof.get("publish_continue_record_id")]
    require(len(parent_rows) == 1 and parent_rows[0].get("event") == "controller_decision"
            and parent_rows[0].get("decision") == "continue" and parent_rows[0].get("coordinator_role") == ROLE
            and parent_rows[0].get("decision_actor") == ROLE and parent_rows[0].get("responsible_assistant") == ROLE
            and parent_rows[0].get("outbox") == published_review["current_producer"]
            and publish_pin in parent_rows[0].get("evidence", []), "actual original publish continue record required")
    from scoped_candidate_adoption import _committed
    _committed(root, parent_rows[0])
    parent = doc(root, proof.get("completed_parent"))
    from managed_cms_permit_issuer import validate_completed_parent_status
    parent_run = proof.get("parent_run_id")
    parent_permit = proof.get("parent_permit_id")
    require(type(parent_run) is int and parent_run > 0 and isinstance(parent_permit, str) and parent_permit,
            "real original completed parent permit/run required")
    validate_completed_parent_status(parent, target, parent_permit, parent_run)
    current = doc(root, proof.get("saved_record"))
    before = doc(root, row["backup"])
    desired = doc(root, row["candidate"])
    require(set(current) == set(before) and current.get("id") == row["record_id"]
            and current.get("updated_at") == parent["savedUpdatedAt"]
            and current["updated_at"] != row["raw_updated_at"]
            and type(current.get("version")) is int and current["version"] > row["native_version"]
            and all(current[k] == desired[k] for k in row["changed_fields"])
            and all(current[k] == before[k] for k in current if k not in {*row["changed_fields"], "updated_at", "version"}),
            "fresh exact Saved ID/microsecond CAS and unchanged retained values required")
    producer = doc(root, current_pin)
    require(producer["evidence"].get("completed_parent") == proof["completed_parent"]
            and producer["evidence"].get("saved_record") == proof["saved_record"],
            "current producer must freeze actual protected Save/status/readback")
    restored = {**current, **{k: before[k] for k in row["changed_fields"]}}
    restore_pin = pin(root, proof.get("restore_candidate"))
    require(doc(root, restore_pin) == restored, "original backup-only restore; no other field changes")
    typed_pin = pin(root, proof.get("typed_preview"))
    typed = doc(root, typed_pin).get("request", {})
    require(typed.get("mode") == "dry-run" and typed.get("contentType") == "service"
            and typed.get("expectedUpdatedAt") == current["updated_at"] and typed.get("record") == restored
            and typed.get("managedCandidate") == {"taskId": TASK, "actionId": f"rollback-{VERSION}",
                "operation": "rollback", "scope": row["scope"], "candidateVersion": ROLLBACK_VERSION},
            "distinct rollback tuple and fresh Saved CAS request required")
    frozen = [plan_pin, current_pin, publish_pin, bindings, manifest, *sources,
              proof["completed_parent"], proof["saved_record"], restore_pin, typed_pin]
    if "actual_machine_source" in expected:
        frozen += [expected["original_machine_source"], expected["actual_machine_source"]]
    require(all(p in box.get("evidence", []) for p in frozen), "new rollback V2 must freeze all source/readback/recovery bytes")
    _native(root, box, [TASK, ROLLBACK_VERSION, current_pin["sha256"], "PASS_ROLLBACK_CANDIDATE_ONLY"])
    reviewed, continued_at = w._parse_observed_at(box.get("created_at")), w._parse_observed_at(continued.get("created_at"))
    require(reviewed is not None and continued_at is not None and reviewed <= continued_at <= dt.datetime.now(dt.timezone.utc),
            "new rollback review must precede its actual continue")
    recovery_row = {**row, "action_id": f"rollback-{VERSION}", "raw_updated_at": current["updated_at"],
        "native_version": current["version"], "baseline_sha256": digest(current), "desired_sha256": digest(restored),
        "candidate": restore_pin, "typed_preview": typed_pin}
    return {"task_id": TASK, "scope": row["scope"], "acceptance_model": MODEL, "operation": "rollback",
        "candidate_version": ROLLBACK_VERSION, "verdict": "pass_rollback_candidate_only",
        "candidate_acceptance_record_id": continued["record_id"], "candidate_acceptance_record_hash": continued["record_hash"],
        "created_at": box["created_at"], "responsible_assistant": ROLE, "risk_level": "R3",
        "review_outbox": review_pin, "review_plan": plan_pin, "candidate": restore_pin,
        "authorization_pin": expected["authority"], "current_producer": current_pin, "row": recovery_row,
        **{k: expected[k] for k in ("original_machine_source", "actual_machine_source") if k in expected},
        "consumer_sources": sources,
        "preflights": proof.get("execution_preflights", []), "parent_run_id": parent_run, "parent_permit_id": parent_permit,
        "completed_parent": proof["completed_parent"], "saved_record": proof["saved_record"],
        "business_goal_closed": False, "production_write_allowed": False}


@strict
def validate_machine(root, item, accepted):
    """Bind the reviewed run and original issuer, not a self-consistent new actor."""
    machine_pin = pin(root, item.get("machine_identity"))
    machine = doc(root, machine_pin)
    original_pin = pin(root, accepted["original_machine_source"])
    original = doc(root, original_pin)["actual_original_machine_channel_metadata"]
    issuer_pin = next(p for p in accepted["consumer_sources"] if p["path"] == "tools/managed_cms_permit_issuer.py")
    require(machine.get("schema") == "actual_t3_protected_machine_binding_v1"
            and machine.get("original_machine_source") == original_pin
            and machine.get("issuer_source") == issuer_pin, "original reviewed machine and issuer source pins required")
    pin(root, issuer_pin)
    expected = {"task_id": TASK, "candidate_version": item["candidate_version"], "department": PRODUCER,
        "action_id": item["action_id"], "scope": item["scope"], "action_class": "cms_write",
        "record_id": accepted["row"]["record_id"], "payload_sha256": item["payload_sha256"],
        "github_actor_id": original["existing_actor_id"], "repository": original["repository"],
        "workflow_id": original["workflow_id"], "workflow_path": original["workflow_path"],
        "repository_id": 1248188229,
        "workflow_ref": "wangchaozhuanyong/zhuangxiuwangzhan/.github/workflows/content-publish-approved.yml@refs/heads/main"}
    require(all(machine.get(k) == v for k, v in expected.items())
            and machine["repository"] == "wangchaozhuanyong/zhuangxiuwangzhan"
            and machine["workflow_path"] == ".github/workflows/content-publish-approved.yml"
            and type(machine.get("github_actor_id")) is int and machine["github_actor_id"] > 0
            and type(machine.get("run_id")) is int and machine["run_id"] > 0
            and type(machine.get("run_attempt")) is int and machine["run_attempt"] > 0
            and re.fullmatch(r"[0-9a-f]{40}", str(machine.get("workflow_sha", "")))
            and re.fullmatch(r"[0-9a-f]{40}", str(machine.get("main_sha", ""))),
            "exact original actor/run/attempt/workflow/source identity required")
    run, probe, receipt, payload = [doc(root, machine.get(k)) for k in
                                  ("run_snapshot", "identity_probe", "locked_preview", "payload_digest")]
    identity = probe.get("identity", {})
    require(run.get("id") == machine["run_id"] and run.get("run_attempt") == machine["run_attempt"]
            and run.get("actor", {}).get("id") == machine["github_actor_id"]
            and run.get("workflow_id") == machine["workflow_id"] and run.get("path") == machine["workflow_path"]
            and run.get("head_sha") == machine["main_sha"] and run.get("head_branch") == "main"
            and run.get("event") == "workflow_dispatch" and run.get("conclusion") == "success"
            and probe.get("ok") is True and probe.get("dry_run") is True and probe.get("performed_write") is False
            and all(identity.get(k) == machine[v] for k, v in {
                "runId": "run_id", "runAttempt": "run_attempt", "actorId": "github_actor_id",
                "repositoryId": "repository_id", "workflowRef": "workflow_ref", "workflowSha": "workflow_sha"}.items()),
            "reviewed server OIDC probe must bind the same original machine/run")
    require(receipt.get("task_id") == TASK and receipt.get("candidate_version") == item["candidate_version"]
            and receipt.get("action_id") == item["action_id"] and receipt.get("scope") == item["scope"]
            and receipt.get("operation") == item.get("operation", "publish") and receipt.get("http_status") == 200
            and receipt.get("dry_run") is True and receipt.get("performed_write") is False
            and receipt.get("external_writes") == 0 and receipt.get("row_unchanged_after_dry_run") is True
            and payload.get("task_id") == TASK and payload.get("operation") == item.get("operation", "publish")
            and payload.get("payload_sha256") == item["payload_sha256"]
            and payload.get("expected_updated_at") == accepted["row"]["raw_updated_at"],
            "reviewed machine must freeze this exact zero-write preview/payload/raw CAS")
    if "actual_machine_source" in accepted:
        actual_pin = pin(root, accepted["actual_machine_source"])
        facts = doc(root, actual_pin)
        require(machine.get("actual_machine_source") == actual_pin, "reviewed machine must bind latest V4 facts")
        if item.get("operation", "publish") == "publish":
            records = [r for r in facts["records"] if r.get("slug") == accepted["row"]["slug"]]
            require(len(records) == 1, "one current V4 preview for this exact row required")
            current = records[0]
            require(current.get("identity") == identity
                    and pin(root, current.get("identity_probe")) == pin(root, machine["identity_probe"])
                    and current.get("protected_forward_receipt") == receipt
                    and current.get("actual_payload_sha256") == item["payload_sha256"]
                    and current.get("writes") == 0 and machine["workflow_sha"] == facts["machine_workflow_sha"]
                    and machine["main_sha"] == facts["machine_workflow_sha"],
                    "latest V4 run/attempt/probe/preview/payload cannot use historical V3 facts")
    stamp = w._parse_observed_at(run.get("updated_at"))
    now = dt.datetime.now(dt.timezone.utc)
    require(stamp is not None and now - dt.timedelta(minutes=30) <= stamp <= now,
            "reviewed run is stale or future; new run requires new independent proof")
    if "actual_machine_source" in accepted:
        previewed = w._parse_observed_at(receipt.get("checked_at"))
        require(previewed is not None and now - dt.timedelta(minutes=30) <= previewed <= stamp,
                "actual protected preview expired; metadata read cannot refresh its time")
    return machine


@strict
def validate_issuer_machine(root, target, accepted, run, probe, actor, payload, receipt):
    action = target["action_id"] if accepted["operation"] == "publish" else f"rollback-{VERSION}"
    matches = [item for item in accepted.get("preflights", []) if item.get("action_id") == action
               and item.get("scope") == target["scope"]]
    require(len(matches) == 1, "one reviewed row machine preflight required")
    machine = validate_machine(root, matches[0], accepted)
    require(actor == machine["github_actor_id"] and run == doc(root, machine["run_snapshot"])
            and probe == doc(root, machine["identity_probe"])
            and payload == doc(root, machine["payload_digest"])
            and receipt == doc(root, machine["locked_preview"]),
            "issuer CLI/download cannot replace the A2-frozen actor/run/attempt/workflow/source")
    return machine


def _website_bytes(value):
    """Read only the original website's frozen T3 deployment evidence."""
    require(isinstance(value, dict), "frozen original website source pin required")
    path = Path(str(value.get("path", "")))
    require(path.is_absolute() and path.resolve().is_relative_to((WEBSITE / DEPLOYMENT_EVIDENCE).resolve()),
            "website evidence outside original T3 deployment package forbidden")
    raw = path.read_bytes()
    require(type(value.get("size", value.get("bytes"))) is int
            and len(raw) == value.get("size", value.get("bytes"))
            and hashlib.sha256(raw).hexdigest() == value.get("sha256"), "original deployed website source bytes changed")
    return raw


def _website_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result, "unambiguous website source JSON required")
            result[key] = item
        return result
    return json.loads(_website_bytes(value), object_pairs_hook=unique)


def _git_source(commit, path):
    require(re.fullmatch(r"[0-9a-f]{40}", str(commit)) is not None, "exact source commit required")
    try:
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=WEBSITE,
                                capture_output=True, timeout=15, check=False)
    except subprocess.TimeoutExpired as error:
        raise w.WorkflowError("bounded T3 CMS: source commit read timed out") from error
    require(result.returncode == 0, "actual website commit source unavailable")
    return result.stdout


@strict
def source_coherence(root, source, deployment, machine, accepted):
    """Compare original deployment bytes with the actual run commit, never a SHA alias."""
    proof = doc(root, source.get("source_coherence"))
    production, main = source["production_sha"], machine["main_sha"]
    require(proof.get("schema") == "A2_owned_T3_v4_workflow_commit_runtime_digest_equivalence_preliminary_v1"
            and proof.get("task_id") == TASK and proof.get("formal_T3_PASS") is False
            and proof.get("actual_machine_main_sha") == main
            and proof.get("actual_machine_workflow_sha") == machine["workflow_sha"]
            and proof.get("actual_deployed_runtime_sha") == production
            and type(proof.get("actual_function_version")) is int
            and type(proof.get("actual_deployment_run")) is int
            and source.get("function_version") == deployment.get("function_version") == proof["actual_function_version"]
            and deployment.get("deployment_run_id") == proof["actual_deployment_run"]
            and deployment.get("original_deployment_source_proof") == proof.get("actual_deployment_source_proof"),
            "separate actual workflow/deployment source proof required")
    if "actual_machine_source" in accepted:
        facts = doc(root, accepted["actual_machine_source"])
        producer = doc(root, accepted.get("current_producer"))
        require(_machine_sources(root, producer)["actual_machine_source"] == pin(root, accepted["actual_machine_source"]),
                "coherence must belong to latest reviewed producer")
        source_facts = doc(root, producer["evidence"]["source_and_original_backups"])
        require(facts["machine_workflow_sha"] == main == machine["workflow_sha"]
                and facts["native_frontend_loaded_sha"] == production
                and source_facts.get("task_id") == TASK and source_facts.get("content_candidate_version") == VERSION
                and source_facts.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
                and source_facts.get("production_website_sha") == production
                and pin(WEBSITE, source_facts["deployment_proof"]) == pin(WEBSITE, proof["actual_deployment_source_proof"]),
                "source proof must bind current V4 workflow and deployed runtime separately")
    original = _website_json(proof["actual_deployment_source_proof"])
    require(original.get("task_id") == TASK and original.get("content_candidate_version") == VERSION
            and original.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
            and original.get("status") == "PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP"
            and original.get("production_website_sha") == production
            and original.get("run_id") == proof["actual_deployment_run"]
            and original.get("actual_function", {}).get("name") == "content-publish"
            and original["actual_function"].get("status") == "ACTIVE"
            and original["actual_function"].get("after_version") == original["actual_function"].get("after_download_version")
                == proof["actual_function_version"]
            and pin(WEBSITE, original["actual_readback"]["manifest"]) == pin(WEBSITE, proof["actual_deployed_runtime_manifest"]),
            "original actual deployed version77/source provenance required")
    run = _website_json(original["run_proof"])["run"]
    require(run.get("id") == proof["actual_deployment_run"] and run.get("head_sha") == production
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("event") == "workflow_dispatch", "original completed deployment run required")
    for name in ("functions-after.json", "functions-after-download.json"):
        matches = [p for p in original["artifact_metadata_pins"] if p["path"].endswith("/" + name)]
        require(len(matches) == 1, "actual deployment metadata snapshots required")
        functions = _website_json(matches[0])
        require(isinstance(functions, list) and len([f for f in functions if f.get("name") == "content-publish"
                and f.get("version") == proof["actual_function_version"] and f.get("status") == "ACTIVE"]) == 1,
                "actual deployed function version differs")
    manifest = _website_json(proof["actual_deployed_runtime_manifest"])
    files, mapping = manifest.get("files", []), proof.get("runtime_file_map", [])
    closure_digest = hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(manifest.get("schema") == "content-publish-runtime-source/v1"
            and manifest.get("entrypoint") == "content-publish/index.ts"
            and len(files) == len(mapping) == proof.get("actual_runtime_source_closure_file_count") == 21
            and len({f.get("path") for f in files}) == 21
            and len({f.get("runtime_path") for f in mapping}) == 21
            and {f.get("path") for f in files} == {f.get("runtime_path") for f in mapping}
            and closure_digest == proof.get("actual_runtime_source_closure_digest") == original["actual_readback"]["source_sha256"],
            "complete exact deployed21 runtime closure required")
    readback = WEBSITE / DEPLOYMENT_EVIDENCE / f"production-r3-run-{run['id']}-artifacts/readback/edge-after/supabase/functions"
    require(Path(original["actual_readback"]["root"]).resolve() == readback.resolve(), "original runtime download root required")
    for entry in files:
        path = entry["path"]
        require(re.fullmatch(r"(?:_shared|content-publish)/[a-zA-Z0-9_-]+\.ts", path) is not None,
                "exact runtime source path required")
        mapped = next(m for m in mapping if m["runtime_path"] == path)
        require(mapped.get("git_path") == "supabase/functions/" + path and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("actual_deployed_v77_sha256") == entry["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("actual_deployed_v77_bytes") == entry["bytes"],
                "runtime source map digest differs")
        raw = _website_bytes({"path": str(readback / path), "sha256": entry["sha256"], "size": entry["bytes"]})
        require(_git_source(main, mapped["git_path"]) == _git_source(production, mapped["git_path"]) == raw,
                "actual workflow/deployed runtime byte coherence failed")
    workflow_map = proof.get("workflow_and_CLI_source_map", [])
    require(len(workflow_map) == 3 and {p.get("path") for p in workflow_map} == set(WORKFLOW_CLI),
            "original protected workflow and exact CLI/target closure required")
    for mapped in workflow_map:
        approved = [p for p in original["source_pins"] if p.get("path") == mapped["path"]]
        require(len(approved) == 1 and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("approved_5237_source_sha256") == approved[0]["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("approved_5237_source_bytes") == approved[0]["bytes"],
                "original protected workflow/CLI source map differs")
        raw = _git_source(main, mapped["path"])
        require(raw == _git_source(production, mapped["path"])
                and hashlib.sha256(raw).hexdigest() == approved[0]["sha256"] and len(raw) == approved[0]["bytes"],
                "actual workflow/CLI/target source bytes differ")
    for runtime in ("content-publish/service.ts", "_shared/managed-targets.ts"):
        entry = next(f for f in files if f["path"] == runtime)
        require(any(p.get("path", "").endswith("/" + runtime.rsplit("/", 1)[-1])
                and p.get("sha256") == entry["sha256"] and p.get("size") == entry["bytes"]
                for p in source.get("source_snapshots", [])), "recovery snapshots must match actual deployed restore implementation")
    return pin(root, source["source_coherence"])


@strict
def preflight(root, snapshot, action, action_class, scope, department):
    require(exact_tuple(snapshot.get("task_id"), action, scope, department, action_class), "exact native row cannot broaden project authority")
    operation = "rollback" if action == f"rollback-{VERSION}" else "publish"
    target = next(t for t in targets(root).values() if t["scope"] == scope
                  and (operation == "rollback" or t["action_id"] == action))
    accepted = acceptance(root, snapshot, target, operation)
    expected = {"task_id": TASK, "action_id": action, "action_class": action_class, "scope": scope,
                "department": department, "candidate_version": accepted["candidate_version"], "record_id": target["record_id"]}
    items = [item for item in accepted["preflights"] if isinstance(item, dict) and all(item.get(k) == v for k, v in expected.items())]
    require(len(items) == 1, "one exact row production self-check still required")
    item = items[0]
    require(item.get("operation", "publish") == operation, "distinct reviewed production operation required")
    require(item.get("risk_level") == "R3" and w.SHA256_PATTERN.fullmatch(str(item.get("payload_sha256", ""))) is not None,
            "exact production risk/payload required")
    machine = validate_machine(root, item, accepted)
    facts, check, rollback = [doc(root, item.get(k)) for k in ("facts", "self_check", "rollback")]
    require(pin(root, item.get("backup")) == accepted["row"]["backup"], "original current native backup required")
    require(all(check.get(k) == v and facts.get(k) == v and rollback.get(k) == v for k, v in expected.items())
            and check.get("status") == "PASS" and check.get("payload_sha256") == item["payload_sha256"]
            and facts.get("raw_updated_at") == accepted["row"]["raw_updated_at"]
            and facts.get("native_version") == accepted["row"]["native_version"]
            and facts.get("baseline_sha256") == accepted["row"]["baseline_sha256"]
            and facts.get("desired_sha256") == accepted["row"]["desired_sha256"], "exact successful row CAS/self-check required")
    observed = w._parse_observed_at(facts.get("checked_at"))
    now = dt.datetime.now(dt.timezone.utc)
    require(observed is not None and now - dt.timedelta(minutes=30) <= observed <= now,
            "fresh authenticated native raw CAS required")
    require(check.get("protected_preview_zero_write") is True and check.get("production_endpoint_verified") is True
            and check.get("actor_workflow_run_verified") is True and check.get("single_use_state") == "unused",
            "real endpoint/actor/workflow/run/unused permit preflight required")
    require(rollback.get("rollback_execution_ready") is True
            and rollback.get("binding_strategy") == "fresh_saved_CAS_after_exact_Save"
            and rollback.get("backup") == accepted["row"]["backup"]
            and rollback.get("candidate") == accepted["row"]["candidate"], "original exact backup and executable recovery plan required")
    if operation == "publish":
        # The protected restore dry-run correctly rejects the old baseline.
        # Successful rollback preview requires Saved CAS, so it is a later gate.
        before = doc(root, accepted["row"]["backup"])
        require(rollback.get("stage") == "before_Save"
                and rollback.get("restore_fields_sha256") == digest({k: before[k] for k in target["changed_fields"]})
                and rollback.get("required_after_Save") == ["fresh_SavedCAS", "completed_publish_permit_and_run",
                    "successful_protected_rollback_preview", "independent_rollback_acceptance", "new_single_use_rollback_permit"],
                "before-Save plan must retain every later SavedCAS/review/permit gate")
        source_pin = rollback.get("source_verification")
        require(isinstance(source_pin, dict) and source_pin in check.get("evidence", []), "reviewed deployed recovery source proof required")
        source = doc(root, source_pin)
        require(all(source.get(k) == v for k, v in expected.items())
                and source.get("status") == "DEPLOYED_RESTORE_IMPLEMENTATION_VERIFIED"
                and source.get("repository") == "wangchaozhuanyong/zhuangxiuwangzhan"
                and re.fullmatch(r"[0-9a-f]{40}", str(source.get("production_sha", "")))
                and source.get("saved_CAS_required") is True and source.get("protected_route") == "content-publish"
                and source.get("successful_rollback_preview_performed") is False,
                "deployed original recovery implementation required; no fabricated pre-Save recovery PASS")
        deployment = doc(root, source.get("deployment_record"))
        require(deployment.get("status") == "DEPLOYED" and deployment.get("actual_execution") is True
                and deployment.get("repository") == source["repository"]
                and deployment.get("production_sha") == source["production_sha"], "exact actual deployment/source version required")
        snapshots = source.get("source_snapshots", [])
        require(isinstance(snapshots, list) and len(snapshots) >= 2
                and {p.get("path", "").rsplit("/", 1)[-1] for p in snapshots} >= {"service.ts", "managed-targets.ts"}
                and deployment.get("source_snapshots") == snapshots,
                "frozen deployed restore source snapshots must belong to the same actual deployment")
        for frozen in snapshots:
            pin(root, frozen)
        if "actual_machine_source" in accepted or source["production_sha"] != machine["main_sha"]:
            require(source.get("source_coherence") in check.get("evidence", [])
                    and isinstance(source.get("source_coherence"), dict),
                    "reviewed cross-commit deployed recovery source coherence required")
            source_coherence(root, source, deployment, machine, accepted)
        if rollback.get("guard_evidence") is not None:
            guard = doc(root, rollback["guard_evidence"])
            require(guard.get("http_status") == 409 and guard.get("performed_write") is False
                    and guard.get("external_writes") == 0 and guard.get("expected_baseline_rejection") is True
                    and guard.get("successful_rollback_preview_performed") is False,
                    "a pre-Save 409 proves the baseline guard, never a recovery PASS")
    else:
        require(rollback.get("stage") == "after_Save"
                and rollback.get("completed_parent") == accepted["completed_parent"]
                and rollback.get("saved_record") == accepted["saved_record"], "actual after-Save recovery binding required")
        # validate_machine has already matched the successful rollback preview,
        # fresh Saved CAS, exact actor/run/source and independently reviewed pins.
    return {**item, "authorized_project_scope": SCOPE, "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"]}


@strict
def decision(root, value, target, payload_sha256, accepted, now):
    require(accepted.get("acceptance_model") == MODEL, "bounded acceptance required")
    expected = {"department": ROLE, "assistant_chat_task_id": w.department_registry(root)[ROLE]["chat_binding"]["task_id"],
        "decision": "EXECUTE_AUTHORIZED_ACTION", "operation": accepted["operation"], "task_id": TASK,
        "action_id": target["action_id"] if accepted["operation"] == "publish" else f"rollback-{VERSION}", "action_class": "cms_write", "scope": target["scope"],
        "candidate_version": accepted["candidate_version"], "record_id": target["record_id"], "payload_sha256": payload_sha256,
        "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"],
        "controller_decision_record_id": accepted["candidate_acceptance_record_id"],
        "review_outbox": accepted["review_outbox"], "review_plan": accepted["review_plan"],
        "authorization_pin": accepted["authorization_pin"]}
    verified_preflight = preflight(root, w.read_json(w.snapshot_path(root, TASK)), expected["action_id"],
                                  "cms_write", target["scope"], PRODUCER)
    require(verified_preflight.get("payload_sha256") == payload_sha256, "routine decision cannot replace reviewed row payload")
    expected["machine_identity"] = verified_preflight["machine_identity"]
    require(all(value.get(k) == v for k, v in expected.items()) and value.get("decision_id")
            and not value.get("qa_receipt_id"), "exact routine continue; no invented QA receipt")
    fresh = acceptance(root, w.read_json(w.snapshot_path(root, TASK)), target, accepted["operation"])
    require(fresh == accepted, "candidate acceptance changed before production decision")
    stamp = w._parse_observed_at(value.get("decided_at"))
    row = next(r for r in w._result_handoff_rows(root, TASK) if r["record_id"] == accepted["candidate_acceptance_record_id"])
    continued = w._parse_observed_at(row["created_at"])
    require(stamp is not None and continued <= stamp <= now and now - dt.timedelta(hours=24) <= stamp,
            "fresh original continue decision required")
    return value
