#!/usr/bin/env python3
"""Measure every storyboard scene instead of sampling only a few fixed timestamps."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


SIGNAL_RE = re.compile(r"lavfi\.signalstats\.([A-Z0-9]+)=(-?[0-9]+(?:\.[0-9]+)?)")
REQUIRED_SIGNALS = ("YAVG", "YMIN", "YMAX", "UAVG", "VAVG", "SATAVG")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("ffmpeg is required")
    return binary


def number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def scene_sample_time(scene: dict[str, Any]) -> float:
    if scene.get("quality_sample_time") is not None:
        return number(scene["quality_sample_time"], "quality_sample_time")
    start = number(scene.get("start"), "scene.start")
    end = number(scene.get("end"), "scene.end")
    if end <= start:
        raise ValueError(f"scene end must be greater than start: {scene.get('id')}")
    return start + (end - start) / 2.0


def measure_frame(ffmpeg: str, video: Path, timestamp: float) -> dict[str, float]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-ss",
        f"{timestamp:.6f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "signalstats,metadata=print",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    values = {key: float(raw) for key, raw in SIGNAL_RE.findall(result.stdout + result.stderr)}
    missing = [key for key in REQUIRED_SIGNALS if key not in values]
    if missing:
        raise RuntimeError(f"signalstats missing {missing} at {timestamp:.3f}s")
    return {key: values[key] for key in REQUIRED_SIGNALS}


def evaluate(
    video: Path,
    storyboard_path: Path,
    content_plan_path: Path,
) -> dict[str, Any]:
    storyboard = load_json(storyboard_path)
    content_plan = load_json(content_plan_path)
    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("storyboard.scenes must be a non-empty array")

    grade_profile = content_plan.get("grade_profile")
    if not isinstance(grade_profile, dict):
        raise ValueError("content-plan.grade_profile must be an object")
    max_adjacent_delta = number(
        grade_profile.get("max_adjacent_yavg_delta"),
        "grade_profile.max_adjacent_yavg_delta",
    )
    max_scene_range = number(
        grade_profile.get("max_scene_yavg_range"),
        "grade_profile.max_scene_yavg_range",
    )
    max_highlight = number(
        grade_profile.get("max_highlight_ymax"),
        "grade_profile.max_highlight_ymax",
    )

    ffmpeg = require_ffmpeg()
    errors: list[str] = []
    warnings: list[str] = []
    samples: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    for index, raw_scene in enumerate(scenes):
        if not isinstance(raw_scene, dict):
            errors.append(f"scene_{index + 1}_must_be_object")
            continue
        scene_id = str(raw_scene.get("id") or "").strip()
        if not scene_id:
            errors.append(f"scene_{index + 1}_missing_id")
            continue
        if scene_id in seen_ids:
            errors.append(f"duplicate_scene_id:{scene_id}")
            continue
        seen_ids.add(scene_id)

        target = raw_scene.get("grade_target")
        if not isinstance(target, dict):
            errors.append(f"scene_missing_grade_target:{scene_id}")
            continue
        try:
            yavg_min = number(target.get("yavg_min"), f"{scene_id}.grade_target.yavg_min")
            yavg_max = number(target.get("yavg_max"), f"{scene_id}.grade_target.yavg_max")
            if yavg_max <= yavg_min:
                raise ValueError("yavg_max must be greater than yavg_min")
            timestamp = scene_sample_time(raw_scene)
            signals = measure_frame(ffmpeg, video, timestamp)
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            errors.append(f"scene_measure_failed:{scene_id}:{exc}")
            continue

        scene_errors: list[str] = []
        if not yavg_min <= signals["YAVG"] <= yavg_max:
            scene_errors.append(
                f"yavg_out_of_target:{signals['YAVG']:.3f}:expected_{yavg_min:.3f}_{yavg_max:.3f}"
            )
        if signals["YMAX"] > max_highlight:
            scene_errors.append(
                f"highlight_over_limit:{signals['YMAX']:.3f}:max_{max_highlight:.3f}"
            )
        warmth_index = signals["VAVG"] - signals["UAVG"]
        warmth_min = target.get("warmth_index_min")
        warmth_max = target.get("warmth_index_max")
        if warmth_min is not None and warmth_index < number(warmth_min, "warmth_index_min"):
            scene_errors.append(f"warmth_below_target:{warmth_index:.3f}")
        if warmth_max is not None and warmth_index > number(warmth_max, "warmth_index_max"):
            scene_errors.append(f"warmth_above_target:{warmth_index:.3f}")

        if scene_errors:
            errors.extend(f"{scene_id}:{item}" for item in scene_errors)
        samples.append(
            {
                "scene_id": scene_id,
                "sample_time_seconds": round(timestamp, 6),
                "target": target,
                "signals": {key: round(value, 4) for key, value in signals.items()},
                "warmth_index": round(warmth_index, 4),
                "status": "FAIL" if scene_errors else "PASS",
                "errors": scene_errors,
                "allow_luma_jump": bool(raw_scene.get("allow_luma_jump")),
                "luma_jump_reason": raw_scene.get("luma_jump_reason", ""),
            }
        )

    yavg_values = [item["signals"]["YAVG"] for item in samples]
    measured_range = max(yavg_values) - min(yavg_values) if yavg_values else None
    if measured_range is not None and measured_range > max_scene_range:
        errors.append(
            f"scene_yavg_range_exceeded:{measured_range:.3f}:max_{max_scene_range:.3f}"
        )

    adjacent: list[dict[str, Any]] = []
    for previous, current in zip(samples, samples[1:]):
        delta = abs(current["signals"]["YAVG"] - previous["signals"]["YAVG"])
        allowed = bool(previous["allow_luma_jump"] or current["allow_luma_jump"])
        item = {
            "from": previous["scene_id"],
            "to": current["scene_id"],
            "absolute_yavg_delta": round(delta, 4),
            "limit": max_adjacent_delta,
            "allowed_exception": allowed,
        }
        if delta > max_adjacent_delta:
            if allowed:
                reason = current["luma_jump_reason"] or previous["luma_jump_reason"]
                if not str(reason).strip():
                    errors.append(
                        f"luma_jump_exception_missing_reason:{previous['scene_id']}->{current['scene_id']}"
                    )
                else:
                    warnings.append(
                        f"intentional_luma_jump:{previous['scene_id']}->{current['scene_id']}:{delta:.3f}"
                    )
            else:
                errors.append(
                    f"adjacent_yavg_delta_exceeded:{previous['scene_id']}->{current['scene_id']}:{delta:.3f}"
                )
        adjacent.append(item)

    return {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "task_id": storyboard.get("task_id"),
        "run_id": storyboard.get("run_id"),
        "video": str(video),
        "input_fingerprints": {
            "video_sha256": sha256(video),
            "storyboard_sha256": sha256(storyboard_path),
            "content_plan_sha256": sha256(content_plan_path),
        },
        "grade_profile": grade_profile,
        "scene_count_expected": len(scenes),
        "scene_count_measured": len(samples),
        "scene_yavg_range": round(measured_range, 4) if measured_range is not None else None,
        "samples": samples,
        "adjacent_scene_deltas": adjacent,
        "errors": errors,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--storyboard", required=True, type=Path)
    parser.add_argument("--content-plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    video = args.video.expanduser().resolve()
    storyboard = args.storyboard.expanduser().resolve()
    content_plan = args.content_plan.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (video, storyboard, content_plan):
        if not path.is_file():
            raise FileNotFoundError(path)
    report = evaluate(video, storyboard, content_plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
