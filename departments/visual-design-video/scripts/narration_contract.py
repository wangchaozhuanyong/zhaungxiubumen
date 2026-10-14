#!/usr/bin/env python3
"""Additive narration contract checks; absent narration preserves legacy behavior."""
from __future__ import annotations
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


def _spoken_units(value: str) -> str:
    """Ignore punctuation/spacing only; retain numbers and every spoken word."""
    return "".join(re.findall(r"\w", unicodedata.normalize("NFKC", value), re.UNICODE))


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
        for key in ("voice_audio_path", "alignment_path", "spoken_copy_path", "audio_mix_report_path", "timing_path"):
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
    paths = {}
    digests = narration.get("evidence_sha256", {})
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
        for key in ("voice_audio_path", "alignment_path", "spoken_copy_path", "audio_mix_report_path", "timing_path"):
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
        if final_media is not None and not 45 <= duration(final_media) <= 60:
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
        check_pin(mix["mixed_audio"])
        if mix.get("status") != "PASS_TECHNICAL_PENDING_LISTENING" or mix.get("music_looped") is not False:
            errors.append("narration_mix_not_technically_passed")
        if abs(float(mix["loudness"]["input_i"]) + 16) > 1 or float(mix["loudness"]["input_tp"]) > -1:
            errors.append("narration_mix_levels_outside_target")
        if alignment.get("language") != "zh-CN" or not alignment.get("words"):
            errors.append("narration_actual_chinese_alignment_required")
        if timing.get("status") != "DERIVED_FROM_ACTUAL_ALIGNMENT" or not timing.get("lines"):
            errors.append("narration_actual_line_timing_required")
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
            errors.extend(validate_subtitle_html(composition.read_text(), subtitles))
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
