#!/usr/bin/env python3
"""Validate FLASH CAST Douyin copy, hashtag, Qingdou, and cover evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import importlib.util
from pathlib import Path
import re
from typing import Any

try:
    from public_copy_guard import (
        DEFAULT_LEXICON, POLICY_VERSION, batch_text, load_lexicon, scan, sha_bytes,
        project_path, preflight_package, reject_synthetic, require_capture_review,
        hashtag_fields, HASHTAG_POLICY_VERSION,
    )
except ModuleNotFoundError as exc:
    # Existing consumers load this validator by file path solely for its hash API.
    if exc.name != "public_copy_guard":
        raise
    spec = importlib.util.spec_from_file_location(
        "flashcast_public_copy_guard", Path(__file__).with_name("public_copy_guard.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    DEFAULT_LEXICON, POLICY_VERSION = module.DEFAULT_LEXICON, module.POLICY_VERSION
    batch_text, load_lexicon, scan, sha_bytes = module.batch_text, module.load_lexicon, module.scan, module.sha_bytes
    project_path, preflight_package = module.project_path, module.preflight_package
    reject_synthetic, require_capture_review = module.reject_synthetic, module.require_capture_review
    hashtag_fields, HASHTAG_POLICY_VERSION = module.hashtag_fields, module.HASHTAG_POLICY_VERSION


FIXED_HASHTAGS = {"#马来西亚装修公司", "#马来西亚全屋定制"}
ADAPTIVE_AXES = {"content_topic", "space_or_style", "local_service_intent"}
QINGDOU_FIELDS = {"on_screen_copy", "cover_copy", "video_description", "hashtags"}
HASHTAG_PATTERN = re.compile(r"^#[^#\s]+$")


def load_json(path: Path, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    path = project_path(path, sandbox_root=sandbox_root)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def resolve(base: Path, value: Any, *, sandbox_root: Path | None = None) -> Path | None:
    if not nonempty(value):
        return None
    candidate = Path(str(value)).expanduser()
    return project_path(candidate if candidate.is_absolute() else base / candidate, sandbox_root=sandbox_root)


def read_text(path: Path | None, field: str, errors: list[str]) -> str:
    if path is not None:
        path = project_path(path)
    if path is None or not path.is_file():
        errors.append(f"{field}_missing")
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        errors.append(f"{field}_invalid:{exc}")
        return ""


def public_text_hash(
    on_screen_copy: str,
    cover_copy: str,
    video_description: str,
    hashtags: list[str],
    spoken_copy: str | None = None,
    hashtags_en: list[str] | None = None,
) -> str:
    fields = {
        "cover_copy": cover_copy,
        "hashtags": hashtags,
        "on_screen_copy": on_screen_copy,
        "video_description": video_description,
    }
    if spoken_copy is not None:
        fields["spoken_copy"] = spoken_copy
    if hashtags_en is not None:
        fields["hashtags_en"] = hashtags_en
    canonical = json.dumps(
        fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate(package_path: Path, lexicon_path: Path = DEFAULT_LEXICON, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    lexicon_path = project_path(lexicon_path, sandbox_root=sandbox_root)
    package_path, package = preflight_package(package_path, sandbox_root)
    base = package_path.parent
    def bounded_path(base: Path, value: Any) -> Path | None:
        return resolve(base, value, sandbox_root=sandbox_root)

    if package.get("platform") != "douyin":
        errors.append("platform_must_be_douyin")
    if package.get("production_profile") not in {"publish", "l4"}:
        errors.append("production_profile_must_be_publish_or_l4")
    for field in ("task_id", "run_id"):
        if not nonempty(package.get(field)):
            errors.append(f"{field}_missing")

    on_screen_path = bounded_path(base, package.get("on_screen_copy_path"))
    on_screen_copy = ""
    if on_screen_path is not None:
        on_screen_copy = read_text(on_screen_path, "on_screen_copy_path", errors)
    else:
        not_applicable = package.get("on_screen_copy_not_applicable")
        if not (
            isinstance(not_applicable, dict)
            and not_applicable.get("status") == "not_applicable"
            and nonempty(not_applicable.get("reason"))
        ):
            errors.append("on_screen_copy_path_or_reason_required")

    cover_copy = read_text(
        bounded_path(base, package.get("cover_copy_path")), "cover_copy_path", errors
    )
    video_description = read_text(
        bounded_path(base, package.get("video_description_path")),
        "video_description_path",
        errors,
    )
    if not cover_copy:
        errors.append("cover_copy_empty")
    if not video_description:
        errors.append("video_description_empty")
    elif len(video_description) < 20 or len(video_description) > 300:
        errors.append("video_description_length_outside_20_300_chars")
    if "#" in video_description:
        errors.append("video_description_must_not_inline_hashtags")

    raw_hashtags = package.get("hashtags")
    dual_hashtags = package.get("hashtag_policy_version") == HASHTAG_POLICY_VERSION
    fixed_hashtags = {"#马来西亚装修公司"} if dual_hashtags else FIXED_HASHTAGS
    try:
        hashtag_sets = hashtag_fields(package)
    except ValueError as exc:
        errors.append(str(exc))
        hashtag_sets = {}
    hashtags = raw_hashtags if isinstance(raw_hashtags, list) else []
    if len(hashtags) != 5:
        errors.append("hashtags_must_contain_exactly_five")
    if any(not isinstance(tag, str) or not HASHTAG_PATTERN.fullmatch(tag) for tag in hashtags):
        errors.append("hashtag_format_invalid")
    if len(set(hashtags)) != len(hashtags):
        errors.append("hashtags_must_be_unique")
    missing_fixed = sorted(fixed_hashtags - set(hashtags))
    if missing_fixed:
        errors.append("fixed_hashtags_missing:" + ",".join(missing_fixed))

    caption = read_text(bounded_path(base, package.get("caption_path")), "caption_path", errors)
    expected_caption = video_description + "\n\n" + " ".join(hashtags)
    if caption and caption != expected_caption:
        errors.append("caption_must_equal_description_plus_five_hashtags")
    english_hashtags = hashtag_sets.get("hashtags_en")
    if english_hashtags is not None:
        english_caption = read_text(bounded_path(base, package.get("caption_en_hashtags_path")),
                                    "caption_en_hashtags_path", errors)
        if english_caption and english_caption != video_description + "\n\n" + " ".join(english_hashtags):
            errors.append("english_caption_must_equal_same_description_plus_five_english_hashtags")

    adaptive_tags = [tag for tag in hashtags if tag not in fixed_hashtags]
    raw_rationales = package.get("adaptive_hashtags")
    rationales = raw_rationales if isinstance(raw_rationales, list) else []
    rationale_by_tag = {
        str(item.get("tag")): item
        for item in rationales
        if isinstance(item, dict) and nonempty(item.get("tag"))
    }
    if set(rationale_by_tag) != set(adaptive_tags):
        errors.append("adaptive_hashtag_rationales_must_match_four_tags" if dual_hashtags
                      else "adaptive_hashtag_rationales_must_match_three_tags")
    axes = {
        str(item.get("axis"))
        for item in rationales
        if isinstance(item, dict) and nonempty(item.get("axis"))
    }
    if axes != ADAPTIVE_AXES:
        errors.append("adaptive_hashtags_must_cover_three_axes")
    for tag in adaptive_tags:
        item = rationale_by_tag.get(tag, {})
        if not nonempty(item.get("reason")):
            errors.append(f"adaptive_hashtag_reason_missing:{tag}")

    spoken_copy = None
    if package.get("spoken_copy_path"):
        spoken_copy = read_text(bounded_path(base, package["spoken_copy_path"]), "spoken_copy_path", errors)
        if not spoken_copy:
            errors.append("spoken_copy_empty")
    fields = {"on_screen_copy": on_screen_copy, "cover_copy": cover_copy,
              "video_description": video_description, "hashtags": hashtags}
    if spoken_copy is not None:
        fields["spoken_copy"] = spoken_copy
    if english_hashtags is not None:
        fields["hashtags_en"] = english_hashtags
    computed_hash = public_text_hash(on_screen_copy, cover_copy, video_description, hashtags,
                                     spoken_copy, english_hashtags)
    if package.get("public_text_sha256") != computed_hash:
        errors.append("publish_package_public_text_sha256_mismatch")

    expected_batch = batch_text(fields).encode("utf-8")
    batch_hash = sha_bytes(expected_batch)
    if package.get("copy_policy_version") != POLICY_VERSION:
        errors.append("current_copy_policy_version_required")
    batch_path = bounded_path(base, package.get("public_text_batch_path"))
    if batch_path is None or not batch_path.is_file():
        errors.append("single_public_text_batch_missing")
    elif batch_path.read_bytes() != expected_batch:
        errors.append("single_public_text_batch_stale")
    guard_path = bounded_path(base, package.get("copy_guard_report_path"))
    if guard_path is None or not guard_path.is_file():
        errors.append("copy_guard_report_missing")
    else:
        guard = load_json(guard_path, sandbox_root=sandbox_root)
        reject_synthetic(guard, sandbox_root)
        if (guard.get("status") != "READY_FOR_QINGDOU"
                or guard.get("policy_version") != POLICY_VERSION
                or guard.get("public_text_sha256") != computed_hash
                or guard.get("batch_sha256") != batch_hash
                or set(guard.get("checked_fields", [])) != set(fields)
                or any(guard.get(key) != package.get(key) for key in ("task_id", "run_id"))):
            errors.append("copy_guard_not_current_complete_ready_batch")
    local_hits = scan(fields, load_lexicon(lexicon_path, sandbox_root=sandbox_root))
    if local_hits:
        errors.append("previous_qingdou_risk_term_reused")

    cover_validation_path = bounded_path(base, package.get("cover_validation_path"))
    if cover_validation_path is None or not cover_validation_path.is_file():
        errors.append("cover_validation_path_missing")
    else:
        try:
            cover_validation = load_json(cover_validation_path, sandbox_root=sandbox_root)
            reject_synthetic(cover_validation, sandbox_root)
            if str(cover_validation.get("status") or "").upper() != "PASS":
                errors.append("cover_validation_not_passed")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"cover_validation_invalid:{exc}")

    qingdou_path = bounded_path(base, package.get("qingdou_report_path"))
    if qingdou_path is None or not qingdou_path.is_file():
        errors.append("qingdou_report_path_missing")
    else:
        try:
            qingdou = load_json(qingdou_path, sandbox_root=sandbox_root)
            reject_synthetic(qingdou, sandbox_root)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"qingdou_report_invalid:{exc}")
        else:
            if str(qingdou.get("tool") or "").strip().casefold() not in {"qingdou", "轻抖"}:
                errors.append("qingdou_tool_identity_missing")
            if str(qingdou.get("status") or "").lower() not in {"pass", "passed"}:
                errors.append("qingdou_not_passed")
            if qingdou.get("public_text_sha256") != computed_hash:
                errors.append("qingdou_public_text_sha256_mismatch")
            checked_fields = {
                str(item) for item in qingdou.get("checked_fields", [])
            }
            if checked_fields != set(fields):
                errors.append("qingdou_must_cover_all_public_text_fields")
            if (qingdou.get("submission_mode") != "single_batch"
                    or qingdou.get("batch_sha256") != batch_hash):
                errors.append("qingdou_current_single_batch_required")
            if any(qingdou.get(key) != package.get(key) for key in ("task_id", "run_id")):
                errors.append("qingdou_task_run_mismatch")
            if qingdou.get("findings") != []:
                errors.append("qingdou_findings_must_be_explicitly_empty_for_pass")
            if not nonempty(qingdou.get("checked_at")):
                errors.append("qingdou_checked_at_missing")
            evidence_path = bounded_path(qingdou_path.parent, qingdou.get("evidence_path"))
            if evidence_path is None or not evidence_path.is_file():
                errors.append("qingdou_evidence_missing")
            else:
                evidence = evidence_path.read_bytes()
                if not evidence or qingdou.get("evidence_sha256") != sha_bytes(evidence):
                    errors.append("qingdou_evidence_empty_or_hash_mismatch")
                try:
                    require_capture_review(qingdou, evidence, sandbox_root)
                except ValueError as exc:
                    errors.append(str(exc))

    return {
        "status": ("PASS_SANDBOX_ONLY" if sandbox_root is not None else "PASS") if not errors else "FAIL",
        "validation_mode": "SYNTHETIC_TEST_ONLY" if sandbox_root is not None else "production",
        "capture_authenticity": "REVIEW_DECLARATION_ONLY_NOT_MACHINE_AUTHENTICATED" if sandbox_root is None else "SYNTHETIC_TEST_ONLY",
        "public_release_allowed": False,
        "package": str(package_path),
        "public_text_sha256": computed_hash,
        "batch_sha256": batch_hash,
        "local_risk_hits": local_hits,
        "fixed_hashtags": sorted(fixed_hashtags),
        "hashtag_policy_version": package.get("hashtag_policy_version", "legacy_two_fixed"),
        "hashtags_en": english_hashtags,
        "adaptive_hashtags": adaptive_tags,
        "errors": errors,
    }


def validate(package_path: Path, lexicon_path: Path = DEFAULT_LEXICON, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    try:
        return _validate(package_path, lexicon_path, sandbox_root=sandbox_root)
    except (OSError, ValueError, TypeError) as exc:
        return {"status": "FAIL", "errors": [str(exc)], "public_release_allowed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--test-sandbox-root", type=Path, help="Explicit synthetic-only mode under project drafts/creative")
    args = parser.parse_args()
    try:
        out_path = project_path(args.out, sandbox_root=args.test_sandbox_root) if args.out else None
        lexicon = args.test_sandbox_root / "fixture-risk-lexicon.json" if args.test_sandbox_root is not None else DEFAULT_LEXICON
        result = validate(args.package, lexicon, sandbox_root=args.test_sandbox_root)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)], "public_release_allowed": False}, ensure_ascii=False))
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] in {"PASS", "PASS_SANDBOX_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
