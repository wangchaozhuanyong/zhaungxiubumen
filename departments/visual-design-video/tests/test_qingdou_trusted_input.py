"""Explicit offline fixtures; no real capture, active lexicon or publication."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import public_copy_guard as guard
import validate_douyin_publish_package as publish
import test_validate_douyin_publish_package as fixture_tests

OUTSIDE = Path("/private/tmp/flashcast-trusted-input-unread-unwritten-sentinel")


class TrustedInputTests(unittest.TestCase):
    def setUp(self):
        parent = guard.PROJECT_ROOT / "drafts/creative/.test-sandboxes"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = fixture_tests.DouyinPublishPackageValidatorTests().make_package(self.root)
        self.report = self.root / "qingdou-report.json"
        self.lexicon = self.root / "fixture-risk-lexicon.json"

    def update(self, path, changes):
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data, ensure_ascii=False))
        return data

    def unmarked_untrusted(self):
        # Removing a marker does NOT make these fixture bytes authentic.
        for path in [self.package, self.report, self.root / "copy-check-v1/public-copy-guard.json"]:
            data = json.loads(path.read_text())
            data.pop("provenance", None)
            data.pop("validation_mode", None)
            path.write_text(json.dumps(data, ensure_ascii=False))
        evidence = self.root / "evidence/qingdou-result.png"
        evidence.write_bytes(b"Unverified local bytes, not an authenticated platform capture.")
        self.update(self.report, {"evidence_sha256": guard.sha_bytes(evidence.read_bytes())})

    def risk(self):
        return self.update(self.report, {"status": "risk_detected", "findings": [
            {"term": "高级感", "field": "on_screen_copy", "reason": "unverified allegation without actual capture"}]})

    def declaration(self, report):
        return {"status": "personally_inspected_real_full_batch", "reviewer": "offline-contract-reviewer",
                "reviewed_at": "2026-10-02T03:40:00+08:00", "declaration": "HUMAN_DECLARED_REAL_QINGDOU_FULL_BATCH",
                **{k: report[k] for k in ["task_id", "run_id", "public_text_sha256", "batch_sha256", "evidence_sha256"]}}

    def agent_declaration(self, report):
        return {**self.declaration(report), "status": "agent_inspected_real_full_batch",
                "declaration": "AGENT_VERIFIED_REAL_QINGDOU_FULL_BATCH", "surface": "codex_iab"}

    def agent_contract(self):
        # In-memory declaration contract only; these fixtures are never imported
        # into the active lexicon or saved as real platform evidence/PASS output.
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        report.update(status="PASS", findings=[], observed_result="未检查到敏感词")
        report["capture_review"] = self.agent_declaration(report)
        return report

    def test_no_hit_agent_review_needs_no_human_declaration(self):
        report = self.agent_contract()
        self.assertIsNone(guard.require_capture_review(report, b"unmarked bytes"))
        self.assertNotIn("HUMAN_DECLARED", report["capture_review"]["declaration"])

    def test_agent_shortcut_rejects_risk_unchecked_or_missing_result(self):
        changes = [{"status": "risk_detected"}, {"status": "NOT_PERFORMED"},
                   {"findings": [{"term": "风险"}]}, {"findings": None},
                   {"observed_result": ""}, {"observed_result": "检查到1个敏感词"}]
        report = self.agent_contract()
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "personal_review_required"):
                guard.require_capture_review({**report, **change}, b"unmarked bytes")

    def test_agent_review_requires_named_observation_and_iab_surface(self):
        report = self.agent_contract()
        for key in ["reviewer", "reviewed_at", "status", "declaration", "surface"]:
            review = {**report["capture_review"]}
            review.pop(key)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "personal_review_required"):
                guard.require_capture_review({**report, "capture_review": review}, b"unmarked bytes")

    def test_agent_review_cannot_reuse_mismatched_batch_or_evidence(self):
        report = self.agent_contract()
        for key in ["task_id", "run_id", "public_text_sha256", "batch_sha256", "evidence_sha256"]:
            review = {**report["capture_review"], key: "mismatch"}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "capture_review_binding_mismatch"):
                guard.require_capture_review({**report, "capture_review": review}, b"unmarked bytes")

    def test_agent_review_does_not_allow_synthetic_report_or_capture(self):
        report = self.agent_contract()
        for data, evidence in [({**report, "provenance": "SYNTHETIC_TEST_ONLY"}, b"unmarked bytes"),
                               (report, b"SYNTHETIC_TEST_ONLY")]:
            with self.assertRaisesRegex(ValueError, "synthetic_input"):
                guard.require_capture_review(data, evidence)

    def test_default_real_validation_rejects_synthetic_package(self):
        result = publish.validate(self.package, self.lexicon)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("synthetic_input", " ".join(result["errors"]))

    def test_default_record_rejects_synthetic_without_lexicon_write(self):
        self.risk()
        old = self.lexicon.read_bytes()
        with self.assertRaisesRegex(ValueError, "synthetic_input"):
            guard.record(self.package, self.report, self.lexicon)
        self.assertEqual(old, self.lexicon.read_bytes())

    def test_explicit_markers_rejected_recursively(self):
        markers = ["SYNTHETIC_TEST_ONLY", "synthetic-test-only-not-real", "provenance-test",
                   "合成", "合成测试", "模拟", "测试夹具", "仅供测试", "synthetic", {"is_synthetic": True},
                   {"synthetic_test_only": True}, {"source": {"provenance": "provenance_test"}},
                   "ＳＹＮＴＨＥＴＩＣ＿ＴＥＳＴ＿ＯＮＬＹ", "SYNTHETIC\u200b_TEST_ONLY", {"合成": True}]
        for marker in markers:
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "synthetic_input"):
                guard.reject_synthetic({"nested": [marker]})

    def test_marker_false_does_not_prove_authenticity(self):
        report = {"synthetic": False}
        self.assertFalse(guard.synthetic_marker(report))
        with self.assertRaisesRegex(ValueError, "personal_review_required"):
            guard.require_capture_review(report, b"unmarked bytes")

    def test_unmarked_self_consistent_pass_requires_personal_review(self):
        self.unmarked_untrusted()
        result = publish.validate(self.package, self.lexicon)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("real_full_batch_capture_personal_review_required", result["errors"])

    def test_unmarked_self_consistent_risk_does_not_import_without_review(self):
        self.unmarked_untrusted()
        self.risk()
        old = self.lexicon.read_bytes()
        with self.assertRaisesRegex(ValueError, "personal_review_required"):
            guard.record(self.package, self.report, self.lexicon)
        self.assertEqual(old, self.lexicon.read_bytes())

    def test_claimed_review_cannot_override_report_synthetic_marker(self):
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        report.update(capture_review=self.declaration(report), provenance="SYNTHETIC_TEST_ONLY")
        with self.assertRaisesRegex(ValueError, "synthetic_input"):
            guard.require_capture_review(report, b"unmarked bytes")

    def test_claimed_review_cannot_override_marker_in_evidence_bytes(self):
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        report["capture_review"] = self.declaration(report)
        with self.assertRaisesRegex(ValueError, "synthetic_input"):
            guard.require_capture_review(report, b"PNG-data\x00SYNTHETIC_TEST_ONLY")

    def test_review_bindings_all_required(self):
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        for key in ["task_id", "run_id", "public_text_sha256", "batch_sha256", "evidence_sha256"]:
            with self.subTest(key=key):
                review = self.declaration(report)
                review[key] = "mismatch"
                with self.assertRaisesRegex(ValueError, "capture_review_binding_mismatch"):
                    guard.require_capture_review({**report, "capture_review": review}, b"unmarked bytes")

    def test_reviewer_time_status_declaration_required(self):
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        for key in ["reviewer", "reviewed_at", "status", "declaration"]:
            with self.subTest(key=key):
                review = self.declaration(report)
                review.pop(key)
                with self.assertRaisesRegex(ValueError, "personal_review_required"):
                    guard.require_capture_review({**report, "capture_review": review}, b"unmarked bytes")

    def test_review_helper_is_declaration_check_not_source_authentication(self):
        self.unmarked_untrusted()
        report = json.loads(self.report.read_text())
        report["capture_review"] = self.declaration(report)
        # Only the declaration contract is exercised; no real record or PASS claim.
        self.assertIsNone(guard.require_capture_review(report, b"unmarked bytes"))

    def test_explicit_sandbox_pass_is_never_real_pass(self):
        result = publish.validate(self.package, self.lexicon, sandbox_root=self.root)
        self.assertEqual(result["status"], "PASS_SANDBOX_ONLY")
        self.assertEqual(result["validation_mode"], "SYNTHETIC_TEST_ONLY")
        self.assertFalse(result["public_release_allowed"])

    def test_sandbox_record_is_marked_nonproduction_and_idempotent(self):
        self.risk()
        first = guard.record(self.package, self.report, self.lexicon, sandbox_root=self.root)
        second = guard.record(self.package, self.report, self.lexicon, sandbox_root=self.root)
        data = json.loads(self.lexicon.read_text())
        self.assertEqual(first["added_terms"], 1)
        self.assertEqual(second["status"], "NO_CHANGE")
        self.assertEqual(data["entries"][0]["source"], "synthetic_test_finding")
        self.assertEqual(data["evidence_status"], "SYNTHETIC_TEST_ONLY")
        self.assertFalse(first["public_release_allowed"])
        with self.assertRaisesRegex(ValueError, "synthetic_input"):
            guard.load_lexicon(self.lexicon)

    def test_sandbox_cannot_access_default_active_lexicon(self):
        old = guard.DEFAULT_LEXICON.read_bytes()
        with self.assertRaisesRegex(ValueError, "path_must_belong"):
            guard.record(self.package, self.report, guard.DEFAULT_LEXICON, sandbox_root=self.root)
        self.assertEqual(old, guard.DEFAULT_LEXICON.read_bytes())

    def test_sandbox_root_cannot_be_project_or_external(self):
        for root in [guard.PROJECT_ROOT, OUTSIDE, guard.PROJECT_ROOT / "data/knowledge"]:
            with self.subTest(root=str(root)), self.assertRaisesRegex(ValueError, "test_sandbox_must_be"):
                guard.execution_root(root)

    def test_package_path_outside_blocked_before_any_read(self):
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("outside read attempted")):
            with self.assertRaisesRegex(ValueError, "path_must_belong"):
                guard.read_fields(OUTSIDE)
            result = publish.validate(OUTSIDE, self.lexicon)
        self.assertEqual(result["status"], "FAIL")

    def test_every_public_reference_preflight_blocks_external_before_text_read(self):
        payload = json.loads(self.package.read_text())
        payload.pop("provenance")
        for field in guard.PACKAGE_PATH_FIELDS:
            with self.subTest(field=field), mock.patch.object(guard, "load_json", return_value={**payload, field: str(OUTSIDE)}), mock.patch.object(Path, "read_text", side_effect=AssertionError("text read before preflight")):
                with self.assertRaisesRegex(ValueError, "path_must_belong"):
                    guard.read_fields(self.package)

    def test_absolute_relative_expanduser_and_dotdot_outside_paths_rejected(self):
        for value in [str(OUTSIDE), os.path.relpath(OUTSIDE, self.root), "~/.flashcast-path-preflight-sentinel", str(OUTSIDE.parent / ".." / "tmp" / OUTSIDE.name)]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "path_must_belong"):
                publish.resolve(self.root, value)

    def test_symlink_outside_including_dangling_target_is_rejected(self):
        link = self.root / "outside-link.txt"
        link.symlink_to(OUTSIDE)
        with self.assertRaisesRegex(ValueError, "path_must_belong"):
            guard.local_path(self.root, "outside-link.txt")

    def test_in_project_symlink_normalizes_to_safe_target(self):
        target = self.root / "public-text/cover-copy.txt"
        link = self.root / "safe-link.txt"
        link.symlink_to(target)
        self.assertEqual(guard.local_path(self.root, "safe-link.txt"), target.resolve())

    def test_record_rejects_external_report_and_lexicon_without_writes(self):
        old = self.lexicon.read_bytes()
        for report, lexicon in [(OUTSIDE, self.lexicon), (self.report, OUTSIDE)]:
            with self.subTest(report=str(report), lexicon=str(lexicon)), self.assertRaisesRegex(ValueError, "path_must_belong"):
                guard.record(self.package, report, lexicon)
        self.assertEqual(old, self.lexicon.read_bytes())

    def test_record_external_evidence_symlink_rejected(self):
        self.unmarked_untrusted()
        link = self.root / "evidence/outside-link.png"
        link.symlink_to(OUTSIDE)
        self.update(self.report, {"evidence_path": "evidence/outside-link.png"})
        with self.assertRaisesRegex(ValueError, "path_must_belong"):
            guard.record(self.package, self.report, self.lexicon)

    def test_output_dir_and_broken_output_file_symlink_rejected(self):
        link = self.root / "outside-output"
        link.symlink_to(OUTSIDE, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "path_must_belong"):
            guard.prepare(self.package, link, self.lexicon, sandbox_root=self.root)
        local = self.root / "new-batch"
        local.mkdir()
        (local / "public-text-batch.txt").symlink_to(OUTSIDE)
        with self.assertRaisesRegex(ValueError, "path_must_belong"):
            guard.prepare(self.package, local, self.lexicon, sandbox_root=self.root)

    def test_cli_outside_output_rejected_without_creating_it(self):
        result = subprocess.run([sys.executable, str(Path(publish.__file__)), str(self.package), "--out", str(OUTSIDE)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("path_must_belong", result.stdout)

    def test_four_and_six_tags_rejected_even_in_sandbox(self):
        data = json.loads(self.package.read_text())
        for tags in [data["hashtags"][:4], data["hashtags"] + ["#多余话题"]]:
            with self.subTest(count=len(tags)):
                self.update(self.package, {"hashtags": tags})
                with self.assertRaisesRegex(ValueError, "five_valid_hashtags"):
                    guard.prepare(self.package, self.root / "bad-tags", self.lexicon, sandbox_root=self.root)
                self.assertNotEqual(publish.validate(self.package, self.lexicon, sandbox_root=self.root)["status"], "PASS_SANDBOX_ONLY")

    def test_wrong_task_or_run_rejected_without_import(self):
        self.risk()
        original = json.loads(self.report.read_text())
        old = self.lexicon.read_bytes()
        for key in ["task_id", "run_id"]:
            self.report.write_text(json.dumps({**original, key: "wrong"}))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "task_run_mismatch"):
                guard.record(self.package, self.report, self.lexicon, sandbox_root=self.root)
        self.assertEqual(old, self.lexicon.read_bytes())

    def test_every_text_and_tags_edit_requires_new_complete_batch(self):
        data = json.loads(self.package.read_text())
        for field in ["on_screen_copy_path", "cover_copy_path", "video_description_path"]:
            path = self.root / data[field]
            old = path.read_bytes()
            path.write_bytes(old + "改字".encode())
            result = publish.validate(self.package, self.lexicon, sandbox_root=self.root)
            self.assertIn("single_public_text_batch_stale", result["errors"])
            path.write_bytes(old)
        tags = list(data["hashtags"])
        tags[2] = "#更新主题"
        self.update(self.package, {"hashtags": tags})
        self.assertIn("single_public_text_batch_stale", publish.validate(self.package, self.lexicon, sandbox_root=self.root)["errors"])


if __name__ == "__main__":
    unittest.main()
