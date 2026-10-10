from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_copy_guard import (HASHTAG_POLICY_VERSION, batch_text, check, hashtag_fields,
                               prepare, public_hash, read_fields, sha_bytes)
from validate_douyin_publish_package import public_text_hash, validate
import test_validate_douyin_publish_package as legacy


class DualLanguageHashtagTests(unittest.TestCase):
    def make_dual(self, root: Path) -> tuple[Path, Path]:
        package = legacy.DouyinPublishPackageValidatorTests().make_package(root)
        data = json.loads(package.read_text(encoding="utf-8"))
        data.update(hashtag_policy_version=HASHTAG_POLICY_VERSION,
                    hashtags=["#马来西亚装修公司", "#客厅收纳", "#客厅设计", "#东方木石", "#吉隆坡装修"],
                    hashtags_en=["#RenovationCompanyMalaysia", "#LivingRoomStorage", "#LivingRoomDesign",
                                 "#ModernOrientalInterior", "#KLRenovation"],
                    caption_en_hashtags_path="final/caption-en-tags.txt",
                    adaptive_hashtags=[
                        {"tag": "#客厅收纳", "axis": "content_topic", "reason": "本条收纳需求"},
                        {"tag": "#客厅设计", "axis": "content_topic", "reason": "本条空间品类"},
                        {"tag": "#东方木石", "axis": "space_or_style", "reason": "本条材质风格"},
                        {"tag": "#吉隆坡装修", "axis": "local_service_intent", "reason": "已确认服务地区"}])
        description = (root / data["video_description_path"]).read_text(encoding="utf-8").strip()
        for tags, field in ((data["hashtags"], "caption_path"),
                            (data["hashtags_en"], "caption_en_hashtags_path")):
            (root / data[field]).write_text(description + "\n\n" + " ".join(tags), encoding="utf-8")
        package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        lexicon = root / "fixture-risk-lexicon.json"
        prepared = prepare(package, root / "copy-check-dual", lexicon, sandbox_root=root)
        data.update(prepared["package_binding"])
        package.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        report = json.loads((root / "qingdou-report.json").read_text(encoding="utf-8"))
        report.update(public_text_sha256=prepared["public_text_sha256"],
                      batch_sha256=prepared["batch_sha256"], checked_fields=prepared["checked_fields"])
        (root / "qingdou-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return package, lexicon

    def test_one_fixed_plus_four_adaptive_and_both_captions_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make_dual(root)
            result = validate(package, lexicon, sandbox_root=root)
            self.assertEqual(result["status"], "PASS_SANDBOX_ONLY", result)
            self.assertEqual(result["fixed_hashtags"], ["#马来西亚装修公司"])
            self.assertEqual(len(result["adaptive_hashtags"]), 4)
            _, fields = read_fields(package, sandbox_root=root)
            self.assertEqual(len(fields["hashtags"]), 5)
            self.assertEqual(len(fields["hashtags_en"]), 5)
            self.assertEqual(public_hash(fields), public_text_hash(
                fields["on_screen_copy"], fields["cover_copy"], fields["video_description"],
                fields["hashtags"], hashtags_en=fields["hashtags_en"]))
            batch = batch_text(fields)
            for tag in fields["hashtags"] + fields["hashtags_en"]:
                self.assertIn(tag, batch)
            self.assertEqual(batch.count("【描述】"), 1)

    def test_english_changes_invalidate_old_real_result_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make_dual(root)
            data = json.loads(package.read_text())
            old_hash = data["public_text_sha256"]
            data["hashtags_en"][1] = "#StorageDesignMalaysia"
            package.write_text(json.dumps(data))
            _, fields = read_fields(package, sandbox_root=root)
            self.assertNotEqual(public_hash(fields), old_hash)
            self.assertEqual(check(package, lexicon, sandbox_root=root)["status"], "HOLD_COPY_GATE")
            self.assertNotEqual(validate(package, lexicon, sandbox_root=root)["status"], "PASS_SANDBOX_ONLY")

    def test_capture_must_cover_english_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make_dual(root)
            report_path = root / "qingdou-report.json"
            report = json.loads(report_path.read_text())
            report["checked_fields"].remove("hashtags_en")
            report_path.write_text(json.dumps(report))
            self.assertIn("qingdou_must_cover_all_public_text_fields",
                          validate(package, lexicon, sandbox_root=root)["errors"])
            self.assertEqual(check(package, lexicon, sandbox_root=root)["status"], "HOLD_COPY_GATE")

    def test_exact_five_unique_english_and_required_pair(self):
        good = {"hashtag_policy_version": HASHTAG_POLICY_VERSION,
                "hashtags": ["#马来西亚装修公司", "#客厅收纳", "#客厅设计", "#东方木石", "#吉隆坡装修"],
                "hashtags_en": ["#RenovationCompanyMalaysia", "#LivingRoomStorage", "#LivingRoomDesign",
                                "#ModernOrientalInterior", "#KLRenovation"],
                "caption_en_hashtags_path": "caption-en-tags.txt"}
        mutations = [
            ("hashtags_en", good["hashtags_en"][:4]),
            ("hashtags_en", good["hashtags_en"][:4] + ["#LivingRoomStorage"]),
            ("hashtags_en", ["#WrongCompany"] + good["hashtags_en"][1:]),
            ("hashtags_en", good["hashtags_en"][:4] + ["#KL Renovation"]),
            ("hashtags_en", good["hashtags_en"][:4] + ["#吉隆坡装修"]),
            ("hashtags", ["#室内设计"] + good["hashtags"][1:]),
            ("caption_en_hashtags_path", ""),
            ("hashtag_policy_version", "unknown")]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    hashtag_fields({**good, key: value})

    def test_english_caption_must_keep_identical_description(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, lexicon = self.make_dual(root)
            caption = root / "final/caption-en-tags.txt"
            caption.write_text("不同的描述\n\n" + " ".join(json.loads(package.read_text())["hashtags_en"]))
            self.assertIn("english_caption_must_equal_same_description_plus_five_english_hashtags",
                          validate(package, lexicon, sandbox_root=root)["errors"])

    def test_english_caption_path_cannot_escape_project_sandbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, _ = self.make_dual(root)
            data = json.loads(package.read_text())
            data["caption_en_hashtags_path"] = "/tmp/outside-caption.txt"
            package.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                read_fields(package, sandbox_root=root)

    def test_legacy_hash_and_five_chinese_tags_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = legacy.DouyinPublishPackageValidatorTests().make_package(root)
            _, fields = read_fields(package, sandbox_root=root)
            self.assertNotIn("hashtags_en", fields)
            self.assertEqual(public_hash(fields), legacy.copy_hash(
                fields["on_screen_copy"], fields["cover_copy"], fields["video_description"], fields["hashtags"]))


if __name__ == "__main__":
    unittest.main()
