"""Public export includes dynamic methods, never live identities or grants."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import export_department_system as export
import department_system_package as package


class ExportTests(unittest.TestCase):
    def setUp(self):
        source_root = Path(__file__).resolve().parents[1]
        developer = source_root.parent
        area = Path(os.environ["DEPARTMENT_SYSTEM_TEST_OUTPUT"]) if os.environ.get("DEPARTMENT_SYSTEM_TEST_OUTPUT") else (developer / "migration" / "test-runs" if source_root.name == "candidate" and
                (developer / "baseline-manifest.json").is_file() else source_root / ".test-tmp" / "export-tests")
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="export-", dir=str(area))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.target = self.root / "releases/public"
        for rel in ("AGENTS.md", "README.md", ".codex/config.toml"):
            self.write(rel, "# goal delivery assistant runtime\n")
        rows = []
        for role in ("operations", "operations-assistant-2", "operations-assistant-3", "future-specialist", "qa"):
            for rel in ("departments/" + role + "/SKILL.md", "departments/" + role + "/README.md", ".codex/agents/" + role + ".toml"):
                self.write(rel, "# method for " + role + "\n")
            rows.append({"id": role, "name": role, "role_config": ".codex/agents/" + role + ".toml",
                "professional_skill": "departments/" + role + "/SKILL.md", "department_readme": "departments/" + role + "/README.md",
                "new_dispatch_enabled": role != "qa", "approved_subskills": [],
                "mode": "retired_history" if role == "qa" else "active",
                "coordination_authority": {"routine_decisions": role.startswith("operations-assistant"), "dispatch_approved_next": True},
                "chat_binding": {"task_id": "example-native-edb7b6c4c2a38180", "project_id": "private-project-id", "reply_health": "private-current-health"}})
        self.write_json("data/department-registry.json", {"departments": rows, "project": {"project_id": "private-project-id"},
            "collaboration_bindings": {"designated-development": {"thread_id": "private-development-id", "cwd": "/private/company/project"}}})
        for name in export.POLICIES:
            self.write_json("data/" + name, {"goal_delivery_runtime": {"model": "goal_delivery_assistant_v1",
                                                                      "assistant_decisions_enabled": True}})
        self.write_json("data/action-policy.json", {"routing_policy": {"owner_directed_code_handoff": {"status": "admitted", "private_token": "not-exported"}},
            "action_classes": {"site_publish": {"exact_requests": [{"native_authority": "private-permit"}]}},
            "owner_paid_completion_v42": {"status": "authorized"}, "cms_publisher_native_sparse_admission": {"status": "admitted"},
            "standing_authorizations": [{"real_permit": True}], "autonomous_site_release_policy": {"enabled": True}})
        self.write("tools/new_consumer.py", "MODEL = 'goal_delivery_assistant_v1'\n")
        self.write("tools/nested/helper.py", "ENABLED = True\n")
        for name in ("export_department_system.py", "setup_department_system.py", "flashcast_ops.py",
                     "department_reply.py", "goal_delivery_runtime.py", "workflow_control.py"):
            self.write("tools/" + name, "MODEL = 'goal_delivery_assistant_v1'\n")
        self.write("tools/department_system_package.py", Path(package.__file__).read_text())
        for skill in ("flashcast-department-learning", "flashcast-cms-publishing"):
            self.write("skills/" + skill + "/SKILL.md", "# current runtime method\n")
        self.write("playbooks/department-system-current.md", "# goal_delivery_assistant_v1 current runtime\n完整目标由唯一助理验收。\n")
        self.write("templates/goal-delivery-report.md", "唯一助理验收。父任务范围保留。\n")
        self.write("prompts/automations/assistant-2.md", "以本次完整目标收取原任务结果。\n")

    def test_manifest_exact_full_payload_bytes_and_fingerprint(self):
        export.prepare(self.root, self.target)
        manifest = json.loads((self.target / "release-manifest.json").read_text())
        self.assertEqual(manifest["runtime_model"], "goal_delivery_assistant_v1")
        paths = [row["path"] for row in manifest["files"]]
        actual = {path.relative_to(self.target).as_posix() for path in self.target.rglob("*")
                  if path.is_file() and path.name != "release-manifest.json"}
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), actual)
        for row in manifest["files"]:
            raw = (self.target / row["path"]).read_bytes()
            self.assertEqual(row["bytes"], len(raw), row["path"])
            self.assertEqual(row["release_sha256"], hashlib.sha256(raw).hexdigest(), row["path"])
        unsigned = {key: value for key, value in manifest.items() if key != "fingerprint"}
        canonical = json.dumps(unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        self.assertEqual(manifest["fingerprint"], hashlib.sha256(canonical).hexdigest())

    def test_positive_obsolete_professional_qa_hq_chain_rejected_before_output(self):
        surfaces = ("AGENTS.md", "README.md", "departments/future-specialist/SKILL.md",
                    ".codex/agents/future-specialist.toml", "prompts/automations/assistant-2.md",
                    "templates/goal-delivery-report.md")
        for rel in surfaces:
            with self.subTest(rel=rel):
                old = (self.root / rel).read_bytes()
                self.write(rel, 'routing_note = "专业部门→QA→HQ"\n' if rel.endswith('.toml') else "专业部门→QA→HQ\n")
                try:
                    with self.assertRaises(ValueError):
                        export.prepare(self.root, self.target)
                    self.assertFalse(self.target.exists())
                finally:
                    (self.root / rel).write_bytes(old)

    def test_negative_old_chain_description_and_nonoperational_history_allowed(self):
        self.write("templates/goal-delivery-report.md", "禁止专业部门→QA→HQ旧链。\n不得恢复专业→QA→HQ。\n不要提交给QA。\n不得沿专业结果→QA→总部旧链派工。\n现行模式不能恢复 legacy_fixed_qa。\n完整目标由唯一助理验收。\n")
        self.write_json("examples/nonoperational-history.json", {"historical_only": True,
            "operational_template": False, "reviewer_department": "qa", "required_departments": ["qa"],
            "historical_route": "专业部门→QA→HQ"})
        export.prepare(self.root, self.target)
        manifest = json.loads((self.target / "release-manifest.json").read_text())
        self.assertIn("examples/nonoperational-history.json", manifest["non_runtime_files"])

    def test_unrelated_negation_or_prose_cannot_hide_positive_old_qa_hq_rule(self):
        for text in ("不得自审，专业结果 → QA → 总部\n", "全部专业结果必须经过总部二审\n",
                     "专业结果提交给质检部门审批后交总部\n",
                     "不得上传账号，并把专业结果提交给QA审核后交总部\n",
                     "禁止修改素材，且专业结果→QA→总部\n"):
            with self.subTest(text=text):
                self.write("AGENTS.md", text)
                with self.assertRaises(ValueError):
                    export.prepare(self.root, self.target)
                self.assertFalse(self.target.exists())

    def test_explicit_history_sections_and_noncontract_model_declarations(self):
        variants = (
            ("history-title", "# Tools\n## 历史兼容（非当前、非运行、不作为现行）\n专业部门→QA→HQ\n", True),
            ("history-first-paragraph", "# Tools\n## 历史兼容\n以下非当前、非运行，不作为现行规则。\n专业部门→QA→HQ\n", True),
            ("unmarked-history", "# Tools\n## 历史兼容\n专业部门→QA→HQ\n", False),
            ("current-after-history", "# Tools\n## 历史兼容（非运行）\n专业部门→QA→HQ\n## 当前规则\n专业部门→QA→HQ\n", False),
            ("higher-current-after-history", "# Tools\n## 历史兼容（非当前）\n专业部门→QA→HQ\n# 当前规则\n专业部门→QA→HQ\n", False),
            ("action-model-without-assistant-flag", "# current model rules\n", True),
            ("contract-missing-assistant-flag", "# current model rules\n", False),
            ("action-assistant-disabled", "# current model rules\n", False),
        )
        for kind, text, allowed in variants:
            with self.subTest(kind=kind):
                fixture = ExportTests("runTest")
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                fixture.write("tools/README.md", text)
                path = fixture.root / "data/action-policy.json"
                policy = json.loads(path.read_text())
                policy["goal_delivery_runtime"] = {"model": "goal_delivery_assistant_v1"}
                if kind == "action-assistant-disabled":
                    policy["goal_delivery_runtime"]["assistant_decisions_enabled"] = False
                fixture.write_json("data/action-policy.json", policy)
                if kind == "contract-missing-assistant-flag":
                    path = fixture.root / "data/task-contract.json"
                    contract = json.loads(path.read_text())
                    contract["goal_delivery_runtime"].pop("assistant_decisions_enabled")
                    fixture.write_json("data/task-contract.json", contract)
                if allowed:
                    export.prepare(fixture.root, fixture.target)
                    package.validate_release(fixture.target)
                else:
                    with self.assertRaises(ValueError):
                        export.prepare(fixture.root, fixture.target)
                    self.assertFalse(fixture.target.exists())

    def test_dynamic_new_role_both_fixed_qa_roles_retired_and_dependencies_complete(self):
        registry = json.loads((self.root / "data/department-registry.json").read_text())
        technical = {"id": "qa-technical", "name": "qa-technical", "new_dispatch_enabled": False,
                     "mode": "retired_history",
                     "role_config": ".codex/agents/qa-technical.toml",
                     "professional_skill": "departments/qa-technical/SKILL.md",
                     "department_readme": "departments/qa-technical/README.md"}
        for field in ("role_config", "professional_skill", "department_readme"):
            self.write(technical[field], "# historical retired fixed QA role\n")
        registry["departments"].append(technical)
        self.write_json("data/department-registry.json", registry)
        export.prepare(self.root, self.target)
        manifest = package.validate_release(self.target)
        self.assertIn("future-specialist", manifest["roles"])
        self.assertEqual(set(manifest["retired_roles"]), {"qa", "qa-technical"})
        for rel in ("tools/export_department_system.py", "tools/setup_department_system.py",
                    "tools/department_system_package.py", "tools/flashcast_ops.py",
                    "tools/department_reply.py", "tools/goal_delivery_runtime.py", "tools/workflow_control.py",
                    "skills/flashcast-department-learning/SKILL.md", "skills/flashcast-cms-publishing/SKILL.md",
                    "playbooks/department-system-current.md"):
            self.assertTrue((self.target / rel).is_file(), rel)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_json(self, relative, value):
        self.write(relative, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def test_dynamic_roles_helpers_and_templates_included(self):
        result = export.prepare(self.root, self.target)
        self.assertEqual(result["roles"], 5)
        manifest = json.loads((self.target / "release-manifest.json").read_text())
        self.assertIn("future-specialist", manifest["roles"])
        self.assertEqual(manifest["retired_roles"], ["qa"])
        for rel in ("tools/new_consumer.py", "tools/nested/helper.py", "templates/goal-delivery-report.md", "prompts/automations/assistant-2.md",
                    ".codex/agents/operations-assistant-2.toml", ".codex/agents/operations-assistant-3.toml", "examples/agent-role-policy.example.json"):
            self.assertTrue((self.target / rel).is_file(), rel)

    def test_private_binding_health_business_and_admission_absent(self):
        self.write("accounts/customer-secret.md", "private business ledger\n")
        self.write("logs/actual-receipts.jsonl", "private source receipt\n")
        export.prepare(self.root, self.target)
        registry = json.loads((self.target / "examples/department-registry.example.json").read_text())
        self.assertNotIn("collaboration_bindings", registry)
        self.assertEqual(registry["active_department_count"], 4)
        self.assertFalse(registry["departments"][-1]["new_dispatch_enabled"])
        policy = json.loads((self.target / "examples/action-policy.example.json").read_text())
        self.assertNotIn("owner_paid_completion_v42", policy)
        self.assertNotIn("cms_publisher_native_sparse_admission", policy)
        self.assertEqual(policy["standing_authorizations"], [])
        self.assertEqual(policy["action_classes"]["site_publish"]["exact_requests"], [])
        self.assertFalse(policy["autonomous_site_release_policy"]["enabled"])
        combined = "\n".join(file.read_text() for file in self.target.rglob("*") if file.is_file())
        for private in ("private-project-id", "private-current-health", "private-development-id", "private-permit", "private business ledger"):
            self.assertNotIn(private, combined)

    def test_secret_preflight_leaves_no_partial_output(self):
        self.write("tools/z-secret.py", "access_" + "token = 'synthetic-test-key-material-1234567890'\n")
        with self.assertRaisesRegex(ValueError, "Potential secret"):
            export.prepare(self.root, self.target)
        self.assertFalse(self.target.exists())

    def test_idempotence_and_edited_generated_output_preserved(self):
        export.prepare(self.root, self.target)
        before = (self.target / "release-manifest.json").read_bytes()
        export.prepare(self.root, self.target)
        self.assertEqual((self.target / "release-manifest.json").read_bytes(), before)
        file = self.target / "tools/new_consumer.py"
        file.write_text("user edited WIP\n")
        with self.assertRaisesRegex(ValueError, "Edited or unknown output preserved|Package file fingerprint mismatch"):
            export.prepare(self.root, self.target)
        self.assertEqual(file.read_text(), "user edited WIP\n")

    def test_duplicate_role_and_outside_target_rejected(self):
        path = self.root / "data/department-registry.json"
        registry = json.loads(path.read_text())
        registry["departments"].append(registry["departments"][0])
        path.write_text(json.dumps(registry))
        with self.assertRaisesRegex(ValueError, "duplicate dynamic role"):
            export.prepare(self.root, self.target)
        with self.assertRaisesRegex(ValueError, "inside the source project"):
            export.prepare(self.root, self.root.parent / "outside")

    def test_public_owner_exact_helpers_have_no_native_payload_or_execute(self):
        source = 'AUTH = {"turn_id": "native-private", "text": "private-human-authority"}\nCAMPAIGNS = ["private-business-id"]\ndef check():\n    """exact native check"""\n    return AUTH\n'
        text = export.public_exact_helper("tools/owner_paid_completion_policy.py", export.public_source_text("tools/owner_paid_completion_policy.py", source))
        ast.parse(text)
        self.assertNotIn("native-private", text)
        self.assertNotIn("private-human-authority", text)
        self.assertNotIn("private-business-id", text)
        namespace = {}
        exec(text, namespace)
        with self.assertRaisesRegex(ValueError, "no_native_authorization"):
            namespace["check"]()

    def test_source_and_target_symlinks_rejected(self):
        link = self.root / "tools/link.py"
        link.symlink_to(self.root / "tools/new_consumer.py")
        with self.assertRaisesRegex(ValueError, "symlink source"):
            export.prepare(self.root, self.target)
        link.unlink()
        symlink = self.root / "release-link"
        symlink.symlink_to(self.root / "tools", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink release target"):
            export.prepare(self.root, symlink)

    def test_legacy_fixed_qa_example_and_route_cannot_revive(self):
        self.write_json("examples/qa2-review-plan.json", {"reviewer_department": "qa"})
        with self.assertRaisesRegex(ValueError, "revive retired fixed QA reviewer"):
            export.prepare(self.root, self.target)
        self.write_json("examples/qa2-review-plan.json", {"reviewer_department": "operations-assistant-2"})
        self.write_json("data/department-routing-rules.json", {"routes": [{"required_departments": ["qa"]}]})
        with self.assertRaisesRegex(ValueError, "revive retired fixed QA route"):
            export.prepare(self.root, self.target)

    def test_missing_current_goal_contract_is_rejected(self):
        self.write_json("data/task-contract.json", {"old_fixed_qa_contract": True})
        with self.assertRaisesRegex(ValueError, "goal/assistant runtime contract required"):
            export.prepare(self.root, self.target)


if __name__ == "__main__":
    unittest.main()
