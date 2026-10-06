#!/usr/bin/env python3
"""Validate the runtime contract for visual-music and copy-led video routes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


EXTERNAL_RELEASE_SCOPES = {
    "external_final",
    "cross_platform_final",
    "paid_ad",
    "public_delivery",
}


def load_contract(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Contract root must be an object")
    return data


def audio_stream_count(path: Path) -> int:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for final-media validation")
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return len(json.loads(result.stdout).get("streams", []))


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_contract(contract: dict[str, Any], final_media: Path | None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    presentation = contract.get("presentation_mode")
    copy_mode = contract.get("copy_mode")
    english_status = contract.get("english_status")
    cta_location = contract.get("cta_location")
    stage = contract.get("stage", "planned")
    release_scope = contract.get("release_scope", "internal_reference")
    routing = contract.get("routing", {})
    artifacts = contract.get("artifacts", {})
    music_state = contract.get("music_state", {})
    music_required = presentation == "visual_music" or contract.get("music_required") is True
    audio_required = contract.get("audio_required")
    if audio_required is None:
        audio_required = presentation in {"visual_music", "copy_led"}

    if presentation not in {"visual_music", "minimal_brand", "copy_led"}:
        errors.append("presentation_mode_invalid")
    if copy_mode not in {"none", "minimal", "narrative"}:
        errors.append("copy_mode_invalid")

    if presentation == "visual_music":
        if copy_mode != "none":
            errors.append("visual_music_requires_copy_mode_none")
        if english_status != "not_requested":
            errors.append("visual_music_forbids_automatic_english")
        if cta_location not in {"none", "publish_caption", "separate_cover"}:
            errors.append("visual_music_forbids_in_video_cta")
        for key in ("copy_template_enabled", "english_template_enabled", "cta_template_enabled"):
            if routing.get(key) is not False:
                errors.append(f"visual_music_requires_{key}_false")
        for key in ("music_selection", "music_map", "visual_sequence"):
            if not nonempty(artifacts.get(key)):
                errors.append(f"visual_music_missing_{key}")
        script_or_copy = artifacts.get("script_or_copy")
        if script_or_copy is not None and script_or_copy not in {"", "not_applicable"}:
            errors.append("visual_music_must_not_route_script_or_copy")
        if music_state.get("selected") is not True:
            errors.append("visual_music_requires_selected_music")

    if presentation == "minimal_brand":
        if copy_mode != "minimal":
            errors.append("minimal_brand_requires_copy_mode_minimal")
        if cta_location == "in_video_narrative":
            errors.append("minimal_brand_forbids_narrative_cta")

    if presentation == "copy_led":
        if copy_mode != "narrative":
            errors.append("copy_led_requires_copy_mode_narrative")
        if not nonempty(artifacts.get("script_or_copy")):
            errors.append("copy_led_requires_script_or_copy")

    measured_audio_streams: int | None = None
    if stage == "final_candidate":
        if final_media is None:
            errors.append("final_candidate_requires_final_media")
        elif not final_media.is_file():
            errors.append("final_media_missing")
        else:
            measured_audio_streams = audio_stream_count(final_media)
            if audio_required and measured_audio_streams < 1:
                errors.append("final_media_audio_stream_missing")
        if music_required:
            for key in ("selected", "mounted", "audible"):
                if music_state.get(key) is not True:
                    errors.append(f"final_candidate_requires_music_{key}")
        if (
            music_required
            and release_scope in EXTERNAL_RELEASE_SCOPES
            and music_state.get("rights_cleared") is not True
        ):
            errors.append("external_release_requires_rights_cleared")
    elif stage != "planned":
        warnings.append(f"unrecognized_stage:{stage}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "presentation_mode": presentation,
        "copy_mode": copy_mode,
        "stage": stage,
        "release_scope": release_scope,
        "audio_required": bool(audio_required),
        "music_required": bool(music_required),
        "final_media": str(final_media) if final_media else None,
        "measured_audio_stream_count": measured_audio_streams,
        "errors": errors,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--final-media", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    contract = load_contract(args.contract.expanduser().resolve())
    final_media = args.final_media.expanduser().resolve() if args.final_media else None
    result = validate_contract(contract, final_media)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = args.output.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
