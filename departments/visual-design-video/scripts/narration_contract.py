#!/usr/bin/env python3
"""Additive narration contract checks; absent narration preserves legacy behavior."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import subprocess
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUBTITLE_POLICY = "narration-bilingual-full-v1"
TEMPO_POLICY = "owner-selected-voice-pace-v1"
EXPERIENCE_REVIEW_POLICY = "narration-experience-review-v1"
PACE_RATIO_MIN = 0.90
PACE_RATIO_MAX = 1.10
EXPERIENCE_REVIEW_CHECKS = (
    "voice_pace",
    "voice_naturalness",
    "voice_pronunciation",
    "fixed_voice_stability",
    "music_audibility",
    "voice_music_balance",
    "narration_visual_sync",
)
FINAL_NARRATION_PATHS = (
    "voice_audio_path",
    "alignment_path",
    "spoken_copy_path",
    "audio_mix_report_path",
    "timing_path",
    "tempo_calibration_path",
    "experience_review_path",
)


def _spoken_units(value: str) -> str:
    """Ignore punctuation/spacing only; retain numbers and every spoken word."""
    return "".join(re.findall(r"\w", unicodedata.normalize("NFKC", value), re.UNICODE))


def _resolve_project_file(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else (base or PROJECT_ROOT) / path).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("narration_evidence_outside_project")
    if not resolved.is_file():
        raise FileNotFoundError("narration_evidence_file_missing")
    return resolved


def _resolve_project_destination(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else (base or PROJECT_ROOT) / path).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("narration_output_outside_project")
    if not resolved.parent.is_dir():
        raise FileNotFoundError("narration_output_parent_missing")
    if resolved.exists():
        raise FileExistsError("narration_output_refuses_overwrite")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_pin(path: Path) -> dict:
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _audio_duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("narration_audio_duration_invalid")
    return duration


def build_tempo_calibration_report(voice_audio: str | Path, spoken_copy: str | Path) -> dict:
    """Measure final Chinese speech pace against the owner's selected A audition."""
    from narration_audio import active_profile

    voice_path = _resolve_project_file(voice_audio)
    text_path = _resolve_project_file(spoken_copy)
    profile = active_profile()
    preferences = profile.get("production_preferences", {})
    reference_value = preferences.get("preferred_voice_audio_path")
    reference_path = _resolve_project_file(reference_value)
    reference_audio = _file_pin(reference_path)
    if reference_audio["sha256"] != preferences.get("preferred_voice_audio_sha256"):
        raise ValueError("owner_selected_tempo_reference_hash_mismatch")

    reference_text = profile.get("reference_text", "")
    if hashlib.sha256(reference_text.encode("utf-8")).hexdigest() != profile.get("reference_text_sha256"):
        raise ValueError("owner_selected_tempo_reference_text_hash_mismatch")
    reference_units = len(_spoken_units(reference_text))
    candidate_text = text_path.read_text(encoding="utf-8")
    candidate_units = len(_spoken_units(candidate_text))
    if not reference_units or not candidate_units:
        raise ValueError("narration_tempo_requires_nonempty_chinese_copy")

    expected_reference_duration = float(preferences["preferred_audition_duration_seconds"])
    measured_reference_duration = _audio_duration(reference_path)
    if abs(measured_reference_duration - expected_reference_duration) > 0.05:
        raise ValueError("owner_selected_tempo_reference_duration_mismatch")
    candidate_duration = _audio_duration(voice_path)
    reference_rate = reference_units / measured_reference_duration
    candidate_rate = candidate_units / candidate_duration
    ratio = candidate_rate / reference_rate
    in_range = PACE_RATIO_MIN <= ratio <= PACE_RATIO_MAX
    return {
        "policy_version": TEMPO_POLICY,
        "status": "PASS_PACE_MATCHED_TO_OWNER_AUDITION" if in_range else "HOLD_PACE_OUTSIDE_OWNER_AUDITION_RANGE",
        "voice_profile_id": profile["id"],
        "reference": {
            "audio": reference_audio,
            "text_sha256": profile["reference_text_sha256"],
            "duration_seconds": round(measured_reference_duration, 6),
            "speakable_unit_count": reference_units,
            "speakable_units_per_second": round(reference_rate, 6),
        },
        "candidate": {
            "audio": _file_pin(voice_path),
            "text": _file_pin(text_path),
            "duration_seconds": round(candidate_duration, 6),
            "speakable_unit_count": candidate_units,
            "speakable_units_per_second": round(candidate_rate, 6),
        },
        "pace_ratio_vs_owner_selected_audition": round(ratio, 6),
        "accepted_ratio_range": [PACE_RATIO_MIN, PACE_RATIO_MAX],
        "duration_45_to_60_seconds_is_not_a_pace_check": True,
        "re_align_after_any_audio_change": True,
    }


