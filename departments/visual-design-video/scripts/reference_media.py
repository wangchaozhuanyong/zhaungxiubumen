#!/usr/bin/env python3
"""Freeze and inspect local or Douyin reference media without publishing it."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s\"'<>，。；;、]+")
VIDEO_ID_RE = re.compile(r"(?:douyin\.com/(?:video|note)/|aweme_id=)(\d{10,})")
COOKIE_SOURCE_RE = re.compile(r"^(chrome|firefox|safari)(?::[A-Za-z0-9_. -]{1,80})?$")
DOUYIN_AUDIO_CDN_HOST_RE = re.compile(r"^sf\d+-cdn-tos\.douyinstatic\.com$", re.IGNORECASE)
DOUYIN_AUDIO_CDN_PATH_RE = re.compile(r"^/obj/tos-cn-[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")
DOUYIN_AUDIO_FETCH_TIMEOUT_SECONDS = 180
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
DEFAULT_DOUYIN_ROOT = Path("<USER_HOME>/Desktop/抖音解析")
ALLOWED_DOUYIN_HOSTS = {"douyin.com", "iesdouyin.com"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def douyin_root() -> Path:
    configured = os.environ.get("FLASHCAST_DOUYIN_TOOL_ROOT")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DOUYIN_ROOT


def binary(name: str) -> str | None:
    return shutil.which(name)


def require_binary(name: str) -> str:
    value = binary(name)
    if not value:
        raise RuntimeError(f"Required binary not found: {name}")
    return value


def python_has_ytdlp(python: Path) -> bool:
    if not python.is_file():
        return False
    result = subprocess.run(
        [str(python), "-c", "import yt_dlp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def ytdlp_runner() -> list[str] | None:
    source_python = douyin_root() / ".douyin-mp3-venv" / "bin" / "python"
    if python_has_ytdlp(source_python):
        return [str(source_python), "-m", "yt_dlp"]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    executable = binary("yt-dlp")
    return [executable] if executable else None


def ytdlp_version(runner: list[str] | None) -> str | None:
    if not runner:
        return None
    result = subprocess.run(
        [*runner, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def browser_cookie_source(value: str) -> str:
    if not COOKIE_SOURCE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Use browser or browser:profile with chrome, firefox, or safari; "
            "cookie files and arbitrary paths are not accepted."
        )
    return value


def browser_family(value: str | None) -> str | None:
    return value.split(":", 1)[0] if value else None


def reference_id(urls: list[str]) -> str | None:
    for url in urls:
        match = VIDEO_ID_RE.search(url)
        if match:
            return match.group(1)
    return None


def classify_ytdlp_failure(output: str, cookies_requested: bool) -> tuple[str, list[str]]:
    normalized = output.lower()
    if "fresh cookies" in normalized or "fresh cookie" in normalized:
        if cookies_requested:
            return (
                "browser_session_not_accepted",
                [
                    "Open the exact reference in the selected browser and confirm it plays.",
                    "Retry with the same explicit browser source; if needed specify browser:profile.",
                    "If the browser session is current but rejected, update yt-dlp in the isolated Douyin environment and retry.",
                ],
            )
        return (
            "fresh_browser_session_required",
            [
                "Obtain owner approval before reading browser state.",
                "Retry explicitly with --cookies-from-browser chrome after approval.",
            ],
        )
    if any(
        marker in normalized
        for marker in (
            "could not copy chrome cookie database",
            "failed to decrypt",
            "cookie database",
            "keyring",
        )
    ):
        return (
            "browser_cookie_access_failed",
            [
                "Close competing browser processes only if the owner approves, then retry.",
                "Specify the active browser profile explicitly, for example chrome:Default.",
                "Do not export a cookie file as a workaround.",
            ],
        )
    if "unsupported url" in normalized:
        return "unsupported_source_url", ["Use a public Douyin video or note URL."]
    if any(marker in normalized for marker in ("timed out", "unable to download", "network is unreachable")):
        return "source_network_unreachable", ["Check network reachability and retry without changing account state."]
    if "no video formats found" in normalized or "requested format is not available" in normalized:
        return "source_media_unavailable", ["Confirm the reference is still playable in the selected browser."]
    return (
        "source_extractor_failed",
        [
            "Run the doctor command and confirm ffmpeg, ffprobe, and yt-dlp are available.",
            "Retry with an explicitly approved browser session if the source is playable only in-browser.",
        ],
    )


def write_diagnostic(path: Path | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_allowed_douyin_url(value: str) -> bool:
    try:
        host = (urlparse(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_DOUYIN_HOSTS)


def is_allowed_douyin_audio_url(value: str) -> bool:
    """Accept only unsigned HTTPS audio-object URLs from Douyin's CDN family."""
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and DOUYIN_AUDIO_CDN_HOST_RE.fullmatch(host) is not None
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment
            and DOUYIN_AUDIO_CDN_PATH_RE.fullmatch(parsed.path) is not None
        )
    except ValueError:
        return False


