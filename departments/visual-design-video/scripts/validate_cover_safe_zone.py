#!/usr/bin/env python3
"""Validate FLASH CAST 3:4 Douyin cover and 9:16 first-frame evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any


EXPECTED_CANVAS = (1080, 1920)
EXPECTED_PLATFORM_COVER = (1080, 1440)
MIN_RESERVED = {"top": 240, "bottom": 420, "right": 180, "left": 96}
VERTICAL_RESERVED = {"top": 420, "bottom": 600, "right": 0, "left": 0}
REQUIRED_EMBEDDED_MODE = "separate_and_in_video_first_frame"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("report root must be an object")
    return data


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def rectangle(value: Any, label: str, errors: list[str]) -> dict[str, float]:
    if not isinstance(value, dict):
        errors.append(f"{label}_missing")
        return {}
    result: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        try:
            result[key] = float(value[key])
            if not math.isfinite(result[key]) or (key in {"width", "height"} and result[key] <= 0):
                raise ValueError("nonfinite_or_nonpositive_rectangle")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label}_{key}_invalid")
    if any(f"{label}_{key}_invalid" in errors for key in ("x", "y", "width", "height")):
        return {}
    return result


def inside(inner: dict[str, float], outer: dict[str, float]) -> bool:
    return bool(inner and outer) and (
        inner["x"] >= outer["x"]
        and inner["y"] >= outer["y"]
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
    )


def resolve(report_path: Path, raw: Any) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (report_path.parent / candidate).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def validate(report_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    report = load_json(report_path)
    if str(report.get("schema_version") or "") != "2.0":
        errors.append("cover_report_schema_version_must_be_2.0")
    canvas = report.get("canvas") if isinstance(report.get("canvas"), dict) else {}
    try:
        canvas_size = (int(canvas.get("width")), int(canvas.get("height")))
    except (TypeError, ValueError):
        canvas_size = (0, 0)
    if canvas_size != EXPECTED_CANVAS:
        errors.append("canvas_must_be_1080x1920")

    policy_name = report.get("safe_zone_policy", "legacy_four_sides")
    minimum_reserved = MIN_RESERVED
    if policy_name == "vertical_priority_owner":
        minimum_reserved = VERTICAL_RESERVED
        auth = report.get("layout_authorization", {})
        if not (isinstance(auth, dict) and auth.get("explicit_user_instruction") is True
                and isinstance(report.get("task_id"), str) and report["task_id"].strip()
                and auth.get("task_id") == report["task_id"]
                and isinstance(auth.get("evidence"), str) and auth["evidence"].strip()):
            errors.append("vertical_priority_requires_bound_owner_instruction")
    elif policy_name != "legacy_four_sides":
        errors.append("unknown_safe_zone_policy")

    reserved = report.get("reserved_px") if isinstance(report.get("reserved_px"), dict) else {}
    actual_reserved = {}
    for key, minimum in minimum_reserved.items():
        try:
            actual_reserved[key] = float(reserved.get(key, -1))
            if not math.isfinite(actual_reserved[key]):
                raise ValueError("nonfinite_reserved")
            if actual_reserved[key] < minimum:
                errors.append(f"reserved_{key}_below_{minimum}px")
        except (TypeError, ValueError):
            errors.append(f"reserved_{key}_invalid")

    live = rectangle(report.get("text_live_zone"), "text_live_zone", errors)
    text = rectangle(report.get("text_bounds"), "text_bounds", errors)
    crop = rectangle(report.get("profile_crop"), "profile_crop", errors)
    if len(actual_reserved) == 4 and all(math.isfinite(v) for v in actual_reserved.values()):
        reserved_zone = {"x": actual_reserved["left"], "y": actual_reserved["top"],
                         "width": 1080 - actual_reserved["left"] - actual_reserved["right"],
                         "height": 1920 - actual_reserved["top"] - actual_reserved["bottom"]}
        if reserved_zone["width"] <= 0 or reserved_zone["height"] <= 0 or (live and not inside(live, reserved_zone)):
            errors.append("text_live_zone_outside_reserved_canvas")
    if live and text and not inside(text, live):
        errors.append("text_bounds_outside_live_zone")
    if crop and text and not inside(text, crop):
        errors.append("text_bounds_outside_profile_crop")
    if crop and (crop.get("width"), crop.get("height")) != (1080.0, 1440.0):
        errors.append("profile_crop_must_be_centered_3x4_1080x1440")
    if crop and crop.get("x") != 0.0:
        errors.append("profile_crop_x_must_be_0")
    if crop and crop.get("y") != 240.0:
        errors.append("profile_crop_y_must_be_240")

    checked_paths: dict[str, str] = {}
    for field in (
        "platform_cover_path",
        "first_frame_cover_path",
        "safe_preview_path",
        "copy_compliance_path",
    ):
        path = resolve(report_path, report.get(field))
        if path is None or not path.is_file():
            errors.append(f"{field}_missing")
            continue
        checked_paths[field] = str(path)
        if field in {"platform_cover_path", "first_frame_cover_path", "safe_preview_path"}:
            try:
                expected = (
                    EXPECTED_PLATFORM_COVER
                    if field == "platform_cover_path"
                    else EXPECTED_CANVAS
                )
                if png_size(path) != expected:
                    dimensions = "1080x1440" if expected == EXPECTED_PLATFORM_COVER else "1080x1920"
                    errors.append(f"{field}_must_be_{dimensions}_png")
            except (OSError, ValueError) as exc:
                errors.append(f"{field}_invalid:{exc}")

    compliance_path = resolve(report_path, report.get("copy_compliance_path"))
    if compliance_path and compliance_path.is_file():
        try:
            if str(load_json(compliance_path).get("status", "")).lower() != "passed":
                errors.append("cover_copy_local_check_not_passed")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"cover_copy_compliance_invalid:{exc}")

    platform_cover_path = resolve(report_path, report.get("platform_cover_path"))
    first_frame_cover_path = resolve(report_path, report.get("first_frame_cover_path"))
    safe_preview_path = resolve(report_path, report.get("safe_preview_path"))
    if first_frame_cover_path and safe_preview_path and first_frame_cover_path == safe_preview_path:
        errors.append("safe_preview_cannot_be_formal_cover")

    crop_match_path = resolve(report_path, report.get("platform_crop_match_report_path"))
    if crop_match_path is None or not crop_match_path.is_file():
        errors.append("platform_crop_match_report_missing")
    else:
        checked_paths["platform_crop_match_report_path"] = str(crop_match_path)
        try:
            crop_match = load_json(crop_match_path)
            score = float(crop_match.get("ssim", {}).get("all"))
            threshold = float(crop_match.get("threshold"))
            if str(crop_match.get("status", "")).upper() != "PASS" or score < threshold:
                errors.append("platform_cover_crop_match_not_passed")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"platform_crop_match_report_invalid:{exc}")

    opt_out = report.get("in_video_cover_opt_out")
    opted_out = isinstance(opt_out, dict) and opt_out.get("explicit_user_authorization") is True
    if opted_out:
        if not isinstance(opt_out.get("reason"), str) or not opt_out["reason"].strip():
            errors.append("in_video_cover_opt_out_reason_missing")
        if not isinstance(opt_out.get("evidence"), str) or not opt_out["evidence"].strip():
            errors.append("in_video_cover_opt_out_evidence_missing")
    else:
        if report.get("cover_mode") != REQUIRED_EMBEDDED_MODE:
            errors.append(f"cover_mode_must_be_{REQUIRED_EMBEDDED_MODE}")
        if report.get("in_video_cover") is not True:
            errors.append("formal_cover_must_be_in_video_first_frame")
        first_frame = report.get("in_video_first_frame")
        if not isinstance(first_frame, dict):
            errors.append("in_video_first_frame_missing")
        else:
            source_path = resolve(report_path, first_frame.get("source_path"))
            if source_path is None or not source_path.is_file():
                errors.append("in_video_first_frame_source_missing")
            elif (
                first_frame_cover_path
                and source_path != first_frame_cover_path
                and sha256(source_path) != sha256(first_frame_cover_path)
            ):
                errors.append("in_video_first_frame_source_not_formal_cover")
            if safe_preview_path and source_path == safe_preview_path:
                errors.append("safe_preview_cannot_be_video_first_frame_source")

            frame_zero = resolve(report_path, first_frame.get("frame_0_path"))
            if frame_zero is None or not frame_zero.is_file():
                errors.append("actual_video_frame_0_missing")
            else:
                checked_paths["frame_0_path"] = str(frame_zero)
                try:
                    if png_size(frame_zero) != EXPECTED_CANVAS:
                        errors.append("frame_0_path_must_be_1080x1920_png")
                except (OSError, ValueError) as exc:
                    errors.append(f"frame_0_path_invalid:{exc}")

            if positive_number(first_frame.get("hold_seconds")) is None:
                errors.append("in_video_cover_hold_seconds_invalid")
            transition = first_frame.get("transition")
            if not isinstance(transition, dict):
                errors.append("in_video_cover_transition_missing")
            else:
                try:
                    start = float(transition.get("start_seconds"))
                    end = float(transition.get("end_seconds"))
                    if start < 0 or end <= start:
                        errors.append("in_video_cover_transition_interval_invalid")
                except (TypeError, ValueError):
                    errors.append("in_video_cover_transition_interval_invalid")

            similarity_path = resolve(report_path, first_frame.get("similarity_report_path"))
            if similarity_path is None or not similarity_path.is_file():
                errors.append("first_frame_similarity_report_missing")
            else:
                checked_paths["similarity_report_path"] = str(similarity_path)
                try:
                    similarity = load_json(similarity_path)
                    score = float(similarity.get("ssim", {}).get("all"))
                    threshold = float(similarity.get("threshold"))
                    if str(similarity.get("status", "")).upper() != "PASS" or score < threshold:
                        errors.append("first_frame_similarity_not_passed")
                except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    errors.append(f"first_frame_similarity_report_invalid:{exc}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "report": str(report_path),
        "policy": {
            "platform_cover": "1080x1440 (3:4)",
            "first_frame_canvas": "1080x1920 (9:16)",
            "safe_zone_policy": policy_name,
            "minimum_reserved_px": minimum_reserved,
            "scope": "project authoring baseline; not proof of official platform UI or publishing permission",
            "profile_crop": "3:4 cover maps to centered x=0 y=240 width=1080 height=1440 in first frame",
            "formal_cover": "use a 3:4 platform cover plus a matched 9:16 frame-0 adaptation unless explicit per-task user opt-out",
            "safe_preview": "QA evidence only; never a formal-cover or video-first-frame source",
        },
        "checked_paths": checked_paths,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report_path = args.report.expanduser().resolve()
    try:
        result = validate(report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"status": "FAIL", "report": str(report_path), "errors": [str(exc)]}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
