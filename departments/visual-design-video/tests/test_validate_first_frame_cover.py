from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_first_frame_cover.py"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class FirstFrameCoverValidatorTests(unittest.TestCase):
    def make_fixture(self, root: Path, mismatched_cover: bool = False) -> tuple[Path, Path]:
        cover = root / "cover.png"
        other = root / "other.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=1080x1920", "-frames:v", "1", str(cover)],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=maroon:s=1080x1920", "-frames:v", "1", str(other)],
            check=True,
        )
        source = other if mismatched_cover else cover
        video = root / "fixture.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(source),
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac",
                "-shortest", str(video),
            ],
            check=True,
        )
        return video, cover

    def run_validator(self, video: Path, cover: Path) -> subprocess.CompletedProcess[str]:
        root = video.parent
        return subprocess.run(
            [
                sys.executable, str(SCRIPT), "--video", str(video), "--cover", str(cover),
                "--evidence-dir", str(root / "evidence"), "--output", str(root / "report.json"),
                "--threshold", "0.95",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_matching_first_frame_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video, cover = self.make_fixture(Path(temp))
            result = self.run_validator(video, cover)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["frames"][0]["frame_number"], 0)
            self.assertTrue(Path(report["contact_sheet"]).is_file())

    def test_mismatched_first_frame_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            video, cover = self.make_fixture(Path(temp), mismatched_cover=True)
            result = self.run_validator(video, cover)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("frame_000_ssim_below_threshold", result.stdout)


if __name__ == "__main__":
    unittest.main()
