import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import native_cms_admission as admission
from tools import managed_cms_permit_issuer as issuer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "drafts/operations/fc-20260927-cms-native-staged-admission-v1/admission-manifest.json"


class NativeStagedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_all_18_exact_sources_pass_without_production_permission(self):
        results = admission.validate_manifest(ROOT, self.manifest)
        self.assertEqual(len(results), 18)
        self.assertTrue(all(r["source_admission"] == "PASS"
                            and r["production_authorized"] is False
                            and r["permit_issued"] is False for r in results))

    def test_registered_targets_still_cannot_issue_permits(self):
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

    def test_promoting_manifest_to_release_fails(self):
        for key in ["production_authorized", "issuer_integration_executed", "permit_issued"]:
            with self.subTest(key=key):
                m = copy.deepcopy(self.manifest)
                m[key] = True
                with self.assertRaises(admission.AdmissionError):
                    admission.validate_manifest(ROOT, m)

    def test_missing_or_duplicate_scope_is_rejected(self):
        for entries in [self.manifest["entries"][:-1],
                        self.manifest["entries"][:-1] + [self.manifest["entries"][0]]]:
            with self.assertRaises(admission.AdmissionError):
                admission.validate_manifest(ROOT, {**self.manifest, "entries": entries})

    def test_root_escape_and_unpinned_changes_are_rejected(self):
        for pin in [{"path": "/etc/passwd", "sha256": "a" * 64},
                    {"path": "../AGENTS.md", "sha256": "a" * 64},
                    {**self.manifest["entries"][0]["qa"], "sha256": "b" * 64}]:
            with self.assertRaises(admission.AdmissionError):
                admission.pinned_json(ROOT, pin)

    def assert_mutation_rejected(self, key, mutator):
        # Re-pin the mutated fixture so this tests semantic guards, not just SHA.
        for original in self.manifest["entries"]:
            with self.subTest(candidate=original["candidate_version"], mutation=key):
                with tempfile.TemporaryDirectory(dir=ROOT / "drafts/operations/fc-20260927-cms-native-staged-admission-v1") as folder:
                    root = Path(folder)
                    entry = copy.deepcopy(original)
                    for artifact in ["binding", "source", "baseline", "rollback", "qa", "original_qa"]:
                        raw = (ROOT / original[artifact]["path"]).read_bytes()
                        path = root / original[artifact]["path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                    path = root / entry[key]["path"]
                    row = json.loads(path.read_text())
                    mutator(row)
                    path.write_text(json.dumps(row, ensure_ascii=False))
                    entry[key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    with self.assertRaises(admission.AdmissionError):
                        admission.validate_entry(root, entry)


MUTATIONS = {
    "qa_wrong_fixed_task": ("qa", lambda r: r.update(chat_task_id="other-task")),
    "qa_wrong_project": ("qa", lambda r: r.update(project_id="other-project")),
    "qa_planning_scope": ("qa", lambda r: r.update(review_scope="planning_only")),
    "qa_candidate_scope": ("qa", lambda r: r.update(scope="flashcast.com.my:other")),
    "qa_wrong_action": ("qa", lambda r: r.update(action_id="publish-other")),
    "qa_lacks_gate_status": ("qa", lambda r: r.pop("gate_status")),
    "qa_pretends_release_ready": ("qa", lambda r: r.update(release_ready=True)),
    "qa_wrong_field": ("qa", lambda r: r.update(allowed_fields=["title_en", "content_zh"])),
    "binding_wrong_row": ("binding", lambda r: r.update(record_id="wrong-row")),
    "binding_wrong_body_fields": ("binding", lambda r: r.update(changed_fields=["title_en", "content_zh"])),
    "binding_wrong_scope": ("binding", lambda r: r.update(scope="other-site:services/design")),
    "binding_fake_save": ("binding", lambda r: r.update(saved_id="fake-save")),
    "binding_parent_guard_removed": ("binding", lambda r: r["website_producer"].update(requiresParentRun=False)),
    "baseline_row_swap": ("baseline", lambda r: r.update(id="other-row")),
    "baseline_cas_changed": ("baseline", lambda r: r.update(updated_at="2026-09-27T00:00:00Z")),
    "baseline_retained_changed": ("baseline", lambda r: r.update(slug="other-slug")),
    "rollback_already_applied": ("rollback", lambda r: r.update(applied=True)),
    "rollback_unprotected": ("rollback", lambda r: r.update(separate_protected_rollback_permit_required=False)),
    "original_qa_other_candidate": ("original_qa", lambda r: r.update(candidate_version="other")),
}


for name, (artifact, mutate) in MUTATIONS.items():
    def test(self, key=artifact, mutator=mutate):
        self.assert_mutation_rejected(key, mutator)
    setattr(NativeStagedAdmissionTests, "test_reject_" + name, test)


if __name__ == "__main__":
    unittest.main()
