#!/usr/bin/env python3
"""Bounded adapter for copy-led stable-photo storyboards; never edits legacy QC.

Uses the approved runtime's decoded-motion and audio checks. Caption roles come
from the actual HTML plus storyboard, not an absent English/index template.
Unsupported CSS is rejected rather than guessed. This is machine evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import math
from pathlib import Path
import re
from typing import Any

PROJECT = Path(__file__).resolve().parents[3]
ROLE_LIMITS = {"caption-cn": 48.0, "caption-label": 24.0}
VOID_TAGS = {"img", "meta", "link", "br", "hr", "input", "source"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Elements(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict[str, Any]] = []
        self.stack: list[dict[str, Any]] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "text": ""}
        self.nodes.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data


def classes(node: dict) -> set[str]:
    return set((node["attrs"].get("class") or "").split())


def font_px(html: str, node: dict) -> float | None:
    """Resolve the simple class/ID/inline px CSS used by this exact production.

    Compound/descendant selectors involving the caption cause a fail-closed
    result: native browser measurements are then required instead of guessing.
    """
    values: list[tuple[int, int, str]] = []
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S))
    for order, (selector_list, body) in enumerate(re.findall(r"([^{}]+)\{([^{}]+)\}", css)):
        size = re.findall(r"(?<![-\w])font-size\s*:\s*([^;]+)", body, re.I)
        if not size:
            continue
        for selector in selector_list.split(","):
            selector = selector.strip()
            if selector.startswith(".") and selector[1:] in classes(node):
                values.append((10, order, size[-1].strip()))
            elif selector == "#" + (node["attrs"].get("id") or ""):
                values.append((100, order, size[-1].strip()))
            elif any("." + role in selector for role in ROLE_LIMITS) and re.search(r"[ >+~:[\]]", selector):
                return None
    inline = re.findall(r"(?<![-\w])font-size\s*:\s*([^;]+)", node["attrs"].get("style") or "", re.I)
    if inline:
        values.append((1000, len(values), inline[-1].strip()))
    if not values:
        return None
    chosen = max(values)[2]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)px", chosen)
    return float(m[1]) if m else None


def caption_check(html: str, storyboard: dict) -> dict:
    nodes = Elements(html).nodes
    issues, measured = [], []
    scenes = storyboard.get("scenes") or []
    if not scenes:
        issues.append("storyboard_scenes_missing")
    for role, limit in ROLE_LIMITS.items():
        items = [n for n in nodes if role in classes(n)]
        if len(items) != len(scenes):
            issues.append(f"{role}_count:{len(items)}:expected_{len(scenes)}")
        for i, (node, scene) in enumerate(zip(items, scenes)):
            attrs = node["attrs"]
            size = font_px(html, node)
            expected = (scene.get("screen_text") or [None, None])[0 if role == "caption-label" else 1]
            if node["text"].strip() != expected:
                issues.append(f"{role}_{i}:storyboard_text_mismatch")
            if size is None or size < limit:
                issues.append(f"{role}_{i}:font_unresolved_or_below_{limit:g}")
            try:
                start, length = float(attrs["data-start"]), float(attrs["data-duration"])
                if not all(math.isfinite(v) for v in (start, length)) or length < 1.5:
                    raise ValueError("invalid_or_short")
                if start < float(scene["start"]) - 1e-6 or start + length > float(scene["end"]) + 1 / 60:
                    raise ValueError("outside_nominal_scene")
            except (KeyError, TypeError, ValueError) as exc:
                issues.append(f"{role}_{i}:timing_invalid:{exc}")
            measured.append({"id": attrs.get("id"), "role": role, "font_px": size,
                             "minimum_px": limit, "scene_id": scene.get("id")})
    for forbidden in ("caption-en", "scene-index"):
        if any(forbidden in classes(n) for n in nodes):
            issues.append(f"unexpected_template_role:{forbidden}:separate_contract_required")
    if not re.search(r"text-shadow\s*:|-webkit-text-stroke\s*:", html):
        issues.append("readability_treatment_missing")
    return {"status": "PASS" if not issues else "FAIL", "roles": measured, "errors": issues,
            "note": "Static px CSS/timing evidence; does not replace native contrast/occlusion or mobile review."}


def sample_times(scene: dict) -> tuple[float, float]:
    start, end = float(scene["start"]), float(scene["end"])
    if not all(math.isfinite(v) for v in (start, end)) or end - start < 1.5:
        raise ValueError("scene_too_short_for_two_interior_samples")
    return start + (end - start) * .5, start + (end - start) * .75


def pair_intent(mean_diff: float, changed_ratio: float, hold_expected: bool) -> str:
    if not all(math.isfinite(v) and v >= 0 for v in (mean_diff, changed_ratio)):
        return "FAIL"
    stable = mean_diff < 2.5 and changed_ratio < .35
    return "PASS" if (stable if hold_expected else not stable) else "FAIL"


def full_highlight_gate(scan: dict, expected_frames: int) -> bool:
    """Midpoints cannot clear a complete clip when any decoded frame fails."""
    maximum, count = scan.get("maximum_ymax"), scan.get("frames_decoded")
    return (isinstance(maximum, (float, int)) and math.isfinite(maximum)
            and 0 <= maximum <= 235 and expected_frames > 0 and count == expected_frames
            and scan.get("frames_above235") == 0)


def runtime_module():
    locator = json.loads((Path('<CODEX_HOME>/skills/full-house-custom-ad/references/runtime-locator.json')).read_text())
    runtime = Path(locator["runtime_root"])
    manifest = json.loads((runtime / locator["manifest"]).read_text())
    entry = "scripts/video_qc.py"
    if not any(e["path"] == entry for e in manifest["active_entrypoints"]):
        raise ValueError("runtime_entry_not_approved")
    path = runtime / entry
    spec = importlib.util.spec_from_file_location("approved_legacy_video_qc", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def evaluate(video: Path, index: Path, storyboard_path: Path, original_legacy: Path) -> dict:
    storyboard = json.loads(storyboard_path.read_text())
    html = index.read_text()
    caption = caption_check(html, storyboard)
    module, runtime_path = runtime_module()
    stability = module.motion_stability_check(index, True, video)
    samples = []
    images = [n for n in Elements(html).nodes if "scene-photo" in classes(n)]
    if len(images) != len(storyboard["scenes"]):
        raise ValueError("scene_photo_count_does_not_match_storyboard")
    for node, scene in zip(images, storyboard["scenes"]):
        if node["attrs"].get("src") != scene.get("source"):
            raise ValueError("scene_photo_source_mismatch")
        a, b = sample_times(scene)
        left, right = module.raw_rgb_frame(video, a), module.raw_rgb_frame(video, b)
        if not left or not right:
            raise ValueError("actual_interior_frame_decode_missing")
        diffs = [abs(x - y) for x, y in zip(left, right)]
        mean = sum(diffs) / len(diffs)
        ratio = sum(d > 8 for d in diffs) / len(diffs)
        explicit_hold = "fixed full-bleed plate" in scene.get("camera_or_motion", "")
        has_real_stable_css = bool(re.search(r"\.scene-photo[^{}]*\{[^}]*transform\s*:\s*none", html))
        hold_expected = explicit_hold and has_real_stable_css
        samples.append({"scene_id": scene["id"], "time_a": a, "time_b": b,
                        "within_same_scene": scene["start"] < a < b < scene["end"],
                        "mean_abs_diff": round(mean, 5), "changed_ratio_gt8": round(ratio, 6),
                        "hold_expected_from_plan_and_source": hold_expected,
                        "status": pair_intent(mean, ratio, hold_expected)})
    ok = caption["status"] == "PASS" and stability["status"] == "passed" and all(s["status"] == "PASS" for s in samples)
    return {"schema_version": "1.0", "scope_checks_status": "PASS" if ok else "FAIL",
            "caption_check": caption, "scene_intent_motion": samples, "decoded_whole_frame_stability": stability,
            "input_sha256": {"video": digest(video), "index": digest(index), "storyboard": digest(storyboard_path),
                             "legacy_report": digest(original_legacy), "approved_runtime_code": digest(runtime_path)},
            "legacy_original": {"path": str(original_legacy), "status": json.loads(original_legacy.read_text())["overall_status"], "unaltered": True},
            "independent_qa": "NOT_PERFORMED", "public_release_allowed": False,
            "note": "Adapts only absent-role and cross-cut sampling assumptions. Original FAIL is not overwritten or renamed PASS."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("video", "index", "storyboard", "original-legacy", "output"):
        p.add_argument("--" + flag, required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to(PROJECT) or out.exists():
        raise ValueError("explicit_new_project_output_required")
    result = evaluate(a.video.resolve(), a.index.resolve(), a.storyboard.resolve(), a.original_legacy.resolve())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"scope_checks_status": result["scope_checks_status"], "output": str(out)}))
    return 0 if result["scope_checks_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
