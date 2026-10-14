#!/usr/bin/env python3
"""Project-local adapter to upstream Qwen3-TTS/MLX; no paid provider or implicit downloads."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "departments/visual-design-video/assets/voice/narration-engine.json"
PROFILES = ROOT / "departments/visual-design-video/assets/voice/voice-profiles.json"
GIB = 1024 ** 3


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("path_must_belong_to_flashcast_project")
    return path


def load_json(path: str | Path) -> dict:
    value = json.loads(project_path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("json_root_must_be_object")
    return value


def pin(path: str | Path) -> dict:
    path = project_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def write_json(path: str | Path, value: dict) -> None:
    path = project_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def reserve_disk(download_bytes: int = 0) -> dict:
    config = load_json(CONFIG)
    free = shutil.disk_usage(ROOT).free
    minimum = int(config["minimum_remaining_disk_gib"] * GIB)
    headroom = 256 * 1024 ** 2
    if free - download_bytes - headroom < minimum:
        raise ValueError("INSUFFICIENT_DISK_KEEP_8_GIB")
    return {"free_bytes": free, "download_bytes": download_bytes, "minimum_remaining_bytes": minimum}


def configure_local_cache(offline: bool = True) -> None:
    cache = project_path(ROOT / load_json(CONFIG)["cache_root"])
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.update(HF_HOME=str(cache), HF_HUB_CACHE=str(cache / "hub"),
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1", HF_HUB_DISABLE_TELEMETRY="1",
        HF_HUB_DISABLE_PROGRESS_BARS="1", XDG_CACHE_HOME=str(cache / "xdg"),
        HF_HUB_OFFLINE="1" if offline else "0")


def model_directory(kind: str) -> Path:
    config = load_json(CONFIG)
    entry = config["models"][kind]
    return project_path(ROOT / config["model_root"] / entry["repo_id"].split("/")[-1])


def fetch_model(kind: str, output: Path) -> dict:
    configure_local_cache(offline=False)
    config = load_json(CONFIG)
    entry = config["models"][kind]
    directory = model_directory(kind)
    if (directory / "frozen-model.json").exists():
        result = verify_model(kind)
        write_json(output, result)
        return result
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.utils import disable_progress_bars
    disable_progress_bars()
    info = HfApi(token=False).model_info(entry["repo_id"], revision=entry["revision"], files_metadata=True)
    if info.sha != entry["revision"]:
        raise ValueError("model_revision_mismatch")
    files = [{"name": item.rfilename, "bytes": item.size or 0} for item in info.siblings]
    total = sum(item["bytes"] for item in files)
    if total != entry["expected_bytes"]:
        raise ValueError("model_repository_size_changed")
    missing = sum(item["bytes"] for item in files
        if not (directory / item["name"]).is_file() or (directory / item["name"]).stat().st_size != item["bytes"])
    disk = reserve_disk(missing)
    snapshot_download(repo_id=entry["repo_id"], revision=entry["revision"],
        local_dir=directory, token=False, max_workers=2)
    frozen = {"schema_version": "1.0", "kind": kind, "repo_id": entry["repo_id"],
        "revision": entry["revision"], "license": entry["license"],
        "downloaded_at": datetime.now(timezone.utc).isoformat(), "disk_preflight": disk,
        "files": [pin(directory / item["name"]) for item in files],
        "signed_urls_saved": False, "cookie_or_token_material_saved": False}
    write_json(directory / "frozen-model.json", frozen)
    result = verify_model(kind)
    write_json(output, result)
    return result


def verify_model(kind: str) -> dict:
    directory = model_directory(kind)
    frozen = load_json(directory / "frozen-model.json")
    expected = load_json(CONFIG)["models"][kind]
    if frozen.get("revision") != expected["revision"] or frozen.get("repo_id") != expected["repo_id"]:
        raise ValueError("frozen_model_identity_mismatch")
    for original in frozen["files"]:
        if pin(ROOT / original["path"]) != original:
            raise ValueError("frozen_model_file_changed")
    return {"status": "PASS_LOCAL_MODEL_INTEGRITY", "kind": kind,
        "repo_id": expected["repo_id"], "revision": expected["revision"],
        "model_manifest": pin(directory / "frozen-model.json"),
        "verified_file_count": len(frozen["files"])}


def doctor() -> dict:
    config = load_json(CONFIG)
    errors = []
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        errors.append("apple_silicon_required")
    if sys.version_info[:2] != (3, 12):
        errors.append("isolated_python_3_12_required")
    versions = {}
    for name in ("mlx-audio", "mlx", "soundfile"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append("dependency_missing:" + name)
    if versions.get("mlx-audio") != config["mlx_audio_version"]:
        errors.append("mlx_audio_version_not_pinned")
    for command in ("ffmpeg", "ffprobe"):
        if shutil.which(command) is None:
            errors.append(command + "_missing")
    try:
        disk = reserve_disk()
    except ValueError as exc:
        errors.append(str(exc))
        disk = {"free_bytes": shutil.disk_usage(ROOT).free}
    return {"status": "PASS" if not errors else "BLOCKED", "provider": config["provider"],
        "python": platform.python_version(), "architecture": platform.machine(),
        "versions": versions, "disk": disk, "errors": errors,
        "paid_provider_fallback": False, "implicit_downloads": False}


def audio_metadata(path: Path) -> dict:
    path = project_path(path)
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,sample_rate,channels", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    streams = value.get("streams", [])
    if len(streams) != 1 or streams[0].get("codec_type") != "audio":
        raise ValueError("single_audio_stream_required")
    duration = float(value["format"]["duration"])
    if duration <= 0:
        raise ValueError("audio_duration_invalid")
    return {**pin(path), "duration_seconds": duration, "stream": streams[0]}


def require_copy_gate(package: Path) -> dict:
    import public_copy_guard as guard
    result = guard.check(project_path(package))
    if result["status"] != "PASS_COPY_ONLY":
        raise ValueError("current_complete_qingdou_copy_gate_not_passed")
    return result


def upstream_model(kind: str):
    health = doctor()
    if health["status"] != "PASS":
        raise ValueError("local_narration_doctor_failed")
    verify_model(kind)
    configure_local_cache(offline=True)
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    mx.set_memory_limit(6 * GIB)
    return load_model(str(model_directory(kind)))


def save_generation(results, path: Path) -> dict:
    path = project_path(path)
    if path.exists():
        raise ValueError("use_new_generation_path_no_overwrite")
    import numpy as np
    import soundfile as sf
    chunks = []
    sample_rate = None
    for result in results:
        rate = int(result.sample_rate)
        if sample_rate is not None and rate != sample_rate:
            raise ValueError("tts_sample_rate_changed_between_chunks")
        sample_rate = rate
        chunks.append(np.asarray(result.audio))
    if not chunks or not sample_rate:
        raise ValueError("tts_returned_no_audio")
    waveform = np.concatenate(chunks).reshape(-1)
    if not np.isfinite(waveform).all() or np.max(np.abs(waveform)) < 0.0001:
        raise ValueError("tts_invalid_or_silent_waveform")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), waveform, sample_rate, subtype="PCM_24")
    return audio_metadata(path)


def design(request_path: Path) -> dict:
    request = load_json(request_path)
    copy_gate = require_copy_gate(ROOT / request["publish_package_path"])
    package = load_json(ROOT / request["publish_package_path"])
    text_path = project_path(Path(ROOT / request["publish_package_path"]).parent / package["spoken_copy_path"])
    text = text_path.read_text(encoding="utf-8").strip()
    if request.get("spoken_text_sha256") != pin(text_path)["sha256"]:
        raise ValueError("audition_text_hash_mismatch")
    voices = request.get("voices", [])
    if not voices or len({v["id"] for v in voices}) != len(voices):
        raise ValueError("audition_voice_ids_must_be_unique")
    outputs_to_check = [project_path(ROOT / voice["output_path"]) for voice in voices]
    if len(set(outputs_to_check)) != len(outputs_to_check) or any(path.exists() or path.with_suffix(".json").exists() for path in outputs_to_check):
        raise ValueError("generation_already_exists_read_before_retry")
    model = upstream_model("design")
    import mlx.core as mx
    outputs = []
    for voice in request["voices"]:
        path = project_path(ROOT / voice["output_path"])
        if path.exists():
            raise ValueError("generation_already_exists_read_before_retry")
        print("GENERATING " + voice["id"], flush=True)
        mx.random.seed(int(voice["seed"]))
        result = model.generate_voice_design(text=text, language="Chinese",
            instruct=voice["description"], max_tokens=4096, temperature=0.7)
        metadata = save_generation(result, path)
        record = {"id": voice["id"], "name": voice["name"], "design_instruction": voice["description"],
            "seed": voice["seed"], "reference_text": text, "reference_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "audio": metadata, "provider": "qwen3-tts-mlx", "mlx_audio_version": "0.5.9",
            "model": load_json(CONFIG)["models"]["design"], "owner_selected": False,
            "subjective_voice_quality": "AWAITING_LISTENING_AND_OWNER_SELECTION",
            "copy_gate_public_text_sha256": copy_gate["public_text_sha256"]}
        write_json(path.with_suffix(".json"), record)
        outputs.append(record)
        print(json.dumps({"voice": voice["id"], "duration": metadata["duration_seconds"], "sha256": metadata["sha256"]}), flush=True)
        mx.clear_cache()
    return {"status": "GENERATED_PENDING_OWNER_SELECTION", "voices": outputs,
        "active_voice_profile_id": None, "not_a_full_video": True}


def active_profile() -> dict:
    registry = load_json(PROFILES)
    selected = registry.get("active_voice_profile_id")
    if not selected or registry.get("status") != "OWNER_SELECTED_FIXED_VOICE":
        raise ValueError("VOICE_SELECTION_REQUIRED_NO_DEFAULT_FALLBACK")
    matches = [v for v in registry["profiles"] if v.get("id") == selected]
    if len(matches) != 1 or not matches[0].get("owner_authorization_evidence"):
        raise ValueError("selected_voice_profile_or_authorization_missing")
    profile = matches[0]
    if pin(ROOT / profile["reference_audio"]["path"]) != profile["reference_audio"]:
        raise ValueError("selected_voice_reference_changed")
    if hashlib.sha256(profile["reference_text"].encode()).hexdigest() != profile["reference_text_sha256"]:
        raise ValueError("selected_voice_reference_text_changed")
    authority = profile["owner_authorization_evidence"]
    if not isinstance(authority, dict) or pin(ROOT / authority["path"]) != authority:
        raise ValueError("selected_voice_owner_evidence_changed")
    decision = load_json(ROOT / authority["path"])
    if decision.get("status") != "OWNER_SELECTED" or decision.get("voice_id") != selected or decision.get("source") != "current_user_message":
        raise ValueError("selected_voice_owner_evidence_invalid")
    return profile


def select_profile(reference_record: Path, authorization: Path, output: Path) -> dict:
    """Explicit owner choice only; never called by audition generation."""
    record = load_json(reference_record)
    if project_path(output).exists():
        raise ValueError("selection_receipt_exists_readback_before_retry")
    decision = load_json(authorization)
    if (decision.get("status") != "OWNER_SELECTED" or decision.get("voice_id") != record.get("id")
            or decision.get("source") != "current_user_message"
            or not decision.get("owner_message") or not decision.get("observed_at") or not decision.get("task_id")):
        raise ValueError("actual_owner_voice_selection_evidence_required")
    if pin(ROOT / record["audio"]["path"]) != {k: record["audio"][k] for k in ("path", "sha256", "bytes")}:
        raise ValueError("candidate_reference_changed")
    if hashlib.sha256(record["reference_text"].encode()).hexdigest() != record["reference_text_sha256"]:
        raise ValueError("candidate_reference_text_changed")
    if record.get("model") != load_json(CONFIG)["models"]["design"]:
        raise ValueError("candidate_model_not_pinned")
    original = PROFILES.read_bytes()
    registry = json.loads(original)
    if registry.get("active_voice_profile_id") and not decision.get("explicit_replace_active_voice"):
        raise ValueError("fixed_voice_change_needs_explicit_owner_request")
    profile = {"id": record["id"], "name": record["name"], "reference_audio": pin(ROOT / record["audio"]["path"]),
        "reference_text": record["reference_text"], "reference_text_sha256": record["reference_text_sha256"],
        "model": record["model"], "design_instruction": record["design_instruction"], "seed": record["seed"],
        "owner_authorization_evidence": pin(authorization), "candidate_record": pin(reference_record),
        "provider": "qwen3-tts-mlx", "mlx_audio_version": "0.5.9"}
    updated = {**registry, "active_voice_profile_id": profile["id"], "status": "OWNER_SELECTED_FIXED_VOICE",
        "profiles": [v for v in registry.get("profiles", []) if v.get("id") != profile["id"]] + [profile]}
    # Lock + compare-and-swap and a project-local recoverable original.
    lock = PROFILES.with_suffix(".lock")
    with lock.open("x", encoding="utf-8"):
        try:
            if PROFILES.read_bytes() != original:
                raise ValueError("voice_registry_changed_retry_readback_first")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            backup = ROOT / "backups/voice-profiles" / (stamp + ".json")
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open("xb") as handle:
                handle.write(original)
            temp = PROFILES.with_name("voice-profiles-" + stamp + ".json")
            write_json(temp, updated)
            if PROFILES.read_bytes() != original:
                raise ValueError("voice_registry_changed_retry_readback_first")
            os.replace(temp, PROFILES)
            result = {"status": "OWNER_SELECTED_FIXED_VOICE", "voice_profile_id": profile["id"],
                "registry": pin(PROFILES), "backup": pin(backup), "authorization": pin(authorization),
                "independent_voice_quality_acceptance": "PENDING"}
            write_json(output, result)
            return result
        finally:
            lock.unlink()


def probe_clone(reference_record: Path, package_path: Path, output_audio: Path) -> dict:
    """Audition-only engineering probe; does not select or replace a voice."""
    require_copy_gate(package_path)
    record = load_json(reference_record)
    package = load_json(package_path)
    text = project_path(package_path.parent / package["spoken_copy_path"]).read_text(encoding="utf-8").strip()
    if text != record["reference_text"]:
        raise ValueError("clone_probe_text_must_match_audition_batch")
    if pin(ROOT / record["audio"]["path"])["sha256"] != record["audio"]["sha256"]:
        raise ValueError("clone_probe_reference_changed")
    model = upstream_model("base")
    result = model.generate(text=text, lang_code="Chinese", ref_audio=str(ROOT / record["audio"]["path"]),
        ref_text=record["reference_text"], max_tokens=4096, temperature=0.7)
    metadata = save_generation(result, output_audio)
    return {"status": "CLONE_ENGINE_PROBE_PENDING_LISTENING", "audio": metadata,
        "reference": pin(reference_record), "active_voice_unchanged": True,
        "not_a_production_voice_selection": True}


def speech_chars(text: str) -> str:
    return "".join(c.casefold() for c in text if unicodedata.category(c)[0] in {"L", "N"})


def timeline(alignment_path: Path, lines_path: Path, output: Path) -> dict:
    alignment = load_json(alignment_path)
    request = load_json(lines_path)
    for key in ("audio", "text"):
        if pin(ROOT / alignment[key]["path"]) != alignment[key]:
            raise ValueError("alignment_source_changed")
    words = alignment["words"]
    lines = request["lines"]
    wanted = speech_chars(project_path(ROOT / alignment["text"]["path"]).read_text(encoding="utf-8"))
    if speech_chars("".join(line["text"] for line in lines)) != wanted:
        raise ValueError("timeline_lines_must_cover_frozen_spoken_text")
    chars = [(char, word["start"], word["end"]) for word in words for char in speech_chars(word["text"])]
    if "".join(c[0] for c in chars) != wanted or len({line["id"] for line in lines}) != len(lines):
        raise ValueError("alignment_text_or_line_ids_mismatch")
    offset = 0
    timings = []
    for line in lines:
        size = len(speech_chars(line["text"]))
        if not size:
            raise ValueError("timeline_line_has_no_speech")
        timings.append({"id": line["id"], "text": line["text"],
            "start": chars[offset][1], "end": chars[offset + size - 1][2]})
        offset += size
    result = {"status": "DERIVED_FROM_ACTUAL_ALIGNMENT", "alignment": pin(alignment_path),
        "audio": alignment["audio"], "text": alignment["text"], "lines": timings,
        "visual_sync_error_target_seconds": 0.3, "visual_sync_measured": False}
    write_json(output, result)
    return result


def synthesize(request_path: Path) -> dict:
    request = load_json(request_path)
    require_copy_gate(ROOT / request["publish_package_path"])
    package_path = project_path(ROOT / request["publish_package_path"])
    package = load_json(package_path)
    spoken = project_path(package_path.parent / package["spoken_copy_path"])
    lines = request.get("lines", [])
    if not lines or any(not isinstance(line.get("text"), str) or not line["text"].strip() for line in lines):
        raise ValueError("narration_lines_required")
    frozen_text = spoken.read_text(encoding="utf-8").strip()
    if "\n".join(line["text"] for line in lines).strip() != frozen_text and "".join(line["text"] for line in lines).strip() != frozen_text:
        raise ValueError("narration_lines_do_not_match_frozen_spoken_copy")
    if request.get("spoken_text_sha256") != pin(spoken)["sha256"]:
        raise ValueError("spoken_text_hash_mismatch")
    if len({line["id"] for line in lines}) != len(lines):
        raise ValueError("narration_line_ids_not_unique")
    for line in lines:
        if project_path(ROOT / line["output_path"]).exists():
            raise ValueError("generation_already_exists_read_before_retry")
    profile = active_profile()
    if request.get("voice_profile_id") != profile["id"]:
        raise ValueError("request_voice_not_owner_selected")
    model = upstream_model("base")
    outputs = []
    for line in request["lines"]:
        result = model.generate(text=line["text"], lang_code="Chinese",
            ref_audio=str(ROOT / profile["reference_audio"]["path"]), ref_text=profile["reference_text"],
            max_tokens=4096, temperature=0.7)
        metadata = save_generation(result, project_path(ROOT / line["output_path"]))
        outputs.append({"id": line["id"], "text": line["text"], "audio": metadata,
            "voice_profile_id": profile["id"], "reference_audio_sha256": profile["reference_audio"]["sha256"]})
    return {"status": "SYNTHESIZED_PENDING_ALIGNMENT_AND_QA", "voices": outputs,
        "tts_provider": "qwen3-tts-mlx", "voice_id": profile["id"]}


def assemble(generation_path: Path, output_audio: Path) -> dict:
    generation = load_json(generation_path)
    if generation.get("status") != "SYNTHESIZED_PENDING_ALIGNMENT_AND_QA" or not generation.get("voices"):
        raise ValueError("verified_fixed_voice_generation_required")
    profile = active_profile()
    if generation.get("voice_id") != profile["id"]:
        raise ValueError("assembled_voice_not_active_profile")
    import numpy as np
    import soundfile as sf
    chunks, offsets, offset, rate = [], [], 0.0, None
    for line in generation["voices"]:
        if line["reference_audio_sha256"] != profile["reference_audio"]["sha256"]:
            raise ValueError("assembled_reference_voice_changed")
        path = project_path(ROOT / line["audio"]["path"])
        if audio_metadata(path) != line["audio"]:
            raise ValueError("assembled_line_audio_changed")
        samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if rate is not None and sample_rate != rate:
            raise ValueError("assembled_sample_rate_mismatch")
        rate = sample_rate
        end = offset + len(samples) / rate
        offsets.append({"id": line["id"], "text": line["text"], "start": offset, "end": end})
        chunks.append(samples)
        offset = end
    output_audio = project_path(output_audio)
    if output_audio.exists():
        raise ValueError("assembled_output_exists")
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_audio), np.concatenate(chunks), rate, subtype="PCM_24")
    return {"status": "ASSEMBLED_REQUIRES_ACTUAL_ALIGNMENT", "audio": audio_metadata(output_audio),
        "source_generation": pin(generation_path), "voice_profile_id": profile["id"],
        "lines": offsets, "no_speed_pitch_change": True, "not_a_substitute_for_forced_alignment": True}


def align(audio: Path, text_path: Path, output: Path) -> dict:
    if doctor()["status"] != "PASS":
        raise ValueError("local_narration_doctor_failed")
    verify_model("align")
    configure_local_cache(offline=True)
    from mlx_audio.stt import load
    model = load(str(model_directory("align")))
    text = project_path(text_path).read_text(encoding="utf-8").strip()
    audio = project_path(audio)
    result = model.generate(audio=str(audio), text=text, language="Chinese")
    items = getattr(result, "items", result)
    if callable(items):
        raise ValueError("unexpected_aligner_output")
    words = [{"id": "w" + str(i), "text": item.text, "start": float(item.start_time), "end": float(item.end_time)}
        for i, item in enumerate(items)]
    previous = 0.0
    duration = audio_metadata(audio)["duration_seconds"]
    for word in words:
        if not 0 <= word["start"] <= word["end"] <= duration + 0.05 or word["start"] < previous - 0.01:
            raise ValueError("alignment_time_invalid")
        previous = word["end"]
    if not words:
        raise ValueError("alignment_empty")
    report = {"status": "ALIGNED_REQUIRES_SPOKEN_CONTENT_LISTENING", "audio": pin(audio),
        "text": pin(text_path), "language": "zh-CN", "words": words,
        "force_alignment_is_not_proof_of_correct_pronunciation": True}
    write_json(output, report)
    return report


def loudness(path: Path, duration: float | None = None) -> dict:
    command = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(project_path(path))]
    if duration is not None:
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("loudness_duration_invalid")
        command.extend(["-t", str(duration)])
    command.extend(["-af", "loudnorm=I=-16:TP=-1:LRA=7:print_format=json", "-f", "null", "-"])
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    match = re.search(r'\{\s*"input_i".*?\}', result.stderr, re.S)
    if not match:
        raise ValueError("loudness_measurement_missing")
    return json.loads(match.group(0))


def normalize(voice: Path, output: Path) -> dict:
    output = project_path(output)
    if output.exists():
        raise ValueError("normalized_output_exists")
    measured = loudness(voice)
    filt = "loudnorm=I=-16:TP=-1.5:LRA=7:linear=true:" + ":".join(
        f"{dst}={measured[src]}" for src, dst in (("input_i", "measured_I"), ("input_tp", "measured_TP"),
        ("input_lra", "measured_LRA"), ("input_thresh", "measured_thresh"), ("target_offset", "offset")))
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(project_path(voice)),
        "-af", filt, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(output)], check=True)
    return {"audio": audio_metadata(output), "loudness": loudness(output), "processing": "two_pass_loudness_no_pitch_or_speed_change"}


def mix(voice: Path, music: Path, output: Path, *,
        music_below_voice_db: float = 12.0, ducking_ratio: float = 1.6) -> dict:
    if (not math.isfinite(music_below_voice_db) or not 6 <= music_below_voice_db <= 30
            or not math.isfinite(ducking_ratio) or not 1 <= ducking_ratio <= 6):
        raise ValueError("narration_mix_parameters_invalid")
    voice, music, output = project_path(voice), project_path(music), project_path(output)
    if output.exists():
        raise ValueError("mixed_output_exists")
    duration = audio_metadata(voice)["duration_seconds"]
    if audio_metadata(music)["duration_seconds"] < duration:
        raise ValueError("music_too_short_no_looping")
    voice_lufs = float(loudness(voice)["input_i"])
    # Measure the selected excerpt, not the unused louder or quieter remainder.
    music_lufs = float(loudness(music, duration)["input_i"])
    gain = voice_lufs - music_below_voice_db - music_lufs
    filt = (f"[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume={gain}dB,"
        f"afade=t=in:d=0.4,afade=t=out:st={max(0,duration-0.6)}:d=0.6[b];"
        f"[0:a]asplit[v][sc];[b][sc]sidechaincompress=threshold=0.08:ratio={ducking_ratio}:attack=35:release=300:makeup=1[d];"
        "[v][d]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.891251:level=false[out]")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(voice), "-i", str(music),
        "-filter_complex", filt, "-map", "[out]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(output)], check=True)
    measured = loudness(output)
    passed = abs(float(measured["input_i"]) + 16) <= 1.0 and float(measured["input_tp"]) <= -1.0
    return {"status": "PASS_TECHNICAL_PENDING_LISTENING" if passed else "HOLD_AUDIO_LEVELS",
        "voice": pin(voice), "music": pin(music), "mixed_audio": audio_metadata(output),
        "loudness": measured, "initial_music_below_voice_db": music_below_voice_db,
        "music_excerpt_seconds": duration, "voice_input_lufs": voice_lufs,
        "music_excerpt_input_lufs": music_lufs, "music_gain_db": gain,
        "ducking": {"ratio": ducking_ratio, "threshold": 0.08, "attack_ms": 35, "release_ms": 300}, "music_looped": False,
        "complete_human_listening": "NOT_PERFORMED_BY_THIS_COMMAND"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--output", type=project_path)
    fetch = sub.add_parser("fetch-model")
    fetch.add_argument("--kind", choices=("design", "base", "align"), required=True)
    fetch.add_argument("--output", type=project_path, required=True)
    for command in ("design", "synthesize"):
        item = sub.add_parser(command)
        item.add_argument("--request", type=project_path, required=True)
        item.add_argument("--output", type=project_path, required=True)
    item = sub.add_parser("select")
    item.add_argument("--reference-record", type=project_path, required=True)
    item.add_argument("--authorization-evidence", type=project_path, required=True)
    item.add_argument("--output", type=project_path, required=True)
    item = sub.add_parser("probe-clone")
    item.add_argument("--reference-record", type=project_path, required=True)
    item.add_argument("--package", type=project_path, required=True)
    item.add_argument("--output-audio", type=project_path, required=True)
    item.add_argument("--output", type=project_path, required=True)
    item = sub.add_parser("timeline")
    item.add_argument("--alignment", type=project_path, required=True)
    item.add_argument("--lines", type=project_path, required=True)
    item.add_argument("--output", type=project_path, required=True)
    item = sub.add_parser("assemble")
    item.add_argument("--generation", type=project_path, required=True)
    item.add_argument("--output-audio", type=project_path, required=True)
    item.add_argument("--output", type=project_path, required=True)
    item = sub.add_parser("align")
    item.add_argument("--audio", type=project_path, required=True)
    item.add_argument("--text", type=project_path, required=True)
    item.add_argument("--output", type=project_path, required=True)
    for command in ("normalize", "mix"):
        item = sub.add_parser(command)
        item.add_argument("--voice", type=project_path, required=True)
        item.add_argument("--output-audio", type=project_path, required=True)
        item.add_argument("--output", type=project_path, required=True)
        if command == "mix":
            item.add_argument("--music", type=project_path, required=True)
            item.add_argument("--music-below-voice-db", type=float, default=12.0)
            item.add_argument("--ducking-ratio", type=float, default=1.6)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "fetch-model":
            result = fetch_model(args.kind, args.output)
        elif args.command in {"design", "synthesize"}:
            result = (design if args.command == "design" else synthesize)(args.request)
        elif args.command == "align":
            result = align(args.audio, args.text, args.output)
        elif args.command == "timeline":
            result = timeline(args.alignment, args.lines, args.output)
        elif args.command == "select":
            result = select_profile(args.reference_record, args.authorization_evidence, args.output)
        elif args.command == "probe-clone":
            result = probe_clone(args.reference_record, args.package, args.output_audio)
        elif args.command == "assemble":
            result = assemble(args.generation, args.output_audio)
        elif args.command == "normalize":
            result = normalize(args.voice, args.output_audio)
        else:
            result = mix(args.voice, args.music, args.output_audio,
                         music_below_voice_db=args.music_below_voice_db, ducking_ratio=args.ducking_ratio)
        if args.command not in {"fetch-model", "align", "timeline", "select"} and getattr(args, "output", None):
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 4 if result.get("status") in {"BLOCKED", "HOLD_AUDIO_LEVELS"} else 0
    except Exception as exc:
        # Never emit network exception bodies/signed redirect URLs/credential state.
        reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[A-Za-z0-9_:.-]+", str(exc)) else type(exc).__name__
        print(json.dumps({"status": "BLOCKED", "reason": reason, "command": args.command,
            "paid_provider_fallback": False, "raw_network_error_saved": False}))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
