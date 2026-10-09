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
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        project = Path(__file__).resolve().parents[1]
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

        (self.root / "data/human-control-state.json").write_text(json.dumps({
            "schema_version":1,"paused":False,"revision":1,"project_root":str(self.root),
            "reason":"synthetic_fixture_explicit_initialization"}))

    def plan(self, request, task_id):
        return ops.dispatch_plan(self.root, argparse.Namespace(request=request, task_id=task_id))[0]

    def policy(self, department, task_id, **changes):
        binding = workflow.department_registry(self.root)[department]["chat_binding"]
        args = dict(task_id=task_id, department="operations", action_id="dispatch", action_class="thread_message",
                    scope="department:" + department, source_project_id="test-project", target_project_id="test-project",
                    target_department=department, target_thread_id=binding["task_id"], target_thread_title=binding["title"],
                    target_cwd=str(self.root), target_sidebar_section_id="test-departments", payload_sha256="a" * 64)
        args.update(changes)
        return workflow.policy_check(self.root, **args)[0]

    def test_research_and_maps_route_to_separate_owners_then_qa(self):
        for department, request in (("seo-content-research", "SEO关键词与内容增长部：全站关键词扩展"),
                                    ("local-seo-maps", "本地SEO与地图增长部：地图资料优化")):
            with self.subTest(department=department):
                plan = self.plan(request, "test-" + department)
                self.assertEqual(plan["required_departments"], [department])
                self.assertEqual(plan["follow_up_departments"], ["qa"])
                self.assertEqual(plan["department_dependencies"]["qa"], [department])
                self.assertFalse(plan["controller_may_execute_specialist_work"])

    def test_exact_new_department_route_allowed_and_cross_project_denied(self):
        for department in ("seo-content-research", "local-seo-maps"):
            task_id = "test-" + department
            self.plan(workflow.department_registry(self.root)[department]["name"], task_id)
            self.assertEqual(self.policy(department, task_id)["status"], "allow")
            denied = self.policy(department, task_id, target_project_id="another-project")
            self.assertEqual(denied["status"], "deny")
            self.assertIn("blocked_cross_project:target_project_id_mismatch", denied["reason"])

    def test_new_research_roles_do_not_inherit_site_standing_authorization(self):
        policy = workflow.load_policy(self.root)
        self.assertTrue(policy["standing_authorizations"])
        for department in ("seo-content-research", "local-seo-maps"):
            self.assertNotIn(department, [x["department"] for x in policy["standing_authorizations"]])
        registry = workflow.department_registry(self.root)
        self.assertEqual(len(registry), len(json.loads((self.root / "data/department-registry.json").read_text())["departments"]))
        declared = json.loads((self.root / "data/department-registry.json").read_text())
        self.assertEqual(set(declared["execution_department_ids"]), set(registry) - {"operations"})
        self.assertEqual(declared["execution_department_count"], len(declared["execution_department_ids"]))
        self.assertEqual(registry["seo-content-research"]["approved_subskills"], ["renovation-seo-geo"])


if __name__ == "__main__":
    unittest.main()
