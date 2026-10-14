"""Exact same-goal authority and internal repairs; no native sends or platform writes."""
import copy
import unittest

import goal_delivery_runtime as runtime
import test_goal_runtime_consumers as fixtures
import workflow_control as w


class AuthorizationPrecheckTests(unittest.TestCase):
    setUp = fixtures.GoalRuntimeConsumerTests.setUp
    write = fixtures.GoalRuntimeConsumerTests.write
    make_goal = fixtures.GoalRuntimeConsumerTests.make_goal
    initialize = fixtures.GoalRuntimeConsumerTests.initialize
    requested = fixtures.GoalRuntimeConsumerTests.requested
    snapshot = fixtures.GoalRuntimeConsumerTests.snapshot

    def check(self, **changes):
        request = {**self.requested(sender=fixtures.PRODUCER), **changes}
        before = w.snapshot_path(self.root, self.task_id).read_bytes()
        result = runtime.authorization_precheck(self.root, self.task_id, request)
        self.assertEqual(before, w.snapshot_path(self.root, self.task_id).read_bytes())
        self.assertFalse(result["external_permission_issued"])
        self.assertFalse(result["actual_action_allowed"])
        self.assertFalse(result["writes_performed"])
        return result

    def test_same_scope_new_version_and_message_do_not_need_new_owner_permission(self):
        self.initialize()
        for version in ("v1", "v99"):
            result = self.check(candidate_version=version, action_id="new-bounded-message-" + version)
            self.assertEqual(result["status"], "within_original_authorization")
            self.assertFalse(result["needs_human_confirmation"])

    def test_each_internal_repair_stays_internal_and_does_not_become_permission(self):
        self.initialize()
        for repair in ("health", "binding", "source_binding", "payload", "receipt", "self_check", "backup", "rollback", "version_update"):
            with self.subTest(repair=repair):
                result = self.check(internal_repairs=[repair])
                self.assertEqual(result["status"], "internal_repair_required")
                self.assertFalse(result["needs_human_confirmation"])

    def test_sensitive_delta_is_not_hidden_by_internal_health_repair(self):
        self.initialize()
        for change in ("new_scope", "new_department", "new_project", "new_account", "permission_expansion",
                       "new_fee", "budget_exceeded", "irreversible_delete", "major_security_change", "infrastructure_change"):
            with self.subTest(change=change):
                result = self.check(authorization_changes=[change], internal_repairs=["health"])
                self.assertTrue(result["needs_human_confirmation"])
                self.assertIn(change, result["reasons"])

    def test_different_page_scope_is_not_inherited(self):
        self.initialize()
        self.assertTrue(self.check(scope="other-project:new-page")["needs_human_confirmation"])

    def test_unlisted_collaborator_requires_new_scope(self):
        self.initialize()
        self.assertTrue(self.check(target_department="paid-growth-data")["needs_human_confirmation"])

    def test_wrong_actual_project_is_binding_error_not_owner_reapproval(self):
        self.initialize()
        result = self.check(target_project_id="wrong-project")
        self.assertEqual(result["status"], "internal_repair_required")
        self.assertFalse(result["needs_human_confirmation"])

    def test_expansion_and_wrong_project_cannot_hide_each_other(self):
        self.initialize()
        result = self.check(target_project_id="wrong-project", authorization_changes=["new_fee"])
        self.assertTrue(result["needs_human_confirmation"])

    def test_predeclared_production_requires_its_existing_channel_even_without_reapproval(self):
        scope = "company.example:exact-cms-page"
        action = {"action_id": "save-exact-page", "action_class": "cms_write", "scope": scope,
                  "department": fixtures.PRODUCER}
        self.initialize(authorized_scope=[scope], required_execution_actions=[action])
        result = self.check(**action)
        self.assertEqual(result["status"], "within_original_authorization")
        self.assertIn("existing_production_channel", result["required_internal_checks"])
        self.assertFalse(result["needs_human_confirmation"])
        result = self.check(**{**action, "action_id": "different-save"})
        self.assertEqual(result["status"], "original_action_binding_required")

    def test_legacy_task_recovers_original_source_instead_of_fabricating_authority(self):
        self.initialize()
        snapshot = self.snapshot()
        snapshot.pop("goal_delivery")
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        result = self.check()
        self.assertEqual(result["status"], "original_source_binding_required")
        self.assertFalse(result["needs_human_confirmation"])

    def test_tampered_original_human_source_is_refused(self):
        self.initialize()
        source = self.root / self.snapshot()["goal_delivery"]["authorization_pin"]["path"]
        source.write_text("{}")
        with self.assertRaises(w.WorkflowError):
            self.check()

    def test_nonparticipant_and_wrong_task_are_refused(self):
        self.initialize()
        for changes in ({"sender_department": "paid-growth-data"}, {"task_id": "unrelated-goal-001"}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.check(**changes)

    def test_agent_message_cannot_replace_original_human_authority(self):
        self.initialize()
        snapshot = self.snapshot()
        source = copy.deepcopy(w.read_json(self.root / snapshot["goal_delivery"]["authorization_pin"]["path"]))
        source["message"]["type"] = "agentMessage"
        self.write("reports/agent-fake-authorization.json", source)
        snapshot["goal_delivery"]["authorization_pin"] = w.file_digest(self.root, "reports/agent-fake-authorization.json")
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        # Original event source wins over snapshot mutation.
        self.assertEqual(self.check()["status"], "within_original_authorization")
        with self.assertRaises(w.WorkflowError):
            runtime.validate_goal(self.root, {**self.make_goal(), "human_authorization": {
                **self.make_goal()["human_authorization"], "evidence_path": "reports/agent-fake-authorization.json"}})

    def test_unknown_flags_and_action_types_are_not_silently_accepted(self):
        self.initialize()
        for changes in ({"internal_repairs": ["ignore_all_approvals"]}, {"authorization_changes": ["blanket_permission"]},
                        {"action_class": "arbitrary-write"}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.check(**changes)

    def test_malformed_target_or_flags_fail_as_validation_instead_of_crashing(self):
        self.initialize()
        for changes in ({"authorization_changes": [{}]}, {"internal_repairs": [{}]},
                        {"target_department": []}, {"target_department": None},
                        {"action_class": "cms_write", "department": None}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.check(**changes)

    def test_closed_scope_is_not_reopened_or_reassigned_by_authorization_precheck(self):
        self.initialize()
        snapshot = self.snapshot()
        snapshot['current_state'] = 'closed'
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        result = self.check()
        self.assertEqual(result['status'], 'completed_scope_readback_required')
        self.assertFalse(result['needs_human_confirmation'])
        self.assertEqual(result['next_action'], 'read_actual_completion_and_preserve_remaining_scope')


if __name__ == "__main__":
    unittest.main()
