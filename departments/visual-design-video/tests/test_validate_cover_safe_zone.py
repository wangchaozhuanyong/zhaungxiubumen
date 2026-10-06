from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_cover_safe_zone.py"


def write_png(path: Path, width: int = 1080, height: int = 1920) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    row = b"\x00" + b"\x00\x00\x00" * width
    payload = zlib.compress(row * height, level=1)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", payload)
        + chunk(b"IEND", b"")
    )


class CoverSafeZoneValidatorTests(unittest.TestCase):
    def make_report(self, root: Path) -> Path:
        write_png(root / "cover-3x4.png", width=1080, height=1440)
        write_png(root / "first-frame-cover-9x16.png")
        write_png(root / "safe.png")
        write_png(root / "frame-0.png")
        (root / "copy.json").write_text('{"status":"passed"}', encoding="utf-8")
        (root / "crop-match.json").write_text(
            '{"status":"PASS","threshold":0.95,"ssim":{"all":0.99}}',
            encoding="utf-8",
        )
        (root / "similarity.json").write_text(
            '{"status":"PASS","threshold":0.95,"ssim":{"all":0.99}}',
            encoding="utf-8",
        )
        report = {
            "schema_version": "2.0",
            "cover_mode": "separate_and_in_video_first_frame",
            "in_video_cover": True,
            "platform_cover_path": "cover-3x4.png",
            "first_frame_cover_path": "first-frame-cover-9x16.png",
            "safe_preview_path": "safe.png",
            "copy_compliance_path": "copy.json",
            "platform_crop_match_report_path": "crop-match.json",
            "in_video_first_frame": {
                "source_path": "first-frame-cover-9x16.png",
                "frame_0_path": "frame-0.png",
                "hold_seconds": 0.7,
                "transition": {"start_seconds": 0.55, "end_seconds": 0.85},
                "similarity_report_path": "similarity.json",
            },
            "canvas": {"width": 1080, "height": 1920},
            "reserved_px": {"top": 240, "bottom": 420, "right": 180, "left": 96},
            "profile_crop": {"x": 0, "y": 240, "width": 1080, "height": 1440},
            "text_live_zone": {"x": 96, "y": 320, "width": 804, "height": 1060},
            "text_bounds": {"x": 118, "y": 382, "width": 702, "height": 548},
        }
        path = root / "publish-cover-report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def run_validator(self, report: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), str(report)], capture_output=True, text=True, check=False)

    def test_safe_cover_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_validator(self.make_report(Path(temp)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "PASS")

    def vertical_report(self, root: Path) -> Path:
        report = self.make_report(root)
        payload = json.loads(report.read_text())
        payload.update({"task_id": "cover-vertical-owner-test", "safe_zone_policy": "vertical_priority_owner",
                        "layout_authorization": {"task_id": "cover-vertical-owner-test", "explicit_user_instruction": True,
                                                 "evidence": "SYNTHETIC_TEST_ONLY owner instruction for test layout"},
                        "reserved_px": {"top": 420, "bottom": 600, "left": 0, "right": 0},
                        "text_live_zone": {"x": 0, "y": 420, "width": 1080, "height": 900},
                        "text_bounds": {"x": 50, "y": 600, "width": 960, "height": 240}})
        report.write_text(json.dumps(payload))
        return report

    def test_owner_vertical_policy_does_not_require_side_ui_reserves(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_validator(self.vertical_report(Path(temp)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["policy"]["minimum_reserved_px"]["right"], 0)

    def test_vertical_override_requires_exact_task_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.vertical_report(Path(temp))
            payload = json.loads(report.read_text())
            payload["layout_authorization"]["task_id"] = "another-task"
            report.write_text(json.dumps(payload))
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("vertical_priority_requires_bound_owner_instruction", result.stdout)

    def test_claimed_live_zone_cannot_bypass_top_bottom(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.vertical_report(Path(temp))
            payload = json.loads(report.read_text())
            payload["text_live_zone"] = {"x": 0, "y": 0, "width": 1080, "height": 1920}
            report.write_text(json.dumps(payload))
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("text_live_zone_outside_reserved_canvas", result.stdout)

    def test_nonfinite_rectangle_is_rejected_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp))
            payload = json.loads(report.read_text())
            payload["text_bounds"]["width"] = float("nan")
            report.write_text(json.dumps(payload))
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("text_bounds_width_invalid", result.stdout)

    def test_title_in_bottom_overlay_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["text_bounds"] = {"x": 118, "y": 1320, "width": 702, "height": 300}
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("text_bounds_outside_live_zone", result.stdout)

    def test_small_bottom_reserve_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["reserved_px"]["bottom"] = 320
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reserved_bottom_below_420px", result.stdout)

    def test_platform_cover_must_be_three_by_four(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = self.make_report(root)
            write_png(root / "cover-3x4.png", width=1080, height=1920)
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("platform_cover_path_must_be_1080x1440_png", result.stdout)

    def test_separate_cover_without_video_first_frame_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["cover_mode"] = "separate_publish_cover"
            payload["in_video_cover"] = False
            payload.pop("in_video_first_frame")
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(report)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("formal_cover_must_be_in_video_first_frame", result.stdout)

    def test_explicit_user_opt_out_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.make_report(Path(temp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["cover_mode"] = "separate_publish_cover"
            payload["in_video_cover"] = False
            payload.pop("in_video_first_frame")
            payload["in_video_cover_opt_out"] = {
                "explicit_user_authorization": True,
                "reason": "User requested a clean visual-music first frame.",
                "evidence": "source-thread-message-42",
            }
            report.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_validator(report)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
