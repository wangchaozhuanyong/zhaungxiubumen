from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_copy_guard import prepare as real_prepare, sha_bytes


def prepare(package: Path, output: Path):
    """Original scenario, explicitly isolated; never a real Qingdou result."""
    lexicon = package.parent / "fixture-risk-lexicon.json"
    lexicon.write_text(json.dumps({"source_tool": "Qingdou", "entries": []}), encoding="utf-8")
    return real_prepare(package, output, lexicon, sandbox_root=package.parent)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_douyin_publish_package.py"


def copy_hash(on_screen: str, cover: str, description: str, hashtags: list[str]) -> str:
    canonical = json.dumps(
        {
            "cover_copy": cover,
            "hashtags": hashtags,
            "on_screen_copy": on_screen,
            "video_description": description,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DouyinPublishPackageValidatorTests(unittest.TestCase):
    def make_package(self, root: Path) -> Path:
        public = root / "public-text"
        evidence = root / "evidence"
        final = root / "final"
        public.mkdir()
        evidence.mkdir()
        final.mkdir()
        on_screen = "仅设计效果图\n柜门比例先统一，再谈高级感"
        cover = "全屋柜体怎么做更整齐"
        description = "从柜门比例、收口关系和灯光层次拆解一套全屋定制方案，帮助你在量尺前先看懂设计重点。"
        hashtags = [
            "#马来西亚装修公司",
            "#马来西亚全屋定制",
            "#柜体设计",
            "#意式极简",
            "#吉隆坡装修",
        ]
        digest = copy_hash(on_screen, cover, description, hashtags)
        (public / "on-screen-copy.txt").write_text(on_screen, encoding="utf-8")
        (public / "cover-copy.txt").write_text(cover, encoding="utf-8")
        (public / "video-description.txt").write_text(description, encoding="utf-8")
        (final / "caption.txt").write_text(
            description + "\n\n" + " ".join(hashtags), encoding="utf-8"
        )
        (evidence / "qingdou-result.png").write_bytes(b"fixture")
        (root / "cover-validation.json").write_text(
            json.dumps({"status": "PASS"}), encoding="utf-8"
        )
        (root / "qingdou-report.json").write_text(
            json.dumps(
                {
                    "tool": "Qingdou",
                    "provenance": "SYNTHETIC_TEST_ONLY",
                    "status": "passed",
                    "checked_at": "2026-09-24T16:00:00Z",
                    "checked_fields": [
                        "on_screen_copy",
                        "cover_copy",
                        "video_description",
                        "hashtags",
                    ],
                    "public_text_sha256": digest,
                    "evidence_path": "evidence/qingdou-result.png",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        payload = {
            "schema_version": "1.0",
            "provenance": "SYNTHETIC_TEST_ONLY",
            "platform": "douyin",
            "production_profile": "publish",
            "task_id": "fixture-task",
            "run_id": "fixture-run",
            "on_screen_copy_path": "public-text/on-screen-copy.txt",
            "cover_copy_path": "public-text/cover-copy.txt",
            "video_description_path": "public-text/video-description.txt",
            "caption_path": "final/caption.txt",
            "hashtags": hashtags,
            "adaptive_hashtags": [
                {"tag": "#柜体设计", "axis": "content_topic", "reason": "当前讲柜体比例"},
                {"tag": "#意式极简", "axis": "space_or_style", "reason": "当前视觉风格"},
                {"tag": "#吉隆坡装修", "axis": "local_service_intent", "reason": "真实服务地区"},
            ],
            "public_text_sha256": digest,
            "cover_validation_path": "cover-validation.json",
            "qingdou_report_path": "qingdou-report.json",
        }
        path = root / "publish-package.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        prepared = prepare(path, root / "copy-check-v1")
        payload.update(prepared["package_binding"])
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        qingdou_path = root / "qingdou-report.json"
        qingdou = json.loads(qingdou_path.read_text(encoding="utf-8"))
        qingdou.update({"task_id": payload["task_id"], "run_id": payload["run_id"],
                        "submission_mode": "single_batch", "batch_sha256": prepared["batch_sha256"],
                        "evidence_sha256": sha_bytes(b"fixture"), "findings": []})
        qingdou_path.write_text(json.dumps(qingdou, ensure_ascii=False), encoding="utf-8")
        return path

    def run_validator(self, package: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(package), "--test-sandbox-root", str(package.parent)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_complete_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_validator(self.make_package(Path(temp)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "PASS_SANDBOX_ONLY")
            self.assertFalse(json.loads(result.stdout)["public_release_allowed"])

    def test_fixed_hashtag_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_package(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["hashtags"][0] = "#室内设计"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fixed_hashtags_missing", result.stdout)

    def test_copy_change_invalidates_qingdou_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.make_package(root)
            (root / "public-text" / "cover-copy.txt").write_text(
                "改过的封面标题", encoding="utf-8"
            )
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("public_text_sha256_mismatch", result.stdout)

    def test_qingdou_must_cover_all_public_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.make_package(root)
            qingdou_path = root / "qingdou-report.json"
            qingdou = json.loads(qingdou_path.read_text(encoding="utf-8"))
            qingdou["checked_fields"].remove("cover_copy")
            qingdou_path.write_text(json.dumps(qingdou, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("qingdou_must_cover_all_public_text_fields", result.stdout)

    def test_separate_checks_do_not_replace_single_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.make_package(root)
            report = root / "qingdou-report.json"
            data = json.loads(report.read_text(encoding="utf-8"))
            data["submission_mode"] = "separate_checks"
            report.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("qingdou_current_single_batch_required", result.stdout)

    def test_evidence_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.make_package(root)
            (root / "evidence/qingdou-result.png").write_bytes(b"changed")
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("qingdou_evidence_empty_or_hash_mismatch", result.stdout)

    def test_unbound_legacy_package_is_not_current_policy_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_package(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.pop("copy_policy_version")
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("current_copy_policy_version_required", result.stdout)


if __name__ == "__main__":
    unittest.main()
