import json
from pathlib import Path
import unittest

from tools.native_cms_admission import AdmissionError
from tools.native_cms_admission_v2 import validate_staged_native_manifest
from tools import managed_cms_permit_issuer as issuer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drafts/operations/fc-20260927-cms-native-staged-admission-v2/admission-manifest.json"


class NativeHeaderLocksTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_all_original_18_bindings_still_pass(self):
        results = validate_staged_native_manifest(ROOT, self.manifest)
        self.assertEqual(len(results), 18)
        self.assertTrue(all(not r["permit_issued"] and not r["production_authorized"]
                            for r in results))

    def test_registered_staged_targets_remain_no_permit(self):
        versions = {e["candidate_version"] for e in self.manifest["entries"]}
        self.assertEqual(len(versions), 18)
        for version in versions:
            with self.subTest(version=version):
                target = issuer.TARGETS[version]
                self.assertEqual(target["candidate_shape"], "native_bilingual_body")
                self.assertTrue(target["native_registration_only"])
                self.assertFalse(target["release_ready"])
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_new_permit_target(target)


for field in ["task_id", "candidate_version", "native_capability_head"]:
    for absent in [False, True]:
        def test(self, key=field, missing=absent):
            manifest = dict(self.manifest)
            if missing:
                manifest.pop(key)
            else:
                manifest[key] = "other" if key != "native_capability_head" else "a" * 40
            with self.assertRaises(AdmissionError):
                validate_staged_native_manifest(ROOT, manifest)
        setattr(NativeHeaderLocksTests, "test_reject_" + field + ("_missing" if absent else "_wrong"), test)


if __name__ == "__main__":
    unittest.main()
