"""Affected public-export privacy behavior, using synthetic local fixtures only."""
import ast
import json
from pathlib import Path
import unittest

import export_department_system as export
import department_system_package as package
import test_export_department_system as fixtures


class NumericPrivacyTests(unittest.TestCase):
    setUp = fixtures.ExportTests.setUp
    write = fixtures.ExportTests.write
    write_json = fixtures.ExportTests.write_json

    def test_consistent_native_formats_and_csv(self):
        # Assembly keeps public re-exports from rewriting the test's source data.
        original = "12345" + "678901"
        other = "98765" + "432101"
        source = repr(original) + ' "AW-' + original + '" "locations/' + original + '" ' + repr(other)
        source += ' "google_ads:example:campaigns:' + original + '+' + other + ':business-logo:asset-' + original + '"'
        source += ' "google-business-profile:' + other + ':description-only" "row,' + original + ',AW-' + other + '"'
        result = export.public_numeric_identifiers(source)
        values = ast.literal_eval("[" + result.replace(" ", ",") + "]")
        self.assertTrue(values[0].startswith("000"))
        self.assertEqual(len(values[0]), len(original))
        self.assertEqual(values[1], "AW-" + values[0])
        self.assertEqual(values[2], "locations/" + values[0])
        self.assertNotEqual(values[0], values[3])
        self.assertEqual(values[4], "google_ads:example:campaigns:" + values[0] + "+" + values[3] + ":business-logo:asset-" + values[0])
        self.assertEqual(values[5], "google-business-profile:" + values[3] + ":description-only")
        self.assertEqual(values[6], "row," + values[0] + ",AW-" + values[3])
        self.assertNotIn(original, result)
        self.assertNotIn(other, result)
        self.assertEqual(export.public_text(source, self.root), result)
        self.assertEqual(export.public_numeric_identifiers(result), result)

    def test_identifier_width_boundaries_and_nonidentifier_types(self):
        for width in (10, 11, 22):
            original = "1" * width
            result = ast.literal_eval(export.public_numeric_identifiers(repr(original)))
            self.assertEqual(len(result), width)
            self.assertTrue(result.startswith("000"))
            self.assertNotEqual(result, original)
        for width in (9, 23):
            original = "1" * width
            self.assertEqual(export.public_numeric_identifiers(repr(original)), repr(original))
        original = "12345" + "678901"
        numeric_expression = "(" + original + "," + original + ")"
        dates_and_short_ids = ' "2026-10-10" "20261010" "tiny-id" '
        self.assertEqual(export.public_numeric_identifiers(numeric_expression), numeric_expression)
        self.assertEqual(export.public_numeric_identifiers(dates_and_short_ids), dates_and_short_ids)

    def test_all_resource_and_scope_forms_reuse_same_synthetic_value(self):
        original = "54321" + "678901"
        expected = ast.literal_eval(export.public_numeric_identifiers(repr(original)))
        for resource in ("locations", "customers", "accounts", "campaigns", "adGroups", "assets"):
            self.assertEqual(export.public_numeric_identifiers(resource + "/" + original), resource + "/" + expected)
        for resource in ("campaign", "campaigns", "asset", "assets", "google-business-profile"):
            for separator in (":", "/", "-"):
                self.assertEqual(export.public_numeric_identifiers(resource + separator + original), resource + separator + expected)

    def test_prepare_removes_numeric_destinations_without_changing_source(self):
        original = "24680" + "123456"
        tool = "NATIVE_ID = " + repr(original) + "\nRESOURCE = 'customers/" + original + "'\n"
        self.write("tools/new_consumer.py", tool)
        self.write_json("templates/privacy-check.json", {"scope": "campaigns:" + original, "destination": original})
        source_bytes = (self.root / "tools/new_consumer.py").read_bytes()
        export.prepare(self.root, self.target)
        package.validate_release(self.target)
        public_tool = (self.target / "tools/new_consumer.py").read_text()
        public_template = json.loads((self.target / "templates/privacy-check.json").read_text())
        self.assertNotIn(original, public_tool)
        self.assertNotEqual(public_template["destination"], original)
        self.assertEqual(public_template["scope"], "campaigns:" + public_template["destination"])
        self.assertEqual((self.root / "tools/new_consumer.py").read_bytes(), source_bytes)
        namespace = {}
        exec(public_tool, namespace)
        self.assertIsInstance(namespace["NATIVE_ID"], str)
        self.assertEqual(namespace["RESOURCE"], "customers/" + namespace["NATIVE_ID"])
        manifest_before = (self.target / "release-manifest.json").read_bytes()
        export.prepare(self.root, self.target)
        self.assertEqual((self.target / "release-manifest.json").read_bytes(), manifest_before)

    def test_chat_health_bindings_and_permissions_stay_unusable(self):
        # Existing consumer paths must still remove bindings and native permits.
        private_chat = "private-chat-not-native"
        private_permission = "synthetic-private-exact-permission"
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text())
        for row in registry["departments"]:
            row["chat_binding"]["task_id"] = private_chat
            row["chat_binding"]["dispatch_eligible"] = True
        self.write_json("data/department-registry.json", registry)
        self.write("tools/new_consumer.py", "FIXED_CHAT = " + repr(private_chat) + "\n")
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text())
        policy["action_classes"]["site_publish"]["exact_requests"] = [{"native_authority": private_permission}]
        self.write_json("data/action-policy.json", policy)
        export.prepare(self.root, self.target)
        combined = "\n".join(path.read_text() for path in self.target.rglob("*") if path.is_file())
        self.assertNotIn(private_chat, combined)
        self.assertNotIn(private_permission, combined)
        self.assertNotIn("private-current-health", combined)
        public_registry = json.loads((self.target / "examples/department-registry.example.json").read_text())
        for row in public_registry["departments"]:
            self.assertEqual(row["chat_binding"]["status"], "unbound")
            self.assertFalse(row["chat_binding"]["dispatch_eligible"])
            self.assertEqual(row["chat_binding"]["task_id"], "")
            self.assertEqual(row["chat_binding"]["reply_health"], "not_verified")
        public_policy = json.loads((self.target / "examples/action-policy.example.json").read_text())
        self.assertEqual(public_policy["standing_authorizations"], [])
        self.assertEqual(public_policy["action_classes"]["site_publish"]["exact_requests"], [])
        self.assertFalse(public_policy["autonomous_site_release_policy"]["enabled"])

    def test_public_exact_helper_cannot_reuse_permission(self):
        source = 'AUTH = {"text": "synthetic-private-exact-permission"}\ndef check():\n    return AUTH\n'
        result = export.public_exact_helper("tools/owner_example_policy.py", source)
        self.assertNotIn("synthetic-private-exact-permission", result)
        namespace = {}
        exec(result, namespace)
        with self.assertRaisesRegex(ValueError, "public_template_has_no_native_authorization"):
            namespace["check"]()


if __name__ == "__main__":
    unittest.main()
