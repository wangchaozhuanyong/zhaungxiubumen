"""Conditional instruction reads and real entry output; no external effects."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import department_rule_context as rules
import department_system_package as package
import flashcast_ops as ops
import test_flashcast_ops as ops_fixtures
import test_export_department_system as export_fixtures


class RuleContextTests(unittest.TestCase):
    def setUp(self):
        area = Path(__file__).resolve().parents[1] / ".test-tmp"
        area.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="rule-context-", dir=str(area))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = "departments/example/SKILL.md"
        for rel in ["AGENTS.md", "playbooks/department-system-current.md", self.skill,
                    rules.REFERENCE, *rules.FACTS]:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("Current " + rel, encoding="utf-8")

    def build(self, **kwargs):
        return rules.build(self.root, "example", self.skill, **kwargs)

    def save(self, value):
        p = self.root / "read-view.json"
        p.write_text(json.dumps({"rule_context": value}), encoding="utf-8")
        return p.name

    def test_resume_has_no_exception_or_history_work_by_default(self):
        result = self.build(phase="resume", work_type="system")
        self.assertEqual(result["reference_sections"], [])
        self.assertEqual(result["triggered_exceptions"], [])
        self.assertFalse(result["constraints_are_actions"])
        self.assertFalse(result["cached_permissions"])
        self.assertTrue(result["live_assignment_and_result_checks_required"])

    def test_identical_resume_needs_zero_instruction_rereads(self):
        prior = self.build(phase="resume")
        result = self.build(phase="resume", known_rules=self.save(prior))
        self.assertEqual(result["sources_to_read"], [])
        self.assertEqual(result["normal_next_step"], "continue_current_assignment")

    def test_one_changed_rule_only_reloads_that_rule(self):
        prior = self.build(phase="resume")
        name = "playbooks/department-system-current.md"
        (self.root / name).write_text("Changed current procedure")
        result = self.build(phase="resume", known_rules=self.save(prior))
        self.assertEqual([p["path"] for p in result["sources_to_read"]], [name])

    def test_changed_fact_is_not_a_full_restart(self):
        prior = self.build(phase="work", work_type="content")
        name = "service-area.md"
        (self.root / name).write_text("New confirmed service area")
        result = self.build(phase="work", work_type="content", known_rules=self.save(prior))
        self.assertEqual([p["path"] for p in result["sources_to_read"]], [name])

    def test_new_phase_reads_new_section_despite_unchanged_reference_file(self):
        dispatch = self.build(phase="dispatch")
        production = self.build(phase="production", known_rules=self.save(dispatch))
        self.assertEqual(production["reference_sections_to_read"], [rules.REFERENCE + "#production"])
        back = self.build(phase="dispatch", known_rules=self.save(production))
        self.assertEqual(back["sources_to_read"], [])
        self.assertEqual(back["reference_sections_to_read"], [])

    def test_changed_reference_reloads_its_relevant_section(self):
        prior = self.build(phase="delivery")
        (self.root / rules.REFERENCE).write_text("Changed delivery implementation")
        result = self.build(phase="delivery", known_rules=self.save(prior))
        self.assertEqual(result["reference_sections_to_read"], [rules.REFERENCE + "#delivery"])

    def test_only_actual_exception_loads_its_handler(self):
        result = self.build(phase="resume", triggers=("target_not_loaded",))
        self.assertEqual(result["reference_sections"], [rules.REFERENCE + "#target-state"])
        self.assertNotIn(rules.REFERENCE + "#authority-change", result["reference_sections"])

    def test_missing_relevant_reference_is_explicit(self):
        (self.root / rules.REFERENCE).unlink()
        self.assertIn(rules.REFERENCE, self.build(phase="recovery")["optional_sources_missing"])

    def test_other_role_or_project_cannot_reuse_read_state(self):
        prior = self.build()
        for key, value in [("department", "other"), ("project_root", "/other/project")]:
            bad = copy.deepcopy(prior)
            bad[key] = value
            with self.assertRaisesRegex(ValueError, "another project or role"):
                self.build(known_rules=self.save(bad))

    def test_external_path_symlink_or_malformed_read_state_rejected(self):
        with self.assertRaises(ValueError):
            self.build(known_rules="../outside.json")
        (self.root / "link.json").symlink_to(self.root / "AGENTS.md")
        with self.assertRaises(ValueError):
            self.build(known_rules="link.json")
        bad = self.build()
        bad["read_receipt_sources"][0]["sha256"] = "z" * 64
        with self.assertRaises(ValueError):
            self.build(known_rules=self.save(bad))

    def test_unknown_phase_or_exception_does_not_broaden_work(self):
        with self.assertRaises(ValueError):
            self.build(phase="audit_everything")
        with self.assertRaises(ValueError):
            self.build(triggers=("scan_every_site",))

    def test_prompt_migration_preserves_business_budget_target_and_schedule_text(self):
        business = "仅原账户；预算RM100，期限2026-10-24；保留固定目标、原排程和合法权限。"
        text = ("先读取本项目唯一共同规则 playbooks/department-system-current.md、动态注册表。\n\n"
                "现行交付接续：完整目标或完整业务批次结束才一次交付；旧重复共同正文。\n\n" + business)
        migrated = rules.normalize_automation_prompt(text, "example")
        self.assertIn(business, migrated)
        self.assertIn("--phase daily", migrated)
        self.assertNotIn("旧重复共同正文", migrated)
        self.assertEqual(rules.normalize_automation_prompt(migrated, "example"), migrated)

    def test_paid_startup_list_is_conditional_but_original_budget_is_retained(self):
        text = "启动先读唯一共同规则playbooks/department-system-current.md、公司七份资料。原预算RM100/日，期限不变。"
        migrated = rules.normalize_automation_prompt(text, "paid-growth-data")
        self.assertNotIn("启动先读唯一共同规则", migrated)
        self.assertIn("原预算RM100/日，期限不变。", migrated)

    def test_workflow_wording_changes_do_not_invalidate_stable_professional_method(self):
        import workflow_control as workflow
        import goal_continuity
        method = self.root / "methods/review.md"
        method.parent.mkdir()
        method.write_text("Existing independent source and release checks")
        catalog = self.root / "methods/catalog.json"
        catalog.write_text(json.dumps({"production_permissions_inherited": False,
            "methods": {"cms": [workflow.file_digest(self.root, "methods/review.md")]}}))
        registry = self.root / "data/department-registry.json"
        registry.parent.mkdir()
        registry.write_text(json.dumps({"departments": [{"id": "assistant", "professional_skill": self.skill,
            "coordination_authority": {"routine_decisions": True,
                "shared_review_methods": workflow.file_digest(self.root, "methods/catalog.json")}}]}))
        goal = {"producer_departments": ["producer"], "acceptance_capability": "cms"}
        self.assertTrue(goal_continuity.shared_capable(self.root, "assistant", goal))
        (self.root / self.skill).write_text("Only the current startup cadence changed")
        self.assertTrue(goal_continuity.shared_capable(self.root, "assistant", goal))
        method.write_text("Unverified method change")
        self.assertFalse(goal_continuity.shared_capable(self.root, "assistant", goal))


class EffectiveEntryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ops_fixtures.DepartmentLearningEffectiveTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.fixture.seed({"verified_lessons": [self.fixture.lesson("one",
            lesson="DO THE OLD FULL-SITE SCAN", outcome="OLD TASK RESULT")]})

    def test_default_learning_is_index_only_and_explicit_reference_is_nonexecutable(self):
        view, _ = ops.department_learning_effective(self.root, "operations")
        self.assertNotIn("DO THE OLD FULL-SITE SCAN", json.dumps(view))
        self.assertNotIn("OLD TASK RESULT", json.dumps(view))
        detailed, _ = ops.department_learning_effective(self.root, "operations", include_reference_details=True)
        self.assertEqual(detailed["current_lessons"][0]["lesson"], "DO THE OLD FULL-SITE SCAN")
        self.assertFalse(detailed["current_lessons"][0]["executable_instruction"])
        self.assertFalse(detailed["current_lessons"][0]["grants_execution_authority"])
        self.assertNotIn("OLD DISPATCH COMMAND", json.dumps(detailed))

    def test_rule_reuse_does_not_cache_live_assignment_or_queue(self):
        with mock.patch("result_coordination.current_assignment_for_role", side_effect=[
                {"task_id": "original-unfinished"}, {"task_id": "new-current"}]) as assignment, \
             mock.patch("goal_continuity.work_boundary", side_effect=[
                {"actionable_count": 0}, {"actionable_count": 1, "ready_actions": [{"task_id": "new-result"}]}]) as boundary:
            first, _ = ops.department_learning_effective(self.root, "operations", phase="resume")
            p = self.root / "read-view.json"
            p.write_text(json.dumps(first))
            second, _ = ops.department_learning_effective(self.root, "operations", phase="resume", known_rules=p.name)
        self.assertEqual(second["rule_context"]["sources_to_read"], [])
        self.assertEqual(second["actual_current_assignment"]["task_id"], "new-current")
        self.assertEqual(second["work_boundary"]["actionable_count"], 1)
        self.assertEqual(assignment.call_count, 2)
        self.assertEqual(boundary.call_count, 2)

    def test_real_cli_renderer_keeps_actual_assignment_boundary_and_read_plan(self):
        payload = {"status": "department_learning_effective_read_only",
                   "actual_current_assignment": {"task_id": "unfinished"},
                   "work_boundary": {"actionable_count": 1},
                   "rule_context": {"normal_next_step": "continue_current_assignment"}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ops.print_artifacts(payload, [], self.root)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["actual_current_assignment"], payload["actual_current_assignment"])
        self.assertEqual(parsed["work_boundary"], payload["work_boundary"])
        self.assertEqual(parsed["rule_context"], payload["rule_context"])

    def test_cli_phase_and_reference_switches_are_consumed(self):
        args = ops.build_parser().parse_args(["department-learning-effective", "--department", "operations",
            "--phase", "resume", "--work-type", "system", "--include-reference-details"])
        payload, artifacts = args.handler(self.root, args)
        self.assertEqual(payload["rule_context"]["phase"], "resume")
        self.assertTrue(payload["reference_loading_policy"]["details_explicitly_requested"])
        self.assertEqual(artifacts, [])


class RulePackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = export_fixtures.ExportTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        contract = json.loads((self.root / "data/task-contract.json").read_text())
        contract["goal_delivery_runtime"]["rule_execution"] = {
            "model": rules.MODEL, "normal_flow_source": "playbooks/department-system-current.md",
            "reference_source": rules.REFERENCE, "reader": "tools/department_rule_context.py",
            "default_reference_loading": "index_only", "instruction_reuse_grants_permission": False,
            "live_assignment_and_action_gates_unchanged": True}
        self.fixture.write_json("data/task-contract.json", contract)

    def test_export_rejects_missing_new_reader_or_reference(self):
        import export_department_system as exporter
        with self.assertRaisesRegex(ValueError, "Missing conditional rule context dependency"):
            exporter.prepare(self.root, self.fixture.target)

    def test_export_contains_actual_dependencies_and_rejects_permission_cache_mode(self):
        import export_department_system as exporter
        self.fixture.write("tools/department_rule_context.py", Path(rules.__file__).read_text())
        self.fixture.write(rules.REFERENCE, "# Conditional runtime reference\n")
        exporter.prepare(self.root, self.fixture.target)
        package.validate_release(self.fixture.target)
        contract = json.loads((self.root / "data/task-contract.json").read_text())
        contract["goal_delivery_runtime"]["rule_execution"]["instruction_reuse_grants_permission"] = True
        with self.assertRaisesRegex(ValueError, "Invalid conditional"):
            package.validate_model(contract)


if __name__ == "__main__":
    unittest.main()
