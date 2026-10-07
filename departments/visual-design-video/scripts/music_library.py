#!/usr/bin/env python3
"""Audit, analyze and recommend tracks from the visual department music library."""

from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
from typing import Any


DEPARTMENT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = DEPARTMENT_ROOT / "assets" / "music" / "music-catalog.json"


def load_catalog(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("tracks"), list):
        raise ValueError(f"Invalid music catalog: {path}")
    return data


def library_dir(catalog_path: Path) -> Path:
    return catalog_path.resolve().parent


def track_path(track: dict[str, Any], catalog_path: Path) -> Path:
    return library_dir(catalog_path) / str(track["file"])


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise RuntimeError(f"Required binary not found: {name}")
    return binary


def probe(path: Path) -> dict[str, Any]:
    command = [
        require_binary("ffprobe"),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def duration_from_probe(data: dict[str, Any]) -> float:
    raw = data.get("format", {}).get("duration")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def find_track(catalog: dict[str, Any], value: str) -> dict[str, Any]:
    for track in catalog["tracks"]:
        if value in {track.get("id"), track.get("file"), track.get("aweme_id")}:
            return track
    raise KeyError(f"Unknown track: {value}")


def verify_track(track: dict[str, Any], catalog_path: Path) -> dict[str, Any]:
    path = track_path(track, catalog_path)
    errors: list[str] = []
    result: dict[str, Any] = {
        "id": track.get("id"),
        "path": str(path),
        "authorization_status": track.get("authorization_status", "unknown"),
    }
    if not path.is_file():
        errors.append("file_missing")
        result.update({"status": "FAIL", "errors": errors})
        return result

    actual_size = path.stat().st_size
    actual_hash = file_sha256(path)
    if actual_size != int(track.get("size_bytes", -1)):
        errors.append("size_mismatch")
    if actual_hash != track.get("sha256"):
        errors.append("sha256_mismatch")

    try:
        media = probe(path)
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        errors.append(f"ffprobe_failed:{exc}")
        media = {}
    actual_duration = duration_from_probe(media)
    expected_duration = float(track.get("duration_seconds", 0.0))
    if actual_duration <= 0:
        errors.append("audio_duration_missing")
    elif abs(actual_duration - expected_duration) > 0.08:
        errors.append("duration_mismatch")
    audio_streams = [s for s in media.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        errors.append("audio_stream_missing")

    result.update(
        {
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "size_bytes": actual_size,
            "sha256": actual_hash,
            "duration_seconds": round(actual_duration, 6),
            "audio_codec": audio_streams[0].get("codec_name") if audio_streams else None,
        }
    )
    return result


def decode_mono(path: Path, sample_rate: int = 22050) -> array:
    command = [
        require_binary("ffmpeg"),
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    samples = array("f")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise RuntimeError(f"Could not decode audio: {path}")
    return samples


def rms_envelope(samples: array, sample_rate: int = 22050) -> tuple[list[float], float]:
    hop = max(1, int(sample_rate * 0.05))
    window = max(1, int(sample_rate * 0.12))
    values: list[float] = []
    for start in range(0, max(1, len(samples) - window + 1), hop):
        chunk = samples[start : start + window]
        if not chunk:
            continue
        values.append(math.sqrt(sum(value * value for value in chunk) / len(chunk)))
    if not values:
        raise RuntimeError("Audio envelope is empty")
    smoothed: list[float] = []
    radius = 3
    for index in range(len(values)):
        window_values = values[max(0, index - radius) : min(len(values), index + radius + 1)]
        smoothed.append(sum(window_values) / len(window_values))
    return smoothed, hop / sample_rate


def estimate_bpm(envelope: list[float], step_seconds: float) -> int:
    onset = [0.0]
    onset.extend(max(0.0, envelope[i] - envelope[i - 1]) for i in range(1, len(envelope)))
    mean = sum(onset) / len(onset)
    centered = [value - mean for value in onset]
    best_bpm = 96
    best_score = float("-inf")
    for bpm in range(72, 181):
        lag = int(round((60.0 / bpm) / step_seconds))
        if lag < 2 or lag >= len(centered) // 2:
            continue
        score = sum(centered[i] * centered[i + lag] for i in range(len(centered) - lag))
        if score > best_score:
            best_score = score
            best_bpm = bpm
    return best_bpm


def peak_times(envelope: list[float], step_seconds: float, limit: int = 5) -> list[float]:
    candidates = sorted(range(len(envelope)), key=lambda index: envelope[index], reverse=True)
    selected: list[float] = []
    for index in candidates:
        time_value = index * step_seconds
        if all(abs(time_value - existing) >= 0.8 for existing in selected):
            selected.append(round(time_value, 2))
        if len(selected) == limit:
            break
    return sorted(selected)


def energy_sections(envelope: list[float], step_seconds: float, duration: float) -> list[dict[str, Any]]:
    section_count = max(3, min(8, int(round(duration / 3.0))))
    section_length = duration / section_count
    overall = max(sum(envelope) / len(envelope), 1e-8)
    sections: list[dict[str, Any]] = []
    for index in range(section_count):
        start = index * section_length
        end = duration if index == section_count - 1 else (index + 1) * section_length
        values = [
            envelope[position]
            for position in range(len(envelope))
            if start <= position * step_seconds < end
        ]
        ratio = (sum(values) / len(values) / overall) if values else 0.0
        level = "high" if ratio >= 1.14 else "low" if ratio <= 0.86 else "mid"
        sections.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "relative_energy": round(ratio, 3),
                "level": level,
            }
        )
    return sections


def analyze_track(track: dict[str, Any], catalog_path: Path) -> dict[str, Any]:
    path = track_path(track, catalog_path)
    media = probe(path)
    duration = duration_from_probe(media)
    samples = decode_mono(path)
    envelope, step = rms_envelope(samples)
    climax_index = max(range(len(envelope)), key=lambda index: envelope[index])
    bpm = estimate_bpm(envelope, step)
    return {
        "schema_version": "1.0",
        "track_id": track["id"],
        "file": str(path),
        "duration_seconds": round(duration, 6),
        "bpm_estimate": bpm,
        "seconds_per_beat_estimate": round(60.0 / bpm, 4),
        "climax_seconds": round(min(duration, climax_index * step), 2),
        "peak_times_seconds": peak_times(envelope, step),
        "energy_sections": energy_sections(envelope, step, duration),
        "tags": track.get("tags", []),
        "authorization_status": track.get("authorization_status", "unknown"),
        "usage_scope": track.get("usage_scope"),
        "analysis_method": "ffmpeg mono decode + RMS envelope + onset autocorrelation estimate",
        "manual_review_required": True,
        "manual_review_fields": [
            "intro_character",
            "first_clear_downbeat",
            "phrase_changes",
            "mood_and_space_fit",
            "fade_or_clean_end",
        ],
        "music_state": {
            "selected": True,
            "mounted": False,
            "audible": False,
            "rights_cleared": False,
            "rights_evaluation": "requires_requested_scope_and_target_channel",
        },
    }


def tags_from_args(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tags.extend(item.strip() for item in value.split(",") if item.strip())
    return tags


def load_usage_history(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Music usage history not found: {source}")

    if source.suffix.lower() == ".jsonl":
        raw_events = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            raw_events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            raw_events = payload["events"]
        else:
            raise ValueError("History JSON must be a list or an object with events[].")

    mounted_events: list[dict[str, Any]] = []
    for index, event in enumerate(raw_events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"History event {index} must be an object.")
        track_id = str(event.get("track_id", "")).strip()
        if not track_id:
            raise ValueError(f"History event {index} is missing track_id.")
        mounted = event.get("mounted")
        if isinstance(mounted, dict):
            mounted = mounted.get("status")
        mounted_confirmed = mounted is True or event.get("event") == "mounted" or event.get("status") == "mounted"
        if not mounted_confirmed:
            continue
        mounted_events.append(
            {
                "track_id": track_id,
                "task_id": event.get("task_id"),
                "used_at": event.get("used_at"),
                "evidence": event.get("evidence"),
            }
        )
    return mounted_events


def unique_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def query_groups(
    tags: list[str],
    video_types: list[str],
    styles: list[str],
    moods: list[str],
) -> dict[str, list[str]]:
    return {
        "video_type": unique_values(tags_from_args(video_types)),
        "style": unique_values(tags_from_args(styles)),
        "mood": unique_values(tags_from_args(moods)),
        "tag": unique_values(tags),
    }


def tag_similarity(query: str, candidate: str) -> float:
    if query == candidate:
        return 1.0
    if query in candidate or candidate in query:
        return 0.8
    return 0.0


def score_query_group(queries: list[str], track_tags: list[str], weight: float) -> tuple[float, list[str]]:
    score = 0.0
    matches: list[str] = []
    for query in queries:
        similarities = [(tag_similarity(query, candidate), candidate) for candidate in track_tags]
        best_similarity, best_candidate = max(similarities, default=(0.0, ""))
        if best_similarity > 0:
            score += weight * best_similarity
            matches.append(f"{query}->{best_candidate}")
    return score, matches


def duration_fit_score(track_duration: float, requested_duration: float) -> tuple[float, str]:
    if requested_duration <= 0:
        return 0.0, "未指定目标时长"
    if track_duration >= requested_duration:
        overage_ratio = (track_duration - requested_duration) / max(requested_duration, 1.0)
        score = max(1.0, 3.0 - min(2.0, overage_ratio * 0.5))
        return score, "时长可覆盖项目"
    shortage_ratio = (requested_duration - track_duration) / max(requested_duration, 1.0)
    return -min(5.0, shortage_ratio * 5.0), "短于项目时长，需缩短画面或另选音乐"


def ranked_music_candidates(
    catalog: dict[str, Any],
    duration: float,
    groups: dict[str, list[str]],
    scope: str,
    channel: str | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    group_weights = {"video_type": 3.5, "style": 3.0, "mood": 2.5, "tag": 2.0}
    for track in catalog["tracks"]:
        eligible = scope_eligible(track, scope, channel)
        if not eligible:
            continue
        track_tags = unique_values([str(tag) for tag in track.get("tags", [])])
        track_duration = float(track.get("duration_seconds", 0.0))
        duration_score, duration_reason = duration_fit_score(track_duration, duration)
        score_components: dict[str, float] = {"duration": round(duration_score, 6)}
        reasons = [duration_reason]
        total_score = duration_score
        for group_name, queries in groups.items():
            group_score, matches = score_query_group(queries, track_tags, group_weights[group_name])
            score_components[group_name] = round(group_score, 6)
            total_score += group_score
            if matches:
                reasons.append(f"{group_name}匹配：{','.join(matches)}")
        if not any(groups.values()):
            reasons.append("未指定装修类型、风格或情绪标签")
        candidates.append(
            {
                "id": track["id"],
                "file": track["file"],
                "score": round(total_score, 6),
                "score_components": score_components,
                "duration_seconds": track_duration,
                "tags": track.get("tags", []),
                "authorization_status": track.get("authorization_status", "unknown"),
                "usage_scopes": sorted(normalized_usage_scopes(track)),
                "allowed_channels": track.get("allowed_channels", []),
                "eligible_for_requested_scope": eligible,
                "eligible_for_external_render": external_render_eligible(track),
                "reason": "；".join(reasons),
            }
        )
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["id"])))
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates


def recent_usage(history: list[dict[str, Any]], recent_window: int) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    last_used = history[-1]["track_id"] if history else None
    recent_events = history[-max(0, recent_window) :] if recent_window > 0 else []
    recent_ids: list[str] = []
    for event in reversed(recent_events):
        track_id = str(event["track_id"])
        if track_id not in recent_ids:
            recent_ids.append(track_id)
    if last_used and last_used not in recent_ids:
        recent_ids.insert(0, last_used)
    return last_used, recent_ids, recent_events


EXTERNAL_SCOPES = {"external_final", "cross_platform_final", "paid_ad", "public_delivery"}


def normalized_usage_scopes(track: dict[str, Any]) -> set[str]:
    raw = track.get("allowed_scopes", track.get("usage_scope", []))
    if isinstance(raw, str):
        legacy = {
            "internal_reference_or_same_platform_candidate": {
                "internal_reference",
                "same_platform_candidate",
            },
            "internal_reference_only": {"internal_reference"},
        }
        return legacy.get(raw, {raw})
    if isinstance(raw, list):
        return {str(value) for value in raw if value}
    return set()


def scope_eligible(track: dict[str, Any], scope: str, channel: str | None) -> bool:
    scopes = normalized_usage_scopes(track)
    if scope == "internal_reference":
        # Daily scouting writes editing_reference; both labels cover local editing.
        return bool(scopes & {"internal_reference", "editing_reference"})
    if scope == "same_platform_candidate":
        return "same_platform_candidate" in scopes
    if scope not in EXTERNAL_SCOPES:
        return False
    if track.get("authorization_status") != "cleared" or scope not in scopes or not channel:
        return False
    allowed_channels = track.get("allowed_channels", [])
    if not isinstance(allowed_channels, list):
        return False
    normalized_channels = {str(value).lower() for value in allowed_channels}
    return "*" in normalized_channels or channel.lower() in normalized_channels


def external_render_eligible(track: dict[str, Any]) -> bool:
    if track.get("authorization_status") != "cleared":
        return False
    scopes = normalized_usage_scopes(track)
    allowed_channels = track.get("allowed_channels", [])
    return bool(scopes & EXTERNAL_SCOPES) and isinstance(allowed_channels, list) and bool(allowed_channels)


def recommend_tracks(
    catalog: dict[str, Any],
    duration: float,
    tags: list[str],
    scope: str,
    limit: int,
    channel: str | None = None,
    video_types: list[str] | None = None,
    styles: list[str] | None = None,
    moods: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
    history_path: str | None = None,
    recent_window: int = 3,
    seed: int | None = None,
) -> dict[str, Any]:
    groups = query_groups(tags, video_types or [], styles or [], moods or [])
    candidates = ranked_music_candidates(catalog, duration, groups, scope, channel)
    history = history or []
    recent_window = max(0, recent_window)
    last_used, recent_ids, recent_events = recent_usage(history, recent_window)
    recent_set = set(recent_ids)
    filtered_candidates = [candidate for candidate in candidates if candidate["id"] not in recent_set]
    fallback_status = "not_needed"
    pool_source = "ranked_after_recent_exclusion"
    if candidates and not filtered_candidates:
        filtered_candidates = [candidate for candidate in candidates if candidate["id"] != last_used]
        if filtered_candidates:
            fallback_status = "recent_window_relaxed_last_used_still_excluded"
            pool_source = "ranked_after_relaxing_older_recent_tracks"
        else:
            fallback_status = "blocked_only_last_used_candidate"
            pool_source = "none"

    recently_excluded = [
        {
            "id": candidate["id"],
            "rank": candidate["rank"],
            "reason": "last_used" if candidate["id"] == last_used else "within_recent_window",
        }
        for candidate in candidates
        if candidate["id"] in recent_set
    ]
    top_pool_candidates = filtered_candidates[:3]
    top_pool: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    if top_pool_candidates:
        minimum_score = min(float(candidate["score"]) for candidate in top_pool_candidates)
        weights = [max(0.1, float(candidate["score"]) - minimum_score + 1.0) for candidate in top_pool_candidates]
        weight_total = sum(weights)
        for candidate, weight in zip(top_pool_candidates, weights):
            top_pool.append(
                {
                    **candidate,
                    "weight": round(weight, 6),
                    "selection_probability": round(weight / weight_total, 6),
                }
            )
        rng: random.Random = random.Random(seed) if seed is not None else random.SystemRandom()
        selected_index = rng.choices(range(len(top_pool)), weights=weights, k=1)[0]
        selected = dict(top_pool[selected_index])

    if not candidates:
        fallback_status = "no_eligible_candidates"
    selection_status = "recommended_not_mounted" if selected else "blocked_no_eligible_track"
    if fallback_status == "blocked_only_last_used_candidate":
        selection_status = "blocked_no_non_repeating_candidate"
    random_source = "seeded_mt19937" if seed is not None else "system_random"
    rationale = (
        f"从适配度排序后排除最近 {recent_window} 次使用，只在最高 {len(top_pool)} 名中按正权重随机；"
        f"选中适配度第 {selected['rank']} 名。"
        if selected
        else "没有满足授权范围且不会连续复用 last_used 的候选。"
    )
    return {
        "schema_version": "2.0",
        "scope": scope,
        "target_channel": channel,
        "requested_duration_seconds": duration,
        "requested_tags": tags,
        "requested_context": groups,
        "selection_strategy": "suitability_rank_then_recent_exclusion_then_top3_weighted_random",
        "selection_status": selection_status,
        "selected": selected,
        "ranked_candidates": candidates,
        "recently_excluded": recently_excluded,
        "top_pool": top_pool,
        "weights": [{"id": item["id"], "weight": item["weight"]} for item in top_pool],
        "random_source": random_source,
        "seed": seed,
        "fallback": {
            "status": fallback_status,
            "pool_source": pool_source,
            "last_used": last_used,
            "recent_window": recent_window,
        },
        "history": {
            "path": history_path,
            "read_only": True,
            "mounted_event_count": len(history),
            "recent_events_considered": recent_events,
        },
        "selection_rationale": rationale,
        "candidates": candidates[:limit],
        "music_state": {
            "selected": bool(selected),
            "mounted": False,
            "audible": False,
            "rights_cleared": bool(
                selected
                and scope in EXTERNAL_SCOPES
                and selected["eligible_for_requested_scope"]
            ),
        },
        "warning": (
            "当前库没有同时满足授权状态、目标用途和目标渠道，且不连续复用 last_used 的音乐；请补权利证据、扩充音乐库或在目标平台内选歌。"
            if not selected
            else "推荐结果不等于已挂载、可听或已获发布授权。"
        ),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="列出音乐及授权状态。")
    subparsers.add_parser("verify", help="核验文件、哈希、时长和音频流。")

    analyze = subparsers.add_parser("analyze", help="生成音乐结构估算和 music-map.json。")
    analyze.add_argument("--track", required=True, help="曲目 ID、aweme ID 或文件名。")
    analyze.add_argument("--output", type=Path, help="可选 JSON 输出路径。")

    recommend = subparsers.add_parser("recommend", help="按时长、标签和授权范围推荐音乐。")
    recommend.add_argument("--duration", type=float, default=0.0)
    recommend.add_argument("--tag", action="append", default=[], help="可重复或逗号分隔。")
    recommend.add_argument("--video-type", action="append", default=[], help="装修视频类型，可重复或逗号分隔。")
    recommend.add_argument("--style", action="append", default=[], help="装修风格，可重复或逗号分隔。")
    recommend.add_argument("--mood", action="append", default=[], help="音乐情绪，可重复或逗号分隔。")
    recommend.add_argument(
        "--scope",
        choices=[
            "internal_reference",
            "same_platform_candidate",
            "external_final",
            "cross_platform_final",
            "paid_ad",
            "public_delivery",
        ],
        default="internal_reference",
    )
    recommend.add_argument("--channel", help="外部用途必填，例如 douyin、instagram、tiktok。")
    recommend.add_argument("--history", type=Path, help="只读 JSON/JSONL mounted 使用历史。")
    recommend.add_argument("--recent-window", type=int, default=3, help="排除最近 mounted 事件数，默认 3。")
    recommend.add_argument("--seed", type=int, help="固定随机种子，供测试和复盘复现。")
    recommend.add_argument("--limit", type=int, default=5)
    recommend.add_argument("--output", type=Path, help="可选 JSON 输出路径。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog_path = args.catalog.expanduser().resolve()
    catalog = load_catalog(catalog_path)

    if args.command == "list":
        for track in catalog["tracks"]:
            print(
                "\t".join(
                    [
                        str(track["id"]),
                        f"{float(track['duration_seconds']):.2f}s",
                        str(track.get("authorization_status", "unknown")),
                        ",".join(track.get("tags", [])),
                    ]
                )
            )
        return 0

    if args.command == "verify":
        results = [verify_track(track, catalog_path) for track in catalog["tracks"]]
        payload = {
            "status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
            "catalog": str(catalog_path),
            "track_count": len(results),
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] == "PASS" else 1

    if args.command == "analyze":
        payload = analyze_track(find_track(catalog, args.track), catalog_path)
        if args.output:
            write_json(args.output.expanduser().resolve(), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "recommend":
        history_path = args.history.expanduser().resolve() if args.history else None
        payload = recommend_tracks(
            catalog,
            max(0.0, args.duration),
            tags_from_args(args.tag),
            args.scope,
            max(1, args.limit),
            args.channel,
            tags_from_args(args.video_type),
            tags_from_args(args.style),
            tags_from_args(args.mood),
            load_usage_history(history_path),
            str(history_path) if history_path else None,
            max(0, args.recent_window),
            args.seed,
        )
        if args.output:
            write_json(args.output.expanduser().resolve(), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["selected"] else 3

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
