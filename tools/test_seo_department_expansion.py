from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flashcast_ops as ops
import workflow_control as workflow


class SeoDepartmentExpansionTests(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        temporary_root = project / ".test-tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / "data").mkdir()
        for name in ("department-registry.json", "department-routing-rules.json", "action-policy.json", "task-contract.json"):
            data = json.loads((project / "data" / name).read_text())
            if name == "department-registry.json":
                for item in data["departments"]:
                    binding = item["chat_binding"]
                    binding.update(task_id="fixed-" + item["id"], cwd=str(self.root), project_id="test-project",
                                   status="bound_and_visible", sidebar_section_id="test-departments",
                                   reply_health="healthy_visible_reply_verified", dispatch_eligible=True,
                                   last_health_check_at=dt.datetime.now(dt.timezone.utc).isoformat())
            if name == "action-policy.json":
                data["routing_policy"].update(source_project_id="test-project", source_project_root=str(self.root))
            (self.root / "data" / name).write_text(json.dumps(data))

    def plan(self, request, task_id, department=None):
        department = department or ("local-seo-maps" if "地图" in request or "maps" in request.casefold() else "seo-content-research")
        scope = "department:" + department
        human_source = "reports/" + task_id + "-synthetic-human-source.json"
        source = self.root / human_source
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps({"fixture_only": True, "source_thread_id": "synthetic-owner-thread",
            "message": {"type": "userMessage", "id": "synthetic-owner-message", "content": [
                {"type": "text", "text": "Synthetic authorization for this bounded internal department fixture; no provider action."}]}}, ensure_ascii=False))
        goal = {"objective": request, "completion_criteria": ["Complete this exact internal fixture scope and independent assistant acceptance"],
                "primary_owner": department, "responsible_assistant": "operations-assistant",
                "existing_results": [], "authorized_scope": [scope], "dependencies": [],
                "producer_departments": [department], "acceptance_capability": "seo_geo",
                "human_authorization": {"source_thread_id": "synthetic-owner-thread", "message_id": "synthetic-owner-message",
                    "executor": department, "scope": scope, "evidence_path": human_source}}
        goal_input = "reports/" + task_id + "-synthetic-goal.json"
        (self.root / goal_input).write_text(json.dumps(goal, ensure_ascii=False))
        return ops.dispatch_plan(self.root, argparse.Namespace(request=request, task_id=task_id, goal_input=goal_input))[0]

    def policy(self, department, task_id, **changes):
        binding = workflow.department_registry(self.root)[department]["chat_binding"]
        args = dict(task_id=task_id, department="operations", action_id="dispatch", action_class="thread_message",
                    scope="department:" + department, source_project_id="test-project", target_project_id="test-project",
                    target_department=department, target_thread_id=binding["task_id"], target_thread_title=binding["title"],
                    target_cwd=str(self.root), target_sidebar_section_id="test-departments", payload_sha256="a" * 64)
        args.update(changes)
        return workflow.policy_check(self.root, **args)[0]

    def test_research_and_maps_use_complete_goal_and_single_independent_assistant(self):
        for department, request in (("seo-content-research", "SEO关键词与内容增长部：全站关键词扩展"),
                                    ("local-seo-maps", "本地SEO与地图增长部：地图资料优化")):
            with self.subTest(department=department):
                task_id = "test-" + department
                plan = self.plan(request, task_id, department)
                self.assertEqual(plan["required_departments"], [department])
                self.assertEqual(plan["follow_up_departments"], ["operations-assistant"])
                self.assertEqual(plan["department_dependencies"]["operations-assistant"], [department])
                self.assertFalse(plan["controller_may_execute_specialist_work"])
                self.assertEqual(plan["goal_delivery"]["primary_owner"], department)
                self.assertEqual(plan["goal_delivery"]["acceptance_capability"], "seo_geo")
                self.assertNotIn("operations-assistant", plan["goal_delivery"]["producer_departments"])
                self.assertNotIn("qa", plan["follow_up_departments"])
                self.assertEqual(workflow.read_jsonl(workflow.receipts_path(self.root, task_id)), [])

    def test_exact_new_department_route_allowed_and_cross_project_denied(self):
        for department in ("seo-content-research", "local-seo-maps"):
            task_id = "test-" + department
            self.plan(workflow.department_registry(self.root)[department]["name"], task_id, department)
            self.assertEqual(self.policy(department, task_id)["status"], "allow")
            denied = self.policy(department, task_id, target_project_id="another-project")
            self.assertEqual(denied["status"], "deny")
            self.assertIn("blocked_cross_project:target_project_id_mismatch", denied["reason"])

    def test_new_runtime_rejects_request_without_complete_goal(self):
        with self.assertRaisesRegex(ops.OpsError, "one complete goal and responsible assistant"):
            ops.dispatch_plan(self.root, argparse.Namespace(
                request="SEO关键词与内容增长部：全站关键词扩展", task_id="test-incomplete-goal"))
        self.assertFalse(workflow.snapshot_path(self.root, "test-incomplete-goal").exists())

    def test_new_research_roles_do_not_inherit_site_standing_authorization(self):
        policy = workflow.load_policy(self.root)
        self.assertTrue(policy["standing_authorizations"])
        for department in ("seo-content-research", "local-seo-maps"):
            self.assertNotIn(department, [x["department"] for x in policy["standing_authorizations"]])
        registry = workflow.department_registry(self.root)
        declared = json.loads((self.root / "data/department-registry.json").read_text())
        eligible = {role for role, row in registry.items() if row.get("new_dispatch_enabled") is not False}
        controllers = {role for role in eligible if registry[role].get("mode") == "controller"}
        assistants = {role for role in eligible if registry[role].get("coordination_authority", {}).get("routine_decisions") is True}
        self.assertEqual(declared["total_role_count"], len(registry))
        self.assertEqual(declared["active_department_count"], len(eligible))
        self.assertEqual(set(declared["execution_department_ids"]), eligible - controllers)
        self.assertEqual(declared["execution_department_count"], len(declared["execution_department_ids"]))
        self.assertEqual(declared["controller_count"], len(controllers))
        self.assertEqual(declared["coordination_assistant_count"], len(assistants))
        self.assertEqual(declared["specialist_execution_department_count"], len(eligible - controllers - assistants))
        self.assertEqual(registry["seo-content-research"]["approved_subskills"], ["renovation-seo-geo"])


if __name__ == "__main__":
    unittest.main()