def validate_experience_review(
    review: dict,
    *,
    final_video_sha256: str,
    voice_sha256: str,
    mixed_audio_sha256: str,
    video_duration_seconds: float,
) -> list[str]:
    """Validate a real-review receipt's schema and SHA binding; never infer listening."""
    errors = []
    if not isinstance(review, dict):
        return ["narration_experience_review_invalid"]
    if review.get("policy_version") != EXPERIENCE_REVIEW_POLICY:
        errors.append("narration_experience_review_policy_mismatch")
    if review.get("status") != "PASS":
        errors.append("narration_experience_review_not_passed")
    if not isinstance(review.get("review_id"), str) or not review["review_id"].strip():
        errors.append("narration_experience_review_id_required")
    reviewed_at = review.get("reviewed_at")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            errors.append("narration_experience_review_timezone_required")
    except (AttributeError, TypeError, ValueError):
        errors.append("narration_experience_review_timestamp_invalid")
    reviewer = review.get("reviewer", {})
    if not isinstance(reviewer, dict) or reviewer.get("role") not in {"owner", "independent_qa"} or not isinstance(reviewer.get("id"), str) or not reviewer["id"].strip():
        errors.append("narration_experience_review_reviewer_invalid")
    playback = review.get("playback", {})
    if not isinstance(playback, dict):
        errors.append("narration_experience_review_playback_invalid")
    else:
        try:
            played_seconds = float(playback.get("reviewed_duration_seconds"))
            playback_speed = float(playback.get("speed"))
            if playback.get("mode") != "full_realtime_final_video" or playback_speed != 1.0:
                errors.append("narration_experience_review_full_realtime_playback_required")
            if not math.isfinite(played_seconds) or played_seconds < video_duration_seconds - 0.3:
                errors.append("narration_experience_review_incomplete_playback")
        except (TypeError, ValueError):
            errors.append("narration_experience_review_playback_invalid")
    artifacts = review.get("reviewed_artifacts", {})
    expected = {
        "final_video_sha256": final_video_sha256,
        "voice_audio_sha256": voice_sha256,
        "mixed_audio_sha256": mixed_audio_sha256,
    }
    if not isinstance(artifacts, dict):
        errors.append("narration_experience_review_artifacts_invalid")
    else:
        for key, digest in expected.items():
            actual_digest = artifacts.get(key)
            if not isinstance(actual_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", actual_digest):
                errors.append("narration_experience_review_artifact_hash_invalid:" + key)
            elif actual_digest != digest:
                errors.append("narration_experience_review_artifact_mismatch:" + key)
    checks = review.get("checks", {})
    if not isinstance(checks, dict):
        errors.append("narration_experience_review_checks_invalid")
    else:
        for key in EXPERIENCE_REVIEW_CHECKS:
            if checks.get(key) != "PASS":
                errors.append("narration_experience_review_check_missing:" + key)
    return errors


def validate_subtitle_cues(document: dict, timing: dict, duration: float) -> list[str]:
    """Structure/coverage only, never proves rendering, translation or listening."""
    errors = []
    try:
        if document.get("policy_version") != SUBTITLE_POLICY:
            errors.append("narration_subtitle_policy_mismatch")
        offset = float(document["audio_offset_seconds"])
        if not math.isfinite(offset) or offset < 0 or not math.isfinite(duration):
            return errors + ["narration_subtitle_offset_or_duration_invalid"]
        lines = {line["id"]: line for line in timing["lines"]}
        if len(lines) != len(timing["lines"]) or not lines:
            return errors + ["narration_subtitle_source_lines_invalid"]
        for line in lines.values():
            a, b = float(line["start"]), float(line["end"])
            if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b <= a:
                return errors + ["narration_subtitle_source_line_time_invalid"]
        cues = document.get("cues")
        if not isinstance(cues, list) or not cues:
            return errors + ["narration_full_bilingual_subtitle_cues_required"]
        covered = {key: [] for key in lines}
        bounds = {key: [] for key in lines}
        identifiers = set()
        previous_end = -1.0
        for cue in cues:
            cue_id, line_id = cue["id"], cue["line_id"]
            if not isinstance(cue_id, str) or not cue_id.strip() or cue_id in identifiers:
                errors.append("narration_subtitle_id_invalid_or_duplicate")
            identifiers.add(cue_id)
            if line_id not in lines:
                errors.append("narration_subtitle_unknown_line:" + str(line_id))
                continue
            zh, en = cue.get("zh"), cue.get("en")
            if not isinstance(zh, str) or not _spoken_units(zh) or not isinstance(en, str) or not en.strip():
                errors.append("narration_subtitle_both_languages_required:" + str(cue_id))
                continue
            start, end = float(cue["start"]), float(cue["end"])
            if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start or end > duration + .001:
                errors.append("narration_subtitle_time_invalid:" + str(cue_id))
                continue
            if start < previous_end - .001:
                errors.append("narration_subtitle_cues_overlap_or_out_of_order:" + str(cue_id))
            previous_end = end
            line = lines[line_id]
            if start < float(line["start"]) + offset - .3 or end > float(line["end"]) + offset + .3:
                errors.append("narration_subtitle_outside_spoken_line:" + str(cue_id))
            covered[line_id].append(zh)
            bounds[line_id].append((start, end))
        for line_id, line in lines.items():
            if _spoken_units("".join(covered[line_id])) != _spoken_units(line["text"]):
                errors.append("narration_subtitle_incomplete_spoken_coverage:" + str(line_id))
            ranges = bounds[line_id]
            if not ranges:
                continue
            if abs(ranges[0][0] - (float(line["start"]) + offset)) > .3 or abs(ranges[-1][1] - (float(line["end"]) + offset)) > .3:
                errors.append("narration_subtitle_line_edges_not_synced:" + str(line_id))
            if any(right[0] - left[1] > .3 for left, right in zip(ranges, ranges[1:])):
                errors.append("narration_subtitle_uncovered_spoken_interval:" + str(line_id))
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append("narration_subtitle_document_invalid")
    return errors


def validate_subtitle_html(html: str, document: dict) -> list[str]:
    """Require real clip declarations, not chapter titles or external SRT only."""
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.records = []
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            classes = set(values.get("class", "").split())
            record = next((v[1] for v in reversed(self.stack) if v[1] is not None), None)
            language = next((v[2] for v in reversed(self.stack) if v[2] is not None), None)
            if "narration-subtitle" in classes:
                record = {"attrs": values, "zh": "", "en": ""}
                self.records.append(record)
                language = None
            if "subtitle-zh" in classes:
                language = "zh"
            elif "subtitle-en" in classes:
                language = "en"
            if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
                self.stack.append((tag, record, language))
        def handle_endtag(self, tag):
            for index in range(len(self.stack)-1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break
        def handle_data(self, data):
            if self.stack:
                _, record, language = self.stack[-1]
                if record is not None and language is not None:
                    record[language] += data
    errors = []
    try:
        parser = Reader()
        parser.feed(html)
        records = parser.records
        cues = document["cues"]
        if len(records) != len(cues):
            errors.append("narration_subtitle_html_clip_count_mismatch")
        by_id = {r["attrs"].get("data-cue-id"): r for r in records}
        if len(by_id) != len(records):
            errors.append("narration_subtitle_html_duplicate_cue")
        for cue in cues:
            record = by_id.get(cue["id"])
            if record is None:
                errors.append("narration_subtitle_missing_html_clip:" + cue["id"])
                continue
            attrs = record["attrs"]
            if "clip" not in attrs.get("class", "").split() or "data-track-index" not in attrs or not attrs.get("id"):
                errors.append("narration_subtitle_html_timing_track_required:" + cue["id"])
            start, length = float(attrs["data-start"]), float(attrs["data-duration"])
            if not math.isfinite(start) or not math.isfinite(length) or abs(start-float(cue["start"])) > .001 or abs(start+length-float(cue["end"])) > .001:
                errors.append("narration_subtitle_html_time_mismatch:" + cue["id"])
            if _spoken_units(record["zh"]) != _spoken_units(cue["zh"]) or " ".join(record["en"].split()) != " ".join(cue["en"].split()):
                errors.append("narration_subtitle_html_text_mismatch:" + cue["id"])
    except (KeyError, TypeError, ValueError):
        errors.append("narration_subtitle_html_invalid")
    return errors


def validate_final_mix_mount(html: str, composition_path: Path, expected_mix_sha256: str, expected_duration: float) -> list[str]:
    """Ensure the rendered composition references the exact measured project mix."""
    class AudioReader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.clips = []
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "audio" and "clip" in values.get("class", "").split():
                self.clips.append(values)

    errors = []
    try:
        reader = AudioReader()
        reader.feed(html)
        if len(reader.clips) != 1:
            return ["narration_final_mix_requires_one_mixed_audio_clip"]
        clip = reader.clips[0]
        source = clip.get("src")
        if not source:
            return ["narration_final_mix_source_required"]
        source_path = (composition_path.parent / source).resolve()
        if not source_path.is_relative_to(PROJECT_ROOT) or not source_path.is_file():
            return ["narration_final_mix_source_missing_or_outside_project"]
        if _sha256(source_path) != expected_mix_sha256:
            errors.append("narration_final_mix_source_does_not_match_reviewed_mix")
        actual_duration = float(clip["data-duration"])
        if not math.isfinite(actual_duration) or abs(actual_duration - expected_duration) > .3:
            errors.append("narration_final_mix_clip_duration_mismatch")
    except (KeyError, TypeError, ValueError, OSError):
        errors.append("narration_final_mix_mount_invalid")
    return errors


def enabled_narration(contract: dict) -> bool:
    narration = contract.get("narration")
    return isinstance(narration, dict) and narration.get("enabled") is True


def validate_narration(contract: dict, storyboard: dict | None = None, final: bool = False) -> list[str]:
    errors = []
    narration = contract.get("narration")
    if narration is None:
        return errors
    if not isinstance(narration, dict) or type(narration.get("enabled")) is not bool:
        return ["narration_enabled_must_be_explicit_boolean"]
    if not narration["enabled"]:
        return errors
    if contract.get("presentation_mode") != "copy_led" or contract.get("copy_mode") != "narrative":
        errors.append("narration_requires_copy_led_narrative")
    if contract.get("timing_driver") != "narration":
        errors.append("narration_must_drive_timing")
    if narration.get("language") != "zh-CN":
        errors.append("narration_language_must_be_zh_CN")
    if contract.get("audio_required") is False or contract.get("music_required") is False:
        errors.append("narration_requires_voice_and_low_background_music")
    audition = contract.get("stage") == "five_voice_auditions_before_owner_selection"
    if not audition and not isinstance(narration.get("voice_profile_id"), str):
        errors.append("narration_fixed_voice_selection_required")
    if isinstance(narration.get("voice_profile_id"), str) and not narration["voice_profile_id"].strip():
        errors.append("narration_voice_profile_id_empty")
    if not audition:
        try:
            duration = float(contract.get("duration_seconds", 0))
            if not 45 <= duration <= 60:
                errors.append("narration_duration_must_be_45_to_60_seconds")
        except (TypeError, ValueError):
            errors.append("narration_duration_invalid")
    if final and not audition:
        for key in FINAL_NARRATION_PATHS:
            if not isinstance(narration.get(key), str) or not narration[key].strip():
                errors.append("narration_missing_" + key)
        subtitles = narration.get("subtitles")
        if not isinstance(subtitles, dict) or subtitles.get("enabled") is not True or subtitles.get("mode") != "burned_in_bilingual":
            errors.append("narration_full_burned_in_bilingual_subtitles_required")
        elif subtitles.get("policy_version") != SUBTITLE_POLICY or not isinstance(subtitles.get("cues_path"), str) or not subtitles["cues_path"].strip():
            errors.append("narration_subtitle_policy_and_cues_path_required")
    if storyboard is not None and not audition:
        scenes = storyboard.get("scenes", [])
        if len(scenes) < 2:
            errors.append("narration_requires_changing_visual_explanation")
        targets = set()
        for index, scene in enumerate(scenes):
            line_ids = scene.get("narration_line_ids")
            if not isinstance(line_ids, list) or not line_ids or any(not isinstance(v, str) or not v for v in line_ids):
                errors.append("narration_scene_missing_line_binding:" + str(scene.get("id", index)))
            if not scene.get("spoken_visual_evidence"):
                errors.append("narration_scene_missing_visual_evidence:" + str(scene.get("id", index)))
            target = (tuple(scene.get("source_asset_ids", [])), str(scene.get("spoken_visual_evidence", "")))
            targets.add(target)
        if len(targets) < 2:
            errors.append("narration_cannot_use_one_unchanged_visual_for_entire_voice")
    return errors


def validate_narration_evidence(contract: dict, base: Path, storyboard: dict | None = None, final_media: Path | None = None) -> list[str]:
    """Final read-only checks of real referenced files; never authenticates listening."""
    if not enabled_narration(contract):
        return []
    errors = validate_narration(contract, storyboard, final=True)
    narration = contract["narration"]
    if any(error.startswith("narration_missing_") for error in errors):
        return errors
    paths = {}
    digests = narration.get("evidence_sha256", {})
    if not isinstance(digests, dict):
        digests = {}
    def resolve(value):
        path = Path(value)
        path = (path if path.is_absolute() else base / path).resolve()
        if not path.is_relative_to(PROJECT_ROOT):
            raise ValueError("narration_evidence_outside_project")
        return path
    def sha(path):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    def check_pin(entry, actual_path=None):
        path = resolve(str(PROJECT_ROOT / entry["path"]))
        if actual_path is not None and path != actual_path:
            raise ValueError("narration_evidence_reference_mismatch")
        if sha(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError("narration_evidence_source_changed")
        return path
    try:
        for key in FINAL_NARRATION_PATHS:
            path = resolve(narration[key])
            if not path.is_file() or sha(path) != digests.get(key):
                errors.append("narration_final_file_or_hash_mismatch:" + key)
            paths[key] = path
        if errors:
            return errors
        from narration_audio import active_profile
        if active_profile()["id"] != narration["voice_profile_id"]:
            errors.append("narration_final_voice_not_owner_selected")
        def duration(path):
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, check=True)
            return float(json.loads(probe.stdout)["format"]["duration"])
        voice_duration = duration(paths["voice_audio_path"])
        if not 45 <= voice_duration <= 60 or abs(voice_duration - float(contract["duration_seconds"])) > .3:
            errors.append("narration_actual_voice_duration_outside_contract")
        if final_media is None or not final_media.is_file():
            errors.append("narration_final_video_file_required_for_experience_review")
            final_video_sha = None
            final_video_duration = None
        else:
            final_video_sha = sha(final_media)
            final_video_duration = duration(final_media)
            if not 45 <= final_video_duration <= 60:
                errors.append("narration_actual_video_duration_outside_contract")
        alignment = json.loads(paths["alignment_path"].read_text())
        timing = json.loads(paths["timing_path"].read_text())
        mix = json.loads(paths["audio_mix_report_path"].read_text())
        check_pin(alignment["audio"], paths["voice_audio_path"])
        check_pin(alignment["text"], paths["spoken_copy_path"])
        check_pin(timing["alignment"], paths["alignment_path"])
        check_pin(timing["audio"], paths["voice_audio_path"])
        check_pin(timing["text"], paths["spoken_copy_path"])
        check_pin(mix["voice"], paths["voice_audio_path"])
        check_pin(mix["music"])
        mixed_audio_path = check_pin(mix["mixed_audio"])
        if mix.get("status") != "PASS_TECHNICAL_PENDING_LISTENING" or mix.get("music_looped") is not False:
            errors.append("narration_mix_not_technically_passed")
        if abs(float(mix["loudness"]["input_i"]) + 16) > 1 or float(mix["loudness"]["input_tp"]) > -1:
            errors.append("narration_mix_levels_outside_target")
        if alignment.get("language") != "zh-CN" or not alignment.get("words"):
            errors.append("narration_actual_chinese_alignment_required")
        if timing.get("status") != "DERIVED_FROM_ACTUAL_ALIGNMENT" or not timing.get("lines"):
            errors.append("narration_actual_line_timing_required")

        tempo_report = json.loads(paths["tempo_calibration_path"].read_text(encoding="utf-8"))
        expected_tempo = build_tempo_calibration_report(paths["voice_audio_path"], paths["spoken_copy_path"])
        if tempo_report != expected_tempo:
            errors.append("narration_tempo_calibration_stale_or_mismatched")
        if tempo_report.get("status") != "PASS_PACE_MATCHED_TO_OWNER_AUDITION":
            errors.append("narration_voice_pace_outside_owner_selected_range")

        if final_video_sha is None or final_video_duration is None:
            errors.append("narration_experience_review_requires_final_video")
        else:
            experience_review = json.loads(paths["experience_review_path"].read_text(encoding="utf-8"))
            errors.extend(validate_experience_review(
                experience_review,
                final_video_sha256=final_video_sha,
                voice_sha256=sha(paths["voice_audio_path"]),
                mixed_audio_sha256=sha(mixed_audio_path),
                video_duration_seconds=final_video_duration,
            ))
        lines = {line["id"]: line for line in timing["lines"]}
        if len(lines) != len(timing["lines"]):
            errors.append("narration_timing_line_ids_not_unique")
        subtitle_path = resolve(narration["subtitles"]["cues_path"])
        if not subtitle_path.is_file() or sha(subtitle_path) != digests.get("subtitles.cues_path"):
            errors.append("narration_subtitle_file_or_hash_mismatch")
            return errors
        subtitles = json.loads(subtitle_path.read_text())
        check_pin(subtitles["audio"], paths["voice_audio_path"])
        check_pin(subtitles["text"], paths["spoken_copy_path"])
        check_pin(subtitles["timing"], paths["timing_path"])
        if _spoken_units("".join(line["text"] for line in timing["lines"])) != _spoken_units(paths["spoken_copy_path"].read_text()):
            errors.append("narration_subtitle_timing_does_not_cover_frozen_spoken_copy")
        errors.extend(validate_subtitle_cues(subtitles, timing, float(contract["duration_seconds"])))
        composition = resolve("index.html")
        if not composition.is_file():
            errors.append("narration_subtitle_composition_required")
        else:
            composition_html = composition.read_text()
            errors.extend(validate_subtitle_html(composition_html, subtitles))
            errors.extend(validate_final_mix_mount(
                composition_html,
                composition,
                sha(mixed_audio_path),
                _audio_duration(mixed_audio_path),
            ))
        if storyboard is not None:
            covered = set()
            for scene in storyboard.get("scenes", []):
                for line_id in scene.get("narration_line_ids", []):
                    if line_id not in lines:
                        errors.append("narration_unknown_scene_line:" + str(line_id))
                        continue
                    covered.add(line_id)
                    line = lines[line_id]
                    if float(scene["start"]) > line["start"] + .3 or float(scene["end"]) < line["end"] - .3:
                        errors.append("narration_line_outside_visual_segment:" + line_id)
            if covered != set(lines):
                errors.append("narration_some_lines_have_no_visual_binding")
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        errors.append("narration_evidence_invalid:" + type(exc).__name__)
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a non-overwriting pace calibration report against the selected owner voice.")
    sub = parser.add_subparsers(dest="command", required=True)
    tempo = sub.add_parser("tempo-report")
    tempo.add_argument("--voice", required=True, type=Path)
    tempo.add_argument("--spoken-copy", required=True, type=Path)
    tempo.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "tempo-report":
        report = build_tempo_calibration_report(args.voice, args.spoken_copy)
        output = _resolve_project_destination(args.output)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "output": str(output),
                          "pace_ratio_vs_owner_selected_audition": report["pace_ratio_vs_owner_selected_audition"],
                          "accepted_ratio_range": report["accepted_ratio_range"]}, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS_PACE_MATCHED_TO_OWNER_AUDITION" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
