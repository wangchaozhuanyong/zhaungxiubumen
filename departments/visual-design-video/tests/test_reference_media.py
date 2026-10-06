from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reference_media.py"
SPEC = importlib.util.spec_from_file_location("reference_media", SCRIPT)
assert SPEC and SPEC.loader
reference_media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference_media)


class ReferenceMediaCookieFlowTests(unittest.TestCase):
    def test_cookie_access_is_disabled_by_default(self) -> None:
        args = reference_media.build_parser().parse_args(
            ["fetch", "https://www.douyin.com/video/7524350211596193082", "--output-dir", "/tmp/out"]
        )
        self.assertIsNone(args.cookies_from_browser)

    def test_explicit_chrome_source_is_accepted(self) -> None:
        args = reference_media.build_parser().parse_args(
            [
                "fetch",
                "https://www.douyin.com/video/7524350211596193082",
                "--output-dir",
                "/tmp/out",
                "--cookies-from-browser",
                "chrome:Default",
            ]
        )
        self.assertEqual(args.cookies_from_browser, "chrome:Default")

    def test_cookie_file_path_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            reference_media.build_parser().parse_args(
                [
                    "fetch",
                    "https://www.douyin.com/video/7524350211596193082",
                    "--output-dir",
                    "/tmp/out",
                    "--cookies-from-browser",
                    "/tmp/cookies.txt",
                ]
            )

    def test_unsigned_douyin_music_cdn_asset_is_allowed(self) -> None:
        url = "https://sf11-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/ooYIWIarPDgQ5x0xAaoBAW9TGQlAiiaUMLBA8"
        self.assertTrue(reference_media.is_allowed_douyin_audio_url(url))
        self.assertEqual(reference_media.extract_urls(url), [url])

    def test_signed_or_unrelated_cdn_audio_urls_are_rejected(self) -> None:
        base = "https://sf11-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/asset123"
        self.assertFalse(reference_media.is_allowed_douyin_audio_url(base + "?x=1"))
        self.assertFalse(reference_media.is_allowed_douyin_audio_url("http://sf11-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/asset123"))
        self.assertFalse(reference_media.is_allowed_douyin_audio_url("https://cdn.example.com/obj/tos-cn-ve-2774/asset123"))

    def test_qishui_track_page_is_not_mistaken_for_a_direct_cdn_asset(self) -> None:
        url = "https://music.douyin.com/qishui/share/track?track_id=1234567890123456789"
        self.assertFalse(reference_media.is_allowed_douyin_audio_url(url))
        self.assertIsNone(reference_media.reference_id([url]))

    def test_fresh_cookie_failure_without_browser_is_actionable(self) -> None:
        reason, actions = reference_media.classify_ytdlp_failure(
            "ERROR: Fresh cookies (not necessarily logged in) are needed",
            cookies_requested=False,
        )
        self.assertEqual(reason, "fresh_browser_session_required")
        self.assertTrue(any("--cookies-from-browser chrome" in action for action in actions))

    def test_fresh_cookie_failure_after_browser_is_distinct(self) -> None:
        reason, actions = reference_media.classify_ytdlp_failure(
            "ERROR: Fresh cookies (not necessarily logged in) are needed",
            cookies_requested=True,
        )
        self.assertEqual(reason, "browser_session_not_accepted")
        self.assertTrue(any("browser:profile" in action for action in actions))

    def test_cdn_fetch_is_ipv4_bounded_and_keeps_explicit_chrome(self) -> None:
        # All generated fixtures remain inside the owning project.
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as temporary:
            output = Path(temporary) / "audio"
            args = argparse.Namespace(
                extract_audio=True, output_dir=output,
                cookies_from_browser="chrome", diagnostic_output=None,
            )
            commands = []

            def acquired(command, **kwargs):
                commands.append((command, kwargs))
                (output / "reference-audio.mp3").write_bytes(b"unit-test-audio")
                return subprocess.CompletedProcess(command, 0, "", "")

            media = {"streams": [{"codec_type": "audio"}], "format": {"duration": "1.0"}}
            with patch.object(reference_media.subprocess, "run", side_effect=acquired), \
                    patch.object(reference_media, "ffprobe", return_value=media), \
                    patch.object(reference_media, "ytdlp_version", return_value="test-version"), \
                    redirect_stdout(io.StringIO()):
                result = reference_media.fetch_douyin_audio(
                    args, "https://sf6-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/testasset", ["yt-dlp"]
                )
            self.assertEqual(result, 0)
            command, options = commands[0]
            for flag in ("--force-ipv4", "--ignore-config", "--socket-timeout", "--retries", "--no-overwrites"):
                self.assertIn(flag, command)
            self.assertEqual(command[command.index("--cookies-from-browser") + 1], "chrome")
            self.assertEqual(options["timeout"], 180)

    def test_timeout_returns_safe_diagnostic_without_captured_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as temporary:
            args = argparse.Namespace(
                extract_audio=True, output_dir=Path(temporary) / "audio",
                cookies_from_browser="chrome", diagnostic_output=None,
            )
            error = subprocess.TimeoutExpired("yt-dlp", 180, output=b"SIMULATED_PRIVATE_OUTPUT")
            stderr = io.StringIO()
            with patch.object(reference_media.subprocess, "run", side_effect=error), redirect_stderr(stderr):
                result = reference_media.fetch_douyin_audio(
                    args, "https://sf6-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/testasset", ["yt-dlp"]
                )
            self.assertEqual(result, 4)
            self.assertIn("bounded_audio_fetch_timeout", stderr.getvalue())
            self.assertIn("source_network_unreachable", stderr.getvalue())
            self.assertNotIn("SIMULATED_PRIVATE_OUTPUT", stderr.getvalue())

    def test_cdn_output_rejects_multiple_audio_streams(self) -> None:
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as temporary:
            output = Path(temporary) / "audio"
            args = argparse.Namespace(
                extract_audio=True, output_dir=output,
                cookies_from_browser="chrome", diagnostic_output=None,
            )

            def acquired(command, **kwargs):
                (output / "reference-audio.mp3").write_bytes(b"unit-test-audio")
                return subprocess.CompletedProcess(command, 0, "", "")

            media = {"streams": [{"codec_type": "audio"}, {"codec_type": "audio"}], "format": {"duration": "1.0"}}
            stderr = io.StringIO()
            with patch.object(reference_media.subprocess, "run", side_effect=acquired), \
                    patch.object(reference_media, "ffprobe", return_value=media), \
                    patch.object(reference_media, "ytdlp_version", return_value="test-version"), redirect_stderr(stderr):
                result = reference_media.fetch_douyin_audio(
                    args, "https://sf6-cdn-tos.douyinstatic.com/obj/tos-cn-ve-2774/testasset", ["yt-dlp"]
                )
            self.assertEqual(result, 4)
            self.assertIn("audio_validation_failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
