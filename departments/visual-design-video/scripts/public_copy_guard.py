#!/usr/bin/env python3
"""Freeze one Qingdou submission and learn evidence-backed risk terms (no network)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEXICON = PROJECT_ROOT / "data/knowledge/qingdou-risk-lexicon.json"
POLICY_VERSION = "qingdou-batch-v2-neutral-labels"
FIELD_LABELS = {
    "on_screen_copy": "视频文字",
    "spoken_copy": "口播",
    "cover_copy": "封面",
    "video_description": "描述",
    "hashtags": "话题",
}
PACKAGE_PATH_FIELDS = (
    "on_screen_copy_path", "cover_copy_path", "video_description_path", "spoken_copy_path",
    "public_text_batch_path", "copy_guard_report_path", "caption_path",
    "cover_validation_path", "qingdou_report_path",
)
SYNTHETIC_PATTERN = re.compile(
    r"synthetic[\s_-]*(?:test|fixture|capture)|provenance[\s_-]*test|"
    r"test[\s_-]*only|合成测试|合成夹具|测试夹具|仅供测试", re.I)


def execution_root(sandbox_root: Path | None = None) -> Path:
    if sandbox_root is None:
        return PROJECT_ROOT.resolve()
    root = Path(sandbox_root).expanduser().resolve()
    # An explicit test mode can never reach the production data/knowledge library.
    if not (root.is_relative_to(PROJECT_ROOT.resolve())
            and root.is_relative_to((PROJECT_ROOT / "drafts/creative").resolve())):
        raise ValueError("test_sandbox_must_be_inside_project_drafts_creative")
    return root


def synthetic_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            marker_key = str(key).casefold().replace("-", "_")
            if marker_key in {"synthetic", "is_synthetic", "test_only", "test_fixture", "provenance_test", "synthetic_test_only", "合成", "合成测试", "仅供测试"} and item not in (None, False, "", "false"):
                return True
            if synthetic_marker(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(synthetic_marker(item) for item in value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        value = "".join(c for c in unicodedata.normalize("NFKC", value) if unicodedata.category(c) != "Cf")
        return bool(SYNTHETIC_PATTERN.search(value)) or value.strip().casefold() in {"synthetic", "fixture", "合成", "模拟", "test"}
    return False


def reject_synthetic(value: Any, sandbox_root: Path | None = None) -> None:
    if sandbox_root is None and synthetic_marker(value):
        raise ValueError("synthetic_input_not_allowed_in_real_qingdou_gate")


def preflight_package(package_path: Path, sandbox_root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = project_path(package_path, sandbox_root=sandbox_root)
    package = load_json(path, sandbox_root=sandbox_root)
    reject_synthetic(package, sandbox_root)
    # Normalize and check every referenced path before reading any text/evidence.
    for field in PACKAGE_PATH_FIELDS:
        if package.get(field):
            local_path(path.parent, package[field], sandbox_root=sandbox_root)
    return path, package


def require_capture_review(report: dict[str, Any], evidence_bytes: bytes,
                           sandbox_root: Path | None = None) -> None:
    if sandbox_root is not None:
        execution_root(sandbox_root)
        return
    reject_synthetic(report)
    reject_synthetic(evidence_bytes)
    review = report.get("capture_review")
    if not (isinstance(review, dict)
            and isinstance(review.get("reviewer"), str) and review["reviewer"].strip()
            and isinstance(review.get("reviewed_at"), str) and review["reviewed_at"].strip()):
        raise ValueError("real_full_batch_capture_personal_review_required")
    human_review = (
        review.get("status") == "personally_inspected_real_full_batch"
        and review.get("declaration") == "HUMAN_DECLARED_REAL_QINGDOU_FULL_BATCH"
    )
    # Owner's 2026-10-07 instruction: no extra owner confirmation for a
    # genuinely observed no-hit batch. This never authenticates screenshots.
    agent_no_hit_review = (
        review.get("status") == "agent_inspected_real_full_batch"
        and review.get("declaration") == "AGENT_VERIFIED_REAL_QINGDOU_FULL_BATCH"
        and review.get("surface") == "codex_iab"
        and str(report.get("status", "")).casefold() in {"pass", "passed"}
        and report.get("findings") == []
        and report.get("observed_result") == "未检查到敏感词"
    )
    if not (human_review or agent_no_hit_review):
        raise ValueError("real_full_batch_capture_personal_review_required")
    for key in ("task_id", "run_id", "public_text_sha256", "batch_sha256", "evidence_sha256"):
        if review.get(key) != report.get(key):
            raise ValueError("capture_review_binding_mismatch:" + key)
    # A named human/agent review declaration is not automated authenticity proof.


def load_json(path: Path, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    path = project_path(path, sandbox_root=sandbox_root)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("json_root_must_be_object")
    return value


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def public_hash(fields: dict[str, Any]) -> str:
    return sha_bytes(json.dumps(fields, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8"))


def local_path(base: Path, value: Any, *, sandbox_root: Path | None = None) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("text_path_missing")
    path = Path(value).expanduser()
    return project_path(path if path.is_absolute() else base / path, sandbox_root=sandbox_root)


def read_fields(package_path: Path, *, sandbox_root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    package_path, package = preflight_package(package_path, sandbox_root)
    for key in ("task_id", "run_id"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            raise ValueError(f"{key}_missing")
    fields: dict[str, Any] = {}
    for field in ("on_screen_copy", "cover_copy", "video_description"):
        path_value = package.get(field + "_path")
        if field == "on_screen_copy" and not path_value:
            reason = package.get("on_screen_copy_not_applicable", {})
            if not (isinstance(reason, dict) and reason.get("status") == "not_applicable"
                    and isinstance(reason.get("reason"), str) and reason["reason"].strip()):
                raise ValueError("on_screen_copy_path_or_reason_required")
            fields[field] = ""
        else:
            fields[field] = local_path(package_path.parent, path_value, sandbox_root=sandbox_root).read_text(
                encoding="utf-8").strip()
            if field != "on_screen_copy" and not fields[field]:
                raise ValueError(f"{field}_empty")
    if package.get("spoken_copy_path"):
        fields["spoken_copy"] = local_path(package_path.parent, package["spoken_copy_path"], sandbox_root=sandbox_root).read_text(
            encoding="utf-8").strip()
        if not fields["spoken_copy"]:
            raise ValueError("spoken_copy_empty")
    tags = package.get("hashtags")
    if not isinstance(tags, list) or len(tags) != 5 or any(
            not isinstance(tag, str) or not re.fullmatch(r"#[^#\s]+", tag) for tag in tags):
        raise ValueError("five_valid_hashtags_required")
    if len(set(tags)) != 5 or not {"#马来西亚装修公司", "#马来西亚全屋定制"}.issubset(tags):
        raise ValueError("fixed_unique_hashtags_required")
    fields["hashtags"] = tags
    return package, fields


def batch_text(fields: dict[str, Any]) -> str:
    parts = []
    for key, label in FIELD_LABELS.items():
        if key in fields:
            value = " ".join(fields[key]) if key == "hashtags" else fields[key]
            parts.append(f"【{label}】\n{value or '（无）'}")
    return "\n\n".join(parts) + "\n"


def normalized(value: str) -> str:
    # Catch accidental full-width, whitespace and invisible-character variants;
    # never propose disguised spellings as a way around a platform warning.
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in text if not char.isspace()
                   and unicodedata.category(char) != "Cf")


def load_lexicon(path: Path = DEFAULT_LEXICON, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    value = load_json(path, sandbox_root=sandbox_root)
    reject_synthetic(value, sandbox_root)
    if value.get("source_tool") != "Qingdou" or not isinstance(value.get("entries"), list):
        raise ValueError("risk_lexicon_invalid")
    seen = set()
    for entry in value["entries"]:
        if not isinstance(entry, dict) or entry.get("status") != "avoid":
            raise ValueError("risk_lexicon_entry_invalid")
        term = entry.get("term")
        if not isinstance(term, str) or not normalized(term) or normalized(term) in seen:
            raise ValueError("risk_lexicon_term_invalid_or_duplicate")
        if not isinstance(entry.get("observations"), list) or not entry["observations"]:
            raise ValueError("risk_lexicon_evidence_missing")
        seen.add(normalized(term))
    return value


def scan(fields: dict[str, Any], lexicon: dict[str, Any]) -> list[dict[str, str]]:
    hits = []
    for field, value in fields.items():
        values = value if isinstance(value, list) else [value]
        for index, text in enumerate(values):
            for entry in lexicon["entries"]:
                if normalized(entry["term"]) in normalized(text):
                    hits.append({"term": entry["term"], "field": field,
                                 "location": f"{field}[{index}]" if isinstance(value, list) else field})
    return hits


def prepare(package_path: Path, output_dir: Path,
            lexicon_path: Path = DEFAULT_LEXICON, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    package_path = project_path(package_path, sandbox_root=sandbox_root)
    output_dir = project_path(output_dir, sandbox_root=sandbox_root)
    lexicon_path = project_path(lexicon_path, sandbox_root=sandbox_root)
    package, fields = read_fields(package_path, sandbox_root=sandbox_root)
    lexicon = load_lexicon(lexicon_path, sandbox_root=sandbox_root)
    hits = scan(fields, lexicon)
    text = batch_text(fields)
    batch_path = project_path(output_dir / "public-text-batch.txt", sandbox_root=sandbox_root)
    report_path = project_path(output_dir / "public-copy-guard.json", sandbox_root=sandbox_root)
    if batch_path.exists() or report_path.exists():
        raise ValueError("use_new_version_output_directory_no_overwrite")
    result = {
        "policy_version": POLICY_VERSION,
        "status": "BLOCKED_LOCAL_RISK_TERMS" if hits else "READY_FOR_QINGDOU",
        "task_id": package["task_id"], "run_id": package["run_id"],
        "checked_fields": sorted(fields), "public_text_sha256": public_hash(fields),
        "batch_sha256": sha_bytes(text.encode("utf-8")),
        "lexicon_sha256": sha_bytes(lexicon_path.read_bytes()),
        "hits": hits, "qingdou_status": "NOT_PERFORMED",
        "validation_mode": "SYNTHETIC_TEST_ONLY" if sandbox_root is not None else "production",
        "public_release_allowed": False,
        "package_binding": {
            "copy_policy_version": POLICY_VERSION,
            "public_text_sha256": public_hash(fields),
            "public_text_batch_path": str(batch_path.resolve()),
            "copy_guard_report_path": str(report_path.resolve()),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_path.write_text(text, encoding="utf-8")
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def checked_report(package_path: Path, report_path: Path, *,
                   sandbox_root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    """Review a current complete capture without writing the risk library."""
    package_path = project_path(package_path, sandbox_root=sandbox_root)
    report_path = project_path(report_path, sandbox_root=sandbox_root)
    package, fields = read_fields(package_path, sandbox_root=sandbox_root)
    report = load_json(report_path, sandbox_root=sandbox_root)
    reject_synthetic(report, sandbox_root)
    text = batch_text(fields)
    batch_path = local_path(package_path.parent, package.get("public_text_batch_path"), sandbox_root=sandbox_root)
    if package.get("copy_policy_version") != POLICY_VERSION or batch_path.read_bytes() != text.encode("utf-8"):
        raise ValueError("current_single_batch_required")
    if package.get("public_text_sha256") != public_hash(fields):
        raise ValueError("package_public_text_hash_mismatch")
    if str(report.get("tool", "")).casefold() not in {"qingdou", "轻抖"}:
        raise ValueError("qingdou_tool_required")
    if (report.get("public_text_sha256") != public_hash(fields)
            or report.get("batch_sha256") != sha_bytes(text.encode("utf-8"))
            or report.get("submission_mode") != "single_batch"
            or set(report.get("checked_fields", [])) != set(fields)):
        raise ValueError("qingdou_current_complete_batch_required")
    if any(report.get(key) != package[key] for key in ("task_id", "run_id")):
        raise ValueError("qingdou_task_run_mismatch")
    checked_at = report.get("checked_at")
    if not isinstance(checked_at, str) or not checked_at.strip():
        raise ValueError("qingdou_checked_at_missing")
    evidence = local_path(report_path.parent, report.get("evidence_path"), sandbox_root=sandbox_root)
    evidence_bytes = evidence.read_bytes()
    if not evidence_bytes or report.get("evidence_sha256") != sha_bytes(evidence_bytes):
        raise ValueError("qingdou_evidence_empty_or_hash_mismatch")
    require_capture_review(report, evidence_bytes, sandbox_root)
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise ValueError("qingdou_findings_list_required")
    status = str(report.get("status", "")).casefold()
    if status not in {"pass", "passed", "fail", "failed", "risk_detected"}:
        raise ValueError("qingdou_result_status_invalid")
    if (status in {"pass", "passed"}) == bool(findings):
        raise ValueError("qingdou_status_findings_inconsistent")
    # Validate the entire result before a caller can change any entry or file.
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("qingdou_finding_invalid")
        term, field = finding.get("term"), finding.get("field")
        if not isinstance(term, str) or not normalized(term) or field not in fields:
            raise ValueError("qingdou_finding_term_or_field_invalid")
        value = fields[field]
        if not any(normalized(term) in normalized(part) for part in (value if isinstance(value, list) else [value])):
            raise ValueError("qingdou_finding_not_in_submitted_field")
        if not isinstance(finding.get("reason"), str) or not finding["reason"].strip():
            raise ValueError("qingdou_finding_reason_missing")
    return package, fields, report, evidence


def check(package_path: Path, lexicon_path: Path = DEFAULT_LEXICON, *,
          sandbox_root: Path | None = None) -> dict[str, Any]:
    """Copy-only preproduction gate, independent of video/cover completion."""
    result: dict[str, Any] = {
        "status": "HOLD_COPY_GATE", "scope": "public_copy_only",
        "validation_mode": "SYNTHETIC_TEST_ONLY" if sandbox_root is not None else "production",
        "public_release_allowed": False, "errors": [],
    }
    try:
        package_path = project_path(package_path, sandbox_root=sandbox_root)
        lexicon_path = project_path(lexicon_path, sandbox_root=sandbox_root)
        package, fields = read_fields(package_path, sandbox_root=sandbox_root)
        result.update(task_id=package["task_id"], run_id=package["run_id"],
                      checked_fields=sorted(fields), public_text_sha256=public_hash(fields),
                      batch_sha256=sha_bytes(batch_text(fields).encode("utf-8")))
        if package.get("platform") != "douyin":
            raise ValueError("platform_must_be_douyin")
        hits = scan(fields, load_lexicon(lexicon_path, sandbox_root=sandbox_root))
        result["local_risk_hits"] = hits
        if hits:
            result["errors"].append("previous_qingdou_risk_term_reused")
        guard_path = local_path(package_path.parent, package.get("copy_guard_report_path"), sandbox_root=sandbox_root)
        guard = load_json(guard_path, sandbox_root=sandbox_root)
        reject_synthetic(guard, sandbox_root)
        if (guard.get("status") != "READY_FOR_QINGDOU"
                or guard.get("policy_version") != POLICY_VERSION
                or guard.get("public_text_sha256") != result["public_text_sha256"]
                or guard.get("batch_sha256") != result["batch_sha256"]
                or set(guard.get("checked_fields", [])) != set(fields)
                or any(guard.get(key) != package[key] for key in ("task_id", "run_id"))):
            raise ValueError("copy_guard_not_current_complete_ready_batch")
        report_path = local_path(package_path.parent, package.get("qingdou_report_path"), sandbox_root=sandbox_root)
        _, _, report, _ = checked_report(package_path, report_path, sandbox_root=sandbox_root)
        result["qingdou_result_status"] = report["status"]
        if report["findings"]:
            result["errors"].append("qingdou_risk_detected_rewrite_then_recheck_full_batch")
        if not result["errors"]:
            result["status"] = "PASS_SANDBOX_ONLY" if sandbox_root is not None else "PASS_COPY_ONLY"
    except (OSError, ValueError, TypeError) as exc:
        result["errors"].append(str(exc))
    return result


def record(package_path: Path, report_path: Path,
           lexicon_path: Path = DEFAULT_LEXICON, *, sandbox_root: Path | None = None) -> dict[str, Any]:
    package_path = project_path(package_path, sandbox_root=sandbox_root)
    report_path = project_path(report_path, sandbox_root=sandbox_root)
    lexicon_path = project_path(lexicon_path, sandbox_root=sandbox_root)
    package, fields, report, evidence = checked_report(package_path, report_path, sandbox_root=sandbox_root)
    findings = report["findings"]
    checked_at = report["checked_at"]
    lexicon = load_lexicon(lexicon_path, sandbox_root=sandbox_root)
    existing = {normalized(entry["term"]): entry for entry in lexicon["entries"]}
    added = 0
    changed = False
    for finding in findings:
        term = finding["term"].strip()
        key = normalized(term)
        observation = {
            "task_id": package["task_id"], "run_id": package["run_id"],
            "public_text_sha256": public_hash(fields), "batch_sha256": report["batch_sha256"],
            "checked_at": checked_at, "field": finding["field"],
            "reason": finding["reason"], "suggested_rewrite": finding.get("suggested_rewrite", ""),
            "report_path": str(report_path.resolve()), "report_sha256": sha_bytes(report_path.read_bytes()),
            "evidence_path": str(evidence.resolve()), "evidence_sha256": report["evidence_sha256"],
            "capture_review": report.get("capture_review"),
            "capture_authenticity": "NOT_AUTHENTICATED_BY_LOCAL_TOOL",
        }
        if key not in existing:
            entry = {"term": term, "status": "avoid", "source": "synthetic_test_finding" if sandbox_root is not None else "qingdou_verified_finding",
                     "observations": []}
            lexicon["entries"].append(entry)
            existing[key] = entry
            added += 1
        entry = existing[key]
        if observation not in entry["observations"]:
            entry["observations"].append(observation)
            changed = True
    if changed:
        lexicon["evidence_status"] = "SYNTHETIC_TEST_ONLY" if sandbox_root is not None else "VERIFIED_FINDINGS_RECORDED"
        lexicon["updated_at"] = datetime.now(timezone.utc).isoformat()
        lexicon_path.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "RECORDED" if changed else "NO_CHANGE", "added_terms": added,
            "lexicon_entries": len(lexicon["entries"]), "qingdou_result_status": report["status"],
            "validation_mode": "SYNTHETIC_TEST_ONLY" if sandbox_root is not None else "production",
            "capture_authenticity": "NOT_AUTHENTICATED_BY_LOCAL_TOOL",
            "public_release_allowed": False}


def project_path(value: Path, *, sandbox_root: Path | None = None) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(execution_root(sandbox_root)):
        raise ValueError("path_must_belong_to_flashcast_project")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("package", type=Path)
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--test-sandbox-root", type=Path, help="Explicit fixture mode under drafts/creative; never real validation")
    learn = sub.add_parser("record")
    learn.add_argument("package", type=Path)
    learn.add_argument("--qingdou-report", type=Path, required=True)
    learn.add_argument("--test-sandbox-root", type=Path, help="Explicit fixture mode; cannot write active lexicon")
    learn.add_argument("--test-lexicon", type=Path, help="Only allowed with --test-sandbox-root")
    gate = sub.add_parser("check", help="Read-only copy gate before production; no cover or final-video requirement")
    gate.add_argument("package", type=Path)
    gate.add_argument("--out", type=Path)
    gate.add_argument("--test-sandbox-root", type=Path)
    args = parser.parse_args()
    try:
        sandbox = args.test_sandbox_root
        execution_root(sandbox)
        if getattr(args, "test_lexicon", None) and sandbox is None:
            raise ValueError("test_lexicon_requires_explicit_sandbox")
        lexicon = (getattr(args, "test_lexicon", None) or sandbox / "fixture-risk-lexicon.json") if sandbox is not None else DEFAULT_LEXICON
        out_path = project_path(args.out, sandbox_root=sandbox) if args.command == "check" and args.out else None
        if out_path is not None and out_path.exists():
            raise ValueError("use_new_version_output_file_no_overwrite")
        if args.command == "prepare":
            result = prepare(args.package, args.output_dir, lexicon, sandbox_root=sandbox)
        elif args.command == "record":
            result = record(args.package, args.qingdou_report, lexicon, sandbox_root=sandbox)
        else:
            result = check(args.package, lexicon, sandbox_root=sandbox)
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED_LOCAL_RISK_TERMS" or result["status"].startswith("HOLD") else 0


if __name__ == "__main__":
    raise SystemExit(main())
