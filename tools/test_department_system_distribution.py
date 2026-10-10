from pathlib import Path
import copy
import importlib.util
import json
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import setup_department_system as setup
import export_department_system as exporter
import department_system_package as package
import test_export_department_system as export_tests


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(os.environ.get("DEPARTMENT_SYSTEM_TEST_OUTPUT", str(Path(__file__).resolve().parents[1] / ".test-tmp" / "distribution-tests")))
        self.area.mkdir(parents=True, exist_ok=True)

    def temporary_directory(self):
        return tempfile.TemporaryDirectory(dir=self.area)

    def preparation_example(self):
        return ('from pathlib import Path\nfrom typing import Any\n'
                'AUTH_TURN_ID = "private-turn-fixture"\n'
                'AUTH_MESSAGE_ID = "private-message-fixture"\n'
                'AUTH_TEXT = "private-owner-fixture"\n'
                'AUTH_TEXT_SHA256 = "private-digest-fixture"\n'
                'def _require(condition, reason):\n'
                '    if not condition: raise ValueError(reason)\n'
                'def _frozen_request(root: Path, policy: dict[str, Any]) -> dict[str, Any]:\n'
                '    return policy\n')

    def test_owner_evidence_is_synthetic_and_example_cannot_authorize(self):
        result = exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", self.preparation_example())
        self.assertNotIn("private-", result)
        namespace = {}
        exec(result, namespace)
        self.assertEqual(namespace["AUTH_TEXT_SHA256"], hashlib.sha256(namespace["AUTH_TEXT"].encode()).hexdigest())
        with self.assertRaisesRegex(ValueError, "public_template_has_no_native_authorization"):
            namespace["_frozen_request"](Path("."), {"routing_policy": {"status": "approved_single_use"}})
        self.assertEqual(exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", result), result)

    def test_unknown_owner_evidence_or_changed_entrypoint_blocks_export(self):
        for source in (self.preparation_example() + 'AUTH_NEW_FIELD = "private-new-fixture"\n',
                       self.preparation_example().replace("def _frozen_request", "def renamed_request")):
            with self.assertRaises(ValueError):
                exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", source)

    def test_owner_transform_does_not_change_live_or_unrelated_module(self):
        source = self.preparation_example()
        self.assertEqual(exporter.public_source_text("tools/unrelated.py", source), source)
        exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", source)
        self.assertIn("private-owner-fixture", source)

    def test_followthrough_examples_remove_real_record_ids_and_source_pins(self):
        source = 'TARGET_IDS = ["private-record-fixture"]\nSOURCE_PINS = {"v17": ("private-pin-fixture", "private-other-pin")}\n'
        result = exporter.public_source_text("tools/owner_delegated_publisher_followthrough.py", source)
        self.assertNotIn("private-", result)
        namespace = {}
        exec(result, namespace)
        self.assertEqual(len(namespace["TARGET_IDS"]), 3)
        self.assertEqual(set(namespace["SOURCE_PINS"]), {"v17", "v18", "v20"})

    def fixture(self, root):
        source_fixture = export_tests.ExportTests("runTest")
        source_fixture.setUp()
        self.addCleanup(source_fixture.doCleanups)
        source = root / "source"
        shutil.copytree(source_fixture.root, source)
        target = source / "releases/public"
        exporter.prepare(source, target)
        return target

    def files(self, root):
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def reseal(self, root):
        path = root / "release-manifest.json"
        manifest = json.loads(path.read_text())
        for row in manifest["files"]:
            raw = (root / row["path"]).read_bytes()
            row["bytes"] = len(raw)
            row["release_sha256"] = hashlib.sha256(raw).hexdigest()
        path.write_text(json.dumps(package.seal_manifest(manifest), ensure_ascii=False, indent=2) + "\n")

    def test_setup_does_not_activate_chats_or_accounts(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            root = self.fixture(root)
            result = setup.setup(root)
            self.assertEqual(result["external_permissions_issued"], 0)
            self.assertEqual(result["chats_created"], 0)
            binding = json.loads((root / "data/department-registry.json").read_text())["departments"][0]["chat_binding"]
            self.assertFalse(binding["dispatch_eligible"])

    def test_repeat_setup_preserves_local_bindings_and_company_edits(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            root = self.fixture(root)
            setup.setup(root)
            path = root / "data/department-registry.json"
            value = json.loads(path.read_text())
            value["local_history"] = "keep"
            value["departments"][0]["chat_binding"]["task_id"] = "fixture-local-history-binding"
            path.write_text(json.dumps(value))
            company = root / "company-context.md"
            company.write_text("本机已确认资料")
            result = setup.setup(root)
            self.assertEqual(result["created"], [])
            self.assertIn("local_history", path.read_text())
            self.assertEqual(company.read_text(), "本机已确认资料")

    def test_missing_examples_fail_before_creation(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def test_incomplete_examples_fail_before_creation(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            root = self.fixture(root)
            (root / "examples/faq.md").unlink()
            with self.assertRaises((FileNotFoundError, ValueError)):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def release_root(self):
        if os.environ.get("DEPARTMENT_SYSTEM_TEST_RELEASE"):
            return Path(os.environ["DEPARTMENT_SYSTEM_TEST_RELEASE"])
        project = Path(__file__).resolve().parents[1]
        return project

    def test_export_refuses_outside_project_directory(self):
        with self.temporary_directory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            with self.assertRaises(ValueError):
                exporter.prepare(root, Path(directory) / "other-project")

    def test_actual_export_to_setup_complete_model_roles_and_learning_sources(self):
        with self.temporary_directory() as directory:
            root = self.fixture(Path(directory))
            manifest = package.validate_release(root)
            result = setup.setup(root)
            self.assertEqual(result["external_permissions_issued"], 0)
            self.assertEqual(result["chats_created"], 0)
            current = json.loads((root / "data/task-contract.json").read_text())
            self.assertEqual(current["goal_delivery_runtime"]["model"], "goal_delivery_assistant_v1")
            roles = json.loads((root / "data/department-registry.json").read_text())["departments"]
            self.assertEqual({role["id"] for role in roles}, set(manifest["roles"]))
            self.assertFalse(next(role for role in roles if role["id"] == "qa")["new_dispatch_enabled"])
            self.assertIn("future-specialist", {role["id"] for role in roles})
            for role in roles:
                self.assertTrue((root / role["professional_skill"]).is_file())
                self.assertTrue((root / ("data/learning/departments/" + role["id"] + ".json")).is_file())

    def test_missing_tampered_or_unknown_package_fails_before_any_local_creation(self):
        variants = ("missing", "tampered", "unknown", "bad-fingerprint", "bad-bytes")
        for kind in variants:
            with self.subTest(kind=kind), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                if kind == "missing":
                    (root / "tools/flashcast_ops.py").unlink()
                elif kind == "tampered":
                    (root / "tools/flashcast_ops.py").write_text("changed package bytes\n")
                elif kind == "unknown":
                    (root / "tools/unmanifested.py").write_text("EXTRA = True\n")
                else:
                    path = root / "release-manifest.json"
                    manifest = json.loads(path.read_text())
                    if kind == "bad-fingerprint":
                        manifest["fingerprint"] = "0" * 64
                    else:
                        manifest["files"][0]["bytes"] += 1
                        manifest = package.seal_manifest(manifest)
                    path.write_text(json.dumps(manifest))
                before = self.files(root)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertFalse((root / "data").exists())

    def test_resealed_old_or_unknown_model_semantics_cannot_install(self):
        for model in ("professional_qa_hq_v1", "unknown-future-model", None):
            with self.subTest(model=model), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                path = root / "examples/task-contract.example.json"
                value = json.loads(path.read_text())
                value["goal_delivery_runtime"]["model"] = model
                path.write_text(json.dumps(value))
                self.reseal(root)
                before = self.files(root)
                with self.assertRaises(ValueError):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertFalse((root / "data").exists())

    def test_existing_five_configs_old_runtime_model_rejected_before_additional_writes(self):
        # These are existing local installation inputs, not public defaults.
        for name in package.CONFIG_NAMES:
            with self.subTest(existing_config=name), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                value = json.loads((root / ("examples/" + name + ".example.json")).read_text())
                value["runtime_model"] = "legacy_fixed_qa"
                value["local_history"] = "fixture-existing-local-history"
                data = root / "data"
                data.mkdir()
                existing_path = data / (name + ".json")
                existing_raw = (json.dumps(value, ensure_ascii=False, indent=3) + "\n").encode("utf-8")
                existing_path.write_bytes(existing_raw)
                wip_path = data / "fixture-existing-business-wip.bin"
                wip_raw = b"\x00fixture existing business WIP\n\xff"
                wip_path.write_bytes(wip_raw)
                # The release itself is valid; only the effective local input is obsolete.
                package.validate_release(root)
                before = self.files(root)
                before_paths = {path.relative_to(root).as_posix() for path in root.rglob("*")}
                with self.assertRaisesRegex(ValueError, "Obsolete default runtime model"):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertEqual({path.relative_to(root).as_posix() for path in root.rglob("*")}, before_paths)
                self.assertEqual(existing_path.read_bytes(), existing_raw)
                self.assertEqual(wip_path.read_bytes(), wip_raw)
                self.assertEqual(set(path.name for path in data.iterdir()), {name + ".json", wip_path.name})

    def test_resealed_current_model_flags_or_retired_role_semantics_rejected(self):
        variants = ("assistant-disabled", "HQ_second_review_required", "producer_self_review_allowed",
                    "fixed_qa_new_dispatch_enabled", "single_acceptance_owner", "qa-reactivated", "qa-mode")
        for kind in variants:
            with self.subTest(kind=kind), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                if kind.startswith("qa-"):
                    path = root / "examples/department-registry.example.json"
                    value = json.loads(path.read_text())
                    qa = next(role for role in value["departments"] if role["id"] == "qa")
                    qa["new_dispatch_enabled" if kind == "qa-reactivated" else "mode"] = True if kind == "qa-reactivated" else "active"
                else:
                    path = root / "examples/task-contract.example.json"
                    value = json.loads(path.read_text())
                    model = value["goal_delivery_runtime"]
                    model["assistant_decisions_enabled" if kind == "assistant-disabled" else kind] = False if kind in {"assistant-disabled", "single_acceptance_owner"} else True
                path.write_text(json.dumps(value))
                self.reseal(root)
                before = self.files(root)
                with self.assertRaises(ValueError):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertFalse((root / "data").exists())

    def test_resealed_obsolete_positive_chain_still_rejected_by_setup(self):
        texts = ("专业部门→QA→HQ\n", "不得自审，专业结果 → QA → 总部\n",
                 "全部专业结果必须经过总部二审\n", "专业结果提交给质检部门审批后交总部\n")
        for text in texts:
            with self.subTest(text=text), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                (root / "AGENTS.md").write_text(text)
                self.reseal(root)
                before = self.files(root)
                with self.assertRaises(ValueError):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertFalse((root / "data").exists())

    def test_resealed_core_route_flags_cannot_hide_retired_qa_route(self):
        variants = ({"historical_only": True, "operational_template": False},
                    {"new_dispatch_enabled": False})
        for flags in variants:
            with self.subTest(flags=flags), self.temporary_directory() as directory:
                root = self.fixture(Path(directory))
                path = root / "examples/department-routing-rules.example.json"
                path.write_text(json.dumps({**flags, "routes": [{"required_departments": ["qa"]}]}))
                if flags.get("historical_only"):
                    manifest_path = root / "release-manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["non_runtime_files"].append(path.relative_to(root).as_posix())
                    manifest_path.write_text(json.dumps(manifest))
                self.reseal(root)
                before = self.files(root)
                with self.assertRaises(ValueError):
                    setup.setup(root)
                self.assertEqual(self.files(root), before)
                self.assertFalse((root / "data").exists())

    def test_repeat_setup_preserves_binding_authority_business_and_user_wip(self):
        with self.temporary_directory() as directory:
            root = self.fixture(Path(directory))
            setup.setup(root)
            path = root / "data/department-registry.json"
            registry = json.loads(path.read_text())
            registry["departments"][0]["chat_binding"].update(task_id="fixture-local-fixed-chat", status="bound")
            path.write_text(json.dumps(registry))
            policy = root / "data/action-policy.json"
            policy.write_text(json.dumps({"standing_authorizations": [{"fixture_only": True, "local_owner_grant": "preserve"}]}))
            (root / "company-context.md").write_text("本机已确认资料 fixture\n")
            (root / "drafts/user-wip.md").write_text("user WIP fixture\n")
            before = self.files(root)
            result = setup.setup(root)
            self.assertEqual(result["created"], [])
            self.assertEqual(self.files(root), before)

    def test_install_io_failure_rolls_back_only_this_run_created_paths(self):
        with self.temporary_directory() as directory:
            root = self.fixture(Path(directory))
            (root / "company-context.md").write_text("existing company WIP\n")
            (root / "logs").mkdir()
            (root / "logs/user-history.jsonl").write_text("existing fixture history\n")
            before = self.files(root)
            original_create = setup._create_file
            calls = []
            def fail_after_second_write(path, raw):
                original_create(path, raw)
                calls.append(path)
                if len(calls) == 2:
                    raise OSError("synthetic installation I/O failure after actual fixture write")
            with mock.patch.object(setup, "_create_file", fail_after_second_write), self.assertRaises(OSError):
                setup.setup(root)
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.files(root), before)
            self.assertTrue((root / "logs").is_dir())
            self.assertFalse((root / "data").exists())

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
        self.assertNotIn("owner_delegated_publishing_preparation", policy["routing_policy"])
        self.assertNotIn("owner_delegated_publisher_followthrough", policy["routing_policy"])
        self.assertFalse(policy["autonomous_site_release_policy"]["enabled"])
        for rule in policy["action_classes"].values():
            if isinstance(rule, dict) and "exact_requests" in rule:
                self.assertEqual(rule["exact_requests"], [])
        helper = release / "tools/owner_delegated_publishing_preparation.py"
        if helper.is_file():
            spec = importlib.util.spec_from_file_location("public_owner_preparation", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(module.PUBLIC_TEMPLATE_ONLY)
            self.assertEqual(module.AUTH_TURN_ID, "example-turn-not-native")
            self.assertEqual(module.AUTH_MESSAGE_ID, "example-message-not-native")
            with self.assertRaisesRegex(ValueError, "public_template_has_no_native_authorization"):
                module._frozen_request(release, {})


if __name__ == "__main__":
    unittest.main()
