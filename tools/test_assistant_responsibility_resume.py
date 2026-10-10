"""Synthetic original responsibility chains; never sends native messages.

Exercise actual goal initialization, routing policy and receipt entry points.
All fixtures are owned by this delivery, outside the live shared ledgers.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import workflow_control as w
import goal_delivery_runtime as runtime
import test_goal_result_coordination as claims
import test_workflow_control as legacy


def _project_test_tmp(source_file: Path) -> Path:
    """Use the owning project's existing test-output convention in either layout."""
    for project in source_file.resolve().parents:
        if ((project / "AGENTS.md").is_file()
                and (project / "data/task-contract.json").is_file()
                and (project / "tools/workflow_control.py").is_file()):
            test_tmp = (project / ".test-tmp").resolve()
            if not test_tmp.is_relative_to(project):
                raise RuntimeError("test output must remain inside its owning project")
            return test_tmp
    raise RuntimeError("owning FLASH CAST project required for test output")


TMP = _project_test_tmp(Path(__file__))
ASSISTANT = "operations-assistant-3"
SCOPE = "project:flashcast:synthetic-original-responsibility:v1"


class AssistantResponsibilityResumeTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.fixture = legacy.WorkflowControlTests("runTest")
        original = tempfile.TemporaryDirectory
        with mock.patch.object(tempfile, "TemporaryDirectory",
                               side_effect=lambda *a, **k: original(*a, dir=TMP, **k)):
            self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        claims.configure(self.root)
        self.task_id = "assistant-original-responsibility-synthetic-001"
        self.scope = SCOPE
        self.send_path = "reports/original-native-send.json"
        self.ack_path = "reports/original-native-ack.json"

    def write(self, path, document):
        w.atomic_write_json(self.root / path, document)
        return path

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, self.task_id))

    def initialize(self, **changes):
        goal = {
            **claims.goal(ASSISTANT),
            "objective": "Resume the original prepared-only responsibility using its actual source",
            "primary_owner": "operations",
            "producer_departments": ["operations"],
            "authorized_scope": [self.scope],
            "parent_task_id": "synthetic-parent-upgrade-001",
            "coordination_review_contract": {
                "task_id": self.task_id, "producer": "operations", "reviewer": ASSISTANT,
                "not_professional_producer": True, "prepared_only": True,
                "technical_acceptor": "operations-assistant-2", "cleanup_tool_producer": "paid-growth-data",
                "review_subject": "Synthetic original coordination responsibility, no platform actions",
            },
            **changes,
        }
        goal["human_authorization"] = {
            **goal["human_authorization"], "executor": goal["primary_owner"], "scope": self.scope,
        }
        path = self.write("drafts/operations/original-goal.json", goal)
        runtime.initialize_goal(self.root, self.task_id, path)
        self.fixture.task_id = self.task_id
        self.fixture.routing_decisions = {}
        self.assertEqual(self.snapshot()["departments"][-1]["depends_on"], ["operations"])
        return goal

    def requested(self, **changes):
        binding = w.department_registry(self.root)[ASSISTANT]["chat_binding"]
        payload = self.root / "reports/read-only-resume-message.txt"
        payload.write_text(self.task_id + " Resume the original exact read-only scope " + self.scope,
                           encoding="utf-8")
        request = {
            "task_id": self.task_id, "department": "operations", "action_class": "thread_message",
            "action_id": "resume-original-read-only-responsibility-v1", "scope": self.scope,
            "source_project_id": "flashcast-test-project", "target_project_id": binding["project_id"],
            "target_department": ASSISTANT, "target_thread_id": binding["task_id"],
            "target_thread_title": binding["title"], "target_cwd": binding["cwd"],
            "target_sidebar_section_id": binding["sidebar_section_id"],
            "payload_sha256": w.file_digest(self.root, "reports/read-only-resume-message.txt")["sha256"],
        }
        return {**request, **changes}

    def policy(self, request=None):
        return w.policy_check(self.root, **(request or self.requested()))[0]

    @staticmethod
    def envelope(document, **changes):
        return {"content": [{"type": "text", "text": json.dumps(document)}], "isError": False, **changes}

    def initial_assignment(self, *, send=True, ack=True):
        # Bounded deterministic chronology, including second-resolution legacy receipts.
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.policy_time = (now - dt.timedelta(seconds=90)).isoformat()
        self.send_time = (now - dt.timedelta(seconds=60)).isoformat()
        self.ack_time = (now - dt.timedelta(seconds=20)).isoformat()
        self.ack_started = (now - dt.timedelta(seconds=40)).timestamp()
        request = self.requested(action_id="assign-goal-review:" + self.task_id,
                                 payload_sha256=self.snapshot()["goal_contract"]["sha256"])
        with mock.patch.object(w, "utc_timestamp", return_value=self.policy_time):
            decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision.get("reason"))
        self.initial_decision_id = decision["decision_id"]
        binding = w.department_registry(self.root)[ASSISTANT]["chat_binding"]
        self.send_document = self.envelope({"threadId": binding["task_id"]})
        self.ack_document = self.envelope({
            "schemaVersion": 1,
            "thread": {"id": binding["task_id"], "title": binding["title"], "cwd": binding["cwd"],
                       "projectId": binding["project_id"], "status": {"type": "active"}},
            "turns": [{"id": "synthetic-original-ack-turn", "status": "inProgress", "error": None,
                       "startedAt": self.ack_started, "items": [
                           {"type": "agentMessage", "id": "synthetic-original-ack-message",
                            "text": "I accept the original exact prepared-only responsibility.",
                            "phase": "commentary"},
                       ]}],
        })
        if send:
            self.write(self.send_path, self.send_document)
        if ack:
            self.write(self.ack_path, self.ack_document)
        with mock.patch.object(w, "utc_timestamp", return_value=self.send_time):
            self.fixture.receipt("dispatch_sent", ASSISTANT, "original-responsibility-send",
                                 policy_decision_id=decision["decision_id"], action_id=request["action_id"],
                                 action_class="thread_message", scope=self.scope,
                                 evidence=self.send_path if send else "")
        with mock.patch.object(w, "utc_timestamp", return_value=self.ack_time):
            self.fixture.receipt("chat_ack", ASSISTANT, "original-responsibility-ack",
                                 evidence=self.ack_path if ack else "")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])

    def prepare(self, **changes):
        self.initialize(**changes)
        self.initial_assignment()

    def rewrite_receipts(self, change):
        path = w.receipts_path(self.root, self.task_id)
        rows = w.read_jsonl(path)
        change(rows)
        previous = ""
        for row in rows:
            row["previous_hash"] = previous
            row["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(row))
            previous = row["receipt_hash"]
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        return rows

    def rewrite_native(self, path, document):
        self.write(path, document)
        pin = w.file_digest(self.root, path)
        self.rewrite_receipts(lambda rows: [
            row.update(evidence=[pin if item["path"] == path else item for item in row["evidence"]])
            for row in rows
        ])

    def rewrite_initial_policy(self, **changes):
        path = self.root / w.POLICY_DECISIONS
        rows = w.read_jsonl(path)
        for row in rows:
            if row.get("decision_id") == self.initial_decision_id:
                row.update(changes)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def assert_dependency_denied(self, request=None):
        decision = self.policy(request)
        self.assertEqual(decision["status"], "deny", decision)
        self.assertIn("goal_dispatch_dependency_missing:operations", decision.get("reason", []))
        return decision

    def helper(self, **changes):
        request = self.requested()
        fields = {"sender_department": request["department"], "target_department": request["target_department"],
                  "target_thread_id": request["target_thread_id"], "scope": request["scope"],
                  "payload_sha256": request["payload_sha256"], **changes}
        receipts, invalid = w._validate_receipt_chain(self.root, self.task_id)
        self.assertEqual(invalid, [])
        return w._coordination_responsibility_resume_ready(self.root, self.snapshot(), receipts, **fields)

    def early_received_input(self):
        """Model a native input caused by the exact send before receipt registration."""
        binding = w.department_registry(self.root)["operations"]["chat_binding"]
        body = w.safe_path(self.root, self.snapshot()["goal_contract"]["path"]).read_text(encoding="utf-8")
        return {"type": "functionCallOutput", "id": "synthetic-actual-received-original-message",
                "name": "send_message_to_thread", "namespace": "codex_app", "output": {
                    "truncated": False,
                    "text": "<codex_delegation>\n  <source_thread_id>" + binding["task_id"]
                    + "</source_thread_id>\n  <input>" + body + "</input>\n</codex_delegation>"}}

    def set_early_ack(self, received):
        native = json.loads(self.ack_document["content"][0]["text"])
        native["turns"][0]["startedAt"] = dt.datetime.fromisoformat(self.send_time).timestamp() - 3
        if received is not None:
            native["turns"][0]["items"].insert(0, received)
        self.rewrite_native(self.ack_path, self.envelope(native))
        return native

    def test_exact_native_send_input_before_receipt_registration_allows_resume(self):
        self.prepare()
        self.set_early_ack(self.early_received_input())
        self.assertTrue(self.helper())
        decision = self.policy()
        self.assertEqual(decision["status"], "allow", decision.get("reason"))

    def test_old_health_ack_before_actual_send_without_received_input_is_denied(self):
        self.prepare()
        self.set_early_ack(None)
        self.assertFalse(self.helper())
        self.assert_dependency_denied()

    def test_early_received_foreign_sender_is_denied(self):
        self.prepare()
        item = self.early_received_input()
        item["output"]["text"] = item["output"]["text"].replace(
            "<source_thread_id>", "<source_thread_id>foreign-", 1)
        self.set_early_ack(item)
        self.assertFalse(self.helper())

    def test_early_received_other_task_or_changed_utf8_is_denied(self):
        self.prepare()
        item = self.early_received_input()
        item["output"]["text"] = item["output"]["text"].replace(
            "</input>", " different original task</input>", 1)
        self.set_early_ack(item)
        self.assertFalse(self.helper())

    def test_truncated_early_native_input_is_denied(self):
        self.prepare()
        item = self.early_received_input()
        item["output"]["truncated"] = True
        self.set_early_ack(item)
        self.assertFalse(self.helper())

    def test_later_original_input_does_not_rebind_old_health_turn(self):
        self.prepare()
        native = self.set_early_ack(None)
        native["turns"][0]["items"].append(self.early_received_input())
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assertFalse(self.helper())

    def test_early_native_input_before_policy_is_denied(self):
        self.prepare()
        native = self.set_early_ack(self.early_received_input())
        native["turns"][0]["startedAt"] = dt.datetime.fromisoformat(self.policy_time).timestamp() - 1
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assertFalse(self.helper())

    def test_native_send_turn_id_cannot_match_a_different_ack_turn(self):
        self.prepare()
        self.set_early_ack(self.early_received_input())
        binding = w.department_registry(self.root)[ASSISTANT]["chat_binding"]
        self.rewrite_native(self.send_path, self.envelope({"threadId": binding["task_id"], "turnId": "foreign-turn"}))
        self.assertFalse(self.helper())

    def test_missing_early_native_output_is_denied(self):
        self.prepare()
        item = self.early_received_input()
        item.pop("output")
        self.set_early_ack(item)
        self.assertFalse(self.helper())

    def test_existing_actual_responsibility_resumes_without_operations_outbox(self):
        self.prepare()
        self.assertTrue(self.helper())
        decision = self.policy()
        self.assertEqual(decision["status"], "allow", decision.get("reason"))
        self.assertFalse(any(row.get("receipt_type") == "outbox_received"
                             and row.get("department") == "operations"
                             for row in w.read_jsonl(w.receipts_path(self.root, self.task_id))))

    def test_resume_allow_remains_recordable_and_duplicate_action_is_denied(self):
        self.prepare()
        request = self.requested()
        decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision.get("reason"))
        self.fixture.receipt("dispatch_sent", ASSISTANT, "synthetic-resume-success",
                             policy_decision_id=decision["decision_id"], action_id=request["action_id"],
                             action_class=request["action_class"], scope=request["scope"], evidence=self.send_path)
        again = self.policy(request)
        self.assertEqual(again["status"], "deny")
        self.assertIn("thread_dispatch_exact_action_already_sent", again["reason"])
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])

    def test_no_original_dispatch_source_is_denied(self):
        self.initialize()
        self.assert_dependency_denied()

    def test_missing_actual_native_send_is_denied(self):
        self.initialize()
        self.initial_assignment(send=False)
        self.assert_dependency_denied()

    def test_missing_actual_native_ack_is_denied(self):
        self.initialize()
        self.initial_assignment(ack=False)
        self.assert_dependency_denied()

    def test_boolean_ack_without_ack_receipt_does_not_suffice(self):
        self.prepare()
        self.rewrite_receipts(lambda rows: rows.pop())
        self.assert_dependency_denied()

    def test_frozen_native_pin_drift_is_denied(self):
        self.prepare()
        (self.root / self.send_path).write_text("{}", encoding="utf-8")
        self.assert_dependency_denied()

    def test_native_send_wrong_thread_is_denied_with_rehashed_receipts(self):
        self.prepare()
        self.rewrite_native(self.send_path, self.envelope({"threadId": "foreign-fixed-thread"}))
        self.assert_dependency_denied()

    def test_native_send_error_envelope_is_denied_with_rehashed_receipts(self):
        self.prepare()
        self.rewrite_native(self.send_path, {**self.send_document, "isError": True})
        self.assert_dependency_denied()

    def test_native_ack_error_envelope_is_denied_with_rehashed_receipts(self):
        self.prepare()
        self.rewrite_native(self.ack_path, {**self.ack_document, "isError": True})
        self.assert_dependency_denied()

    def test_ack_before_original_send_is_denied_with_rehashed_receipts(self):
        self.prepare()
        native = json.loads(self.ack_document["content"][0]["text"])
        native["turns"][0]["startedAt"] = dt.datetime.fromisoformat(self.send_time).timestamp() - 1
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assert_dependency_denied()

    def test_ack_after_observed_ack_is_denied_with_rehashed_receipts(self):
        self.prepare()
        native = json.loads(self.ack_document["content"][0]["text"])
        native["turns"][0]["startedAt"] = dt.datetime.fromisoformat(self.ack_time).timestamp() + 1
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assert_dependency_denied()

    def test_ack_empty_user_or_error_turn_is_denied_with_rehashed_receipts(self):
        self.prepare()
        original = json.loads(self.ack_document["content"][0]["text"])
        for change in ({"text": " "}, {"type": "userMessage"}, {"id": ""}):
            with self.subTest(change=change):
                native = copy.deepcopy(original)
                native["turns"][0]["items"][0].update(change)
                self.rewrite_native(self.ack_path, self.envelope(native))
                self.assert_dependency_denied()
        native = copy.deepcopy(original)
        native["turns"][0]["error"] = {"message": "synthetic failure"}
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assert_dependency_denied()

    def test_ack_fixed_thread_identity_mismatch_is_denied_with_rehashed_receipts(self):
        self.prepare()
        original = json.loads(self.ack_document["content"][0]["text"])
        for key, value in (("id", "foreign-thread"), ("title", "foreign-title"),
                           ("cwd", "/unrelated-project"), ("projectId", "foreign-project")):
            with self.subTest(field=key):
                native = copy.deepcopy(original)
                native["thread"][key] = value
                self.rewrite_native(self.ack_path, self.envelope(native))
                self.assert_dependency_denied()

    def test_raw_ack_without_optional_project_id_remains_supported(self):
        self.prepare()
        native = json.loads(self.ack_document["content"][0]["text"])
        native["thread"].pop("projectId")
        self.rewrite_native(self.ack_path, self.envelope(native))
        self.assertEqual(self.policy()["status"], "allow")

    def test_initial_policy_must_bind_exact_original_contract_payload(self):
        self.prepare()
        self.rewrite_initial_policy(payload_sha256="f" * 64)
        self.assert_dependency_denied()

    def test_initial_policy_must_be_from_original_coordinator(self):
        self.prepare()
        self.rewrite_initial_policy(department="operations-assistant-2")
        self.assert_dependency_denied()

    def test_initial_policy_must_be_allow_and_original_fixed_identity(self):
        self.prepare()
        policy_path = self.root / w.POLICY_DECISIONS
        original = policy_path.read_bytes()
        for changes in ({"status": "deny"}, {"target_project_id": "foreign-project"},
                        {"source_project_id": "foreign-project"}, {"target_thread_title": "foreign-title"},
                        {"target_cwd": "/foreign-project"}, {"target_sidebar_section_id": "foreign-sidebar"},
                        {"target_thread_id": "foreign-thread"}, {"target_department": "operations-assistant-2"}):
            with self.subTest(changes=changes):
                policy_path.write_bytes(original)
                self.rewrite_initial_policy(**changes)
                self.assert_dependency_denied()

    def test_initial_policy_cannot_postdate_actual_dispatch(self):
        self.prepare()
        self.rewrite_initial_policy(checked_at=self.ack_time)
        self.assert_dependency_denied()

    def test_changed_current_human_evidence_does_not_resume(self):
        self.prepare()
        auth_path = self.snapshot()["goal_delivery"]["authorization_pin"]["path"]
        with (self.root / auth_path).open("a", encoding="utf-8") as handle:
            handle.write("\n")
        self.assert_dependency_denied()

    def test_changed_frozen_goal_contract_bytes_do_not_resume(self):
        self.prepare()
        path = self.snapshot()["goal_contract"]["path"]
        with (self.root / path).open("a", encoding="utf-8") as handle:
            handle.write("\n")
        self.assert_dependency_denied()

    def test_mutable_snapshot_responsibility_flags_do_not_manufacture_source(self):
        self.initialize(coordination_review_contract={"task_id": self.task_id, "producer": "operations",
                                                      "reviewer": ASSISTANT, "prepared_only": False,
                                                      "not_professional_producer": False})
        self.initial_assignment()
        snapshot = self.snapshot()
        snapshot["goal_delivery"]["coordination_review_contract"].update(
            prepared_only=True, not_professional_producer=True)
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        self.assert_dependency_denied()

    def test_ordinary_professional_goal_keeps_operations_result_dependency(self):
        self.initialize(coordination_review_contract={})
        self.initial_assignment()
        self.assert_dependency_denied()

    def test_wrong_scope_or_project_cannot_reuse_original_responsibility(self):
        self.prepare()
        for changes in ({"scope": "project:flashcast:foreign:v1"},
                        {"target_project_id": "foreign-project"}, {"source_project_id": "foreign-project"}):
            with self.subTest(changes=changes):
                result = self.policy(self.requested(**changes))
                self.assertEqual(result["status"], "deny", result)

    def test_foreign_sender_or_reviewer_does_not_inherit_source(self):
        self.prepare()
        self.assertFalse(self.helper(sender_department="operations-assistant-2"))
        self.assertFalse(self.helper(target_department="operations-assistant-2",
                                     target_thread_id="fixed-operations-assistant-2"))
        self.assertEqual(self.policy(self.requested(department="paid-growth-data"))["status"], "deny")

    def test_changed_current_reviewer_and_self_review_are_denied(self):
        self.prepare()
        original = self.snapshot()
        for changes in ({"responsible_assistant": "operations-assistant-2"},
                        {"producer_departments": ["operations", ASSISTANT]}):
            with self.subTest(changes=changes):
                snapshot = copy.deepcopy(original)
                snapshot["goal_delivery"].update(changes)
                w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
                self.assert_dependency_denied()

    def test_other_professional_dependency_is_not_waived(self):
        self.prepare()
        snapshot = self.snapshot()
        planned = next(row for row in snapshot["departments"] if row["department"] == ASSISTANT)
        planned["depends_on"].append("paid-growth-data")
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        result = self.policy()
        self.assertEqual(result["status"], "deny")
        self.assertIn("goal_dispatch_dependency_missing:paid-growth-data", result["reason"])
        self.assertNotIn("goal_dispatch_dependency_missing:operations", result["reason"])

    def test_named_external_dependency_is_not_waived(self):
        self.initialize(dependencies=[{"id": "original-tool-adoption", "owner": "paid-growth-data",
                                       "scope": self.scope, "unblock_condition": "Synthetic independent actual adoption",
                                       "applies_to": [ASSISTANT]}])
        # This dependency already blocks the first assignment; do not fabricate
        # a historic allow/ACK solely to manufacture a resumption fixture.
        initial = self.requested(action_id="assign-goal-review:" + self.task_id,
                                 payload_sha256=self.snapshot()["goal_contract"]["sha256"])
        for request in (initial, self.requested()):
            with self.subTest(action=request["action_id"]):
                result = self.policy(request)
                self.assertEqual(result["status"], "deny")
                self.assertIn("goal_dispatch_named_dependency_missing:original-tool-adoption", result["reason"])

    def test_terminal_successor_and_plan_gates_are_not_waived(self):
        self.prepare()
        original = self.snapshot()
        for changes, expected in (({"current_state": "closed"}, "thread_dispatch_workflow_terminal"),
                                  ({"workflow_successor_link": {"task_id": "synthetic-next"}},
                                   "thread_dispatch_existing_successor_no_redispatch"),
                                  ({"plan_status": "blocked"}, "thread_dispatch_plan_not_ready")):
            with self.subTest(changes=changes):
                w.atomic_write_json(w.snapshot_path(self.root, self.task_id), {**original, **changes})
                result = self.policy()
                self.assertEqual(result["status"], "deny")
                self.assertIn(expected, result["reason"])

    def test_original_assignment_action_cannot_be_resent(self):
        self.prepare()
        result = self.policy(self.requested(action_id="assign-goal-review:" + self.task_id,
                                            payload_sha256=self.snapshot()["goal_contract"]["sha256"]))
        self.assertEqual(result["status"], "deny")
        self.assertIn("thread_dispatch_exact_action_already_sent", result["reason"])

    def test_read_only_resume_does_not_grant_production_action_authority(self):
        self.prepare()
        for action_class in ("site_publish", "ads_write", "cms_write"):
            with self.subTest(action_class=action_class):
                result = self.policy(self.requested(action_class=action_class,
                                                    action_id="synthetic-production-action-" + action_class))
                self.assertEqual(result["status"], "deny", result)
                self.assertFalse(result.get("approval_consumed", False))

    def test_receipt_or_event_chain_damage_cannot_manufacture_resume(self):
        self.prepare()
        receipt_path = w.receipts_path(self.root, self.task_id)
        original = receipt_path.read_bytes()
        rows = w.read_jsonl(receipt_path)
        rows[-1]["receipt_hash"] = "f" * 64
        receipt_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.assert_dependency_denied()
        receipt_path.write_bytes(original)
        event_path = self.root / w.WORKFLOW_EVENTS
        events = w.read_jsonl(event_path)
        events[-1]["event_hash"] = "f" * 64
        event_path.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")
        self.assert_dependency_denied()

    def test_direct_precheck_missing_sender_or_payload_does_not_inherit_source(self):
        self.prepare()
        request = self.requested()
        fields = {key: request[key] for key in
                  ("task_id", "target_department", "target_thread_id", "action_id", "scope")}
        for extra in ({}, {"sender_department": "operations"},
                      {"payload_sha256": request["payload_sha256"]}):
            with self.subTest(fields=extra):
                reasons = w._ordinary_thread_dispatch_precheck(self.root, snapshot=self.snapshot(), **fields, **extra)
                self.assertIn("goal_dispatch_dependency_missing:operations", reasons)

    def test_missing_or_ambiguous_original_policy_is_denied(self):
        self.prepare()
        path = self.root / w.POLICY_DECISIONS
        rows = w.read_jsonl(path)
        source = next(row for row in rows if row.get("decision_id") == self.initial_decision_id)
        for replacements in ([], [source, copy.deepcopy(source)]):
            with self.subTest(source_count=len(replacements)):
                changed = [row for row in rows if row.get("decision_id") != self.initial_decision_id] + replacements
                path.write_text("".join(json.dumps(row) + "\n" for row in changed), encoding="utf-8")
                self.assert_dependency_denied()

    def test_ack_invalid_started_at_or_turn_status_is_denied(self):
        self.prepare()
        original = json.loads(self.ack_document["content"][0]["text"])
        for changes in ({"startedAt": True}, {"startedAt": "not-a-native-timestamp"},
                        {"startedAt": None}, {"id": ""}, {"status": "failed"}):
            with self.subTest(changes=changes):
                native = copy.deepcopy(original)
                native["turns"][0].update(changes)
                self.rewrite_native(self.ack_path, self.envelope(native))
                self.assert_dependency_denied()

    def test_duplicate_native_sends_cannot_manufacture_unique_original_send(self):
        self.prepare()
        self.rewrite_receipts(lambda rows: rows[0].update(evidence=rows[0]["evidence"] * 2))
        self.assert_dependency_denied()

    def test_declared_production_goal_does_not_inherit_prepared_only_exception(self):
        self.prepare(required_execution_actions=[{"action_id": "synthetic-declared-site-publish",
                                                  "action_class": "site_publish", "scope": self.scope,
                                                  "department": "operations"}])
        self.assert_dependency_denied()

    def test_appended_malformed_receipt_line_is_rejected_even_if_legacy_reader_skips_it(self):
        self.prepare()
        with w.receipts_path(self.root, self.task_id).open("a", encoding="utf-8") as handle:
            handle.write("{malformed-synthetic-receipt\n")
        self.assert_dependency_denied()


if __name__ == "__main__":
    unittest.main()
