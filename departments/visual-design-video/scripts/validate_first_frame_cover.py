#!/usr/bin/env python3
"""Extract and validate a formal Douyin cover embedded at video frame zero."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


FRAME_SPECS = (
    ("frame_000", 0.0, 0),
    ("frame_001", 1 / 30, 1),
    ("frame_0500ms", 0.50, None),
    ("frame_0700ms", 0.70, None),
    ("frame_0900ms", 0.90, None),
)
EXPECTED_SIZE = (1080, 1920)


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} is required")
    return path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, Any]:
    result = run(
        [
            require_binary("ffprobe"),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def video_summary(payload: dict[str, Any]) -> dict[str, Any]:
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("avg_frame_rate"),
        "video_duration_seconds": float(video.get("duration") or 0),
        "audio_duration_seconds": float(audio.get("duration") or 0),
        "format_duration_seconds": float(payload.get("format", {}).get("duration") or 0),
        "video_streams": sum(item.get("codec_type") == "video" for item in streams),
        "audio_streams": sum(item.get("codec_type") == "audio" for item in streams),
    }


def extract_frame(video: Path, output: Path, time_seconds: float, frame_number: int | None) -> None:
    ffmpeg = require_binary("ffmpeg")
    if frame_number is not None:
        command = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"select=eq(n\\,{frame_number})",
            "-vsync",
            "0",
            "-frames:v",
            "1",
            str(output),
        ]
    else:
        command = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{time_seconds:.6f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(output),
        ]
    run(command)
    if not output.is_file():
        raise RuntimeError(f"frame extraction did not create {output}")


def measure_ssim(reference: Path, actual: Path, stats_path: Path) -> float:
    result = subprocess.run(
        [
            require_binary("ffmpeg"),
            "-y",
            "-i",
            str(reference),
            "-i",
            str(actual),
            "-lavfi",
            f"[0:v][1:v]ssim=stats_file={stats_path}",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(r"All:([0-9.]+)", result.stderr)
    if result.returncode != 0 or not match:
        raise RuntimeError(f"ffmpeg SSIM failed: {result.stderr[-1200:]}")
    return float(match.group(1))


def make_contact_sheet(frames: list[Path], output: Path) -> None:
    command = [require_binary("ffmpeg"), "-y", "-v", "error"]
    for frame in frames:
        command.extend(["-i", str(frame)])
    command.extend(
        [
            "-filter_complex",
            "[0:v]scale=360:640[a0];[1:v]scale=360:640[a1];"
            "[2:v]scale=360:640[a2];[3:v]scale=360:640[a3];"
            "[4:v]scale=360:640[a4];"
            "[a0][a1][a2][a3][a4]xstack=inputs=5:"
            "layout=0_0|360_0|720_0|0_640|360_640:fill=black[out]",
            "-map",
            "[out]",
            "-frames:v",
            "1",
            str(output),
        ]
    )
    run(command)


def validate(video: Path, cover: Path, evidence_dir: Path, threshold: float) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    summary = video_summary(probe(video))
    if (summary["width"], summary["height"]) != EXPECTED_SIZE:
        errors.append("video_must_be_1080x1920")
    if summary["video_streams"] != 1:
        errors.append("video_stream_count_must_be_1")
    if summary["audio_streams"] < 1:
        errors.append("audio_stream_missing")

    cover_probe = probe(cover)
    cover_video = next(
        (item for item in cover_probe.get("streams", []) if item.get("codec_type") == "video"),
        {},
    )
    if (cover_video.get("width"), cover_video.get("height")) != EXPECTED_SIZE:
        errors.append("cover_must_be_1080x1920")

    extracted: list[dict[str, Any]] = []
    frame_paths: list[Path] = []
    for label, time_seconds, frame_number in FRAME_SPECS:
        path = evidence_dir / f"actual-{label}.png"
        extract_frame(video, path, time_seconds, frame_number)
        frame_paths.append(path)
        extracted.append(
            {
                "label": label,
                "time_seconds": round(time_seconds, 6),
                "frame_number": frame_number,
                "path": str(path),
                "sha256": sha256(path),
            }
        )

    stats_path = evidence_dir / "frame-000-ssim.log"
    score = measure_ssim(cover, frame_paths[0], stats_path)
    if score < threshold:
        errors.append("frame_000_ssim_below_threshold")

    contact_sheet = evidence_dir / "first-frame-contact-sheet.jpg"
    make_contact_sheet(frame_paths, contact_sheet)
    report = {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "policy": "formal Douyin cover must be video frame 0; safe-zone previews are not accepted",
        "video": str(video),
        "cover": str(cover),
        "video_sha256": sha256(video),
        "cover_sha256": sha256(cover),
        "threshold": threshold,
        "ssim": {"all": score, "stats_path": str(stats_path)},
        "probe": summary,
        "frames": extracted,
        "contact_sheet": str(contact_sheet),
        "contact_sheet_sha256": sha256(contact_sheet),
        "errors": errors,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--cover", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.95)
    args = parser.parse_args()

    try:
        report = validate(
            args.video.expanduser().resolve(),
            args.cover.expanduser().resolve(),
            args.evidence_dir.expanduser().resolve(),
            args.threshold,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        report = {"schema_version": "1.0", "status": "FAIL", "errors": [str(exc)]}
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
