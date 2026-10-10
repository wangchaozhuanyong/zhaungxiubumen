"""Synthetic bounded project tests through actual transfer and reviewer consumers."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import goal_delivery_runtime as runtime
import qa_review_plan as review
import result_coordination as coordination
import technical_review_backup as backup
import test_goal_result_coordination as claims
import test_result_coordination as existing
import workflow_control as w

A2, A3 = "operations-assistant-2", "operations-assistant-3"
SCOPE = "project:flashcast:test-technical-backup:v1"


class TechnicalBackupTests(unittest.TestCase):
    receive = existing.ResultCoordinationIntegrationTests.receive
    claim = existing.ResultCoordinationIntegrationTests.claim
    draft = existing.ResultCoordinationIntegrationTests.draft
    claimed_request = existing.ResultCoordinationIntegrationTests.claimed_request
    set_goal = claims.GoalCoordinationTests.set_goal

    def setUp(self):
        output = Path(os.environ.get("TECHNICAL_BACKUP_TEST_OUTPUT", str(Path(__file__).resolve().parents[1] / ".test-tmp")))
        output.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(existing, "CANDIDATE", output), mock.patch.object(claims, "TMP", output):
            (output / ".test-tmp").mkdir(parents=True, exist_ok=True)
            claims.GoalCoordinationTests.setUp(self)
        self.set_goal(A2, authorized_scope=[SCOPE], human_authorization={
            **claims.goal(A2)["human_authorization"], "scope": SCOPE})
        self.install_backup()

    def install_backup(self, enabled=True):
        registry = w.read_json(self.root / "data/department-registry.json")
        row = next(item for item in registry["departments"] if item["id"] == A3)
        row["production_write_allowed"] = False
        row["professional_skill"] = "departments/operations-assistant-3/SKILL.md"
        skill = w.safe_path(self.root, row["professional_skill"])
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("Synthetic technical backup acceptance method, no authority.\n")
        methods = []
        for name in (backup.PRIMARY_METHOD, "web-dev-toolkit:design-acceptance"):
            path = self.root / "fixture-methods" / (name.split(":")[-1] + ".md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic acceptance resource, no production invocation.\n")
            methods.append({"name": name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "size": path.stat().st_size, "use": "independent affected-scope acceptance",
                            "production_tool_invocation_granted": False})
        manifest = {"schema_version": 1, "department": A3, "capability": "development_backup",
                    "mapped_acceptance_capability": "development", "use_scope": "independent_acceptance_only",
                    "required_methods": [backup.PRIMARY_METHOD], "methods": methods,
                    "production_write_allowed": False, "account_permissions_granted": False,
                    "producer_implementation_allowed": False}
        rel = "departments/operations-assistant-3/technical-backup-methods.json"
        w.atomic_write_json(self.root / rel, manifest)
        row["approved_subskills"] = [method["name"] for method in methods]
        row["approved_subskill_paths"] = [method["path"] for method in methods]
        row["coordination_authority"] = {"routine_decisions": True,
            "review_capabilities": ["paid", "data", "visual", "sales"] + (["development_backup"] if enabled else []),
            "technical_review_backup": {"enabled": enabled, "capability": "development_backup",
                "mapped_acceptance_capability": "development", "default_assistant": A2, "transfer_from": [A2],
                # Existing queue fixture uses this synthetic producer; real candidate is system-development only.
                "allowed_producer_departments": ["content-organic-website"],
                "allowed_scope_prefixes": ["project:flashcast:"], "explicit_transfer_required": True,
                "production_write_allowed": False, "professional_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
                "method_manifest": w.file_digest(self.root, rel)}}
        w.atomic_write_json(self.root / "data/department-registry.json", registry)

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))

    def mutate_role(self, callback):
        registry = w.read_json(self.root / "data/department-registry.json")
        callback(next(row for row in registry["departments"] if row["id"] == A3))
        w.atomic_write_json(self.root / "data/department-registry.json", registry)

    def transfer(self, lease, **changes):
        return self.a.transfer(self.identity, A2, A2, lease, A3, A3, "explicit-technical-transfer", **changes)

    def ready_lease(self):
        lease = self.a.claim(self.identity, A2, A2, "assigned-development")
        self.draft(lease)
        return lease

    def test_current_capability_shortage_rejects_without_mutation(self):
        self.install_backup(enabled=False)
        lease = self.ready_lease()
        with self.assertRaisesRegex(w.WorkflowError, "capability"):
            self.transfer(lease)
        self.assertEqual(self.a.readback(self.identity)["token"], lease["token"])
        self.assertEqual(self.snapshot()["goal_delivery"]["responsible_assistant"], A2)

    def test_no_default_assignment_or_unfenced_backup_claim(self):
        with self.assertRaisesRegex(w.WorkflowError, "assigned"):
            self.a.claim(self.identity, A3, A3, "cannot-steal")
        task_goal = copy.deepcopy(self.snapshot()["goal_delivery"])
        task_goal["responsible_assistant"] = A3
        with self.assertRaisesRegex(w.WorkflowError, "capability"):
            runtime.validate_goal(self.root, task_goal)
        forged = {**self.snapshot(), "goal_delivery": task_goal}
        with self.assertRaisesRegex(w.WorkflowError, "capable"):
            review._goal_reviewer(self.root, forged)

    def test_explicit_fenced_transfer_enables_same_goal_backup(self):
        lease = self.ready_lease()
        transferred = self.transfer(lease)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["goal_delivery"]["responsible_assistant"], A3)
        self.assertEqual(snapshot["goal_delivery"]["acceptance_capability"], "development")
        self.assertEqual(review._goal_reviewer(self.root, snapshot), A3)
        self.assertTrue(backup.review_capable(self.root, A3, snapshot["goal_delivery"], task_id=self.identity["task_id"]))
        self.assertGreater(transferred["fence"], lease["fence"])
        self.assertFalse(transferred["external_permission_issued"])
        self.a.renew(self.identity, A3, A3, transferred)
        with self.assertRaisesRegex(w.WorkflowError, "foreign coordination"):
            self.a.renew(self.identity, A2, A2, lease)
        self.assertEqual(len(snapshot["goal_delivery"]["assignment_history"]), 1)

    def test_missing_primary_whitelist_name_or_path_rejects(self):
        for field in ("approved_subskills", "approved_subskill_paths"):
            with self.subTest(field=field):
                self.install_backup()
                self.mutate_role(lambda row: row[field].pop(0))
                self.assertFalse(backup.review_capable(self.root, A3, self.snapshot()["goal_delivery"], transfer_from=A2))
        lease = self.ready_lease()
        with self.assertRaisesRegex(w.WorkflowError, "approved backup methods"):
            self.transfer(lease)
        self.assertEqual(self.a.readback(self.identity)["token"], lease["token"])

    def test_missing_or_changed_method_resource_and_skill_reject(self):
        for kind in ("missing-resource", "changed-resource", "changed-skill", "changed-manifest"):
            with self.subTest(kind=kind):
                self.install_backup()
                row = w.department_registry(self.root)[A3]
                if kind == "missing-resource":
                    Path(row["approved_subskill_paths"][0]).unlink()
                elif kind == "changed-resource":
                    Path(row["approved_subskill_paths"][0]).write_text("changed fixture resource")
                elif kind == "changed-skill":
                    w.safe_path(self.root, row["professional_skill"]).write_text("changed fixture skill")
                else:
                    pin = row["coordination_authority"]["technical_review_backup"]["method_manifest"]
                    w.safe_path(self.root, pin["path"]).write_text("{}\n")
                self.assertFalse(backup.review_capable(self.root, A3, self.snapshot()["goal_delivery"], transfer_from=A2))

    def test_producer_self_review_rejects_before_transfer(self):
        self.set_goal(A2, authorized_scope=[SCOPE], producer_departments=["content-organic-website", A3])
        lease = self.ready_lease()
        with self.assertRaisesRegex(w.WorkflowError, "self review"):
            self.transfer(lease)
        self.assertEqual(self.a.readback(self.identity)["token"], lease["token"])

    def test_scope_producer_external_action_and_other_source_reject(self):
        base = self.snapshot()["goal_delivery"]
        for changes in ({"authorized_scope": ["project:other-company:review"]},
                        {"producer_departments": ["publishing"]},
                        {"required_execution_actions": [{"action_class": "site_publish"}]}):
            with self.subTest(changes=changes):
                self.assertFalse(backup.review_capable(self.root, A3, {**base, **changes}, transfer_from=A2))
        self.assertFalse(backup.review_capable(self.root, A3, base, transfer_from="operations"))

    def test_fabricated_assignment_history_cannot_activate_backup(self):
        snapshot = self.snapshot()
        goal = snapshot["goal_delivery"]
        goal.update(responsible_assistant=A3, assignment_history=[{
            "previous_assistant": A2, "target_assistant": A3, "result_identity": self.identity, "fence": 1}])
        self.assertFalse(backup.review_capable(self.root, A3, goal, task_id=self.identity["task_id"]))
        with self.assertRaisesRegex(w.WorkflowError, "capable"):
            review._goal_reviewer(self.root, snapshot)

    def test_changed_committed_audit_or_event_cannot_activate_backup(self):
        lease = self.ready_lease()
        self.transfer(lease)
        snapshot = self.snapshot()
        task_goal = snapshot["goal_delivery"]
        self.assertTrue(backup.review_capable(self.root, A3, task_goal, task_id=self.identity["task_id"]))
        event_path = self.root / w.WORKFLOW_EVENTS
        original = event_path.read_bytes()
        events = w.read_jsonl(event_path)
        events[-1]["event_hash"] = "0" * 64
        event_path.write_text("".join(json.dumps(event) + "\n" for event in events))
        self.assertFalse(backup.review_capable(self.root, A3, task_goal, task_id=self.identity["task_id"]))
        event_path.write_bytes(original)
        self.a.conn.execute("UPDATE coordination_audit SET record_hash=? WHERE seq=(SELECT MAX(seq) FROM coordination_audit)", ("0" * 64,))
        self.a.conn.commit()
        self.assertFalse(backup.review_capable(self.root, A3, task_goal, task_id=self.identity["task_id"]))

    def test_bound_plan_requires_exact_transfer_and_keeps_old_candidate(self):
        snapshot = self.snapshot()
        snapshot["departments"] = [{"department": role, "chat_task_id": "fixed-" + role}
                                   for role in ("content-organic-website", A2)]
        w.atomic_write_json(w.snapshot_path(self.root, self.identity["task_id"]), snapshot)
        candidate_path = "drafts/operations/technical-backup-candidate.json"
        w.atomic_write_json(self.root / candidate_path, {"task_id": self.identity["task_id"],
            "department": "content-organic-website", "candidate_version": self.identity["candidate_version"]})
        candidate = w.file_digest(self.root, candidate_path)
        plan = {"schema_version": 1, "task_id": self.identity["task_id"], "action_id": "review-result",
            "action_class": "internal_control_candidate", "scope": SCOPE,
            "candidate_version": self.identity["candidate_version"], "candidate_sha256": candidate["sha256"],
            "candidate": candidate, "producer_department": "content-organic-website", "reviewer_department": A2,
            "reviewer_thread_id": "fixed-" + A2, "controller_department": "operations",
            "controller_thread_id": "fixed-operations", "single_final_reviewer": True,
            "risk_level": "R0", "production_write_allowed": False, "external_permission_issued": False}
        path = "drafts/operations/technical-review-plan.json"
        w.atomic_write_json(self.root / path, plan)
        review.bind_plan(self.root, task_id=self.identity["task_id"], plan_path=path, coordinator_role=A2)
        lease = self.ready_lease()
        with self.assertRaisesRegex(w.WorkflowError, "new frozen review plan"):
            self.transfer(lease)
        target_path = "drafts/operations/technical-review-plan-transfer.json"
        w.atomic_write_json(self.root / target_path, {**plan, "reviewer_department": A3, "reviewer_thread_id": "fixed-" + A3})
        prepared = review.transfer_plan(self.root, task_id=self.identity["task_id"], plan_path=target_path,
                                       target_role=A3, prepare_only=True)
        self.assertEqual(prepared["candidate"], candidate)
        self.assertFalse(prepared["old_verdict_migrated"])
        transferred = self.transfer(lease, review_plan_path=target_path)
        self.assertEqual(review.reviewer_department(self.root, self.snapshot()), A3)
        self.assertEqual(transferred["assignment_change"]["review_plan_transfer"]["candidate"], candidate)

    def test_existing_nontechnical_capabilities_are_preserved(self):
        for capability in ("paid", "data", "visual", "sales"):
            task_goal = {**self.snapshot()["goal_delivery"], "acceptance_capability": capability,
                         "responsible_assistant": A3}
            self.assertTrue(backup.review_capable(self.root, A3, task_goal))


if __name__ == "__main__":
    unittest.main()
