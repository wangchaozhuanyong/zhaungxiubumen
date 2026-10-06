from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_renovation_workflow.py"


class RenovationWorkflowValidatorTests(unittest.TestCase):
    def make_project(self, root: Path) -> None:
        (root / "asset.jpg").write_bytes(b"fixture")
        source = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "request_type": "new_video",
            "input_mode": "autonomous_direct",
            "video_need": "space_showcase",
            "presentation_mode": "visual_music",
            "copy_mode": "none",
            "production_profile": "candidate",
            "source_tier": "ai_concept",
            "target_channel": "douyin",
            "aspect_ratio": "9:16",
            "duration_seconds": 10,
            "authenticity_label": "L1 AI 原创概念效果图视频",
            "compliance_overlays": [
                {
                    "text": "仅设计效果图",
                    "role": "truthfulness_disclosure",
                    "placement": "bottom_left_safe_zone",
                    "persistent": True,
                }
            ],
            "constraints": {
                "video_copy": False,
                "english": False,
                "voiceover": False,
                "cta": "none",
            },
        }
        content = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "candidate_directions": [
                {"id": "neutral-daylight", "difference": "日光中性、慢节奏"},
                {"id": "warm-walnut", "difference": "胡桃木暖灰、材质切换"},
            ],
            "selected_direction_id": "neutral-daylight",
            "visual_thesis": "用干净日光和材质层次让空间自己说话",
            "selection_reason": "符合无文案空间展示需求",
            "style_profile": {"family": "daylight_neutral"},
            "grade_profile": {
                "max_adjacent_yavg_delta": 30,
                "max_scene_yavg_range": 45,
                "max_highlight_ymax": 242,
            },
            "music": {
                "required": True,
                "selection_path": "runtime/music-selection.json",
                "map_path": "runtime/music-map.json",
            },
            "copy": {"mode": "none"},
        }
        storyboard = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "creative_direction": {"visual_thesis": content["visual_thesis"]},
            "scenes": [
                {
                    "id": "scene-01",
                    "start": 0,
                    "end": 5,
                    "spatial_value": "入口与客餐厅关系",
                    "source_asset_ids": ["asset-01"],
                    "composition": "纵深大景",
                    "camera_or_motion": "稳定前景揭示",
                    "change_reason": "建立空间",
                    "transition_out": "按乐句硬切",
                    "grade_target": {"yavg_min": 90, "yavg_max": 125},
                    "on_screen_text": [],
                },
                {
                    "id": "scene-02",
                    "start": 5,
                    "end": 10,
                    "spatial_value": "木饰面与五金细节",
                    "source_asset_ids": ["asset-01"],
                    "composition": "材质近景",
                    "camera_or_motion": "局部扫光",
                    "change_reason": "从尺度进入触感",
                    "transition_out": "音乐尾音收束",
                    "grade_target": {"yavg_min": 78, "yavg_max": 115},
                    "on_screen_text": [],
                },
            ],
        }
        assets = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "assets": [
                {
                    "id": "asset-01",
                    "path": "asset.jpg",
                    "source_kind": "generated_support",
                    "rights_status": "owner_project_use",
                    "authenticity_role": "ai_concept",
                }
            ],
        }
        qa = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "status": "not_run",
        }
        handoff = {
            "schema_version": "1.0",
            "task_id": "fixture-task",
            "run_id": "fixture-run-1",
            "gate": {"status": "not_ready"},
        }
        files = {
            "source-brief.json": source,
            "content-plan.json": content,
            "storyboard.json": storyboard,
            "asset-manifest.json": assets,
            "qa-report.json": qa,
            "handoff-package.json": handoff,
        }
        for name, payload in files.items():
            (root / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root), "--phase", "plan"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_visual_music_plan_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "PASS")

    def test_visual_music_rejects_visible_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "storyboard.json"
            storyboard = json.loads(path.read_text(encoding="utf-8"))
            storyboard["scenes"][0]["on_screen_text"] = ["AI 帮你设计新家"]
            path.write_text(json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("visual_music_scene_contains_text:scene-01", result.stdout)

    def test_visual_music_allows_declared_compliance_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "storyboard.json"
            storyboard = json.loads(path.read_text(encoding="utf-8"))
            storyboard["scenes"][0]["on_screen_text"] = ["仅设计效果图"]
            path.write_text(json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ai_concept_requires_exact_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"][0]["text"] = "AI设计"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ai_concept_requires_exact_design_effect_disclosure", result.stdout)

    def test_ai_concept_disclosure_requires_persistent_bottom_left(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"][0]["persistent"] = False
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "ai_concept_disclosure_requires_persistent_bottom_left_safe_zone",
                result.stdout,
            )

    def test_ai_concept_allows_no_visible_disclosure_with_origin_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"] = []
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ai_concept_no_overlay_still_requires_origin_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"] = []
            source["authenticity_label"] = ""
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source_brief_missing_authenticity_label", result.stdout)

    def test_ai_concept_rejects_enabled_right_corner_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"][0]["placement"] = "bottom_right_safe_zone"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ai_concept_disclosure_requires_persistent_bottom_left_safe_zone", result.stdout)

    def test_ai_concept_rejects_malformed_overlay_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"] = "disabled"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ai_concept_compliance_overlays_requires_explicit_list", result.stdout)

    def test_ai_concept_rejects_unclassified_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["compliance_overlays"][0]["role"] = "decoration"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ai_concept_disclosure_role_invalid", result.stdout)

    def test_rejects_unknown_production_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["production_profile"] = "everything"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("production_profile_invalid", result.stdout)

    def test_preview_profile_does_not_require_qa_or_handoff_at_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            source_path = root / "source-brief.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["production_profile"] = "preview"
            source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            (root / "qa-report.json").unlink()
            (root / "handoff-package.json").unlink()
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["production_profile"], "preview")

    def test_run_id_mismatch_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "qa-report.json"
            qa = json.loads(path.read_text(encoding="utf-8"))
            qa["run_id"] = "old-run"
            path.write_text(json.dumps(qa, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("run_id_mismatch:qa-report.json", result.stdout)

    def test_formal_cover_requires_video_first_frame_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            path = root / "source-brief.json"
            source = json.loads(path.read_text(encoding="utf-8"))
            source["formal_cover"] = {
                "path": "cover.png",
                "in_video_first_frame": False,
            }
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_validator(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("formal_cover_requires_in_video_first_frame", result.stdout)


if __name__ == "__main__":
    unittest.main()
