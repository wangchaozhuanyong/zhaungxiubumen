"""Local issuer integration and fail-closed checks; no remote calls or secrets."""
import copy
import hashlib
import json
from pathlib import Path
import types
import unittest

from . import managed_cms_permit_issuer as active
from . import native_cms_issuer_integration as integration

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "drafts/operations/fc-20260927-cms-native-issuer-integration-v1"


class NativeIssuerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_hash = hashlib.sha256((ROOT / "tools/managed_cms_permit_issuer.py").read_bytes()).hexdigest()
        cls.original_targets = copy.deepcopy(active.TARGETS)
        source = (DIR / "proposed-managed-cms-permit-issuer.py").read_text()
        cls.candidate = types.ModuleType("tools._native_candidate")
        cls.candidate.__package__ = "tools"
        cls.candidate.__file__ = str(ROOT / "tools/managed_cms_permit_issuer.py")
        exec(compile(source, str(DIR / "proposed-managed-cms-permit-issuer.py"), "exec"), cls.candidate.__dict__)
        cls.new = cls.candidate.NATIVE_TARGETS

    def read_adapter(self, target):
        return json.loads((ROOT / target["candidate"][0]).read_text())

    def test_historical_targets_and_registered_stage_unchanged(self):
        self.assertEqual(active.TARGETS, self.original_targets)
        self.assertEqual(hashlib.sha256((ROOT / "tools/managed_cms_permit_issuer.py").read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(len(self.candidate.TARGETS), 65)
        self.assertEqual(len(self.new), 18)
        for name, target in self.candidate.TARGETS.items():
            self.assertEqual(active.TARGETS[name], target)
        for name in self.new:
            with self.subTest(name=name):
                target = active.TARGETS[name]
                self.assertTrue(target["native_registration_only"])
                self.assertFalse(target["release_ready"])
                with self.assertRaises(active.PermitEvidenceError):
                    active.validate_new_permit_target(target)

    def test_all_exact_native_execution_adapters_valid(self):
        for name, target in self.new.items():
            with self.subTest(name=name):
                self.candidate.validate_candidate_binding(self.read_adapter(target), target)
                self.assertIn(name, self.candidate.PARENT_RUN_TARGETS)
                self.assertEqual(self.candidate.rollback_parent_binding(name, "rollback", "test-parent", 12), {"parentPermitId": "test-parent", "parentRunId": 12})

    def test_all_native_targets_require_completed_parent_for_rollback(self):
        for name in self.new:
            for permit, run in [(None, None), ("test-parent", None), (None, 12), ("test-parent", 0)]:
                with self.subTest(name=name, permit=permit, run=run):
                    with self.assertRaises(self.candidate.PermitEvidenceError):
                        self.candidate.rollback_parent_binding(name, "rollback", permit, run)

    def test_every_binding_only_source_qa_is_rejected_for_release(self):
        for name, target in self.new.items():
            with self.subTest(name=name):
                row = json.loads((ROOT / target["qa_outbox"][0]).read_text())
                self.assertFalse(self.candidate.structured_qa_outbox_matches(row, target))
                with self.assertRaisesRegex(self.candidate.PermitEvidenceError, "no actual release readiness"):
                    self.candidate.validate_new_permit_target(target)

    def test_record_cas_retained_fields_and_managed_identity_mutations_rejected(self):
        for name, target in self.new.items():
            original = self.read_adapter(target)
            mutations = []
            for key in ["task_id", "action_id", "candidate_version", "record_id", "scope", "table", "content_type", "expected_updated_at", "expected_version"]:
                row = copy.deepcopy(original); row[key] = "wrong"; mutations.append((key, row))
            for key, value in [("mode", "publish"), ("contentType", "site_page"), ("expectedUpdatedAt", "wrong")]:
                row = copy.deepcopy(original); row["request"][key] = value; mutations.append((key, row))
            row = copy.deepcopy(original); row["request"]["record"]["title_en"] = "changed unrelated title"; mutations.append(("retained", row))
            row = copy.deepcopy(original); row["request"]["record"]["content_en"] += " changed"; mutations.append(("body", row))
            row = copy.deepcopy(original); row["request"]["managedCandidate"]["scope"] = "wrong"; mutations.append(("managed", row))
            row = copy.deepcopy(original); row["changed_fields"].append("faqs_en"); mutations.append(("extra field", row))
            row = copy.deepcopy(original); row["request"]["record"].pop("version"); mutations.append(("omitted CAS", row))
            row = copy.deepcopy(original); row["source_frozen_candidate"]["sha256"] = "0" * 64; mutations.append(("source pin", row))
            for label, row in mutations:
                with self.subTest(name=name, mutation=label):
                    with self.assertRaises(self.candidate.PermitEvidenceError):
                        self.candidate.validate_candidate_binding(row, target)

    def test_target_registry_identity_mutations_rejected(self):
        for name, target in self.new.items():
            for key in ["task_id", "record_id", "scope", "slug"]:
                bad = copy.deepcopy(target); bad[key] = "wrong"
                with self.subTest(name=name, key=key):
                    with self.assertRaises(self.candidate.PermitEvidenceError):
                        self.candidate.validate_candidate_binding(self.read_adapter(target), bad)

    def test_qa_exact_candidate_source_scope_and_readiness_are_all_required(self):
        target = next(iter(self.new.values())); entry = target["native_source_entry"]
        row = {"department": "qa", "task_id": target["task_id"], "status": "completed",
               "gate_status": "PASS_FOR_AUTO_RELEASE", "risk_level": "R1", "verdict": "pass",
               "action_id": target["action_id"], "candidate_version": target["candidate_version"],
               "candidate_sha256": target["candidate"][1], "scope": target["scope"], "blockers": [],
               "release_ready": True, "review_scope": "exact_body_release_with_protected_zero_write_preview",
               "source_candidate_path": entry["source"]["path"], "source_candidate_sha256": entry["source"]["sha256"],
               "allowed_fields": ["content_en", "content_zh"], "record_id": target["record_id"], "table": target["table"]}
        # A matcher fixture is not a receipt chain, QA file or actual release.
        self.assertTrue(self.candidate.structured_qa_outbox_matches(row, target))
        for key in ["task_id", "candidate_sha256", "scope", "release_ready", "review_scope", "source_candidate_sha256", "record_id", "table"]:
            bad = copy.deepcopy(row); bad[key] = "wrong"
            with self.subTest(key=key):
                self.assertFalse(self.candidate.structured_qa_outbox_matches(bad, target))

    def test_registration_index_is_pinned(self):
        from .native_cms_admission import AdmissionError, pinned_json
        self.assertEqual(len(pinned_json(ROOT, integration.INDEX_PIN)["entries"]), 18)
        with self.assertRaises(AdmissionError):
            pinned_json(ROOT, {**integration.INDEX_PIN, "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
