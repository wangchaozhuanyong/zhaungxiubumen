from __future__ import annotations

import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_copy_guard import batch_text, check, load_lexicon as real_load_lexicon, normalized, prepare as real_prepare, public_hash, read_fields as real_read_fields, record as real_record, scan, sha_bytes
import test_validate_douyin_publish_package as publish_tests
from validate_douyin_publish_package import validate as real_validate


def prepare(package, output, lexicon):
    return real_prepare(package, output, lexicon, sandbox_root=package.parent)


def read_fields(package):
    return real_read_fields(package, sandbox_root=package.parent)


def record(package, report, lexicon):
    return real_record(package, report, lexicon, sandbox_root=package.parent)


def load_lexicon(lexicon):
    return real_load_lexicon(lexicon, sandbox_root=lexicon.parent)


def validate(package, lexicon):
    return real_validate(package, lexicon, sandbox_root=package.parent)


class PublicCopyGuardTests(unittest.TestCase):
    def test_neutral_headers_do_not_add_claims_and_hash_covers_same_fields(self) -> None:
        fields = {"on_screen_copy": "柜墙形成整体", "spoken_copy": "先看动线",
                  "cover_copy": "意式客厅", "video_description": "概念方案",
                  "hashtags": ["#马来西亚装修公司", "#马来西亚全屋定制", "#空间设计", "#意式简约", "#吉隆坡装修"]}
        before = public_hash(fields)
        text = batch_text(fields)
        self.assertNotIn("全部", text)
        for header in ("视频文字", "口播", "封面", "描述", "话题"):
            self.assertIn("【" + header + "】", text)
        for value in fields.values():
            for item in value if isinstance(value, list) else [value]:
                self.assertIn(item, text)
        self.assertEqual(before, public_hash(fields))

    def test_candidate_copy_gate_does_not_require_cover_or_final_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            data = json.loads(package.read_text())
            data["production_profile"] = "candidate"
            data.pop("cover_validation_path")
            package.write_text(json.dumps(data))
            (root / "cover-validation.json").unlink()
            before = lexicon.read_bytes()
            result = check(package, lexicon, sandbox_root=root)
            self.assertEqual(result["status"], "PASS_SANDBOX_ONLY")
            self.assertEqual(result["scope"], "public_copy_only")
            self.assertFalse(result["public_release_allowed"])
            self.assertEqual(lexicon.read_bytes(), before)

    def test_copy_gate_refuses_missing_real_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            (root / "qingdou-report.json").unlink()
            result = check(package, lexicon, sandbox_root=root)
            self.assertEqual(result["status"], "HOLD_COPY_GATE")
            self.assertTrue(result["errors"])

    def test_copy_gate_risk_result_cannot_pass_or_implicitly_learn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            report = self.risk_report(package)
            data = json.loads(package.read_text())
            data["qingdou_report_path"] = report.name
            package.write_text(json.dumps(data))
            before = lexicon.read_bytes()
            result = check(package, lexicon, sandbox_root=root)
            self.assertEqual(result["status"], "HOLD_COPY_GATE")
            self.assertIn("qingdou_risk_detected_rewrite_then_recheck_full_batch", result["errors"])
            self.assertEqual(before, lexicon.read_bytes())

    def test_copy_gate_rechecks_current_lexicon_without_platform_resubmission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            report = self.risk_report(package)
            record(package, report, lexicon)
            result = check(package, lexicon, sandbox_root=root)
            self.assertEqual(result["status"], "HOLD_COPY_GATE")
            self.assertIn("previous_qingdou_risk_term_reused", result["errors"])

    def test_copy_gate_refuses_changed_text_and_partial_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            path = root / "public-text/cover-copy.txt"
            original = path.read_bytes()
            path.write_bytes(original + "已修改".encode())
            self.assertEqual(check(package, lexicon, sandbox_root=root)["status"], "HOLD_COPY_GATE")
            path.write_bytes(original)
            report = root / "qingdou-report.json"
            data = json.loads(report.read_text())
            data["checked_fields"].remove("hashtags")
            report.write_text(json.dumps(data))
            self.assertEqual(check(package, lexicon, sandbox_root=root)["status"], "HOLD_COPY_GATE")

    def test_copy_gate_real_entry_refuses_synthetic_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, lexicon = self.make(Path(temp))
            result = check(package, lexicon)
            self.assertEqual(result["status"], "HOLD_COPY_GATE")
            self.assertIn("synthetic_input", " ".join(result["errors"]))

    def make(self, root: Path) -> tuple[Path, Path]:
        package = publish_tests.DouyinPublishPackageValidatorTests().make_package(root)
        lexicon = root / "fixture-risk-lexicon.json"
        lexicon.write_text(json.dumps({"source_tool": "Qingdou", "entries": []}), encoding="utf-8")
        return package, lexicon

    def risk_report(self, package: Path, term: str = "高级感", field: str = "on_screen_copy") -> Path:
        # Synthetic test evidence only; never passed to the production CLI/lexicon.
        data, fields = read_fields(package)
        path = package.parent / "fixture-qingdou-risk.json"
        path.write_text(json.dumps({
            "tool": "Qingdou", "status": "risk_detected", "checked_at": "2026-10-02T02:00:00Z",
            "provenance": "SYNTHETIC_TEST_ONLY",
            "task_id": data["task_id"], "run_id": data["run_id"],
            "checked_fields": sorted(fields), "submission_mode": "single_batch",
            "public_text_sha256": public_hash(fields),
            "batch_sha256": sha_bytes(batch_text(fields).encode("utf-8")),
            "evidence_path": "evidence/qingdou-result.png", "evidence_sha256": sha_bytes(b"fixture"),
            "findings": [{"term": term, "field": field, "reason": "synthetic-test-only-not-a-real-risk-claim"}],
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def test_one_file_contains_all_four_fields_and_five_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, lexicon = self.make(Path(temp))
            result = prepare(package, package.parent / "check-v2", lexicon)
            text = Path(result["package_binding"]["public_text_batch_path"]).read_text(encoding="utf-8")
            _, fields = read_fields(package)
            for field, value in fields.items():
                for part in value if isinstance(value, list) else [value]:
                    self.assertIn(part, text, field)
            self.assertEqual(result["qingdou_status"], "NOT_PERFORMED")
            self.assertEqual(result["status"], "READY_FOR_QINGDOU")

    def test_spoken_copy_is_hashed_and_required_in_qingdou_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            data = json.loads(package.read_text(encoding="utf-8"))
            data["spoken_copy_path"] = "spoken-copy.txt"
            (root / "spoken-copy.txt").write_text("先看店面布局，再看理发工位。", encoding="utf-8")
            old_hash = data["public_text_sha256"]
            package.write_text(json.dumps(data), encoding="utf-8")
            result = prepare(package, root / "with-spoken", lexicon)
            self.assertNotEqual(result["public_text_sha256"], old_hash)
            self.assertIn("spoken_copy", result["checked_fields"])
            data.update(result["package_binding"])
            package.write_text(json.dumps(data), encoding="utf-8")
            checked = validate(package, lexicon)
            self.assertIn("qingdou_must_cover_all_public_text_fields", checked["errors"])

    def test_evidence_backed_learning_is_idempotent_and_blocks_future_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            report = self.risk_report(package)
            first = record(package, report, lexicon)
            second = record(package, report, lexicon)
            self.assertEqual(first["added_terms"], 1)
            self.assertEqual(second["status"], "NO_CHANGE")
            self.assertEqual(len(load_lexicon(lexicon)["entries"][0]["observations"]), 1)
            self.assertEqual(load_lexicon(lexicon)["entries"][0]["source"], "synthetic_test_finding")
            self.assertEqual(load_lexicon(lexicon)["evidence_status"], "SYNTHETIC_TEST_ONLY")
            result = prepare(package, root / "after-learning", lexicon)
            self.assertEqual(result["status"], "BLOCKED_LOCAL_RISK_TERMS")
            self.assertIn("previous_qingdou_risk_term_reused", validate(package, lexicon)["errors"])

    def test_all_fields_including_tags_and_spoken_are_scanned(self) -> None:
        lexicon = {"entries": [{"term": "夹具风险"}]}
        for field in ("on_screen_copy", "cover_copy", "video_description", "spoken_copy", "hashtags"):
            fields = {field: ["#夹具风险"] if field == "hashtags" else "夹具风险"}
            self.assertEqual(scan(fields, lexicon)[0]["field"], field)

    def test_stale_copy_or_missing_evidence_never_writes_lexicon(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make(root)
            report = self.risk_report(package)
            original = lexicon.read_bytes()
            (root / "evidence/qingdou-result.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "evidence_empty_or_hash_mismatch"):
                record(package, report, lexicon)
            self.assertEqual(lexicon.read_bytes(), original)
            (root / "evidence/qingdou-result.png").write_bytes(b"fixture")
            (root / "public-text/cover-copy.txt").write_text("新封面", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "current_single_batch_required"):
                record(package, report, lexicon)
            self.assertEqual(lexicon.read_bytes(), original)

    def test_unknown_term_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, lexicon = self.make(Path(temp))
            report = self.risk_report(package, term="未出现在原文的合成词")
            original = lexicon.read_bytes()
            with self.assertRaisesRegex(ValueError, "finding_not_in_submitted_field"):
                record(package, report, lexicon)
            self.assertEqual(original, lexicon.read_bytes())

    def test_incomplete_platform_result_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, lexicon = self.make(Path(temp))
            report = self.risk_report(package)
            data = json.loads(report.read_text(encoding="utf-8"))
            data["checked_fields"].remove("hashtags")
            report.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete_batch_required"):
                record(package, report, lexicon)

    def test_missing_library_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, _ = self.make(Path(temp))
            with self.assertRaises(FileNotFoundError):
                prepare(package, package.parent / "failed", package.parent / "missing.json")

    def test_whitespace_fullwidth_and_invisible_variants_match(self) -> None:
        self.assertEqual(normalized("Ａ I\u200b"), "ai")
        self.assertTrue(scan({"cover_copy": "夹具 风\u200b险"}, {"entries": [{"term": "夹具风险"}]}))

    def test_previous_batch_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package, lexicon = self.make(Path(temp))
            batch = package.parent / "copy-check-v1/public-text-batch.txt"
            original = batch.read_bytes()
            with self.assertRaisesRegex(ValueError, "no_overwrite"):
                prepare(package, batch.parent, lexicon)
            self.assertEqual(original, batch.read_bytes())

    def test_existing_file_path_hash_import_remains_compatible(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts/validate_douyin_publish_package.py"
        code = ("import importlib.util; "
                f"s=importlib.util.spec_from_file_location('legacy_validator', {str(script)!r}); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "print(m.public_text_hash('a','b','c',['#x']))")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), public_hash({"on_screen_copy": "a", "cover_copy": "b",
                                                          "video_description": "c", "hashtags": ["#x"]}))


if __name__ == "__main__":
    unittest.main()