def extract_urls(value: str) -> list[str]:
    urls: list[str] = []
    for raw in URL_RE.findall(value):
        cleaned = raw.rstrip(".,，。;；!！?？)]）")
        if (is_allowed_douyin_url(cleaned) or is_allowed_douyin_audio_url(cleaned)) and cleaned not in urls:
            urls.append(cleaned)
    return urls


def fetch_douyin_audio(args: argparse.Namespace, url: str, runner: list[str]) -> int:
    if not args.extract_audio:
        print("Direct Douyin music assets require --extract-audio.", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    prepare_output_dir(output_dir, force=False)
    before = {path.resolve() for path in output_dir.iterdir() if path.is_file()}
    command = [
        *runner,
        "--ignore-config",
        "--force-ipv4",
        "--socket-timeout",
        "20",
        "--retries",
        "1",
        "--extractor-retries",
        "1",
        "--no-playlist",
        "--no-overwrites",
        "--no-progress",
        "--no-write-info-json",
        "--no-write-description",
        "--no-write-thumbnail",
        "--no-write-comments",
        "--no-write-subs",
        "--no-cache-dir",
        "--format",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--paths",
        str(output_dir),
        "--output",
        "reference-audio.%(ext)s",
    ]
    if args.cookies_from_browser:
        command.extend(["--cookies-from-browser", args.cookies_from_browser])
    command.append(url)

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False,
            timeout=DOUYIN_AUDIO_FETCH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # Exception output may contain browser material; never print or save it.
        diagnostic = {
            "schema_version": "1.0",
            "status": "BLOCKED",
            "reason_code": "source_network_unreachable",
            "failure_detail": "bounded_audio_fetch_timeout",
            "reference_kind": "douyin_music_asset",
            "browser_state_mode": "explicit_read_only" if args.cookies_from_browser else "disabled",
            "browser_family": browser_family(args.cookies_from_browser),
            "cookie_material_persisted": False,
            "timeout_seconds": DOUYIN_AUDIO_FETCH_TIMEOUT_SECONDS,
            "next_actions": [
                "Check public source reachability and the selected Chrome profile before a bounded retry.",
                "Do not export browser material or persist raw download logs.",
            ],
        }
        write_diagnostic(args.diagnostic_output, diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4
    audio_files = [
        path for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".mp3" and path.resolve() not in before
    ]
    if result.returncode != 0 or len(audio_files) != 1:
        reason_code, next_actions = classify_ytdlp_failure(
            f"{result.stdout}\n{result.stderr}", bool(args.cookies_from_browser)
        )
        if result.returncode == 0:
            reason_code = "source_media_unavailable"
            next_actions = ["Confirm the selected music asset remains publicly playable in the Douyin page."]
        diagnostic = {
            "schema_version": "1.0",
            "status": "BLOCKED",
            "reason_code": reason_code,
            "reference_kind": "douyin_music_asset",
            "browser_state_mode": "explicit_read_only" if args.cookies_from_browser else "disabled",
            "browser_family": browser_family(args.cookies_from_browser),
            "cookie_material_persisted": False,
            "yt_dlp_version": ytdlp_version(runner),
            "next_actions": next_actions,
        }
        write_diagnostic(args.diagnostic_output, diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4

    audio = audio_files[0]
    try:
        media = ffprobe(audio)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        media = {}
    streams = media.get("streams", [])
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    duration = duration_seconds(media)
    if len(audio_streams) != 1 or video_streams or duration <= 0 or audio.stat().st_size <= 0:
        diagnostic = {
            "schema_version": "1.0",
            "status": "BLOCKED",
            "reason_code": "audio_validation_failed",
            "reference_kind": "douyin_music_asset",
            "browser_state_mode": "explicit_read_only" if args.cookies_from_browser else "disabled",
            "browser_family": browser_family(args.cookies_from_browser),
            "cookie_material_persisted": False,
            "yt_dlp_version": ytdlp_version(runner),
            "next_actions": ["Keep the candidate out of the library until a single decodable audio stream is verified."],
        }
        write_diagnostic(args.diagnostic_output, diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4

    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    diagnostic = {
        "schema_version": "1.0",
        "status": "PASS",
        "reason_code": "audio_acquired",
        "reference_kind": "douyin_music_asset",
        "browser_state_mode": "explicit_read_only" if args.cookies_from_browser else "disabled",
        "browser_family": browser_family(args.cookies_from_browser),
        "cookie_material_persisted": False,
        "yt_dlp_version": ytdlp_version(runner),
        "audio_file": str(audio),
        "audio_stream_count": len(audio_streams),
        "video_stream_count": len(video_streams),
        "duration_seconds": round(duration, 6),
        "size_bytes": audio.stat().st_size,
        "sha256": digest,
        "warning": "Acquisition does not grant reuse rights or authorize publishing.",
    }
    write_diagnostic(args.diagnostic_output, diagnostic)
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    return 0


def ffprobe(path: Path) -> dict[str, Any]:
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


def duration_seconds(probe: dict[str, Any]) -> float:
    raw = probe.get("format", {}).get("duration")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def prepare_output_dir(path: Path, force: bool) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise FileExistsError(f"Output directory is not empty; use --force: {path}")
    path.mkdir(parents=True, exist_ok=True)


def create_contact_sheet(source: Path, destination: Path, duration: float, force: bool) -> None:
    interval = max(0.5, duration / 9.0) if duration > 0 else 1.0
    overwrite = "-y" if force else "-n"
    video_filter = (
        f"fps=1/{interval:.6f},"
        "scale=360:640:force_original_aspect_ratio=decrease,"
        "pad=360:640:(ow-iw)/2:(oh-ih)/2:black,"
        "tile=3x3"
    )
    command = [
        require_binary("ffmpeg"),
        overwrite,
        "-v",
        "error",
        "-i",
        str(source),
        "-vf",
        video_filter,
        "-frames:v",
        "1",
        str(destination),
    ]
    subprocess.run(command, check=True)


def extract_audio(source: Path, destination: Path, force: bool) -> None:
    overwrite = "-y" if force else "-n"
    command = [
        require_binary("ffmpeg"),
        overwrite,
        "-v",
        "error",
        "-i",
        str(source),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(destination),
    ]
    subprocess.run(command, check=True)


def analyze_media(source: Path, output_dir: Path, want_audio: bool, force: bool) -> dict[str, Any]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    prepare_output_dir(output_dir, force)

    media = ffprobe(source)
    duration = duration_seconds(media)
    video_streams = [item for item in media.get("streams", []) if item.get("codec_type") == "video"]
    audio_streams = [item for item in media.get("streams", []) if item.get("codec_type") == "audio"]
    artifacts: dict[str, str] = {}

    if video_streams:
        sheet = output_dir / "contact-sheet.jpg"
        create_contact_sheet(source, sheet, duration, force)
        artifacts["contact_sheet"] = str(sheet)
    if want_audio and audio_streams:
        audio = output_dir / "reference-audio.mp3"
        extract_audio(source, audio, force)
        artifacts["extracted_audio"] = str(audio)

    report = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "source_file": str(source),
        "source_size_bytes": source.stat().st_size,
        "duration_seconds": round(duration, 6),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "ffprobe": media,
        "artifacts": artifacts,
        "reference_status": "local_playable_body_confirmed",
        "rights_status": "unknown_until_recorded_in_task_asset_manifest",
        "manual_review_required": True,
        "manual_review_checklist": [
            "video_type_and_viewing_experience",
            "first_and_last_second",
            "camera_start_height_direction_and_spatial_path",
            "shot_duration_and_transition_structure",
            "color_light_material_and_composition",
            "text_density_none_minimal_or_copy_led",
            "music_intro_downbeat_energy_sections_climax_and_end",
            "elements_to_learn_without_copying_assets_copy_brand_or_full_sequence",
        ],
    }
    report_path = output_dir / "media-analysis.json"
    report["artifacts"]["analysis_json"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def run_doctor() -> int:
    root = douyin_root()
    runner = ytdlp_runner()
    payload = {
        "status": "PASS" if binary("ffmpeg") and binary("ffprobe") and runner else "BLOCKED",
        "ffmpeg": binary("ffmpeg"),
        "ffprobe": binary("ffprobe"),
        "douyin_tool_root": str(root),
        "source_parser": str(root / "douyin_to_mp3.py"),
        "source_parser_exists": (root / "douyin_to_mp3.py").is_file(),
        "yt_dlp_runner": runner,
        "yt_dlp_version": ytdlp_version(runner),
        "automatic_dependency_install": False,
        "cookie_mode_default": "disabled",
        "cookie_policy": "browser state is read only when --cookies-from-browser is explicitly supplied; cookie files and arbitrary paths are rejected; browser data is never copied or saved here",
        "supported_cookie_sources": ["chrome", "chrome:profile", "firefox", "firefox:profile", "safari"],
        "safe_diagnostic_supported": True,
        "publish_capability": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 2


def fetch_reference(args: argparse.Namespace) -> int:
    urls = extract_urls(args.input)
    if not urls:
        print(
            "No allowed Douyin URL found. Accepted hosts are douyin.com and its subdomains.",
            file=sys.stderr,
        )
        return 2
    runner = ytdlp_runner()
    if not runner:
        print(
            "yt-dlp is unavailable. Restore the configured Douyin parser environment or set "
            "FLASHCAST_DOUYIN_TOOL_ROOT; this tool will not install dependencies automatically.",
            file=sys.stderr,
        )
        return 2

    audio_urls = [url for url in urls if is_allowed_douyin_audio_url(url)]
    if audio_urls:
        if len(urls) != 1 or len(audio_urls) != 1:
            print("Fetch one Douyin media source at a time.", file=sys.stderr)
            return 2
        return fetch_douyin_audio(args, audio_urls[0], runner)

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_dir.iterdir() if path.is_file()}
    command = [
        *runner,
        "--no-playlist",
        "--no-overwrites",
        "--no-progress",
        "--merge-output-format",
        "mp4",
        "--format",
        "bv*+ba/b",
        "--paths",
        str(output_dir),
        "--output",
        "%(title).120s [%(id)s].%(ext)s",
    ]
    if args.cookies_from_browser:
        command.extend(["--cookies-from-browser", args.cookies_from_browser])
    command.extend(urls)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        reason_code, next_actions = classify_ytdlp_failure(
            f"{result.stdout}\n{result.stderr}",
            bool(args.cookies_from_browser),
        )
        diagnostic = {
            "schema_version": "1.0",
            "status": "BLOCKED",
            "reason_code": reason_code,
            "reference_id": reference_id(urls),
            "browser_state_mode": (
                "explicit_read_only" if args.cookies_from_browser else "disabled"
            ),
            "browser_family": browser_family(args.cookies_from_browser),
            "cookie_material_persisted": False,
            "yt_dlp_version": ytdlp_version(runner),
            "next_actions": next_actions,
        }
        write_diagnostic(args.diagnostic_output, diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4

    videos = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and path.resolve() not in before
    ]
    if not videos:
        videos = [path for path in output_dir.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        print("Download finished but no playable video body was found.", file=sys.stderr)
        return 3

    reports = []
    for video in sorted(videos):
        analysis_dir = output_dir / "analysis" / video.stem
        reports.append(analyze_media(video, analysis_dir, args.extract_audio, args.force_analysis))
    diagnostic = {
        "schema_version": "1.0",
        "status": "PASS",
        "reason_code": "reference_acquired",
        "reference_id": reference_id(urls),
        "browser_state_mode": "explicit_read_only" if args.cookies_from_browser else "disabled",
        "browser_family": browser_family(args.cookies_from_browser),
        "cookie_material_persisted": False,
        "yt_dlp_version": ytdlp_version(runner),
        "downloaded_or_reused_videos": [str(path) for path in videos],
        "reports": reports,
        "warning": "Reference acquisition does not grant reuse rights and does not authorize publishing.",
    }
    write_diagnostic(args.diagnostic_output, diagnostic)
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="检查 ffmpeg、ffprobe 和抖音解析运行环境。")

    analyze = subparsers.add_parser("analyze", help="分析本地可播放参考素材。")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--output-dir", type=Path, required=True)
    analyze.add_argument("--extract-audio", action="store_true")
    analyze.add_argument("--force", action="store_true")

    fetch = subparsers.add_parser("fetch", help="从抖音分享文案或 URL 冻结参考视频并生成分析证据。")
    fetch.add_argument("input", help="抖音 URL 或包含 URL 的整段分享文案。")
    fetch.add_argument("--output-dir", type=Path, required=True)
    fetch.add_argument("--extract-audio", action="store_true")
    fetch.add_argument(
        "--cookies-from-browser",
        type=browser_cookie_source,
        help="显式只读浏览器会话，例如 chrome 或 chrome:Default；默认禁用，不接受 Cookie 文件路径。",
    )
    fetch.add_argument(
        "--diagnostic-output",
        type=Path,
        help="可选：写入不含 Cookie/Token 和原始下载日志的安全诊断 JSON。",
    )
    fetch.add_argument("--force-analysis", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return run_doctor()
    if args.command == "analyze":
        report = analyze_media(
            args.input,
            args.output_dir.expanduser().resolve(),
            args.extract_audio,
            args.force,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "fetch":
        return fetch_reference(args)
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
