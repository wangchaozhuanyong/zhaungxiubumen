from pathlib import Path
import importlib.util
import json
import hashlib
import tempfile
import unittest

import setup_department_system as setup
import export_department_system as exporter


class DistributionTests(unittest.TestCase):
    def fixture(self, root):
        examples = root / "examples"
        examples.mkdir()
        for name in ("department-registry", "department-routing-rules", "task-contract", "action-policy", "delegation-policy"):
            value = {"departments": [{"id": "operations-assistant", "professional_skill": "departments/operations-assistant/SKILL.md", "chat_binding": {"status": "unbound", "dispatch_eligible": False}}]} if name == "department-registry" else {}
            (examples / (name + ".example.json")).write_text(json.dumps(value))
        for name in ("company-context", "service-area", "services-and-pricing", "customer-personas", "brand-guidelines", "case-studies", "faq"):
            (examples / (name + ".md")).write_text("待确认")

    def test_setup_does_not_activate_chats_or_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = setup.setup(root)
            self.assertEqual(result["external_permissions_issued"], 0)
            self.assertEqual(result["chats_created"], 0)
            binding = json.loads((root / "data/department-registry.json").read_text())["departments"][0]["chat_binding"]
            self.assertFalse(binding["dispatch_eligible"])

    def test_repeat_setup_preserves_local_bindings_and_company_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            setup.setup(root)
            path = root / "data/department-registry.json"
            path.write_text('{"departments": [], "local_history": "keep"}')
            company = root / "company-context.md"
            company.write_text("本机已确认资料")
            result = setup.setup(root)
            self.assertEqual(result["created"], [])
            self.assertIn("local_history", path.read_text())
            self.assertEqual(company.read_text(), "本机已确认资料")

    def test_missing_examples_fail_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def test_incomplete_examples_fail_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "examples/faq.md").unlink()
            with self.assertRaises(FileNotFoundError):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def release_root(self):
        project = Path(__file__).resolve().parents[1]
        return project if (project / "release-manifest.json").is_file() else project / "releases/zhaungxiubumen"

    def test_export_refuses_outside_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            with self.assertRaises(ValueError):
                exporter.prepare(root, Path(directory) / "other-project")

    def test_export_contains_no_runtime_account_or_history_files(self):
        # Test the actual release assembled for this project, if present.
        release = self.release_root()
        manifest = release / "release-manifest.json"
        if not manifest.exists():
            self.skipTest("source release not assembled in this workspace")
        data = json.loads(manifest.read_text())
        self.assertFalse(data["live_bindings_exported"])
        self.assertFalse(data["external_permissions_exported"])
        for row in data["files"]:
            self.assertNotIn(Path(row["path"]).parts[0], {"data", "logs", "reports", "accounts", "backups", "history"})
            self.assertNotIn("learning", Path(row["path"]).parts)
            self.assertNotIn(str(Path.home()), (release / row["path"]).read_text())

    def test_release_source_hashes_match_actual_bundle(self):
        release = self.release_root()
        if not (release / "release-manifest.json").is_file():
            self.skipTest("source release not assembled in this workspace")
        manifest = json.loads((release / "release-manifest.json").read_text())
        for row in manifest["files"]:
            self.assertEqual(hashlib.sha256((release / row["path"]).read_bytes()).hexdigest(), row["release_sha256"], row["path"])

    def test_public_templates_have_no_live_binding_or_grant(self):
        release = self.release_root()
        if not (release / "release-manifest.json").is_file():
            self.skipTest("source release not assembled in this workspace")
        registry = json.loads((release / "examples/department-registry.example.json").read_text())
        for role in registry["departments"]:
            self.assertTrue((release / role["role_config"]).is_file(), role["id"])
            self.assertTrue((release / role["professional_skill"]).is_file(), role["id"])
            binding = role["chat_binding"]
            self.assertEqual(binding["status"], "unbound")
            self.assertFalse(binding["dispatch_eligible"])
            for name in ("task_id", "project_id", "cwd", "title", "sidebar_section_id"):
                self.assertEqual(binding[name], "")
        policy = json.loads((release / "examples/action-policy.example.json").read_text())
        self.assertEqual(policy["standing_authorizations"], [])
        self.assertFalse(policy["autonomous_site_release_policy"]["enabled"])
        for rule in policy["action_classes"].values():
            if isinstance(rule, dict) and "exact_requests" in rule:
                self.assertEqual(rule["exact_requests"], [])


if __name__ == "__main__":
    unittest.main()
