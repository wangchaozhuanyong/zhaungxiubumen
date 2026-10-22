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


class OwnerDelegatedDecisionTests(unittest.TestCase):
    """Synthetic decision tests; no owner source, business event or pilot is fabricated."""

    write=AuthorizationPrecheckTests.write
    make_goal=AuthorizationPrecheckTests.make_goal
    initialize=AuthorizationPrecheckTests.initialize
    requested=AuthorizationPrecheckTests.requested
    snapshot=AuthorizationPrecheckTests.snapshot
    check=AuthorizationPrecheckTests.check

    def setUp(self):
        AuthorizationPrecheckTests.setUp(self)
        self.initialize()
        registry=w.read_json(self.root/'data/department-registry.json')
        row=next(x for x in registry['departments'] if x['id']=='operations')
        row['chat_binding']['cwd']=str(self.root)
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        fixed=row['chat_binding']
        document={'source_thread_id':fixed['task_id'],'source_turn_id':'fixture-owner-turn',
                  'message':{'type':'userMessage','id':'fixture-owner-message','content':[
                      {'type':'text','text':'Synthetic current-project nonpayment decision delegation.'}]},
                  'actual_native_thread':{'id':fixed['task_id'],'cwd':str(self.root)}}
        source=self.write('reports/fixture-owner-decision-source.json',document)
        profile={'pin':w.file_digest(self.root,source),'source_thread_id':fixed['task_id'],
                 'source_turn_id':'fixture-owner-turn','source_message_id':'fixture-owner-message',
                 'cwd':str(self.root),'project_id':fixed['project_id']}
        from unittest import mock
        patcher=mock.patch.object(runtime,'_OWNER_DECISION_SOURCE',profile)
        patcher.start();self.addCleanup(patcher.stop)

    def test_related_necessary_implementation_is_same_goal_without_new_permission(self):
        result=self.check(action_class='internal_control_candidate')
        self.assertEqual(result['status'],'within_original_authorization')
        self.assertFalse(result['needs_human_confirmation'])
        self.assertEqual(result['decision_owner'],fixtures.PRODUCER)
        self.assertTrue(result['decision_delegation']['execution_authority_unchanged'])

    def test_original_roles_continue_without_an_owner_online_dependency(self):
        for sender in (fixtures.PRODUCER,fixtures.ASSISTANT,'operations'):
            with self.subTest(sender=sender):
                result=self.check(sender_department=sender)
                self.assertEqual(result['status'],'within_original_authorization')
                self.assertFalse(result['needs_human_confirmation'])
                self.assertEqual(result['decision_owner'],sender)

    def test_nonpayment_changes_route_to_HQ_but_do_not_authorize_execution(self):
        for change in ('new_scope','new_department','new_project','new_account','permission_expansion',
                       'irreversible_delete','major_security_change','infrastructure_change'):
            with self.subTest(change=change):
                result=self.check(authorization_changes=[change])
                self.assertEqual(result['status'],'authorization_change_required')
                self.assertFalse(result['needs_human_confirmation'])
                self.assertEqual(result['next_owner'],'operations')
                self.assertTrue(result['blocks_only_dependent_action'])
                self.assertFalse(result['actual_action_allowed'])

    def test_payments_and_new_fees_still_require_actual_owner(self):
        for changes in (['new_fee'],['budget_exceeded'],['new_scope','new_fee']):
            result=self.check(authorization_changes=changes,internal_repairs=['source_binding'])
            self.assertTrue(result['needs_human_confirmation'])
            self.assertEqual(result['next_owner'],'human_owner')
            self.assertEqual(result['next_action'],'ask_owner_for_exact_payment')
            self.assertEqual(result['status'],'authorization_change_required')

    def test_internal_source_repair_does_not_become_owner_reapproval_or_permission(self):
        result=self.check(internal_repairs=['source_binding','receipt'])
        self.assertEqual(result['status'],'internal_repair_required')
        self.assertFalse(result['needs_human_confirmation'])
        self.assertEqual(result['next_owner'],fixtures.PRODUCER)
        self.assertFalse(result['external_permission_issued'])

    def test_HQ_decision_route_cannot_pass_normal_message_action_gate(self):
        from unittest import mock
        import goal_source_recovery as recovery
        req=self.requested(sender='operations');req['authorization_changes']=['new_scope']
        with mock.patch.object(w,'policy_check') as policy:
            result=recovery.prepare_message(self.root,req)
            self.assertEqual(result['status'],'blocked');policy.assert_not_called()
        self.assertFalse(result['authorization_precheck']['needs_human_confirmation'])

    def test_external_target_and_permit_requirements_survive_delegation(self):
        result=self.check(action_class='cms_write',action_id='unlisted-production',department=fixtures.PRODUCER)
        self.assertEqual(result['status'],'original_action_binding_required')
        self.assertFalse(result['actual_action_allowed'])
        self.assertIn('existing_production_channel',result['required_internal_checks'])

    def test_changed_or_agent_delegation_source_is_rejected(self):
        source=self.root/runtime._OWNER_DECISION_SOURCE['pin']['path'];source.write_text('{}')
        with self.assertRaises(w.WorkflowError):self.check()

    def test_other_project_cannot_inherit_the_current_owner_delegation(self):
        from unittest import mock
        other={**runtime._OWNER_DECISION_SOURCE,'cwd':str(self.root/'different-project')}
        with mock.patch.object(runtime,'_OWNER_DECISION_SOURCE',other):
            result=self.check(authorization_changes=['new_scope'])
        self.assertTrue(result['needs_human_confirmation'])
        self.assertNotIn('decision_delegation',result)

    def test_agent_or_wrong_native_source_is_not_a_human_delegation(self):
        from unittest import mock
        original=copy.deepcopy(w.read_json(self.root/runtime._OWNER_DECISION_SOURCE['pin']['path']))
        for field in ('agent','thread','turn','native_cwd','project'):
            doc=copy.deepcopy(original);profile=copy.deepcopy(runtime._OWNER_DECISION_SOURCE)
            if field=='agent':doc['message']['type']='agentMessage'
            elif field=='thread':doc['source_thread_id']='wrong-thread'
            elif field=='turn':doc['source_turn_id']='wrong-turn'
            elif field=='native_cwd':doc['actual_native_thread']['cwd']='other-project'
            else:profile['project_id']='other-project'
            path=self.write('reports/changed-owner-delegation.json',doc);profile['pin']=w.file_digest(self.root,path)
            with self.subTest(field=field),mock.patch.object(runtime,'_OWNER_DECISION_SOURCE',profile),self.assertRaises(w.WorkflowError):
                self.check()


if __name__ == "__main__":
    unittest.main()
