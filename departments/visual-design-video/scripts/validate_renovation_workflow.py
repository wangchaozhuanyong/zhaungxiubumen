#!/usr/bin/env python3
"""Validate the six-artifact, demand-adaptive renovation video workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from validate_douyin_publish_package import validate as validate_douyin_publish_package


CORE_FILES = {
    "source": "source-brief.json",
    "content": "content-plan.json",
    "storyboard": "storyboard.json",
    "assets": "asset-manifest.json",
    "qa": "qa-report.json",
    "handoff": "handoff-package.json",
}
INPUT_MODES = {
    "autonomous_direct",
    "reference_driven",
    "asset_driven",
    "coordinated_campaign",
}
VIDEO_NEEDS = {
    "space_showcase",
    "material_craft",
    "walkthrough",
    "before_after",
    "design_explainer",
    "renovation_guide",
    "brand_process",
    "lead_ad",
    "commercial_showcase",
}
PRESENTATION_MODES = {"visual_music", "minimal_brand", "copy_led"}
COPY_MODES = {"none", "minimal", "narrative"}
PRODUCTION_PROFILES = {"preview", "candidate", "publish", "l4"}
SOURCE_TIERS = {
    "real_authorized",
    "ai_concept",
    "mixed",
    "segmented_ai_video",
    "continuous_real_or_3d",
    "continuous_ai_video",
}
FINAL_MANUAL_CHECKS = {
    "first_three_seconds",
    "space_readability",
    "material_fidelity",
    "color_consistency",
    "motion_stability",
    "transition_boundaries",
    "full_contact_sheet",
    "authenticity_label",
}


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


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def passed(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("status")
    return str(value or "").strip().lower() in {"pass", "passed"}


def project_path(root: Path, value: Any) -> Path | None:
    if not nonempty(value):
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def probe_streams(path: Path) -> dict[str, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for final validation")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams", [])
    return {
        "video": sum(item.get("codec_type") == "video" for item in streams),
        "audio": sum(item.get("codec_type") == "audio" for item in streams),
    }


def load_core(
    root: Path,
    errors: list[str],
    required_keys: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for key, filename in CORE_FILES.items():
        if required_keys is not None and key not in required_keys:
            continue
        path = root / filename
        if not path.is_file():
            errors.append(f"core_artifact_missing:{filename}")
            continue
        try:
            documents[key] = load_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"core_artifact_invalid:{filename}:{exc}")
    return documents


def validate_identity(documents: dict[str, dict[str, Any]], errors: list[str]) -> tuple[str, str]:
    source = documents.get("source", {})
    task_id = str(source.get("task_id") or "").strip()
    run_id = str(source.get("run_id") or "").strip()
    if not task_id:
        errors.append("source_brief_missing_task_id")
    if not run_id:
        errors.append("source_brief_missing_run_id")
    for key, document in documents.items():
        if task_id and document.get("task_id") != task_id:
            errors.append(f"task_id_mismatch:{CORE_FILES[key]}")
        if run_id and document.get("run_id") != run_id:
            errors.append(f"run_id_mismatch:{CORE_FILES[key]}")
    return task_id, run_id


def validate_route(
    source: dict[str, Any],
    content: dict[str, Any],
    storyboard: dict[str, Any],
    errors: list[str],
) -> None:
    input_mode = source.get("input_mode")
    video_need = source.get("video_need")
    presentation = source.get("presentation_mode")
    copy_mode = source.get("copy_mode")
    source_tier = source.get("source_tier")
    production_profile = source.get("production_profile", "candidate")
    constraints = source.get("constraints") if isinstance(source.get("constraints"), dict) else {}
    formal_cover = source.get("formal_cover")

    if input_mode not in INPUT_MODES:
        errors.append("input_mode_invalid")
    if video_need not in VIDEO_NEEDS:
        errors.append("video_need_invalid")
    if presentation not in PRESENTATION_MODES:
        errors.append("presentation_mode_invalid")
    if copy_mode not in COPY_MODES:
        errors.append("copy_mode_invalid")
    if source_tier not in SOURCE_TIERS:
        errors.append("source_tier_invalid")
    if production_profile not in PRODUCTION_PROFILES:
        errors.append("production_profile_invalid")
    for key in ("target_channel", "aspect_ratio", "authenticity_label"):
        if not nonempty(source.get(key)):
            errors.append(f"source_brief_missing_{key}")
    try:
        if float(source.get("duration_seconds", 0)) <= 0:
            errors.append("source_brief_duration_invalid")
    except (TypeError, ValueError):
        errors.append("source_brief_duration_invalid")

    if isinstance(formal_cover, dict) and nonempty(formal_cover.get("path")):
        opt_out = formal_cover.get("in_video_cover_opt_out")
        opted_out = isinstance(opt_out, dict) and opt_out.get("explicit_user_authorization") is True
        if not opted_out and formal_cover.get("in_video_first_frame") is not True:
            errors.append("formal_cover_requires_in_video_first_frame")
        if opted_out and (
            not nonempty(opt_out.get("reason")) or not nonempty(opt_out.get("evidence"))
        ):
            errors.append("formal_cover_opt_out_requires_reason_and_evidence")

    directions = content.get("candidate_directions")
    if not isinstance(directions, list) or len(directions) < 2:
        errors.append("content_plan_requires_two_directions")
        direction_ids: set[str] = set()
    else:
        direction_ids = {
            str(item.get("id"))
            for item in directions
            if isinstance(item, dict) and nonempty(item.get("id"))
        }
        if len(direction_ids) < 2:
            errors.append("candidate_direction_ids_invalid")
    if content.get("selected_direction_id") not in direction_ids:
        errors.append("selected_direction_not_in_candidates")
    for key in ("visual_thesis", "selection_reason"):
        if not nonempty(content.get(key)):
            errors.append(f"content_plan_missing_{key}")
    for key in ("style_profile", "grade_profile", "music", "copy"):
        if not isinstance(content.get(key), dict):
            errors.append(f"content_plan_missing_{key}")

    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 2:
        errors.append("storyboard_requires_at_least_two_scenes")
        scenes = []
    seen: set[str] = set()
    previous_end: float | None = None
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            errors.append(f"scene_{index + 1}_must_be_object")
            continue
        scene_id = str(scene.get("id") or "").strip()
        if not scene_id:
            errors.append(f"scene_{index + 1}_missing_id")
        elif scene_id in seen:
            errors.append(f"duplicate_scene_id:{scene_id}")
        seen.add(scene_id)
        for key in (
            "spatial_value",
            "composition",
            "camera_or_motion",
            "change_reason",
            "transition_out",
        ):
            if not nonempty(scene.get(key)):
                errors.append(f"scene_missing_{key}:{scene_id or index + 1}")
        if not isinstance(scene.get("source_asset_ids"), list) or not scene["source_asset_ids"]:
            errors.append(f"scene_missing_source_asset_ids:{scene_id or index + 1}")
        if not isinstance(scene.get("grade_target"), dict):
            errors.append(f"scene_missing_grade_target:{scene_id or index + 1}")
        try:
            start = float(scene.get("start"))
            end = float(scene.get("end"))
            if end <= start:
                errors.append(f"scene_time_invalid:{scene_id or index + 1}")
            if previous_end is not None and abs(start - previous_end) > 0.05:
                errors.append(f"scene_timeline_gap_or_overlap:{scene_id or index + 1}")
            previous_end = end
        except (TypeError, ValueError):
            errors.append(f"scene_time_invalid:{scene_id or index + 1}")

    raw_overlays = source.get("compliance_overlays")
    compliance_overlays = raw_overlays if isinstance(raw_overlays, list) else []
    allowed_overlay_texts = {
        str(item.get("text") or "").strip()
        for item in compliance_overlays
        if isinstance(item, dict)
        and item.get("role") == "truthfulness_disclosure"
        and nonempty(item.get("text"))
    }
    if source_tier == "ai_concept" and "production_profile" in source:
        # Current owner/project policy: AI origin remains required in metadata;
        # the visible disclosure is optional, but when enabled is exact and left.
        # This does not waive publish-time disclosure, copy or rights gates.
        if not isinstance(raw_overlays, list):
            errors.append("ai_concept_compliance_overlays_requires_explicit_list")
        for item in compliance_overlays:
            if not isinstance(item, dict) or item.get("role") != "truthfulness_disclosure":
                errors.append("ai_concept_disclosure_role_invalid")
                continue
            if str(item.get("text") or "").strip() != "仅设计效果图":
                errors.append("ai_concept_requires_exact_design_effect_disclosure")
            if (item.get("placement") != "bottom_left_safe_zone"
                    or item.get("persistent") is not True):
                errors.append("ai_concept_disclosure_requires_persistent_bottom_left_safe_zone")

    if presentation == "visual_music":
        if copy_mode != "none":
            errors.append("visual_music_requires_copy_mode_none")
        for key in ("video_copy", "english", "voiceover"):
            if constraints.get(key) is not False:
                errors.append(f"visual_music_requires_{key}_false")
        if constraints.get("cta") not in {"none", "publish_caption", "separate_cover"}:
            errors.append("visual_music_forbids_video_cta")
        copy = content.get("copy", {})
        if copy.get("mode") != "none":
            errors.append("visual_music_content_copy_must_be_none")
        for scene in scenes:
            visible = scene.get("on_screen_text")
            visible_items = [] if visible in (None, "", []) else (visible if isinstance(visible, list) else [visible])
            unauthorized = [
                str(item).strip()
                for item in visible_items
                if str(item).strip() not in allowed_overlay_texts
            ]
            if unauthorized:
                errors.append(f"visual_music_scene_contains_text:{scene.get('id')}")
        music = content.get("music", {})
        if music.get("required") is not True:
            errors.append("visual_music_requires_music")
        for key in ("selection_path", "map_path"):
            if not nonempty(music.get(key)):
                errors.append(f"visual_music_missing_music_{key}")
    elif presentation == "minimal_brand" and copy_mode != "minimal":
        errors.append("minimal_brand_requires_copy_mode_minimal")
    elif presentation == "copy_led":
        if copy_mode != "narrative":
            errors.append("copy_led_requires_copy_mode_narrative")
        if not nonempty(content.get("copy", {}).get("script_path")):
            errors.append("copy_led_requires_script_path")


def validate_assets(
    root: Path,
    documents: dict[str, dict[str, Any]],
    phase: str,
    errors: list[str],
) -> None:
    raw_assets = documents.get("assets", {}).get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        errors.append("asset_manifest_requires_assets")
        return
    ids: set[str] = set()
    for index, asset in enumerate(raw_assets):
        if not isinstance(asset, dict):
            errors.append(f"asset_{index + 1}_must_be_object")
            continue
        asset_id = str(asset.get("id") or "").strip()
        if not asset_id or asset_id in ids:
            errors.append(f"asset_id_invalid_or_duplicate:{asset_id or index + 1}")
            continue
        ids.add(asset_id)
        for key in ("source_kind", "rights_status", "authenticity_role"):
            if not nonempty(asset.get(key)):
                errors.append(f"asset_missing_{key}:{asset_id}")
        path = project_path(root, asset.get("path"))
        if path is None:
            errors.append(f"asset_missing_path:{asset_id}")
        elif phase in {"frames", "final"} and not path.is_file():
            errors.append(f"asset_file_missing:{asset_id}:{path}")

    for scene in documents.get("storyboard", {}).get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for asset_id in scene.get("source_asset_ids", []):
            if asset_id not in ids:
                errors.append(f"scene_unknown_asset:{scene.get('id')}:{asset_id}")


def validate_frames(
    root: Path,
    documents: dict[str, dict[str, Any]],
    run_id: str,
    errors: list[str],
) -> None:
    frame_path = root / "runtime" / "frame-review.json"
    color_path = root / "runtime" / "scene-color-report.json"
    if not frame_path.is_file():
        errors.append("frame_review_missing")
    else:
        frame = load_json(frame_path)
        if frame.get("run_id") != run_id:
            errors.append("frame_review_run_id_mismatch")
        if not passed(frame.get("status")):
            errors.append("frame_review_not_passed")
        coverage = frame.get("coverage") if isinstance(frame.get("coverage"), dict) else {}
        for key in ("opening", "brightest_scene", "darkest_scene", "transition_midpoint"):
            if not passed(coverage.get(key)):
                errors.append(f"frame_review_missing_pass:{key}")
        material = coverage.get("material_detail")
        if not passed(material):
            status = material.get("status") if isinstance(material, dict) else material
            reason = material.get("reason") if isinstance(material, dict) else None
            if str(status or "").lower() != "not_applicable" or not nonempty(reason):
                errors.append("frame_review_material_detail_unresolved")
        expected_storyboard_hash = sha256(root / CORE_FILES["storyboard"])
        if frame.get("storyboard_sha256") != expected_storyboard_hash:
            errors.append("frame_review_stale_storyboard")

    if not color_path.is_file():
        errors.append("scene_color_report_missing")
    else:
        color = load_json(color_path)
        if color.get("run_id") != run_id:
            errors.append("scene_color_report_run_id_mismatch")
        if not passed(color.get("status")):
            errors.append("scene_color_report_not_passed")
        expected_storyboard_hash = sha256(root / CORE_FILES["storyboard"])
        expected_content_hash = sha256(root / CORE_FILES["content"])
        fingerprints = color.get("input_fingerprints", {})
        if fingerprints.get("storyboard_sha256") != expected_storyboard_hash:
            errors.append("scene_color_report_stale_storyboard")
        if fingerprints.get("content_plan_sha256") != expected_content_hash:
            errors.append("scene_color_report_stale_content_plan")
        expected_count = len(documents.get("storyboard", {}).get("scenes", []))
        if color.get("scene_count_measured") != expected_count:
            errors.append("scene_color_report_incomplete_scene_coverage")


def validate_final(
    root: Path,
    documents: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, Any] | None:
    qa = documents.get("qa", {})
    handoff = documents.get("handoff", {})
    if not passed(qa.get("status")):
        errors.append("qa_report_not_passed")
    automated = qa.get("automated_evidence") if isinstance(qa.get("automated_evidence"), dict) else {}
    qc_path = project_path(root, automated.get("video_qc"))
    if qc_path is None or not qc_path.is_file():
        errors.append("qa_report_missing_machine_qc_reference")
    else:
        try:
            qc = load_json(qc_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"qa_report_machine_qc_invalid:{exc}")
        else:
            if str(qc.get("overall_status") or "").lower() == "failed":
                errors.append("qa_report_references_failed_machine_qc")
    checks = qa.get("manual_review", {}).get("checks", {})
    required_checks = set(FINAL_MANUAL_CHECKS)
    if documents.get("content", {}).get("music", {}).get("required") is True:
        required_checks.add("music_audible")
    formal_cover = documents.get("source", {}).get("formal_cover")
    if isinstance(formal_cover, dict) and nonempty(formal_cover.get("path")):
        opt_out = formal_cover.get("in_video_cover_opt_out")
        if not (isinstance(opt_out, dict) and opt_out.get("explicit_user_authorization") is True):
            required_checks.add("formal_cover_first_frame")
    for key in sorted(required_checks):
        if not passed(checks.get(key)):
            errors.append(f"qa_manual_check_not_passed:{key}")

    gate = handoff.get("gate", {})
    if not passed(gate.get("status")):
        errors.append("handoff_gate_not_passed")
    final_path = project_path(root, handoff.get("final_video"))
    if final_path is None or not final_path.is_file():
        errors.append("handoff_final_video_missing")
        return None

    try:
        streams = probe_streams(final_path)
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        errors.append(f"final_ffprobe_failed:{exc}")
        return None
    if streams["video"] < 1:
        errors.append("final_video_stream_missing")
    if documents.get("content", {}).get("music", {}).get("required") is True and streams["audio"] < 1:
        errors.append("final_audio_stream_missing")

    fingerprints = handoff.get("input_fingerprints", {})
    expected = {
        "final_video_sha256": sha256(final_path),
        "qa_report_sha256": sha256(root / CORE_FILES["qa"]),
        "storyboard_sha256": sha256(root / CORE_FILES["storyboard"]),
    }
    for key, value in expected.items():
        if fingerprints.get(key) != value:
            errors.append(f"handoff_stale_or_missing_fingerprint:{key}")
    return {"path": str(final_path), "streams": streams, "sha256": expected["final_video_sha256"]}


def validate(root: Path, phase: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        source_probe = load_json(root / CORE_FILES["source"])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        source_probe = {}
        errors.append(f"core_artifact_invalid:{CORE_FILES['source']}:{exc}")
    profile = source_probe.get("production_profile", "candidate")
    if "production_profile" not in source_probe:
        warnings.append("legacy_source_brief_missing_production_profile_defaulted_to_candidate")
    required_keys = {"source", "content", "storyboard", "assets"} if profile == "preview" else set(CORE_FILES)
    documents = load_core(root, errors, required_keys)
    if len(documents) != len(required_keys):
        return {
            "status": "FAIL",
            "phase": phase,
            "project": str(root),
            "errors": errors,
            "warnings": warnings,
        }

    task_id, run_id = validate_identity(documents, errors)
    validate_route(
        documents["source"],
        documents["content"],
        documents["storyboard"],
        errors,
    )
    validate_assets(root, documents, phase, errors)

    final_media: dict[str, Any] | None = None
    if phase in {"frames", "final"}:
        validate_frames(root, documents, run_id, errors)
    if phase == "final":
        if profile == "preview":
            errors.append("preview_profile_cannot_use_final_phase")
        else:
            final_media = validate_final(root, documents, errors)
            if profile in {"publish", "l4"}:
                package_path = root / "publish-package.json"
                if not package_path.is_file():
                    errors.append("douyin_publish_package_missing")
                else:
                    try:
                        publish_result = validate_douyin_publish_package(package_path)
                    except (OSError, json.JSONDecodeError, ValueError) as exc:
                        errors.append(f"douyin_publish_package_invalid:{exc}")
                    else:
                        for item in publish_result.get("errors", []):
                            errors.append(f"douyin_publish_package:{item}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "phase": phase,
        "project": str(root),
        "task_id": task_id,
        "run_id": run_id,
        "presentation_mode": documents["source"].get("presentation_mode"),
        "production_profile": profile,
        "video_need": documents["source"].get("video_need"),
        "core_artifacts": [CORE_FILES[key] for key in CORE_FILES if key in required_keys],
        "final_media": final_media,
        "errors": errors,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--phase", choices=["plan", "frames", "final"], required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    report = validate(root, args.phase)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
