#!/usr/bin/env python3
"""FLASH CAST growth operations layer.

This is the active, project-local adaptation of the old renovation Skill.
It deliberately uses only the Python standard library and writes into the
new project's data/, drafts/, logs/, reports/, backups/ and archive/ folders.

Default behavior is read-only, draft-only or preview-only. It never logs into
Google Ads, CMS, analytics, or customer accounts.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

import workflow_control as workflow
import department_reply


class OpsError(RuntimeError):
    """Expected, user-actionable operation error."""


ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc
BUSINESS_TZ = ZoneInfo("Asia/Kuala_Lumpur")
CONTENT_INVENTORY = Path("data/content/content-publishing-system-map.csv")
SEO_INVENTORY = Path("data/seo/site-index-inventory.csv")
SALES_FUNNEL_READBACK = Path("data/leads/sales-funnel-live-readback.csv")
LEARNING_EVENTS = Path("logs/learning-events.jsonl")
DEPARTMENT_LEARNING_REGISTRY = Path("data/learning/department-learning-registry.json")
DEPARTMENT_MEMORY_DIR = Path("data/learning/departments")
RUN_LEDGER = Path("logs/run-ledger.jsonl")
CHANGE_LOG = Path("logs/change-log.jsonl")

CONTENT_QUEUE_FIELDS = [
    "slot",
    "target_url",
    "paired_url",
    "language",
    "page_type",
    "content_priority",
    "pipeline",
    "content_package",
    "rich_media_slots",
    "owner_input_required",
    "status",
    "qa_status",
    "owner_approval",
]

SEO_FIELDS = [
    "url",
    "language",
    "page_type",
    "lastmod",
    "http_status",
    "final_url",
    "redirected",
    "robots_allowed",
    "meta_robots",
    "indexable",
    "canonical_url",
    "canonical_self",
    "hreflang_pair",
    "sitemap_included",
    "priority_issue",
    "action",
    "notes",
]

ACTION_FIELDS = [
    "action_id",
    "priority",
    "department",
    "title",
    "evidence",
    "recommended_action",
    "approval_required",
    "status",
    "rollback_plan",
    "next_review",
]

GA4_FIELDS = [
    "window_start",
    "window_end",
    "scope",
    "event_name",
    "event_page",
    "source_medium",
    "campaign",
    "action_count",
    "unique_users",
    "sessions",
    "measurement_note",
    "key_event_status",
    "source_record",
]

LEAD_FIELDS = [
    "lead_id",
    "date",
    "source",
    "campaign",
    "service",
    "area",
    "contact_channel",
    "status",
    "qualified",
    "quoted",
    "won",
    "quote_value_myr",
    "loss_reason",
    "landing_page",
    "lead_quality",
    "decision_label",
    "revenue_myr",
    "source_record",
]

SOURCE_SPECS = (
    ("Google Ads campaigns", Path("data/google-ads"), ("campaign",), ("广告系列", "Campaign"), 3, True),
    ("Google Ads ad groups", Path("data/google-ads"), ("ad-groups",), ("广告组", "Ad group"), 3, True),
    ("Google Ads keywords", Path("data/google-ads"), ("keywords",), ("关键字", "Keyword"), 3, True),
    ("Google Ads search terms", Path("data/google-ads"), ("search-terms",), ("搜索字词", "Search term"), 3, True),
    ("Google Ads devices", Path("data/google-ads"), ("devices",), ("设备", "Device"), 3, True),
    ("Google Ads locations", Path("data/google-ads"), ("locations",), ("相符的地理位置", "Location"), 3, True),
    ("Google Ads ads and RSA assets", Path("data/google-ads"), ("ads",), ("广告状态", "Ad status"), 3, False),
    ("Google Ads conversion actions", Path("data/google-ads"), ("conversion-actions",), ("转化操作", "转化动作", "Conversion action"), 3, True),
    ("Google Ads impression share", Path("data/google-ads"), ("impression-share",), ("搜索网络展示次数份额", "Search impression share"), 3, False),
    ("Google Ads auction insights", Path("data/google-ads"), ("auction-insights",), ("显示网址域", "Display URL domain"), 7, False),
    ("Google Ads recommendations", Path("data/google-ads"), ("recommendations",), ("建议", "Recommendation"), 3, False),
    ("Google Ads change history", Path("data/google-ads"), ("change-history",), ("变更", "Change"), 7, False),
    ("Lead quality log", Path("data/leads/lead-quality-log.csv"), (), ("lead_id", "线索"), 7, True),
    ("Sales funnel live readback", SALES_FUNNEL_READBACK, (), ("observed_at",), 1, True),
    ("GA4 consultation actions", Path("data/analytics/ga4-consultation-actions.csv"), (), ("event_name", "event"), 3, True),
    ("GA4 organic traffic", Path("data/analytics"), ("ga4-organic-traffic",), ("sessions", "会话"), 3, True),
    ("Google Search Console organic performance", Path("data/analytics"), ("gsc-organic-performance",), ("clicks", "点击"), 3, True),
    ("Content system map", CONTENT_INVENTORY, (), ("target_url", "content"), 30, True),
    ("SEO URL inventory", SEO_INVENTORY, (), ("url", "URL"), 7, True),
)


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def timestamp() -> str:
    return now_utc().isoformat(timespec="seconds")


def today() -> str:
    return now_utc().astimezone(BUSINESS_TZ).date().isoformat()


def safe_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise OpsError(f"路径超出项目目录，已阻止：{path}") from exc


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    safe_rel(root, resolved)
    return resolved


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_json(path: Path, payload: object) -> Path:
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if not lines:
            return []
        header_index = 0
        for index, line in enumerate(lines[:12]):
            fields = next(csv.reader([line]))
            if len(fields) >= 2 and not str(fields[0]).strip().endswith("报告"):
                header_index = index
                break
        reader = csv.DictReader(lines[header_index:])
        return [
            {str(key): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise OpsError(f"CSV 无法读取：{path}；{exc}") from exc


def optional_number(row: dict[str, str], *keys: str) -> float | None:
    """Parse an explicitly present numeric value without turning missing data into zero."""
    for key in keys:
        value = row.get(key, "")
        if str(value).strip() == "":
            continue
        try:
            return float(str(value).replace(",", "").replace("RM", "").strip())
        except ValueError:
            continue
    return None


def parse_observed_at(value: str) -> dt.datetime | None:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    if not normalized:
        return None
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def write_csv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def infer_date_window(path: Path) -> tuple[str, str]:
    matches = re.findall(r"20\d{2}-\d{2}-\d{2}", path.name)
    if len(matches) >= 2:
        return matches[0], matches[-1]
    if len(matches) == 1:
        return matches[0], matches[0]
    return "", ""


def infer_data_window(path: Path, rows: list[dict[str, str]]) -> tuple[str, str, str]:
    start, end = infer_date_window(path)
    if start and end:
        return start, end, "filename"
    dates: list[str] = []
    for row in rows:
        for key in ("window_start", "date", "日期"):
            value = row.get(key, "").strip()
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
                dates.append(value)
        value = row.get("window_end", "").strip()
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
            dates.append(value)
    if dates:
        return min(dates), max(dates), "data_columns"
    return "", "", ""


def file_observed_at(path: Path) -> dt.datetime:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def source_file_sort_key(path: Path) -> tuple[int, str, float, str, str]:
    """Prefer the newest actual data window, not the most recently touched file.

    A copied or touched historical export must not replace a later complete
    window.  For equal data-end dates, an explicit extraction/observation time
    wins.  Filename and content hash make the final tie deterministic without
    relying on mutable filesystem metadata.  Files with no usable data window
    retain mtime as a last-resort fallback.
    """

    try:
        rows = read_csv(path)
    except OpsError:
        rows = []
    _, data_end, _ = infer_data_window(path, rows)
    explicit_times: list[dt.datetime] = []
    for row in rows:
        for key in ("extracted_at", "observed_at", "collected_at", "generated_at"):
            parsed = parse_observed_at(row.get(key, ""))
            if parsed is not None:
                explicit_times.append(parsed)
    explicit_timestamp = max((value.timestamp() for value in explicit_times), default=0.0)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if data_end:
        return (2, data_end, explicit_timestamp, path.name.casefold(), digest)
    if explicit_timestamp:
        return (1, "", explicit_timestamp, path.name.casefold(), digest)
    return (0, "", path.stat().st_mtime, path.name.casefold(), digest)


def source_files(root: Path, path: Path, name_fragments: tuple[str, ...]) -> list[Path]:
    resolved = root / path
    if resolved.is_file():
        return [resolved]
    if not resolved.exists():
        return []
    files = [item for item in resolved.glob("*.csv") if item.is_file()]
    if name_fragments:
        files = [item for item in files if all(fragment.casefold() in item.name.casefold() for fragment in name_fragments)]
    return sorted(files, key=source_file_sort_key, reverse=True)


def first_header(row: dict[str, str]) -> set[str]:
    return {str(key or "").strip().casefold() for key in row.keys() if key}


def source_manifest(root: Path) -> tuple[dict[str, Any], list[Path]]:
    generated = now_utc()
    rows: list[dict[str, Any]] = []
    for name, path, fragments, required_headers, max_age_days, required_for_core_decision in SOURCE_SPECS:
        files = source_files(root, path, fragments)
        row: dict[str, Any] = {
            "source": name,
            "path": safe_rel(root, files[0]) if files else path.as_posix(),
            "status": "missing",
            "row_count": 0,
            "collected_at": "",
            "data_start": "",
            "data_end": "",
            "age_days": None,
            "freshness_basis": "",
            "max_age_days": max_age_days,
            "required_for_core_decision": required_for_core_decision,
            "missing_columns": [],
            "decision_usable": False,
            "decision_use": (
                "DATA MISSING: source does not exist"
                if required_for_core_decision
                else "OPTIONAL DATA MISSING: specialist checks are limited"
            ),
        }
        if not files:
            rows.append(row)
            continue
        file_path = files[0]
        try:
            file_rows = read_csv(file_path)
        except OpsError as exc:
            row.update({"status": "invalid", "decision_use": f"DATA INVALID: {exc}"})
            rows.append(row)
            continue
        row["row_count"] = len(file_rows)
        observed = file_observed_at(file_path)
        row["collected_at"] = observed.isoformat(timespec="seconds")
        start, end, window_basis = infer_data_window(file_path, file_rows)
        row["data_start"], row["data_end"] = start, end
        if window_basis:
            row["freshness_basis"] = f"{window_basis}_data_end"
        if end:
            try:
                age_days = max(0, (generated.date() - dt.date.fromisoformat(end)).days)
                if not row["freshness_basis"]:
                    row["freshness_basis"] = "data_end"
            except ValueError:
                age_days = max(0, (generated - observed).days)
                row["freshness_basis"] = "filesystem_mtime_fallback"
        else:
            age_days = max(0, (generated - observed).days)
            row["freshness_basis"] = "filesystem_mtime"
        row["age_days"] = age_days
        header_set = first_header(file_rows[0]) if file_rows else set()
        missing_columns = []
        if not file_rows:
            missing_columns = list(required_headers)
        elif not any(item.casefold() in header_set for item in required_headers):
            missing_columns = list(required_headers)
        row["missing_columns"] = missing_columns
        if not file_rows:
            row.update({"status": "empty", "decision_use": "DATA EMPTY: source cannot drive decisions"})
        elif missing_columns:
            row.update({"status": "invalid", "decision_use": "DATA INVALID: required columns are missing"})
        elif age_days > max_age_days:
            row.update({"status": "ready_stale", "decision_use": "STALE: historical context only"})
        else:
            row.update({"status": "ready_fresh", "decision_usable": True, "decision_use": "fresh local evidence; bounded decisions only"})
        rows.append(row)

    # A historical lead-quality table is expected to age when the business has no
    # new submissions. A fresh, explicit zero from the live sales-funnel readback
    # proves the system was checked; it does not rewrite the historical lead date.
    rows_by_source = {row["source"]: row for row in rows}
    lead_row = rows_by_source.get("Lead quality log")
    sales_readback_row = rows_by_source.get("Sales funnel live readback")
    if (
        lead_row
        and sales_readback_row
        and sales_readback_row.get("status") == "ready_fresh"
    ):
        readback_rows = read_csv(root / SALES_FUNNEL_READBACK)
        latest_30d = [row for row in readback_rows if row.get("period_days", "").strip() == "30"]
        new_submissions_30d = optional_number(latest_30d[-1], "submissions") if latest_30d else None
        if new_submissions_30d == 0 and lead_row.get("status") == "ready_stale":
            lead_row["required_for_core_decision"] = False
            lead_row["decision_use"] = (
                "historical outcomes only; fresh live readback explicitly confirms "
                "0 new submissions in the last 30 days"
            )

    counts = {status: sum(row["status"] == status for row in rows) for status in ("ready_fresh", "ready_stale", "missing", "empty", "invalid")}
    manifest = {
        "generated_at": generated.isoformat(timespec="seconds"),
        "status": "growth_source_manifest_ready",
        "counts": counts,
        "total_sources": len(rows),
        "decision_usable_sources": sum(row["decision_usable"] for row in rows),
        "sources": rows,
        "truth_policy": {
            "stale_data_is_historical_context_only": True,
            "missing_data_is_not_zero": True,
            "clicks_are_not_leads": True,
            "current_account_state_requires_live_read_only_evidence": True,
        },
    }
    data_path = root / "data/source-manifest.json"
    health_path = root / "data/data-health.json"
    report_path = root / "reports" / f"{today()}-data-health.md"
    health = {
        "generated_at": manifest["generated_at"],
        "status": "data_health_blocked" if any(
            row["required_for_core_decision"] and row["status"] in {"missing", "empty", "invalid", "ready_stale"}
            for row in rows
        ) else "data_health_ready",
        "decision_usable_sources": manifest["decision_usable_sources"],
        "total_sources": manifest["total_sources"],
        "counts": counts,
        "blockers": [
            f"{row['source']}: {row['decision_use']}"
            for row in rows
            if row["required_for_core_decision"] and row["status"] in {"missing", "empty", "invalid", "ready_stale"}
        ],
        "warnings": [
            f"{row['source']}: {row['decision_use']}"
            for row in rows
            if (row["status"] == "ready_stale" and not row["required_for_core_decision"])
            or (not row["required_for_core_decision"] and row["status"] in {"missing", "empty", "invalid"})
        ],
        "rows": rows,
    }
    write_json(data_path, manifest)
    write_json(health_path, health)
    report_lines = [
        "# FLASH CAST 数据来源和新鲜度检查",
        "",
        f"- 生成时间：`{manifest['generated_at']}`",
        f"- 可用于受控决策：`{manifest['decision_usable_sources']}/{manifest['total_sources']}`",
        f"- 新鲜/过期/缺失/空/无效：`{counts['ready_fresh']}/{counts['ready_stale']}/{counts['missing']}/{counts['empty']}/{counts['invalid']}`",
        "- 规则：缺失不等于 0，过期只能做历史参考，点击不等于线索。",
        "",
        "## 数据源",
        "",
    ]
    for row in rows:
        report_lines.append(
            f"- {row['source']}：`{row['status']}`；rows={row['row_count']}；"
            f"window={row['data_start'] or 'N/A'}..{row['data_end'] or 'N/A'}；"
            f"age_days={row['age_days'] if row['age_days'] is not None else 'N/A'}；"
            f"core_required={str(row['required_for_core_decision']).lower()}；{row['decision_use']}"
        )
    report_lines.extend(["", "## 阻断和警告", ""])
    report_lines.extend(f"- 阻断：{item}" for item in health["blockers"]) if health["blockers"] else report_lines.append("- 阻断：None")
    report_lines.extend(f"- 警告：{item}" for item in health["warnings"]) if health["warnings"] else report_lines.append("- 警告：None")
    write_text(report_path, "\n".join(report_lines) + "\n")
    run_id = append_run(
        root,
        "source-manifest",
        "complete_with_gaps" if health["blockers"] else "complete",
        [row["path"] for row in rows if row["path"]],
        [safe_rel(root, data_path), safe_rel(root, health_path), safe_rel(root, report_path)],
        blocker_count=len(health["blockers"]),
    )
    manifest["run_id"] = run_id
    health["run_id"] = run_id
    write_json(data_path, manifest)
    write_json(health_path, health)
    return manifest, [data_path, health_path, report_path]


def latest_ads_file(root: Path, fragment: str) -> Path | None:
    files = source_files(root, Path("data/google-ads"), (fragment,))
    return files[0] if files else None


def data_window_status(path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    start, end, basis = infer_data_window(path, rows)
    age_days: int | None = None
    if end:
        try:
            age_days = max(0, (now_utc().date() - dt.date.fromisoformat(end)).days)
        except ValueError:
            age_days = None
    return {"data_start": start, "data_end": end, "age_days": age_days, "freshness_basis": basis}


def summarize_ads(root: Path) -> dict[str, Any]:
    campaign_path = latest_ads_file(root, "campaign")
    if not campaign_path:
        return {"status": "missing", "file": "", "impressions": None, "clicks": None, "spend_myr": None, "primary_conversions": None, "data_start": "", "data_end": "", "age_days": None}
    rows = read_csv(campaign_path)
    if not rows:
        return {"status": "empty", "file": safe_rel(root, campaign_path), "impressions": None, "clicks": None, "spend_myr": None, "primary_conversions": None, "data_start": "", "data_end": "", "age_days": None}
    summary = {
        "status": "ready",
        "file": safe_rel(root, campaign_path),
        "impressions": 0.0,
        "clicks": 0.0,
        "spend_myr": 0.0,
        "primary_conversions": 0.0,
        "campaigns": [],
        **data_window_status(campaign_path, rows),
    }
    for row in rows:
        campaign_name = row.get("广告系列", row.get("campaign", "")).strip()
        campaign_status = row.get("广告系列状态", row.get("status", "")).strip()
        if (
            not campaign_name
            or campaign_name == "--"
            or campaign_name.casefold().startswith(("总计", "total"))
            or campaign_status.casefold().startswith(("总计", "total"))
        ):
            continue
        impressions = numeric(row, "展示次数", "impressions", "Impr.")
        clicks = numeric(row, "点击次数", "clicks", "Clicks", "互动次数")
        spend = numeric(row, "费用", "spend_myr", "cost", "Cost")
        conversions = numeric(row, "转化次数", "primary_conversions", "conversions", "Conversions")
        summary["impressions"] += impressions
        summary["clicks"] += clicks
        summary["spend_myr"] += spend
        summary["primary_conversions"] += conversions
        summary["campaigns"].append(
            {
                "name": campaign_name,
                "status": row.get("广告系列状态", row.get("状态", "")),
                "clicks": clicks,
                "spend_myr": spend,
                "primary_conversions": conversions,
            }
        )
    return summary


def summarize_ads_conversion_actions(root: Path) -> dict[str, Any]:
    path = latest_ads_file(root, "conversion-actions")
    if not path:
        return {
            "status": "missing",
            "file": "",
            "action_count": None,
            "primary_action_count": None,
            "primary_tracking_issue_count": None,
            "primary_actions_needing_attention": [],
            "recorded_conversions": None,
            "actions": [],
            "data_start": "",
            "data_end": "",
            "age_days": None,
        }
    rows = read_csv(path)
    if not rows:
        return {
            "status": "empty",
            "file": safe_rel(root, path),
            "action_count": None,
            "primary_action_count": None,
            "primary_tracking_issue_count": None,
            "primary_actions_needing_attention": [],
            "recorded_conversions": None,
            "actions": [],
            "data_start": "",
            "data_end": "",
            "age_days": None,
        }
    actions: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("Conversion action", row.get("转化操作", row.get("转化动作", ""))).strip()
        if not name or name.casefold().startswith(("total", "总计")):
            continue
        optimization = row.get("Action optimization", row.get("操作优化", row.get("主要转化", ""))).strip()
        normalized = optimization.casefold()
        is_primary = normalized in {"primary", "主要", "yes", "true", "1", "是", "主要转化"} or "主要" in optimization
        tracking_status = row.get("Tracking status", row.get("追踪状态", row.get("跟踪状态", ""))).strip()
        tracking_normalized = tracking_status.casefold()
        has_tracking_issue = any(
            marker in tracking_normalized
            for marker in (
                "needs attention",
                "setup issue",
                "misconfigured",
                "unverified",
                "error",
                "需要注意",
                "配置问题",
                "未验证",
                "错误",
            )
        )
        actions.append(
            {
                "name": name,
                "status": row.get("Status", row.get("状态", "")),
                "source": row.get("Source", row.get("来源", "")),
                "tracking_status": tracking_status,
                "optimization": optimization,
                "is_primary": is_primary,
                "has_tracking_issue": has_tracking_issue,
                "count_method": row.get("Count", row.get("计数", "")),
                "click_window": row.get("Click-through conversion window", row.get("点击型转化时间范围", "")),
                "included_in_account_goals": row.get("Included in account-level goals", row.get("纳入账号级目标", "")),
                "conversion_action_id": row.get("Conversion action ID", row.get("转化操作 ID", "")),
                "destination": row.get("Destination", row.get("目标", "")),
                "conversions": numeric(row, "Conversions", "转化次数", "转化", "All conv."),
            }
        )
    window = data_window_status(path, rows)
    primary_actions_needing_attention = [
        item["name"] for item in actions if item["is_primary"] and item["has_tracking_issue"]
    ]
    return {
        "status": "ready" if actions else "empty",
        "file": safe_rel(root, path),
        "action_count": len(actions) if actions else None,
        "primary_action_count": sum(item["is_primary"] for item in actions) if actions else None,
        "primary_tracking_issue_count": len(primary_actions_needing_attention) if actions else None,
        "primary_actions_needing_attention": primary_actions_needing_attention,
        "recorded_conversions": sum(item["conversions"] for item in actions) if actions else None,
        "actions": actions,
        **window,
    }


def summarize_sales_funnel_readback(root: Path) -> dict[str, Any]:
    path = root / SALES_FUNNEL_READBACK
    base: dict[str, Any] = {
        "status": "missing",
        "file": safe_rel(root, path),
        "observed_at": "",
        "observation_date": "",
        "age_days": None,
        "fresh": False,
        "new_submissions_30d": None,
        "submissions_90d": None,
        "inquiries_90d": None,
        "quote_requests_90d": None,
        "contacted_90d": None,
        "site_visits_90d": None,
        "quoted_90d": None,
        "won_90d": None,
        "total_amount_myr_90d": None,
        "last_non_test_submission_local": "",
        "last_non_test_submission_data_date_utc": "",
        "mode": "",
    }
    if not path.exists():
        return base
    rows = read_csv(path)
    if not rows:
        return {**base, "status": "empty"}

    parsed_rows = [
        (observed, row)
        for row in rows
        if (observed := parse_observed_at(row.get("observed_at", ""))) is not None
    ]
    if not parsed_rows:
        return {**base, "status": "invalid"}
    latest_observed = max(observed for observed, _ in parsed_rows)
    latest_rows = [row for observed, row in parsed_rows if observed == latest_observed]
    row_30d = next((row for row in latest_rows if row.get("period_days", "").strip() == "30"), None)
    row_90d = next((row for row in latest_rows if row.get("period_days", "").strip() == "90"), None)
    new_submissions_30d = optional_number(row_30d or {}, "submissions")
    if row_30d is None or new_submissions_30d is None:
        return {
            **base,
            "status": "invalid",
            "observed_at": latest_observed.isoformat(timespec="seconds"),
        }

    observation_date = latest_observed.astimezone(BUSINESS_TZ).date()
    age_days = max(0, (now_utc().astimezone(BUSINESS_TZ).date() - observation_date).days)
    metadata_row = row_30d or row_90d or {}
    return {
        **base,
        "status": "ready",
        "observed_at": latest_observed.isoformat(timespec="seconds"),
        "observation_date": observation_date.isoformat(),
        "age_days": age_days,
        "fresh": age_days <= 1,
        "new_submissions_30d": new_submissions_30d,
        "submissions_90d": optional_number(row_90d or {}, "submissions"),
        "inquiries_90d": optional_number(row_90d or {}, "inquiries"),
        "quote_requests_90d": optional_number(row_90d or {}, "quote_requests"),
        "contacted_90d": optional_number(row_90d or {}, "contacted"),
        "site_visits_90d": optional_number(row_90d or {}, "site_visits"),
        "quoted_90d": optional_number(row_90d or {}, "quoted"),
        "won_90d": optional_number(row_90d or {}, "won"),
        "total_amount_myr_90d": optional_number(row_90d or {}, "total_amount_myr"),
        "last_non_test_submission_local": metadata_row.get("last_non_test_submission_local", ""),
        "last_non_test_submission_data_date_utc": metadata_row.get("last_non_test_submission_data_date_utc", ""),
        "mode": metadata_row.get("mode", ""),
    }


def summarize_leads(root: Path) -> dict[str, Any]:
    path = root / "data/leads/lead-quality-log.csv"
    live_readback = summarize_sales_funnel_readback(root)
    if not path.exists():
        return {"status": "missing", "file": safe_rel(root, path), "lead_count": None, "qualified": None, "quoted": None, "won": None, "by_status": {}, "data_start": "", "data_end": "", "age_days": None, "live_readback": live_readback, "truth_current": False}
    rows = read_csv(path)
    if not rows:
        return {"status": "empty", "file": safe_rel(root, path), "lead_count": None, "qualified": None, "quoted": None, "won": None, "by_status": {}, "data_start": "", "data_end": "", "age_days": None, "live_readback": live_readback, "truth_current": False}
    by_status: dict[str, int] = {}
    for row in rows:
        status = row.get("status", row.get("状态", "unclassified")) or "unclassified"
        by_status[status] = by_status.get(status, 0) + 1
    truth_current = bool(
        live_readback.get("status") == "ready"
        and live_readback.get("fresh") is True
        and live_readback.get("new_submissions_30d") is not None
    )
    history_window = data_window_status(path, rows)
    return {
        "status": "ready",
        "file": safe_rel(root, path),
        "lead_count": len(rows),
        "qualified": sum(str(row.get("qualified", "")).lower() in {"true", "yes", "1", "是"} for row in rows),
        "quoted": sum(str(row.get("quoted", "")).lower() in {"true", "yes", "1", "是"} for row in rows),
        "won": sum(str(row.get("won", "")).lower() in {"true", "yes", "1", "是"} for row in rows),
        "by_status": by_status,
        "live_readback": live_readback,
        "truth_current": truth_current,
        "decision_freshness_basis": "sales_funnel_live_readback" if truth_current else "lead_quality_log",
        "decision_age_days": live_readback.get("age_days") if truth_current else history_window.get("age_days"),
        "historical_last_lead_date": history_window.get("data_end", ""),
        **history_window,
    }


def summarize_ga4(root: Path) -> dict[str, Any]:
    path = root / "data/analytics/ga4-consultation-actions.csv"
    if not path.exists():
        return {"status": "missing", "file": safe_rel(root, path), "actions": None, "by_event": {}, "data_start": "", "data_end": "", "age_days": None}
    rows = read_csv(path)
    if not rows:
        return {"status": "empty", "file": safe_rel(root, path), "actions": None, "by_event": {}, "data_start": "", "data_end": "", "age_days": None}
    valid_ends = sorted(
        row.get("window_end", "").strip()
        for row in rows
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", row.get("window_end", "").strip())
    )
    latest_end = valid_ends[-1] if valid_ends else ""
    latest_rows = [row for row in rows if row.get("window_end", "").strip() == latest_end] if latest_end else rows
    union_rows = [row for row in latest_rows if row.get("scope", "").casefold() == "all_website_union"]
    event_rows = [row for row in latest_rows if row.get("scope", "").casefold() == "all_website_by_event"]
    if union_rows:
        total_rows = union_rows
    elif event_rows:
        total_rows = event_rows
    else:
        total_rows = latest_rows[:1]
    breakdown_rows = event_rows or union_rows or total_rows
    by_event: dict[str, float] = {}
    for row in breakdown_rows:
        event = row.get("event_name", row.get("event", row.get("事件", "unknown"))) or "unknown"
        by_event[event] = by_event.get(event, 0.0) + numeric(row, "action_count", "count", "actions", "次数")
    paid_search_actions = sum(
        numeric(row, "action_count", "count", "actions", "次数")
        for row in latest_rows
        if row.get("scope", "").casefold() == "source_campaign_union"
        and row.get("source_medium", "").casefold() == "google / cpc"
    )
    paid_search_actions_by_window: dict[str, float] = {}
    for row in rows:
        if row.get("scope", "").casefold() != "source_campaign_union" or row.get("source_medium", "").casefold() != "google / cpc":
            continue
        window_key = f"{row.get('window_start', '')}..{row.get('window_end', '')}"
        paid_search_actions_by_window[window_key] = paid_search_actions_by_window.get(window_key, 0.0) + numeric(row, "action_count", "count", "actions", "次数")
    source_breakdown: dict[str, float] = {}
    for row in latest_rows:
        if row.get("scope", "").casefold() != "source_campaign_union":
            continue
        source_medium = row.get("source_medium", "") or "unknown"
        source_breakdown[source_medium] = source_breakdown.get(source_medium, 0.0) + numeric(row, "action_count", "count", "actions", "次数")
    key_event_statuses = sorted({row.get("key_event_status", "").strip() for row in latest_rows if row.get("key_event_status", "").strip()})
    key_events_configured: bool | None = None
    if key_event_statuses:
        key_events_configured = not any(status.casefold() in {"not_marked", "not_configured", "no"} for status in key_event_statuses)
    window = data_window_status(path, latest_rows)
    return {
        "status": "ready",
        "file": safe_rel(root, path),
        "actions": sum(numeric(row, "action_count", "count", "actions", "次数") for row in total_rows),
        "by_event": by_event,
        "paid_search_actions": paid_search_actions,
        "paid_search_actions_by_window": paid_search_actions_by_window,
        "source_breakdown": source_breakdown,
        "key_event_statuses": key_event_statuses,
        "key_events_configured": key_events_configured,
        "available_windows": sorted(set(valid_ends)),
        **window,
        "aggregation_rule": "use only the latest window_end; prefer all_website_union; use all_website_by_event only for event breakdown; never sum source/page detail rows",
    }


def migrate_historical_inputs(root: Path) -> tuple[dict[str, Any], list[Path]]:
    """Promote only the old, non-secret structured snapshots into empty active inputs."""
    migrations = [
        {
            "name": "GA4 consultation actions",
            "source": root / "history/skill-zhuangxiuseogeo/seo-workspace/data/ga4-consultation-actions.csv",
            "target": root / "data/analytics/ga4-consultation-actions.csv",
            "fields": GA4_FIELDS,
            "mapper": lambda row: {
                **{field: row.get(field, "") for field in GA4_FIELDS},
                "source_record": "history/skill-zhuangxiuseogeo/seo-workspace/data/ga4-consultation-actions.csv",
            },
        },
        {
            "name": "Lead quality log",
            "source": root / "history/skill-zhuangxiuseogeo/seo-workspace/data/lead-quality-log.csv",
            "target": root / "data/leads/lead-quality-log.csv",
            "fields": LEAD_FIELDS,
            "mapper": lambda row: {
                "lead_id": row.get("lead_ref", ""),
                "date": row.get("date", ""),
                "source": row.get("source", ""),
                "campaign": row.get("campaign", ""),
                "service": row.get("service_type", ""),
                "area": row.get("service_area", ""),
                "contact_channel": row.get("contact_channel", ""),
                "status": row.get("lead_quality", "") or "unclassified",
                "qualified": "yes" if row.get("lead_quality", "").casefold() in {"high", "medium"} else "no",
                "quoted": row.get("quoted", ""),
                "won": row.get("won", ""),
                "quote_value_myr": "",
                "loss_reason": row.get("owner_notes", "") or row.get("decision_label", ""),
                "landing_page": row.get("landing_page", ""),
                "lead_quality": row.get("lead_quality", ""),
                "decision_label": row.get("decision_label", ""),
                "revenue_myr": row.get("revenue_myr", ""),
                "source_record": "history/skill-zhuangxiuseogeo/seo-workspace/data/lead-quality-log.csv",
            },
        },
    ]
    migrated: list[dict[str, Any]] = []
    migrated_paths: list[Path] = []
    skipped: list[dict[str, Any]] = []
    input_paths: list[str] = []
    output_paths: list[str] = []
    for item in migrations:
        source = item["source"]
        target = item["target"]
        if not source.exists():
            skipped.append({"name": item["name"], "reason": "historical source missing"})
            continue
        source_rows = read_csv(source)
        target_rows = read_csv(target) if target.exists() else []
        input_paths.append(safe_rel(root, source))
        if target_rows:
            skipped.append({"name": item["name"], "reason": "active target already contains rows", "target": safe_rel(root, target)})
            continue
        if not source_rows:
            skipped.append({"name": item["name"], "reason": "historical source is empty"})
            continue
        normalized = [item["mapper"](row) for row in source_rows]
        write_csv(target, normalized, item["fields"])
        migrated_paths.append(target)
        migrated.append(
            {
                "name": item["name"],
                "source": safe_rel(root, source),
                "target": safe_rel(root, target),
                "rows": len(normalized),
                "source_window": infer_data_window(source, source_rows)[:2],
                "historical_only": True,
            }
        )
        output_paths.append(safe_rel(root, target))

    data_path = root / "data/first-batch-input-migration.json"
    report_path = root / "reports" / f"{today()}-first-batch-input-migration.md"
    payload = {
        "generated_at": timestamp(),
        "status": "historical_inputs_migrated" if migrated else "historical_inputs_not_migrated",
        "migrated": migrated,
        "skipped": skipped,
        "policy": [
            "Only empty active targets may be populated by this command.",
            "Historical rows remain traceable through source_record and must not be treated as current live truth.",
            "No credentials, cookies, tokens or direct customer PII are copied.",
        ],
    }
    write_json(data_path, payload)
    lines = [
        "# 第一批历史结构化输入迁移",
        "",
        f"- 状态：`{payload['status']}`",
        "- 范围：只把旧 Skill 中非凭证、脱敏、结构化的 GA4 和线索快照放入空的 active 输入表。",
        "- 说明：这些记录带有 `source_record`，仍然是历史参考；后续应使用最新时间窗覆盖或补充。",
        "",
        "## 已迁移",
        "",
    ]
    lines.extend(f"- {item['name']}：{item['rows']} 行；{item['source']} → {item['target']}；window={item['source_window'][0]}..{item['source_window'][1]}" for item in migrated) if migrated else lines.append("- None")
    lines.extend(["", "## 跳过", ""])
    lines.extend(f"- {item['name']}：{item['reason']}" for item in skipped) if skipped else lines.append("- None")
    lines.extend(["", "## 下一步", "", "- 用最新 GA4 和销售数据替换/追加 active 输入，再重新运行 `ads-daily`。", "- 在任何广告预算、出价或广告状态修改前，等待 Reality Checker 放行和负责人明确批准。"])
    write_text(report_path, "\n".join(lines) + "\n")
    output_paths.append(safe_rel(root, data_path))
    output_paths.append(safe_rel(root, report_path))
    run_id = append_run(root, "migrate-historical-inputs", payload["status"], input_paths, output_paths, migrated_count=len(migrated), skipped_count=len(skipped))
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path] + migrated_paths


def conversion_reconcile(root: Path) -> tuple[dict[str, Any], list[Path]]:
    ads = summarize_ads(root)
    ads_conversion_actions = summarize_ads_conversion_actions(root)
    ga4 = summarize_ga4(root)
    leads = summarize_leads(root)
    blockers: list[str] = []
    if ads["status"] != "ready":
        blockers.append("Google Ads 当前导出缺失或为空。")
    elif ads.get("age_days") is not None and ads["age_days"] > 3:
        blockers.append(f"Google Ads 广告系列导出已过期 {ads['age_days']} 天（数据截至 {ads.get('data_end') or '未知'}）。")
    if ads_conversion_actions["status"] != "ready":
        blockers.append("Google Ads 转化动作清单缺失或为空，无法确认哪些动作是主要转化以及是否已从 GA4 导入。")
    elif ads_conversion_actions.get("age_days") is not None and ads_conversion_actions["age_days"] > 3:
        blockers.append(f"Google Ads 转化动作清单已过期 {ads_conversion_actions['age_days']} 天（数据截至 {ads_conversion_actions.get('data_end') or '未知'}）。")
    elif (ads_conversion_actions.get("primary_action_count") or 0) == 0:
        blockers.append("Google Ads 转化动作清单中没有主要转化，不能用于智能出价或扩量。")
    elif ads_conversion_actions.get("primary_actions_needing_attention"):
        blockers.append(
            "Google Ads 主要转化动作存在追踪配置问题："
            + "、".join(ads_conversion_actions["primary_actions_needing_attention"])
            + "。应修复现有动作并完成同窗测试，禁止重复创建或导入同一咨询转化。"
        )
    if ga4["status"] != "ready":
        blockers.append("GA4 咨询动作数据缺失或为空，不能确认网站事件是否触发。")
    elif ga4.get("age_days") is not None and ga4["age_days"] > 3:
        blockers.append(f"GA4 咨询动作数据已过期 {ga4['age_days']} 天（数据截至 {ga4.get('data_end') or '未知'}）。")
    if ga4.get("key_events_configured") is False:
        blockers.append("GA4 当前有咨询事件上报，但关键事件数为 0；quote_form_success、WhatsApp/电话事件尚未形成关键事件闭环。")
    if leads["status"] != "ready":
        blockers.append("真实线索质量表缺失或为空，不能确认有效线索、报价或成交。")
    else:
        sales_readback = leads.get("live_readback", {})
        if sales_readback.get("status") in {"missing", "empty"}:
            blockers.append("销售漏斗现场回读缺失或为空，不能确认旧线索日期代表无新增提交还是数据中断。")
        elif sales_readback.get("status") == "invalid":
            blockers.append("销售漏斗现场回读无效，必须包含可解析的 observed_at、30 天窗口和明确 submissions 数值。")
        elif sales_readback.get("fresh") is not True:
            blockers.append(
                f"销售漏斗现场回读已过期 {sales_readback.get('age_days') if sales_readback.get('age_days') is not None else '未知'} 天"
                f"（观察日期 {sales_readback.get('observation_date') or '未知'}）。"
            )
        elif (sales_readback.get("new_submissions_30d") or 0) > 0 and leads.get("age_days") is not None and leads["age_days"] > 7:
            blockers.append(
                f"销售后台近 30 天有 {sales_readback.get('new_submissions_30d')} 个新增提交，"
                f"但线索质量表最后日期仍是 {leads.get('data_end') or '未知'}；新增记录尚未完成脱敏质量回传。"
            )
    if ads["status"] == "ready" and (ads["clicks"] or 0) > 0 and (ads["primary_conversions"] or 0) == 0:
        blockers.append("Ads 有点击/花费但记录 0 个主要转化，需先检查追踪和销售对账，不能直接扩量。")
    windows_aligned = bool(
        ads.get("data_start")
        and ads.get("data_end")
        and ads.get("data_start") == ga4.get("data_start")
        and ads.get("data_end") == ga4.get("data_end")
    )
    if ads.get("status") == "ready" and ga4.get("status") == "ready" and not windows_aligned:
        blockers.append(
            "Ads 与 GA4 日期窗口不一致："
            f"Ads={ads.get('data_start') or '未知'}..{ads.get('data_end') or '未知'}；"
            f"GA4={ga4.get('data_start') or '未知'}..{ga4.get('data_end') or '未知'}，不能直接比较转化数。"
        )
    historical_paid = ga4.get("paid_search_actions_by_window", {}) if isinstance(ga4.get("paid_search_actions_by_window"), dict) else {}
    historical_resolution = (
        "旧的 4 次 google/cpc 咨询动作属于 2026-08-02..2026-08-31；"
        f"当前最新 GA4 窗口 {ga4.get('data_start') or '未知'}..{ga4.get('data_end') or '未知'} 的 google/cpc 咨询动作是 {ga4.get('paid_search_actions') if ga4.get('paid_search_actions') is not None else 'DATA MISSING'}。"
        "两者不是同一窗口，旧差异已从当前决策中剔除。"
        if historical_paid.get("2026-08-02..2026-08-31") == 4.0
        else "未发现可复核的旧 4 次 google/cpc 咨询动作窗口。"
    )
    payload = {
        "generated_at": timestamp(),
        "status": "conversion_reconciliation_blocked" if blockers else "conversion_reconciliation_ready",
        "decision": "HOLD_OFF_RM0" if blockers else "READY_FOR_CONTROLLED_REVIEW",
        "ads": ads,
        "ads_conversion_actions": ads_conversion_actions,
        "ga4": ga4,
        "lead_truth": leads,
        "window_alignment": {
            "aligned": windows_aligned,
            "ads": f"{ads.get('data_start') or ''}..{ads.get('data_end') or ''}",
            "ga4": f"{ga4.get('data_start') or ''}..{ga4.get('data_end') or ''}",
        },
        "historical_discrepancy_resolution": historical_resolution,
        "funnel_policy": [
            "Ads clicks are traffic, not leads.",
            "Phone/WhatsApp clicks are observations, not verified conversations.",
            "Only sales/CRM-confirmed lead records can establish qualified leads, quotes or wins.",
            "Missing data is not zero.",
        ],
        "blockers": blockers,
        "warnings": [
            "不同日期范围、账户、货币或时区的数据不能直接相加。",
            "当前报告是本地导出对账，不代表实时后台状态。",
        ],
    }
    data_path = root / "data/leads/conversion-reconciliation.json"
    report_path = root / "reports" / f"{today()}-conversion-reconciliation.md"
    write_json(data_path, payload)
    report = f"""# FLASH CAST Google Ads 转化对账

- 生成时间：`{payload['generated_at']}`
- 状态：`{payload['status']}`
- Ads 文件：`{ads['file'] or 'DATA MISSING'}`
- Ads 转化动作文件：`{ads_conversion_actions['file'] or 'DATA MISSING'}`
- GA4 文件：`{ga4['file'] or 'DATA MISSING'}`
- 真实线索文件：`{leads['file'] or 'DATA MISSING'}`

## 当前漏斗证据

- Ads 展示：`{ads['impressions'] if ads['impressions'] is not None else 'DATA MISSING'}`
- Ads 点击：`{ads['clicks'] if ads['clicks'] is not None else 'DATA MISSING'}`
- Ads 花费 MYR：`{ads['spend_myr'] if ads['spend_myr'] is not None else 'DATA MISSING'}`
- Ads 主要转化：`{ads['primary_conversions'] if ads['primary_conversions'] is not None else 'DATA MISSING'}`
- Ads 转化动作数：`{ads_conversion_actions['action_count'] if ads_conversion_actions['action_count'] is not None else 'DATA MISSING'}`
- Ads 主要转化动作数：`{ads_conversion_actions['primary_action_count'] if ads_conversion_actions['primary_action_count'] is not None else 'DATA MISSING'}`
- Ads 主要转化追踪异常数：`{ads_conversion_actions['primary_tracking_issue_count'] if ads_conversion_actions['primary_tracking_issue_count'] is not None else 'DATA MISSING'}`
- GA4 咨询动作：`{ga4['actions'] if ga4['actions'] is not None else 'DATA MISSING'}`
- GA4 google/cpc 咨询动作：`{ga4['paid_search_actions'] if ga4.get('paid_search_actions') is not None else 'DATA MISSING'}`
- GA4 关键事件配置：`{'configured' if ga4.get('key_events_configured') is True else 'not_configured' if ga4.get('key_events_configured') is False else 'DATA MISSING'}`
- 线索记录数：`{leads['lead_count'] if leads['lead_count'] is not None else 'DATA MISSING'}`
- 已验证有效线索：`{leads['qualified'] if leads['qualified'] is not None else 'DATA MISSING'}`
- 已报价：`{leads['quoted'] if leads['quoted'] is not None else 'DATA MISSING'}`
- 已成交：`{leads['won'] if leads['won'] is not None else 'DATA MISSING'}`
- 销售现场回读：`{leads.get('live_readback', {}).get('status', 'DATA MISSING')}`；观察日期=`{leads.get('live_readback', {}).get('observation_date') or 'DATA MISSING'}`；age_days=`{leads.get('live_readback', {}).get('age_days') if leads.get('live_readback', {}).get('age_days') is not None else 'DATA MISSING'}`
- 近 30 天后台新增提交：`{leads.get('live_readback', {}).get('new_submissions_30d') if leads.get('live_readback', {}).get('new_submissions_30d') is not None else 'DATA MISSING'}`
- 最后非测试提交：`{leads.get('live_readback', {}).get('last_non_test_submission_local') or 'DATA MISSING'}`

## 时间窗与旧差异处置

- Ads：`{ads.get('data_start') or 'DATA MISSING'}..{ads.get('data_end') or 'DATA MISSING'}`
- GA4：`{ga4.get('data_start') or 'DATA MISSING'}..{ga4.get('data_end') or 'DATA MISSING'}`
- 同窗：`{str(windows_aligned).lower()}`
- 结论：{historical_resolution}

## 阻断项

{chr(10).join(f'- {item}' for item in blockers) if blockers else '- None'}

## 规则

- 缺失数据不等于 0。
- 电话/WhatsApp 按钮点击不等于接通或实际入站。
- 真实有效线索、报价和成交必须由销售/CRM 逐条确认。
- 本报告不修改 Ads、GA4、GTM、网站或 CRM。
"""
    write_text(report_path, report)
    run_id = append_run(
        root,
        "conversion-reconcile",
        "blocked" if blockers else "complete",
        [path for path in (ads.get("file"), ads_conversion_actions.get("file"), ga4.get("file"), leads.get("file"), leads.get("live_readback", {}).get("file")) if path],
        [safe_rel(root, data_path), safe_rel(root, report_path)],
        blocker_count=len(blockers),
    )
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def action_queue(root: Path) -> tuple[dict[str, Any], list[Path]]:
    manifest_path = root / "data/source-manifest.json"
    conversion_path = root / "data/leads/conversion-reconciliation.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else source_manifest(root)[0]
    conversion = read_json(conversion_path) if conversion_path.exists() else conversion_reconcile(root)[0]
    actions: list[dict[str, str]] = []

    def add(priority: str, department: str, title: str, evidence: str, recommendation: str, rollback_plan: str) -> None:
        action_key = re.sub(r"[^a-z0-9]+", "-", f"{department}-{title}".casefold()).strip("-")
        actions.append(
            {
                "action_id": f"FC-{today().replace('-', '')}-{action_key[:70]}",
                "priority": priority,
                "department": department,
                "title": title,
                "evidence": evidence,
                "recommended_action": recommendation,
                "approval_required": "yes" if department in {"paid-growth-data", "content-organic-website", "visual-design-video", "sales"} else "no",
                "status": "blocked_by_data" if priority == "P0" else "needs_owner_review",
                "rollback_plan": rollback_plan,
                "next_review": "补齐数据后复核" if priority == "P0" else "下次周复盘",
            }
        )

    source_blockers = [
        f"{row.get('source')}: {row.get('decision_use')}"
        for row in manifest.get("sources", [])
        if row.get("status") in {"missing", "empty", "invalid"}
    ]
    if source_blockers:
        add(
            "P0",
            "paid-growth-data",
            "补齐数据源并统一时间窗",
            "; ".join(source_blockers),
            "补齐 GA4 咨询动作、线索质量和必要的 Ads 转化配置导出；统一账户、日期、MYR 和马来西亚时区后再决策。",
            "不执行线上动作；补数失败则保持 blocked。",
        )

    conversion_blockers = conversion.get("blockers", [])
    if conversion_blockers:
        add(
            "P0",
            "paid-growth-data",
            "完成 Ads 到真实线索的转化对账",
            "; ".join(str(item) for item in conversion_blockers),
            "逐条对齐 Ads、GA4、网站表单/电话/WhatsApp 和销售状态，区分点击、咨询、有效线索、报价和成交。",
            "对账是只读动作；没有对账结果就不进入扩量。",
        )

    ads = conversion.get("ads", {})
    if ads.get("clicks") and not ads.get("primary_conversions"):
        add(
            "P0",
            "paid-growth-data",
            "检查主要转化追踪",
            f"{ads.get('clicks')} clicks; {ads.get('spend_myr')} MYR spend; 0 recorded primary conversions",
            "只读检查 GA4/GTM/Google Ads 主要转化、表单成功事件、电话接通和 WhatsApp Business 入站；不直接改设置。",
            "不修改追踪配置；任何修改另行审批并先备份。",
        )

    campaign_states = [str(item.get("status", "")).casefold() for item in ads.get("campaigns", []) if isinstance(item, dict)]
    if campaign_states and all("暂停" in state or "paused" in state for state in campaign_states):
        add(
            "P1",
            "paid-growth-data",
            "复核广告系列暂停状态",
            "当前导出中的广告系列状态均显示为暂停/paused",
            "由负责人在 Google Ads 当前登录态确认是否仍需暂停；仅提交复核建议，不自动启用。",
            "启用前必须保留当前状态证据和人工批准；不自动恢复。",
        )

    locations_path = latest_ads_file(root, "locations")
    location_rows = read_csv(locations_path) if locations_path else []
    if location_rows and len({row.get("相符的地理位置", row.get("location", "")) for row in location_rows}) <= 2:
        add(
            "P1",
            "paid-growth-data",
            "补充 KL 周边地区粒度核对",
            safe_rel(root, locations_path) if locations_path else "DATA MISSING",
            "只读核对吉隆坡中心约 50 公里范围内的城市/位置报告、实际所在地与兴趣地设置；不扩大地区。",
            "不修改地区设置；任何调整需人工批准。",
        )

    search_path = latest_ads_file(root, "search-terms")
    if search_path and read_csv(search_path):
        add(
            "P1",
            "paid-growth-data",
            "审核搜索词和否定词候选",
            safe_rel(root, search_path),
            "按装修服务意图、低意向、招聘/课程/DIY/无关词分类，生成否定词草案；不直接添加到账户。",
            "只保存草案；账户修改需要人工批准。",
        )

    if not actions:
        add(
            "P2",
            "operations",
            "继续观察并记录下一次数据",
            "当前没有新增阻断项",
            "下一次日检继续刷新数据来源、转化、搜索词和真实线索状态。",
            "无线上动作。",
        )

    payload = {
        "generated_at": timestamp(),
        "status": "action_queue_ready_for_review",
        "action_count": len(actions),
        "actions": actions,
        "safety": "local recommendations only; no Ads, website or customer action executed",
    }
    data_path = root / "data/action-queue.json"
    csv_path = root / "data/action-queue.csv"
    report_path = root / "reports" / f"{today()}-action-queue.md"
    write_json(data_path, payload)
    write_csv(csv_path, actions, ACTION_FIELDS)
    report_lines = [
        "# FLASH CAST 增长行动队列",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 行动数：`{len(actions)}`",
        "- 模式：只读建议和人工审核，不修改广告、网站或客户数据。",
        "",
        "## 行动",
        "",
    ]
    for item in actions:
        report_lines.extend(
            [
                f"### {item['action_id']}｜{item['priority']}｜{item['title']}",
                "",
                f"- 部门：`{item['department']}`；状态：`{item['status']}`；需批准：`{item['approval_required']}`",
                f"- 证据：{item['evidence']}",
                f"- 建议：{item['recommended_action']}",
                f"- 回滚：{item['rollback_plan']}",
                f"- 下一次检查：{item['next_review']}",
                "",
            ]
        )
    write_text(report_path, "\n".join(report_lines))
    run_id = append_run(root, "action-queue", "ready_for_review", [safe_rel(root, manifest_path), safe_rel(root, conversion_path)], [safe_rel(root, data_path), safe_rel(root, csv_path), safe_rel(root, report_path)], action_count=len(actions))
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, csv_path, report_path]


def handoff(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    handoff_id = f"{today()}-{args.from_department}-to-{args.to_department}-{hashlib.sha256(timestamp().encode()).hexdigest()[:8]}"
    payload = {
        "handoff_id": handoff_id,
        "created_at": timestamp(),
        "task_id": args.task_id,
        "from_department": args.from_department,
        "to_department": args.to_department,
        "completed": args.completed,
        "unfinished": args.unfinished,
        "evidence": args.evidence,
        "cannot_assume": args.cannot_assume,
        "next_action": args.next_action,
        "owner_approval_required": args.owner_approval_required,
        "status": "waiting_receiver_action",
    }
    jsonl_path = root / "logs/handoffs.jsonl"
    append_jsonl(jsonl_path, payload)
    report_path = root / "logs/handoffs" / f"{handoff_id}.md"
    report = f"""# 部门交接：{args.from_department} → {args.to_department}

- 交接编号：`{handoff_id}`
- 任务编号：`{args.task_id}`
- 时间：`{payload['created_at']}`
- 状态：`{payload['status']}`

## 已完成

{args.completed or 'N/A'}

## 未完成

{args.unfinished or 'N/A'}

## 关键证据

{args.evidence or 'N/A'}

## 不能假设

{args.cannot_assume or 'N/A'}

## 接收部门下一步

{args.next_action or 'N/A'}

## 是否需要老板批准

`{'是' if args.owner_approval_required else '否'}`
"""
    write_text(report_path, report)
    run_id = append_run(root, "handoff", "recorded", [args.evidence] if args.evidence else [], [safe_rel(root, jsonl_path), safe_rel(root, report_path)], handoff_id=handoff_id, task_id=args.task_id)
    payload["run_id"] = run_id
    return payload, [jsonl_path, report_path]


def run_ledger_report(root: Path) -> tuple[dict[str, Any], list[Path]]:
    rows = read_jsonl(root / RUN_LEDGER)
    payload = {
        "generated_at": timestamp(),
        "status": "run_ledger_ready",
        "run_count": len(rows),
        "latest_runs": rows[-50:],
        "note": "运行账本只记录本地工具输入、输出和状态，不代表线上动作已执行。",
    }
    data_path = root / "data/run-ledger-summary.json"
    report_path = root / "reports" / f"{today()}-run-ledger.md"
    write_json(data_path, payload)
    lines = ["# FLASH CAST 运行账本", "", f"- 运行次数：`{len(rows)}`", "- 记录文件：`logs/run-ledger.jsonl`", "", "## 最近运行", ""]
    for row in rows[-50:]:
        lines.append(f"- `{row.get('run_id', '')}`｜{row.get('run_type', '')}｜{row.get('status', '')}｜{row.get('completed_at', '')}")
    write_text(report_path, "\n".join(lines) + "\n")
    run_id = append_run(root, "run-ledger-report", "complete", [safe_rel(root, root / RUN_LEDGER)], [safe_rel(root, data_path), safe_rel(root, report_path)], run_count=len(rows))
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def scan_active_secrets(root: Path) -> list[str]:
    findings: list[str] = []
    scan_dirs = [root / "data", root / "drafts", root / "logs", root / "reports"]
    patterns = (
        # Public OpenPGP commit signatures contain no private key. Exclude only
        # that exact header; other armor/PEM headers and credentials still flag.
        re.compile(r"-----BEGIN (?!PGP SIGNATURE-----)[A-Z ]+-----"),
        re.compile(r"(?:api[_-]?key|client[_-]?secret|private[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]+", re.I),
        # Require the credential prefix delimiter; otherwise normal words such as
        # "skill-zhuangxiuseogeo" would be incorrectly treated as an API key.
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}|\bAIza[A-Za-z0-9_-]{20,}", re.I),
    )
    for base in scan_dirs:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".jsonl", ".csv", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in patterns:
                if pattern.search(text):
                    findings.append(safe_rel(root, path))
                    break
    return sorted(set(findings))


def qa_gate(root: Path, scope: str = "growth-daily") -> tuple[dict[str, Any], list[Path]]:
    manifest = read_json(root / "data/source-manifest.json")
    conversion = read_json(root / "data/leads/conversion-reconciliation.json")
    queue = read_json(root / "data/action-queue.json")
    blockers: list[str] = []
    warnings: list[str] = []
    if not manifest:
        blockers.append("缺少 data/source-manifest.json；尚未完成数据来源检查。")
    else:
        for source in manifest.get("sources", []):
            if not isinstance(source, dict):
                continue
            if source.get("status") in {"missing", "empty", "invalid"}:
                message = f"数据源：{source.get('source')}: {source.get('decision_use')}"
                if source.get("required_for_core_decision", True):
                    blockers.append(message)
                else:
                    warnings.append(message)
            if source.get("status") == "ready_stale":
                warnings.append(f"数据源过期：{source.get('source')}")
    if not conversion:
        blockers.append("缺少 conversion-reconciliation.json；不能证明 Ads 到真实线索的链路。")
    else:
        blockers.extend(f"转化对账：{item}" for item in conversion.get("blockers", []))
    if not queue:
        blockers.append("缺少 action-queue.json；没有统一的行动和审批状态。")
    blocked_content_qa = []
    for path in sorted((root / "data/content").glob("content-qa-*.json")):
        payload = read_json(path)
        if payload.get("status") == "blocked":
            blocked_content_qa.append(safe_rel(root, path))
    blockers.extend(f"内容 QA 未通过：{path}" for path in blocked_content_qa)
    secret_files = scan_active_secrets(root)
    if secret_files:
        blockers.append("活动目录发现疑似敏感内容：" + ", ".join(secret_files))
    p0_actions = [item for item in queue.get("actions", []) if isinstance(item, dict) and item.get("priority") == "P0" and item.get("status") not in {"completed", "closed"}]
    warnings.append(f"当前未关闭 P0 行动：{len(p0_actions)}")
    status = "blocked" if blockers else "ready_for_owner_review"
    payload = {
        "generated_at": timestamp(),
        "scope": scope,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "checks": {
            "source_manifest": bool(manifest),
            "conversion_reconciliation": bool(conversion),
            "action_queue": bool(queue),
            "content_qa": not blocked_content_qa,
            "active_secret_scan": not secret_files,
        },
        "release_policy": "blocked means no external action; ready_for_owner_review still requires explicit approval for Ads/site/customer actions",
    }
    data_path = root / "data/qa-gate.json"
    report_path = root / "reports" / f"{today()}-qa-gate.md"
    write_json(data_path, payload)
    lines = ["# FLASH CAST Reality Checker 质检放行门", "", f"- 范围：`{scope}`", f"- 状态：`{status}`", "", "## 检查结果", ""]
    lines.extend(f"- {key}：`{'PASS' if value else 'FAIL'}`" for key, value in payload["checks"].items())
    lines.extend(["", "## 阻断", ""])
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- None")
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- None")
    lines.extend(["", "- QA 通过只表示可以进入负责人审核，不代表已经修改广告、发布网站或联系客户。"])
    write_text(report_path, "\n".join(lines) + "\n")
    run_id = append_run(root, "qa-gate", status, [safe_rel(root, path) for path in (root / "data/source-manifest.json", root / "data/leads/conversion-reconciliation.json", root / "data/action-queue.json") if path.exists()], [safe_rel(root, data_path), safe_rel(root, report_path)], blocker_count=len(blockers), scope=scope)
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def ads_daily(root: Path) -> tuple[dict[str, Any], list[Path]]:
    """Run the local, audit-only paid growth decision loop."""
    steps: list[dict[str, Any]] = []
    manifest, manifest_artifacts = source_manifest(root)
    steps.append({"name": "source-manifest", "status": manifest.get("status"), "artifacts": [safe_rel(root, path) for path in manifest_artifacts]})
    conversion, conversion_artifacts = conversion_reconcile(root)
    steps.append({"name": "conversion-reconcile", "status": conversion.get("status"), "artifacts": [safe_rel(root, path) for path in conversion_artifacts]})
    queue, queue_artifacts = action_queue(root)
    steps.append({"name": "action-queue", "status": queue.get("status"), "artifacts": [safe_rel(root, path) for path in queue_artifacts]})
    gate, gate_artifacts = qa_gate(root, "google-ads-daily")
    steps.append({"name": "qa-gate", "status": gate.get("status"), "artifacts": [safe_rel(root, path) for path in gate_artifacts]})
    ads = conversion.get("ads", {})
    payload = {
        "generated_at": timestamp(),
        "status": "ads_daily_blocked" if gate.get("status") == "blocked" else "ads_daily_ready_for_owner_review",
        "mode": "audit_only",
        "steps": steps,
        "ads_summary": ads,
        "source_summary": {"usable": manifest.get("decision_usable_sources", 0), "total": manifest.get("total_sources", 0), "counts": manifest.get("counts", {})},
        "conversion_summary": {
            "status": conversion.get("status"),
            "ads_clicks": ads.get("clicks"),
            "ads_spend_myr": ads.get("spend_myr"),
            "ads_primary_conversions": ads.get("primary_conversions"),
            "ga4_actions": conversion.get("ga4", {}).get("actions"),
            "lead_records": conversion.get("lead_truth", {}).get("lead_count"),
            "qualified_leads": conversion.get("lead_truth", {}).get("qualified"),
        },
        "action_count": queue.get("action_count", 0),
        "qa_status": gate.get("status"),
        "blockers": gate.get("blockers", []),
        "warnings": gate.get("warnings", []),
        "safety": {
            "no_ads_change": True,
            "no_website_change": True,
            "no_customer_outreach": True,
            "owner_approval_required_for_external_actions": True,
        },
    }
    data_path = root / "data/google-ads/ads-daily.json"
    report_path = root / "reports" / f"{today()}-google-ads-daily.md"
    write_json(data_path, payload)
    lines = [
        "# FLASH CAST Google Ads 日检决策环",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 状态：`{payload['status']}`",
        "- 模式：`audit_only`；只读取本地导出和当前项目记录。",
        "",
        "## 执行顺序",
        "",
    ]
    lines.extend(f"- {step['name']}：`{step['status']}`" for step in steps)
    lines.extend(
        [
            "",
            "## 当前 Ads 观察",
            "",
            f"- 展示：`{ads.get('impressions', 'DATA MISSING')}`",
            f"- 点击：`{ads.get('clicks', 'DATA MISSING')}`",
            f"- 花费 MYR：`{ads.get('spend_myr', 'DATA MISSING')}`",
            f"- Ads 主要转化：`{ads.get('primary_conversions', 'DATA MISSING')}`",
            f"- GA4 咨询动作：`{conversion.get('ga4', {}).get('actions', 'DATA MISSING')}`",
            f"- 线索记录数：`{conversion.get('lead_truth', {}).get('lead_count', 'DATA MISSING')}`",
            f"- 已验证有效线索：`{conversion.get('lead_truth', {}).get('qualified', 'DATA MISSING')}`",
            "",
            "## 行动队列",
            "",
            f"- 待复核行动：`{queue.get('action_count', 0)}`",
            f"- QA 阻断：`{len(gate.get('blockers', []))}`",
            "",
            "## 外部动作边界",
            "",
            "- 不修改预算、出价、关键词、否定词、地区、广告状态或转化设置。",
            "- 不发布广告、网站、内容，不发送 WhatsApp、邮件或客户消息。",
            "- 所有建议进入行动队列，等待负责人精确批准。",
            "",
            "## 阻断项",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in gate.get("blockers", [])) if gate.get("blockers") else lines.append("- None")
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {item}" for item in gate.get("warnings", [])) if gate.get("warnings") else lines.append("- None")
    write_text(report_path, "\n".join(lines) + "\n")
    run_id = append_run(root, "ads-daily", payload["status"], [safe_rel(root, root / "data/google-ads")], [safe_rel(root, data_path), safe_rel(root, report_path)], action_count=queue.get("action_count", 0), qa_status=gate.get("status"))
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def append_run(root: Path, run_type: str, status: str, inputs: list[str], outputs: list[str], **extra: Any) -> str:
    # UUID entropy prevents collisions when several operations finish within
    # the same second (the previous timestamp-only ID could collide).
    run_id = f"{today()}-{run_type}-{uuid.uuid4().hex[:10]}"
    append_jsonl(
        root / RUN_LEDGER,
        {
            "run_id": run_id,
            "run_type": run_type,
            "status": status,
            "started_at": timestamp(),
            "completed_at": timestamp(),
            "inputs": inputs,
            "outputs": outputs,
            **extra,
        },
    )
    return run_id


def receipt_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.record_receipt(root, args)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def result_handoff_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        input_path = workflow.safe_path(root, args.input)
        request = json.loads(input_path.read_text(encoding="utf-8"))
        result, artifacts = workflow.record_result_handoff(root, request)
        return result, [input_path, *artifacts]
    except (workflow.WorkflowError, OSError, json.JSONDecodeError) as exc:
        raise OpsError(str(exc)) from exc


def result_handoff_status_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.result_handoff_status(root, args.task_id), [workflow.result_handoff_path(root, args.task_id)]
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def result_handoff_pending_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.result_handoff_pending(root), [root / workflow.RESULT_HANDOFF_DIR]
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def approval_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.record_approval(
            root,
            task_id=args.task_id,
            action_id=args.action_id,
            action_class=args.action_class,
            scope=args.scope,
            approval_id=args.approval_id,
            source_thread_id=args.source_thread_id,
            source_message_ref=args.source_message_ref,
            revoke=args.revoke,
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def policy_check_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.policy_check(
            root,
            task_id=args.task_id,
            department=args.department,
            action_id=args.action_id,
            action_class=args.action_class,
            scope=args.scope,
            approval_id=args.approval_id,
            skill=args.skill,
            consume_approval=args.consume_approval,
            source_project_id=getattr(args, "source_project_id", ""),
            target_project_id=getattr(args, "target_project_id", ""),
            target_department=getattr(args, "target_department", ""),
            target_thread_id=getattr(args, "target_thread_id", ""),
            target_thread_title=getattr(args, "target_thread_title", ""),
            target_cwd=getattr(args, "target_cwd", ""),
            target_sidebar_section_id=getattr(args, "target_sidebar_section_id", ""),
            payload_sha256=getattr(args, "payload_sha256", ""),
            target_automation_status=getattr(args, "target_automation_status", ""),
            retry_blocked_execution_receipt_id=getattr(args, "retry_blocked_execution_receipt_id", ""),
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_reconcile_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.reconcile_workflow(root, task_id=args.task_id, shadow=args.shadow)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_refresh_bindings_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.refresh_workflow_bindings(root, args.task_id)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_rebind_qa_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.rebind_qa_after_replacement(
            root, args.task_id, args.old_chat_task_id, args.health_event_hash
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_rebind_department_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.rebind_department_after_replacement(
            root, args.task_id, args.department, args.old_chat_task_id, args.health_event_hash
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_status_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.workflow_status(root, args.task_id)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_repair_plan_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.repair_dispatch_plan(root, args.task_id)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def workflow_correct_route_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.correct_false_positive_route(root, args.task_id, args.route_id)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def department_reply_check(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return department_reply.check_reply(root, args.department, args.turn_id, Path(args.session_path)), []
    except (workflow.WorkflowError, ValueError, OSError) as exc:
        raise OpsError(str(exc)) from exc


def delegation_check_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.delegation_check(
            root,
            task_id=args.task_id,
            department=args.department,
            benefit=args.benefit,
            work_class=args.work_class,
            scope=args.scope,
            parent_thread_id=args.parent_thread_id,
            parent_project_id=args.parent_project_id,
            parent_cwd=args.parent_cwd,
            requested_parallelism=args.requested_parallelism,
            timeout_seconds=args.timeout_seconds,
            interdependent_work=args.interdependent_work,
            overlapping_write_scope=args.overlapping_write_scope,
            external_side_effect=args.external_side_effect,
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def delegation_record_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.record_delegation(root, args)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def delegation_status_command(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    try:
        return workflow.reconcile_delegations(root, args.task_id)
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc


def slug_for_url(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()
    return slug or "homepage"


def pair_key(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    path = re.sub(r"/(?:en|zh)(?=/|$)", "/{lang}", path)
    return path or "/"


def paired_url(url: str, language: str = "") -> str:
    parsed = urlsplit(url)
    if language == "zh" or "/zh/" in parsed.path or parsed.path.rstrip("/").endswith("/zh"):
        replacement = "/en/"
    else:
        replacement = "/zh/"
    path = parsed.path
    if re.search(r"/(?:en|zh)(?=/|$)", path):
        path = re.sub(r"/(?:en|zh)(?=/|$)", replacement.rstrip("/"), path, count=1)
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)).rstrip("/")


def locate_input(root: Path, active: Path, historical: Path) -> tuple[Path | None, str]:
    active_path = root / active
    if active_path.exists():
        return active_path, "active"
    history_path = root / historical
    if history_path.exists():
        return history_path, "historical_read_only"
    return None, "missing"


def content_inventory(root: Path) -> tuple[Path | None, str, list[dict[str, str]]]:
    path, source_state = locate_input(
        root,
        CONTENT_INVENTORY,
        Path("history/skill-zhuangxiuseogeo/seo-workspace/data/content-publishing-system-map.csv"),
    )
    return path, source_state, read_csv(path) if path else []


def priority_rank(value: str) -> int:
    return {"high": 0, "medium-high": 1, "medium": 2, "review": 3}.get(value.lower(), 9)


def pipeline_for(row: dict[str, str]) -> str:
    page_type = row.get("page_type", "").lower()
    if page_type in {"service", "local", "case-study", "home", "case-study-hub"}:
        return "rich-content"
    return "brief"


def build_content_queue(root: Path, limit: int = 0) -> tuple[dict[str, Any], list[Path]]:
    source_path, source_state, rows = content_inventory(root)
    if not rows:
        raise OpsError("没有找到内容发布系统地图。请先补充 data/content/content-publishing-system-map.csv。")

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        url = row.get("target_url", "").strip()
        if url:
            grouped.setdefault(pair_key(url), []).append(row)

    candidates: list[dict[str, str]] = []
    for group in grouped.values():
        english = next((item for item in group if item.get("language") == "en"), group[0])
        chinese = next((item for item in group if item.get("language") == "zh"), None)
        target = english.get("target_url", "").rstrip("/")
        pair = (chinese or {}).get("target_url", "").rstrip("/") or paired_url(target, "en")
        candidates.append(
            {
                "target_url": target,
                "paired_url": pair,
                "language": "en+zh" if chinese else english.get("language", "unknown"),
                "page_type": english.get("page_type", "unknown"),
                "content_priority": english.get("content_priority", "review"),
                "pipeline": pipeline_for(english),
                "content_package": english.get("content_package", ""),
                "rich_media_slots": english.get("rich_media_slots", ""),
                "owner_input_required": english.get("owner_input_required", ""),
                "status": "queued_for_draft",
                "qa_status": "not_run",
                "owner_approval": "required_before_publish",
            }
        )

    candidates.sort(key=lambda item: (priority_rank(item["content_priority"]), item["target_url"]))
    if limit > 0:
        candidates = candidates[:limit]
    for index, item in enumerate(candidates, start=1):
        item["slot"] = str(index)

    data_dir = root / "data/content"
    report_path = root / "reports" / f"{today()}-content-studio-queue.md"
    json_path = data_dir / "content-studio-queue.json"
    csv_path = data_dir / "content-studio-queue.csv"
    payload = {
        "generated_at": timestamp(),
        "status": "content_studio_queue_ready_for_owner_review",
        "source_path": safe_rel(root, source_path) if source_path else "",
        "source_state": source_state,
        "queue_count": len(candidates),
        "queue": candidates,
        "safety": {
            "draft_only": True,
            "no_cms_write": True,
            "no_media_upload": True,
            "no_publish": True,
            "owner_approval_required": True,
        },
    }
    write_json(json_path, payload)
    write_csv(csv_path, candidates, CONTENT_QUEUE_FIELDS)
    lines = [
        "# FLASH CAST Content Studio 内容队列",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 输入来源：`{payload['source_path']}`（{source_state}）",
        f"- 队列数量：`{len(candidates)}`",
        "- 当前模式：draft-only；只生成内容任务，不登录 CMS、不上传图片、不发布网站。",
        "",
        "## 队列",
        "",
    ]
    for item in candidates[:30]:
        lines.extend(
            [
                f"### {item['slot']}. {item['target_url']}",
                "",
                f"- 中文配对页：`{item['paired_url']}`",
                f"- 页面类型：{item['page_type']}；优先级：{item['content_priority']}；流水线：`{item['pipeline']}`",
                f"- 内容包：{item['content_package'] or '待生成'}",
                f"- 媒体要求：{item['rich_media_slots'] or '待确认'}",
                f"- 业主输入：{item['owner_input_required'] or '无已知输入'}",
                "- 状态：待生成草稿、待 QA、待业主批准",
                "",
            ]
        )
    lines.extend(
        [
            "## 放行边界",
            "",
            "- 中英文页面必须成对检查。",
            "- 生成效果图必须标记为设计方案/效果图方案/概念设计，不能当成真实完工案例。",
            "- 未确认的价格、案例、评价、资质、工期、保修和服务区域不能写成事实。",
            "- 发布前必须经过内容 QA、品牌复核、备份、变更日志和回滚计划。",
        ]
    )
    write_text(report_path, "\n".join(lines) + "\n")
    run_id = append_run(
        root,
        "content-queue",
        "ready_for_owner_review",
        [safe_rel(root, source_path)] if source_path else [],
        [safe_rel(root, json_path), safe_rel(root, csv_path), safe_rel(root, report_path)],
        source_state=source_state,
        queue_count=len(candidates),
    )
    payload["run_id"] = run_id
    write_json(json_path, payload)
    return payload, [json_path, csv_path, report_path]


def find_queue_item(root: Path, target_url: str = "", slot: int = 0) -> dict[str, str]:
    queue_path = root / "data/content/content-studio-queue.json"
    if not queue_path.exists():
        build_content_queue(root, limit=0)
    payload = read_json(queue_path)
    rows = payload.get("queue", [])
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        if target_url and str(raw.get("target_url", "")).rstrip("/") == target_url.rstrip("/"):
            return {str(key): str(value or "") for key, value in raw.items()}
        if slot and str(raw.get("slot", "")) == str(slot):
            return {str(key): str(value or "") for key, value in raw.items()}
    raise OpsError("内容队列里找不到目标页面；请先运行 content-queue，或检查 URL/slot。")


def create_content_draft(root: Path, target_url: str = "", slot: int = 0) -> tuple[dict[str, Any], list[Path]]:
    item = find_queue_item(root, target_url, slot)
    target = item["target_url"]
    slug = slug_for_url(target)
    draft_path = root / "drafts/content-studio" / f"{today()}-{slug}.md"
    data_path = root / "data/content/runs" / f"{today()}-{slug}.json"
    report_path = root / "reports" / f"{today()}-content-studio-{slug}.md"
    package = {
        "generated_at": timestamp(),
        "status": "draft_package_ready_for_content_creator",
        "target_url": target,
        "paired_url": item.get("paired_url", ""),
        "page_type": item.get("page_type", ""),
        "pipeline": item.get("pipeline", "brief"),
        "source_queue_item": item,
        "sections": [
            "Chinese copy",
            "English copy",
            "quick answer",
            "service scope",
            "process",
            "budget and timeline factors without invented figures",
            "FAQ",
            "internal links",
            "CTA",
            "structured data recommendation",
        ],
        "media_plan": item.get("rich_media_slots", ""),
        "claim_boundary": [
            "No unsupported prices, reviews, certifications, awards, timelines or project claims.",
            "Generated visuals must be labeled as design/rendering concepts.",
            "Owner approval is required before publication.",
        ],
    }
    markdown = f"""# Content Studio 草稿包：{target}

- 生成时间：`{package['generated_at']}`
- 状态：`{package['status']}`
- 页面类型：`{package['page_type']}`
- 流水线：`{package['pipeline']}`
- 中文配对页：`{package['paired_url']}`
- 内容来源：`data/content/content-studio-queue.json`

## 中文页面建议文案

> 由 Content Creator 根据公司资料、服务规则、案例和 FAQ 填写。这里先保留结构，避免未经证据直接编写业务承诺。

### 标题 / Meta / H1

- Title：待填写
- Meta description：待填写
- H1：待填写

### 主要内容结构

1. 用户问题和快速答案
2. 服务范围与适用场景
3. 规划/施工流程
4. 预算和工期影响因素（不写未经确认的固定数字）
5. FAQ
6. 内部链接
7. CTA

## English page suggested copy

> Content Creator must produce an English counterpart and keep facts aligned with the Chinese page.

### Title / Meta / H1

- Title：To be drafted
- Meta description：To be drafted
- H1：To be drafted

### Content structure

1. Quick answer and customer problem
2. Scope and suitable scenarios
3. Planning and renovation process
4. Budget and timeline factors without unsupported figures
5. FAQ
6. Internal links
7. CTA

## Media plan

{item.get('rich_media_slots') or '待确认'}

Every generated or illustrative image must include Chinese/English alt text, caption, file name, concept label and claim boundary.

## QA and owner approval

- [ ] 中英文事实一致
- [ ] 目标服务意图清楚
- [ ] 未写入未经确认的价格、案例、评价、资质、工期、保修或排名承诺
- [ ] 概念图没有冒充真实完工案例
- [ ] CTA 与页面服务意图一致
- [ ] Brand Guardian 与 Reality Checker 已检查
- [ ] 发布前已有 backup、change log 和 rollback plan
- [ ] 仍需负责人批准发布
"""
    write_text(draft_path, markdown)
    write_json(data_path, package)
    write_text(
        report_path,
        "\n".join(
            [
                f"# Content Studio 运行报告：{target}",
                "",
                f"- 状态：`{package['status']}`",
                f"- 草稿：`{safe_rel(root, draft_path)}`",
                f"- 结构化包：`{safe_rel(root, data_path)}`",
                "- 执行边界：只生成草稿包，未登录 CMS、未上传媒体、未发布、未部署。",
                "- 下一步：Content Creator 写作 → Brand Guardian/Reality Checker QA → 负责人审批。",
            ]
        )
        + "\n",
    )
    run_id = append_run(
        root,
        "content-draft",
        "draft_only",
        [safe_rel(root, root / "data/content/content-studio-queue.json")],
        [safe_rel(root, draft_path), safe_rel(root, data_path), safe_rel(root, report_path)],
        target_url=target,
    )
    package["run_id"] = run_id
    write_json(data_path, package)
    return package, [draft_path, data_path, report_path]


RISK_PATTERNS = (
    (r"(?:RM|MYR)\s*\d[\d,]*(?:\.\d+)?\s*(?:起|最低|保证)?", "固定价格/起步价"),
    (r"(?:最便宜|最低价|第一名|第一选择|保证排名|保证上首页|guaranteed|#1|cheapest)", "排名或价格保证"),
    (r"(?:客户评价|五星评价|customer review|testimonial|award|奖项|认证|certified)", "评价/奖项/认证"),
    (r"(?:\d+\s*(?:天|个月|weeks?|days?)\s*(?:完工|完成|finish|complete))", "固定工期"),
)


def content_qa(root: Path, draft_path: str, require_bilingual: bool = True) -> tuple[dict[str, Any], list[Path]]:
    path = resolve_path(root, draft_path)
    if not path.exists():
        raise OpsError(f"找不到内容草稿：{draft_path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[dict[str, str]] = []
    blockers: list[str] = []
    if require_bilingual:
        lower = text.casefold()
        zh_ok = "中文页面" in text or "中文文案" in text or "chinese copy" in lower
        en_ok = "english page" in lower or "english copy" in lower or "英文页面" in text
        if not zh_ok:
            blockers.append("缺少中文页面区块。")
            findings.append({"code": "missing_zh", "severity": "critical"})
        if not en_ok:
            blockers.append("缺少英文页面区块。")
            findings.append({"code": "missing_en", "severity": "critical"})

    for pattern, label in RISK_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I):
            line = text[max(0, text.rfind("\n", 0, match.start()) + 1): text.find("\n", match.end()) if text.find("\n", match.end()) >= 0 else len(text)]
            if re.search(r"(?:不得|不能|不要|禁止|without|do not|not claim|claim boundary|待填写|to be drafted)", line, flags=re.I):
                continue
            findings.append({"code": "unsupported_claim", "severity": "critical", "evidence": match.group(0)[:120], "category": label})
            blockers.append(f"发现未经证据支持的{label}：{match.group(0)[:80]}")

    concept_mentions = bool(re.search(r"设计方案|效果图方案|概念设计|概念标签|design concept|rendering concept|concept label", text, flags=re.I))
    if re.search(r"效果图|rendering|concept image|概念图", text, flags=re.I) and not concept_mentions:
        blockers.append("提到了效果图/概念图，但没有明确概念标签。")
        findings.append({"code": "missing_concept_label", "severity": "critical"})

    status = "blocked" if blockers else "ready_for_owner_review"
    payload = {
        "generated_at": timestamp(),
        "status": status,
        "draft_path": safe_rel(root, path),
        "require_bilingual": require_bilingual,
        "findings": findings,
        "blockers": blockers,
        "owner_approval_required": True,
    }
    data_path = root / "data/content" / f"content-qa-{today()}-{slug_for_url(path.stem)}.json"
    report_path = root / "reports" / f"{today()}-content-qa-{slug_for_url(path.stem)}.md"
    write_json(data_path, payload)
    report_lines = [
        "# Content Studio 内容 QA",
        "",
        f"- 草稿：`{payload['draft_path']}`",
        f"- 状态：`{status}`",
        f"- 发现数：`{len(findings)}`",
        "",
        "## Blockers",
        "",
    ]
    report_lines.extend(f"- {item}" for item in blockers) if blockers else report_lines.append("- None")
    report_lines.extend(
        [
            "",
            "## 边界",
            "",
            "- QA 通过只代表可以进入负责人审核，不代表已经发布。",
            "- 任何价格、案例、评价、资质、工期、保修或排名承诺仍需要证据。",
        ]
    )
    write_text(report_path, "\n".join(report_lines) + "\n")
    run_id = append_run(
        root,
        "content-qa",
        status,
        [safe_rel(root, path)],
        [safe_rel(root, data_path), safe_rel(root, report_path)],
        blocker_count=len(blockers),
    )
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


class PageSignalsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_robots = ""
        self.canonical = ""
        self.hreflang: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta" and attributes.get("name", "").casefold() == "robots":
            self.meta_robots = attributes.get("content", "")
        if tag.lower() == "link" and attributes.get("rel", "").casefold() == "canonical":
            self.canonical = attributes.get("href", "")
        if tag.lower() == "link" and attributes.get("rel", "").casefold() == "alternate" and attributes.get("hreflang"):
            self.hreflang.append((attributes["hreflang"], attributes.get("href", "")))


def fetch_url(url: str, timeout: int = 8) -> tuple[int, str, str]:
    request = Request(url, headers={"User-Agent": "FLASHCAST-SEO-Audit/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
            return int(response.status), response.geturl(), body
    except HTTPError as exc:
        return int(exc.code), url, ""
    except (URLError, TimeoutError, OSError):
        return 0, url, ""


def parse_sitemap(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    urls: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text:
            urls.append(element.text.strip())
    return urls


def expected_pair_exists(url: str, links: list[tuple[str, str]]) -> bool:
    expected = paired_url(url)
    normalized = {urljoin(url, href).rstrip("/") for _, href in links if href}
    return expected.rstrip("/") in normalized or any(lang in {"en", "zh", "x-default"} for lang, _ in links)


def local_seo_rows(root: Path) -> tuple[list[dict[str, str]], str]:
    path, state = locate_input(
        root,
        SEO_INVENTORY,
        Path("history/skill-zhuangxiuseogeo/seo-workspace/data/url-inventory.csv"),
    )
    return read_csv(path) if path else [], state


def seo_index_audit(root: Path, site: str, remote: bool, max_urls: int) -> tuple[dict[str, Any], list[Path]]:
    rows: list[dict[str, str]] = []
    source_state = "remote_sitemap" if remote else "local_inventory"
    source_path = ""
    if remote:
        sitemap_url = urljoin(site.rstrip("/") + "/", "sitemap.xml")
        status, _, body = fetch_url(sitemap_url)
        urls = parse_sitemap(body) if status == 200 else []
        if not urls:
            raise OpsError(f"无法读取公开 sitemap：{sitemap_url}（HTTP {status or 'network error'}）")
        for url in urls[:max_urls]:
            page_status, final_url, page_body = fetch_url(url)
            parser = PageSignalsParser()
            parser.feed(page_body)
            meta = parser.meta_robots.lower()
            indexable = page_status == 200 and "noindex" not in meta
            canonical = urljoin(final_url, parser.canonical) if parser.canonical else ""
            canonical_self = canonical.rstrip("/") == final_url.rstrip("/") if canonical else False
            redirected = final_url.rstrip("/") != url.rstrip("/")
            hreflang = "yes" if expected_pair_exists(url, parser.hreflang) else "no"
            issue = []
            if page_status != 200:
                issue.append("http_not_200")
            if redirected:
                issue.append("redirect_in_sitemap")
            if not indexable:
                issue.append("noindex_or_unavailable")
            if parser.canonical and not canonical_self:
                issue.append("wrong_canonical")
            if hreflang == "no" and "/en/" in url or hreflang == "no" and "/zh/" in url:
                issue.append("hreflang_pair_missing")
            rows.append(
                {
                    "url": url,
                    "language": "zh" if "/zh/" in url else "en" if "/en/" in url else "unknown",
                    "page_type": "unknown",
                    "lastmod": "",
                    "http_status": str(page_status),
                    "final_url": final_url,
                    "redirected": "yes" if redirected else "no",
                    "robots_allowed": "not_checked",
                    "meta_robots": parser.meta_robots,
                    "indexable": "yes" if indexable else "no",
                    "canonical_url": canonical,
                    "canonical_self": "yes" if canonical_self else "no",
                    "hreflang_pair": hreflang,
                    "sitemap_included": "yes",
                    "priority_issue": ";".join(issue),
                    "action": "fix_before_publish" if issue else "monitor",
                    "notes": "remote read-only audit",
                }
            )
    else:
        inventory, source_state = local_seo_rows(root)
        source_path_obj, _ = locate_input(
            root,
            SEO_INVENTORY,
            Path("history/skill-zhuangxiuseogeo/seo-workspace/data/url-inventory.csv"),
        )
        source_path = safe_rel(root, source_path_obj) if source_path_obj else ""
        rows = inventory[:max_urls]
        for row in rows:
            row.setdefault("priority_issue", "")
            row.setdefault("action", "monitor")
            row.setdefault("notes", "local inventory audit")
            issues: list[str] = []
            if row.get("http_status") not in {"", "200"}:
                issues.append("http_not_200")
            if row.get("redirected", "").lower() == "yes":
                issues.append("redirect_in_sitemap")
            if row.get("robots_allowed", "").lower() == "no":
                issues.append("robots_blocked")
            if row.get("meta_robots", "").lower().find("noindex") >= 0 or row.get("indexable", "").lower() == "no":
                issues.append("noindex_or_not_indexable")
            if row.get("canonical_self", "").lower() == "no":
                issues.append("wrong_canonical")
            if row.get("sitemap_included", "").lower() == "no":
                issues.append("not_in_sitemap")
            if row.get("language") in {"en", "zh"} and row.get("hreflang_pair", "").lower() == "no":
                issues.append("hreflang_pair_missing")
            row["priority_issue"] = ";".join(dict.fromkeys(issues))
            row["action"] = "fix_before_publish" if issues else "monitor"
            rows[rows.index(row)] = row

    counts = {
        "total": len(rows),
        "with_issues": sum(bool(row.get("priority_issue")) for row in rows),
        "http_not_200": sum("http_not_200" in row.get("priority_issue", "") for row in rows),
        "redirects": sum("redirect" in row.get("priority_issue", "") for row in rows),
        "indexability": sum("indexable" in row.get("priority_issue", "") or "noindex" in row.get("priority_issue", "") for row in rows),
        "canonical": sum("canonical" in row.get("priority_issue", "") for row in rows),
        "hreflang": sum("hreflang" in row.get("priority_issue", "") for row in rows),
    }
    payload = {
        "generated_at": timestamp(),
        "status": "seo_index_audit_complete",
        "site": site,
        "source_state": source_state,
        "source_path": source_path,
        "remote_fetch": remote,
        "max_urls": max_urls,
        "counts": counts,
        "rows": rows,
        "safety": "read-only; no sitemap submission, indexing request or website change executed",
    }
    data_json = root / "data/seo/site-index-reconcile.json"
    data_csv = root / "data/seo/site-index-reconcile.csv"
    report = root / "reports" / f"{today()}-seo-index-audit.md"
    write_json(data_json, payload)
    write_csv(data_csv, rows, SEO_FIELDS)
    report_lines = [
        "# FLASH CAST SEO 技术审计与索引对账",
        "",
        f"- 站点：`{site}`",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 数据来源：`{source_path or '公开 sitemap'}`（{source_state}）",
        f"- 检查 URL 数：`{counts['total']}`",
        f"- 有问题 URL：`{counts['with_issues']}`",
        "- 模式：只读；未提交 sitemap、未请求收录、未修改网站。",
        "",
        "## 问题统计",
        "",
        f"- HTTP 非 200：{counts['http_not_200']}",
        f"- sitemap 中包含重定向：{counts['redirects']}",
        f"- noindex/不可索引：{counts['indexability']}",
        f"- canonical 问题：{counts['canonical']}",
        f"- 中英文配对/hreflang 问题：{counts['hreflang']}",
        "",
        "## 需要优先处理的页面",
        "",
    ]
    problem_rows = [row for row in rows if row.get("priority_issue")]
    report_lines.extend(f"- `{row.get('url')}`：{row.get('priority_issue')}；动作：{row.get('action')}" for row in problem_rows[:80])
    if not problem_rows:
        report_lines.append("- 未发现输入清单中标记的问题；仍需结合当前 GSC 证据复核。")
    report_lines.extend(
        [
            "",
            "## 解释",
            "",
            "- 本报告只能证明公开页面或本地清单的技术信号，不能保证 Google 收录或排名。",
            "- 本地历史清单如果不是当前抓取结果，只能作为历史参考；要判断当前状态请使用 `--remote` 并补充 GSC。",
        ]
    )
    write_text(report, "\n".join(report_lines) + "\n")
    run_id = append_run(
        root,
        "seo-index-audit",
        "complete",
        [source_path] if source_path else [],
        [safe_rel(root, data_json), safe_rel(root, data_csv), safe_rel(root, report)],
        site=site,
        remote_fetch=remote,
        counts=counts,
    )
    payload["run_id"] = run_id
    write_json(data_json, payload)
    return payload, [data_json, data_csv, report]


def event_id(event: dict[str, Any]) -> str:
    identity = "\x1f".join(str(event.get(key, "")) for key in ("memory_type", "entity", "signal", "evidence", "observed_at"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _learning_input_sha(event: dict[str, Any], supplied_observed_at: str) -> str:
    """Every caller-supplied value is identity; an omitted timestamp stays omitted."""
    value = {key: item for key, item in event.items()
             if key not in {"observed_at", "freshness_status"}}
    value["observed_at"] = supplied_observed_at
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _learning_existing(events: list[dict[str, Any]], event: dict[str, Any],
                       supplied_observed_at: str) -> dict[str, Any] | None:
    for row in events:
        if row.get("input_sha256") == event["input_sha256"]:
            return row
        # Legacy rows/references remain byte-for-byte unchanged. A full input
        # comparison (including outcome) avoids the old partial-ID collision.
        if not row.get("input_sha256") and all(
            row.get(key, [] if isinstance(value, list) else "") == value for key, value in event.items()
            if key not in {"input_sha256", "event_id", "freshness_status", "observed_at"}
        ) and (not supplied_observed_at or row.get("observed_at") == supplied_observed_at):
            return row
    return None


def _learning_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise OpsError("学习写入路径必须位于项目内")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise OpsError("学习写入路径不能包含软链接")
    return resolve_path(root, str(path))


def _learning_report_once(path: Path, content: str) -> None:
    """Freeze with an exclusive link; failures never expose a partial report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OpsError("学习报告路径不能是软链接")
    encoded = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise OpsError("学习报告身份冲突；保留已有文件，禁止覆盖")
        return
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".learning-", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != encoded:
                raise OpsError("学习报告并发身份冲突；禁止覆盖")
    finally:
        if temporary.exists():
            temporary.unlink()


def _learning_report_readback(root: Path, event: dict[str, Any]) -> Path | None:
    if not event.get("report_path"):
        # No known immutable historical report pin: do not rebuild missing text.
        return None
    path = _learning_path(root, str(event["report_path"]))
    if path.is_symlink() or not path.is_file():
        raise OpsError("DATA_MISSING: 已登记学习报告缺失；保留旧事件与引用，不重建旧文字")
    if hashlib.sha256(path.read_bytes()).hexdigest() != event.get("report_sha256"):
        raise OpsError("学习报告指纹变化；保留原文件并等待准确核验")
    return path


def _append_learning_event(root: Path, event: dict[str, Any]) -> None:
    path = _learning_path(root, LEARNING_EVENTS)
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    # Validate every old row before appending; malformed history is not ignored.
    for line in previous.splitlines():
        if line.strip():
            try:
                if not isinstance(json.loads(line), dict):
                    raise ValueError("not an object")
            except ValueError as exc:
                raise OpsError("学习账本存在坏行；禁止覆盖或隐式跳过") from exc
    workflow.atomic_write_text(path, previous + ("\n" if previous and not previous.endswith("\n") else "") +
                               json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _learning_run_once(root: Path, event: dict[str, Any], run_type: str,
                       inputs: list[str], outputs: list[str]) -> str:
    run_id = str(event["run_id"])
    _learning_path(root, RUN_LEDGER)
    if not any(row.get("run_id") == run_id for row in read_jsonl(root / RUN_LEDGER)):
        append_jsonl(root / RUN_LEDGER, {
            "run_id": run_id, "run_type": run_type, "status": "recorded",
            "started_at": event["observed_at"], "completed_at": timestamp(),
            "inputs": inputs, "outputs": outputs, "event_id": event["event_id"],
            "input_sha256": event["input_sha256"],
        })
    return run_id


def learning_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    with workflow.workflow_lock(root):
        return _learning_record_locked(root, args)


def _learning_record_locked(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    event = {
        "observed_at": args.observed_at or timestamp(),
        "source": args.source or "owner_or_department_observation",
        "memory_type": args.memory_type, "entity": args.entity,
        "signal": args.signal, "evidence": args.evidence, "outcome": args.outcome,
        "next_action": args.next_action, "confidence": args.confidence,
    }
    event["input_sha256"] = _learning_input_sha(event, str(args.observed_at or ""))
    event["event_id"] = event["input_sha256"]
    events = read_jsonl(root / LEARNING_EVENTS)
    existing = _learning_existing(events, event, str(args.observed_at or ""))
    memory_path = _learning_path(root, "data/learning/learning-memory.json")
    if existing and not existing.get("input_sha256"):
        return {**read_json(memory_path), "status": "duplicate_ignored",
                "event_id": existing["event_id"], "historical_report": "DATA_MISSING_OR_UNPINNED"}, []
    report_path = _learning_path(root, f"reports/learning-memory-{event['input_sha256']}.md")
    if existing:
        event = existing
        report_path = _learning_report_readback(root, event)
        if any(row.get("run_id") == event["run_id"] for row in read_jsonl(root / RUN_LEDGER)):
            return {**read_json(memory_path), "status": "duplicate_ignored",
                    "report_path": safe_rel(root, report_path), "run_id": event["run_id"]}, [memory_path, report_path]
    else:
        report_lines = [
            "# FLASH CAST 学习记忆更新", "", "- 状态：`recorded`",
            f"- 事件指纹：`{event['event_id']}`", f"- 记忆类型：`{event['memory_type']}`",
            f"- 对象：`{event['entity']}`", f"- 信号：{event['signal']}",
            f"- 证据：{event['evidence']}", f"- 结果：{event['outcome']}",
            f"- 下一步：{event['next_action']}", f"- 置信度：`{event['confidence']}`", "",
            "学习记录只用于后续分析和周复盘，不自动修改广告、网站或客户数据。",
        ]
        _learning_report_once(report_path, "\n".join(report_lines) + "\n")
        event.update(report_path=safe_rel(root, report_path),
                     report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                     run_id="learning-record-" + event["input_sha256"])
        _append_learning_event(root, event)
        events.append(event)
    latest: dict[str, dict[str, Any]] = {}
    for row in events:
        latest[f"{row.get('memory_type', '')}|{row.get('entity', '')}"] = row
    payload = {"generated_at": timestamp(), "status": "learning_memory_ready",
               "event_count": len(events), "latest_by_entity": latest,
               "source": safe_rel(root, root / LEARNING_EVENTS), "run_id": event["run_id"],
               "report_path": safe_rel(root, report_path)}
    workflow.atomic_write_json(memory_path, payload)
    _learning_run_once(root, event, "learning-record", [safe_rel(root, root / LEARNING_EVENTS)],
                       [safe_rel(root, memory_path), safe_rel(root, report_path)])
    return payload, [memory_path, report_path]


def department_learning_event_id(event: dict[str, Any]) -> str:
    identity = "\x1f".join(
        str(event.get(key, ""))
        for key in (
            "department",
            "task_id",
            "memory_type",
            "lesson",
            "signal",
            "evidence",
            "observed_at",
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def department_learning_config(root: Path, department: str) -> dict[str, Any]:
    registry = read_json(root / DEPARTMENT_LEARNING_REGISTRY)
    for item in registry.get("departments", []):
        if isinstance(item, dict) and item.get("id") == department:
            return item
    raise OpsError(
        f"未找到部门学习配置：{department}；请先检查 {DEPARTMENT_LEARNING_REGISTRY.as_posix()}"
    )


def learning_freshness(review_after: str, last_verified_at: str) -> str:
    value = str(review_after or "").strip()
    if not value:
        return "legacy_or_review_date_missing" if not last_verified_at else "review_date_missing"
    try:
        deadline = dt.date.fromisoformat(value[:10])
    except ValueError:
        return "invalid_review_after"
    return "stale" if deadline < now_utc().astimezone(BUSINESS_TZ).date() else "current"


def department_learning_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    with workflow.workflow_lock(root):
        return _department_learning_record_locked(root, args)


def _department_learning_record_locked(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    department = str(args.department).strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", department):
        raise OpsError("部门身份不是合法注册值")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", str(args.task_id)):
        raise OpsError("学习任务身份不能包含路径或不安全字符")
    config = department_learning_config(root, department)
    memory_path_value = str(config.get("memory_path", "")).strip()
    if not memory_path_value:
        raise OpsError(f"部门学习配置缺少 memory_path：{department}")
    memory_path = _learning_path(root, memory_path_value)
    if memory_path.is_symlink():
        raise OpsError("学习记忆不能写入软链接")
    evidence = [item.strip() for item in str(args.evidence).split(";") if item.strip()]
    if not evidence:
        raise OpsError("至少需要一条证据路径")
    if any(is_sensitive_path(Path(item)) for item in evidence):
        raise OpsError("学习记录不能引用密码、Token、Cookie、OAuth、私钥或凭据路径")

    event = {
        "observed_at": args.observed_at or timestamp(),
        "source": args.source or "department_observation",
        "department": department,
        "task_id": args.task_id,
        "memory_type": args.memory_type,
        "lesson": args.lesson,
        "signal": args.signal,
        "evidence": evidence,
        "outcome": args.outcome,
        "next_action": args.next_action,
        "confidence": args.confidence,
        "lesson_status": args.lesson_status,
        "data_window": str(getattr(args, "data_window", "") or ""),
        "last_verified_at": str(getattr(args, "last_verified_at", "") or ""),
        "review_after": str(getattr(args, "review_after", "") or ""),
        "conflicts_with": [
            item.strip()
            for item in str(getattr(args, "conflicts_with", "") or "").split(";")
            if item.strip()
        ],
        "supersedes": [
            item.strip()
            for item in str(getattr(args, "supersedes", "") or "").split(";")
            if item.strip()
        ],
    }
    event["freshness_status"] = learning_freshness(event["review_after"], event["last_verified_at"])
    event["input_sha256"] = _learning_input_sha(event, str(args.observed_at or ""))
    event["event_id"] = event["input_sha256"]

    event_log = root / LEARNING_EVENTS
    events = read_jsonl(event_log)
    existing = _learning_existing(events, event, str(args.observed_at or ""))
    duplicate = existing is not None
    if existing and not existing.get("input_sha256"):
        return {"status": "department_learning_duplicate_ignored", "department": department,
                "task_id": args.task_id, "event_id": existing["event_id"],
                "event_count": len([row for row in events if row.get("department") == department]),
                "memory_path": safe_rel(root, memory_path), "report_path": None,
                "historical_report": "DATA_MISSING_OR_UNPINNED", "run_id": None}, []
    report_path = _learning_path(root, f"reports/learning-{department}-{event['input_sha256']}.md")
    if existing:
        event = existing
        report_path = _learning_report_readback(root, event)
        if any(row.get("run_id") == event["run_id"] for row in read_jsonl(root / RUN_LEDGER)):
            return {"status": "department_learning_duplicate_ignored", "department": department,
                    "task_id": args.task_id, "event_id": event["event_id"],
                    "event_count": len([row for row in events if row.get("department") == department]),
                    "memory_path": safe_rel(root, memory_path), "report_path": safe_rel(root, report_path),
                    "run_id": event["run_id"]}, [memory_path, report_path]
    memory = read_json(memory_path)
    memory["schema_version"] = "2.0"
    memory["department"] = department
    memory["display_name"] = config.get("name", memory.get("display_name", department))
    memory["status"] = "active"
    memory["skill_path"] = "skills/flashcast-department-learning/SKILL.md"
    memory["professional_skill"] = str(config.get("professional_skill") or memory.get("professional_skill") or "")
    memory.setdefault("inherited_lessons", [])
    memory.setdefault("verified_lessons", [])
    memory.setdefault("provisional_lessons", [])
    memory.setdefault("retired_lessons", [])
    memory.setdefault("blocked_patterns", [])

    lesson_entry = {
        "lesson_id": event["event_id"],
        "task_id": event["task_id"],
        "lesson": event["lesson"],
        "signal": event["signal"],
        "evidence": event["evidence"],
        "outcome": event["outcome"],
        "next_action": event["next_action"],
        "confidence": event["confidence"],
        "status": event["lesson_status"],
        "observed_at": event["observed_at"],
        "data_window": event["data_window"],
        "last_verified_at": event["last_verified_at"],
        "review_after": event["review_after"],
        "freshness_status": event["freshness_status"],
        "conflicts_with": event["conflicts_with"],
        "supersedes": event["supersedes"],
        "record_version": "2.0",
    }
    buckets = {
        "verified": "verified_lessons",
        "provisional": "provisional_lessons",
        "retired": "retired_lessons",
    }
    bucket = buckets[event["lesson_status"]]
    if not any(item.get("lesson_id") == event["event_id"] for item in memory[bucket]):
        memory[bucket].append(lesson_entry)

    department_events = [row for row in events if row.get("department") == department]
    memory["event_count"] = len(department_events) + (0 if duplicate else 1)
    memory["last_updated_at"] = timestamp()
    memory["latest_event"] = lesson_entry
    status = "department_learning_duplicate_ignored" if duplicate else "department_learning_recorded"
    report_lines = [
        f"# {memory['display_name']} 部门学习记录",
        "",
        "- 状态：`department_learning_recorded`",
        f"- 事件指纹：`{event['event_id']}`",
        f"- 任务：`{args.task_id}`",
        f"- 学习状态：`{args.lesson_status}`",
        f"- 经验：{args.lesson}",
        f"- 观察信号：{args.signal}",
        f"- 证据：{'; '.join(evidence)}",
        f"- 结果：{args.outcome}",
        f"- 下一步：{args.next_action}",
        f"- 置信度：`{args.confidence}`",
        f"- 数据窗口：`{event['data_window'] or 'N/A'}`",
        f"- 最后核验：`{event['last_verified_at'] or 'N/A'}`",
        f"- 复核日期：`{event['review_after'] or 'N/A'}`；新鲜度：`{event['freshness_status']}`",
        "",
        "本记录用于下一次同部门任务的上下文继承；不代表已批准任何外部执行。",
    ]
    if not duplicate:
        _learning_report_once(report_path, "\n".join(report_lines) + "\n")
        event.update(report_path=safe_rel(root, report_path),
                     report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                     run_id="department-learning-record-" + event["input_sha256"])
        _append_learning_event(root, event)
    workflow.atomic_write_json(memory_path, memory)
    run_id = _learning_run_once(root, event, "department-learning-record",
                               [safe_rel(root, event_log)] + evidence,
                               [safe_rel(root, memory_path), safe_rel(root, report_path)])
    payload = {
        "status": status,
        "department": department,
        "task_id": args.task_id,
        "event_id": event["event_id"],
        "event_count": memory["event_count"],
        "memory_path": safe_rel(root, memory_path),
        "report_path": safe_rel(root, report_path),
        "run_id": run_id,
    }
    return payload, [memory_path, report_path]


def department_learning_status(root: Path) -> tuple[dict[str, Any], list[Path]]:
    registry = read_json(root / DEPARTMENT_LEARNING_REGISTRY)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in registry.get("departments", []):
        if not isinstance(item, dict):
            continue
        department = str(item.get("id", ""))
        memory_path = root / str(item.get("memory_path", ""))
        memory = read_json(memory_path)
        exists = memory_path.exists()
        if not exists:
            missing.append(department)
        all_lessons = [
            lesson
            for bucket in ("inherited_lessons", "verified_lessons", "provisional_lessons", "retired_lessons")
            for lesson in memory.get(bucket, [])
            if isinstance(lesson, dict)
        ]
        stale_count = sum(
            learning_freshness(str(lesson.get("review_after", "")), str(lesson.get("last_verified_at", ""))) == "stale"
            for lesson in all_lessons
        )
        legacy_count = sum(not lesson.get("record_version") for lesson in all_lessons)
        rows.append(
            {
                "department": department,
                "name": item.get("name", department),
                "memory_path": safe_rel(root, memory_path),
                "professional_skill": item.get("professional_skill", ""),
                "professional_skill_exists": resolve_path(root, str(item.get("professional_skill"))).exists() if item.get("professional_skill") else False,
                "exists": exists,
                "inherited_count": len(memory.get("inherited_lessons", [])),
                "verified_count": len(memory.get("verified_lessons", [])),
                "provisional_count": len(memory.get("provisional_lessons", [])),
                "retired_count": len(memory.get("retired_lessons", [])),
                "event_count": memory.get("event_count", 0),
                "last_updated_at": memory.get("last_updated_at", ""),
                "stale_count": stale_count,
                "legacy_provisional_count": legacy_count,
            }
        )

    payload = {
        "generated_at": timestamp(),
        "status": "department_learning_ready" if not missing else "department_learning_blocked",
        "skill_path": "skills/flashcast-department-learning/SKILL.md",
        "department_count": len(rows),
        "ready_count": sum(1 for row in rows if row["exists"]),
        "missing_departments": missing,
        "departments": rows,
    }
    data_path = root / "data/learning/department-learning-status.json"
    report_path = root / "reports" / f"{today()}-department-learning-status.md"
    write_json(data_path, payload)
    report_lines = [
        "# FLASH CAST 部门学习状态",
        "",
        f"- 状态：`{payload['status']}`",
        f"- 学习 Skill：`{payload['skill_path']}`",
        f"- 部门数：`{payload['department_count']}`",
        f"- 已有记忆档案：`{payload['ready_count']}`",
        "",
        "| 部门 | 继承经验 | 已验证 | 待验证 | 已归档 | 过期 | Legacy | 学习事件 | 最近更新 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    report_lines.extend(
        f"| {row['name']} | {row['inherited_count']} | {row['verified_count']} | {row['provisional_count']} | {row['retired_count']} | {row['stale_count']} | {row['legacy_provisional_count']} | {row['event_count']} | {row['last_updated_at'] or '待更新'} |"
        for row in rows
    )
    if missing:
        report_lines.extend(["", f"缺少记忆档案：{', '.join(missing)}"])
    write_text(report_path, "\n".join(report_lines) + "\n")
    run_id = append_run(
        root,
        "department-learning-status",
        "complete" if not missing else "blocked",
        [safe_rel(root, root / DEPARTMENT_LEARNING_REGISTRY)],
        [safe_rel(root, data_path), safe_rel(root, report_path)],
        department_count=len(rows),
        ready_count=payload["ready_count"],
    )
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def numeric(row: dict[str, str], *keys: str) -> float:
    for key in keys:
        value = row.get(key, "")
        if value != "":
            try:
                return float(str(value).replace(",", "").replace("RM", "").strip())
            except ValueError:
                continue
    return 0.0


def display_number(value: Any, decimals: int = 0) -> str:
    if value is None:
        return "DATA MISSING"
    return f"{float(value):.{decimals}f}"


def weekly_review(root: Path) -> tuple[dict[str, Any], list[Path]]:
    events = read_jsonl(root / LEARNING_EVENTS)
    run_rows = read_jsonl(root / RUN_LEDGER)
    current_runs = [row for row in run_rows if str(row.get("completed_at", "")).startswith(today()[:7])]
    ads = summarize_ads(root)
    ads_summary = {
        "file": ads.get("file", ""),
        "impressions": ads.get("impressions"),
        "clicks": ads.get("clicks"),
        "spend_myr": ads.get("spend_myr"),
        "conversions": ads.get("primary_conversions"),
    }
    payload = {
        "generated_at": timestamp(),
        "status": "weekly_review_ready",
        "week_ending": today(),
        "learning_event_count": len(events),
        "run_count_in_current_month": len(current_runs),
        "ads_summary": ads_summary,
        "data_gaps": [
            "真实线索质量、报价和成交如果未补入 data/leads，不能计算真实 CPL/ROI。",
            "Google Ads CSV 是历史窗口，不能单独代表当前账户状态。",
        ],
        "next_review": "下周复核搜索词、转化追踪、真实线索质量和已批准动作结果。",
    }
    data_path = root / "data/learning/weekly-review.json"
    report_path = root / "reports" / f"{today()}-weekly-growth-review.md"
    write_json(data_path, payload)
    report = f"""# FLASH CAST 周增长复盘

- 生成时间：`{payload['generated_at']}`
- 复盘截止：`{payload['week_ending']}`
- 学习事件：`{payload['learning_event_count']}`
- 本月工具运行记录：`{payload['run_count_in_current_month']}`

## Google Ads 观察

- 数据文件：`{ads_summary['file'] or 'DATA MISSING'}`
- 展示：`{display_number(ads_summary['impressions'])}`
- 点击：`{display_number(ads_summary['clicks'])}`
- 花费（MYR）：`{display_number(ads_summary['spend_myr'], 2)}`
- 转化：`{display_number(ads_summary['conversions'])}`

这些数字只反映当前项目已有导出，不能替代真实线索、报价、签单或完整账单。

## 本周应该复盘

- 学习事件是否转化成明确行动。
- 已批准动作是否有执行证据和结果回传。
- 搜索词、落地页、表单、电话、WhatsApp 和销售状态是否对得上。
- 中英文内容是否保持事实一致。

## 数据缺口

{chr(10).join(f'- {item}' for item in payload['data_gaps'])}

## 下周

{payload['next_review']}
"""
    write_text(report_path, report)
    run_id = append_run(
        root,
        "weekly-review",
        "complete",
        [ads_summary["file"]] if ads_summary["file"] else [],
        [safe_rel(root, data_path), safe_rel(root, report_path)],
        learning_event_count=len(events),
    )
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


SENSITIVE_PARTS = (".env", "password", "passwd", "secret", "token", "cookie", "oauth", "private", ".pem", ".key", "credentials")


def is_sensitive_path(path: Path) -> bool:
    for part in path.parts:
        lower = part.casefold()
        if lower in {".env", ".env.local", ".env.production", ".env.development", "private", "credentials"}:
            return True
        if lower.endswith((".pem", ".key")):
            return True
        if any(fragment in lower for fragment in ("password", "passwd", "secret", "token", "cookie", "oauth")):
            return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(root: Path, source_value: str, change_id: str) -> tuple[dict[str, Any], list[Path]]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,80}", change_id):
        raise OpsError("change_id 只能包含字母、数字、点、下划线和短横线。")
    source = resolve_path(root, source_value)
    if not source.exists():
        raise OpsError(f"备份源不存在：{source_value}")
    source_rel = safe_rel(root, source)
    if source_rel == "backups" or source_rel.startswith("backups/") or source_rel.startswith("history/"):
        raise OpsError("不能把 backups/ 或 history/ 作为新的备份源，避免嵌套和误操作。")
    destination = root / "backups" / change_id
    if destination.exists():
        raise OpsError(f"备份目录已存在，不覆盖：{safe_rel(root, destination)}")
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    files = [source] if source.is_file() else [path for path in source.rglob("*") if path.is_file()]
    for path in files:
        rel = safe_rel(root, path)
        if is_sensitive_path(Path(rel)):
            skipped.append(rel)
            continue
        backup_rel = Path("payload") / rel
        target = destination / backup_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        items.append({"original": rel, "backup": backup_rel.as_posix(), "sha256": sha256_file(path), "size": path.stat().st_size})
    if not items:
        shutil.rmtree(destination, ignore_errors=True)
        raise OpsError("没有可安全备份的文件；可能全部命中了敏感文件规则。")
    manifest = {
        "created_at": timestamp(),
        "status": "backup_ready",
        "change_id": change_id,
        "source": source_rel,
        "backup_root": safe_rel(root, destination),
        "items": items,
        "sensitive_skipped": skipped,
        "rollback_default": "dry_run",
    }
    manifest_path = destination / "manifest.json"
    write_json(manifest_path, manifest)
    report_path = root / "reports" / f"{today()}-backup-{change_id}.md"
    write_text(
        report_path,
        "\n".join(
            [
                f"# 备份报告：{change_id}",
                "",
                f"- 源路径：`{source_rel}`",
                f"- 备份目录：`{safe_rel(root, destination)}`",
                f"- 文件数：`{len(items)}`",
                f"- 跳过敏感文件：`{len(skipped)}`",
                "- 回滚模式：默认 dry-run；真正恢复必须提供 `--apply --owner-approved`。",
            ]
        )
        + "\n",
    )
    append_jsonl(root / CHANGE_LOG, {"timestamp": timestamp(), "change_id": change_id, "status": "backup_created", "files": [item["original"] for item in items], "manifest": safe_rel(root, manifest_path)})
    run_id = append_run(root, "backup", "complete", [source_rel], [safe_rel(root, manifest_path), safe_rel(root, report_path)], change_id=change_id, item_count=len(items))
    manifest["run_id"] = run_id
    write_json(manifest_path, manifest)
    return manifest, [manifest_path, report_path]


def change_log(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    change = {
        "timestamp": timestamp(),
        "change_id": args.change_id,
        "status": args.status,
        "summary": args.summary,
        "files": args.files,
        "approval": "owner_approved" if args.owner_approved else "not_provided",
    }
    append_jsonl(root / CHANGE_LOG, change)
    report_path = root / "reports" / f"{today()}-change-log-{args.change_id}.md"
    write_text(report_path, "\n".join([f"# 变更日志：{args.change_id}", "", f"- 状态：`{args.status}`", f"- 摘要：{args.summary}", f"- 文件：{', '.join(args.files) or 'N/A'}", f"- 批准：`{change['approval']}`"]) + "\n")
    run_id = append_run(root, "change-log", "recorded", [], [safe_rel(root, report_path)], change_id=args.change_id)
    change["run_id"] = run_id
    return change, [report_path]


def rollback(root: Path, change_id: str, apply: bool, owner_approved: bool) -> tuple[dict[str, Any], list[Path]]:
    manifest_path = root / "backups" / change_id / "manifest.json"
    manifest = read_json(manifest_path)
    if not manifest:
        raise OpsError(f"找不到备份清单：{safe_rel(root, manifest_path)}")
    if apply and not owner_approved:
        raise OpsError("回滚写入被阻止：--apply 必须同时提供 --owner-approved。")
    items = manifest.get("items", [])
    actions: list[dict[str, Any]] = []
    pre_dir = root / "backups" / f"{change_id}-pre-rollback-{now_utc().strftime('%Y%m%d%H%M%S')}"
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        original = resolve_path(root, str(item.get("original", "")))
        backup_file = resolve_path(root, f"backups/{change_id}/{item.get('backup', '')}")
        if not backup_file.exists():
            actions.append({"original": safe_rel(root, original), "status": "missing_backup"})
            continue
        action = {"original": safe_rel(root, original), "backup": safe_rel(root, backup_file), "status": "would_restore"}
        if apply:
            if original.exists() and original.is_file():
                pre_target = pre_dir / safe_rel(root, original)
                pre_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, pre_target)
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, original)
            action["status"] = "restored"
        actions.append(action)
    status = "rollback_completed" if apply else "rollback_dry_run_ready"
    report_path = root / "reports" / f"{today()}-rollback-{change_id}.md"
    report_lines = [f"# 回滚报告：{change_id}", "", f"- 状态：`{status}`", f"- 备份清单：`{safe_rel(root, manifest_path)}`", f"- 文件数：`{len(actions)}`", ""]
    report_lines.extend(f"- `{item['original']}`：{item['status']}" for item in actions)
    report_lines.extend(["", "- 默认只生成回滚预演；真实恢复必须由负责人明确批准。"])
    write_text(report_path, "\n".join(report_lines) + "\n")
    append_jsonl(root / CHANGE_LOG, {"timestamp": timestamp(), "change_id": change_id, "status": status, "items": actions, "pre_rollback_backup": safe_rel(root, pre_dir) if apply else ""})
    run_id = append_run(root, "rollback", status, [safe_rel(root, manifest_path)], [safe_rel(root, report_path)], change_id=change_id, apply=apply)
    payload = {"status": status, "change_id": change_id, "items": actions, "report": safe_rel(root, report_path), "run_id": run_id}
    return payload, [report_path]


PROTECTED_MARKERS = ("receipt", "approval", "authorization", "backup", "rollback", "change-log", "learning", "handoff", "migration", "reconciliation", "source-manifest", "site-index-reconcile")


def workspace_maintenance(root: Path, apply: bool, owner_approved: bool, older_than_days: int) -> tuple[dict[str, Any], list[Path]]:
    """Age alone is not a cleanup grant. Production execution stays off in this candidate."""
    if apply:
        raise OpsError("清理写入未准入：需独立验收、准确使用记录与冻结计划；旧 --owner-approved 不再放行按年龄移动。")
    usage_path = root / "data/maintenance/cleanup-usage.json"
    if not usage_path.is_file():
        return {"status": "usage_observations_required", "candidate_count": 0,
                "deletion_executed": False, "execution_enabled": False,
                "next_action": "核验结束任务、7天使用情况、引用和正式保留项后运行tools/safe_cleanup.py"}, []
    import safe_cleanup
    value = safe_cleanup.scan(root, read_json(usage_path))
    value.update(status="frozen_plan_preview", candidate_count=len(value["items"]), execution_enabled=False)
    return value, []


def chat_binding_is_healthy(binding: dict[str, Any], verification_ttl_hours: int = 0) -> bool:
    return workflow._chat_binding_healthy(
        binding, verification_ttl_hours=verification_ttl_hours
    )


def chat_binding_is_stale(binding: dict[str, Any], verification_ttl_hours: int) -> bool:
    return (
        verification_ttl_hours > 0
        and workflow._chat_binding_healthy(binding, verification_ttl_hours=0)
        and not workflow._chat_binding_healthy(
            binding, verification_ttl_hours=verification_ttl_hours
        )
    )


def department_health_record(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    """Record a live fixed-thread health observation without storing chat text."""

    registry_path = root / "data/department-registry.json"
    registry = read_json(registry_path)
    department = str(args.department or "").strip()
    item = next(
        (row for row in registry.get("departments", []) if str(row.get("id")) == department),
        None,
    )
    if not item:
        raise OpsError(f"未登记部门：{department}")
    binding = item.get("chat_binding", {}) if isinstance(item.get("chat_binding"), dict) else {}
    expected = {
        "task_id": str(binding.get("task_id") or ""),
        "project_id": str(binding.get("project_id") or ""),
        "cwd": str(binding.get("cwd") or ""),
        "title": str(binding.get("title") or ""),
        "sidebar_section_id": str(binding.get("sidebar_section_id") or ""),
    }
    observed = {
        "task_id": str(args.task_id or ""),
        "project_id": str(args.project_id or ""),
        "cwd": str(args.cwd or ""),
        "title": str(args.title or ""),
        "sidebar_section_id": str(args.sidebar_section_id or ""),
    }
    mismatches = [key for key, value in expected.items() if not value or observed[key] != value]
    if mismatches:
        raise OpsError("部门现场身份不匹配：" + ", ".join(mismatches))
    reply_ref = str(args.reply_ref or "").strip()
    reply_sha256 = str(args.reply_sha256 or "").strip().lower()
    if reply_ref and not re.fullmatch(r"[A-Za-z0-9._:-]{3,160}", reply_ref):
        raise OpsError("--reply-ref 只能保存消息或轮次标识，不能保存聊天正文")
    run_status = str(args.last_run_status or "success").strip().lower()
    reply_nonempty = bool(args.reply_nonempty)
    if run_status == "success":
        if not reply_nonempty or not re.fullmatch(r"[0-9a-f]{64}", reply_sha256):
            raise OpsError("健康恢复必须提供非空回复证明和 64 位 SHA-256")
        if not reply_ref:
            raise OpsError("健康恢复必须提供 --reply-ref")
    checked_at = timestamp()
    reply_observed_at = str(getattr(args, "reply_observed_at", "") or checked_at)
    observed_time = workflow._parse_observed_at(reply_observed_at)
    if run_status == "success":
        ttl = int((registry.get("health_policy", {}) or {}).get("verification_ttl_hours", 26))
        now = dt.datetime.now(dt.timezone.utc)
        if observed_time is None or not dt.timedelta(minutes=-5) <= now - observed_time <= dt.timedelta(hours=ttl):
            raise OpsError("回复证据过期或时间无效，不能刷新为当前健康")
    event = {
        "schema_version": "1.0",
        "department": department,
        "task_id": observed["task_id"],
        "project_id": observed["project_id"],
        "cwd_sha256": hashlib.sha256(observed["cwd"].encode("utf-8")).hexdigest(),
        "title_sha256": hashlib.sha256(observed["title"].encode("utf-8")).hexdigest(),
        "sidebar_section_id": observed["sidebar_section_id"],
        "reply_ref": reply_ref,
        "reply_sha256": reply_sha256,
        "reply_nonempty": reply_nonempty,
        "reply_observed_at": reply_observed_at,
        "live_status": str(args.live_status or "unknown"),
        "last_run_status": run_status,
        "failure_class": str(args.failure_class or ""),
        "next_retry_at": str(args.next_retry_at or ""),
        "checked_at": checked_at,
        "chat_body_stored": False,
    }
    event["event_hash"] = workflow.sha256_value(event)
    with workflow.workflow_lock(root):
        current = read_json(registry_path)
        current_item = next(
            (row for row in current.get("departments", []) if str(row.get("id")) == department),
            None,
        )
        if not current_item:
            raise OpsError(f"登记过程中部门消失：{department}")
        current_binding = current_item.setdefault("chat_binding", {})
        if any(str(current_binding.get(key) or "") != value for key, value in expected.items()):
            raise OpsError("登记期间部门绑定已变化，禁止覆盖")
        same_observation = (
            bool(reply_ref) and current_binding.get("last_reply_ref") == reply_ref
            and current_binding.get("last_run_status") == run_status
            and current_binding.get("failure_class", "") == event["failure_class"]
            and current_binding.get("last_reply_sha256", "") == reply_sha256
        )
        if same_observation:
            return {"status": "department_health_unchanged", "department": department,
                    "dispatch_eligible": current_binding.get("dispatch_eligible", False),
                    "reply_health": current_binding.get("reply_health"), "chat_body_stored": False}, [registry_path]
        new_observation = not reply_ref or current_binding.get("last_reply_ref") != reply_ref
        current_binding["last_health_check_at"] = checked_at
        current_binding["last_reply_ref"] = reply_ref
        current_binding["last_reply_sha256"] = reply_sha256
        current_binding["last_health_check_task_id"] = f"department-health-{department}-{today().replace('-', '')}"
        current_binding["last_run_status"] = run_status
        current_binding["failure_class"] = event["failure_class"]
        current_binding["next_retry_at"] = event["next_retry_at"]
        if run_status == "success":
            current_binding.update(
                {
                    "status": "bound_and_visible",
                    "last_verified_at": reply_observed_at,
                    "last_health_check_at": reply_observed_at,
                    "reply_health": "healthy_visible_reply_verified",
                    "dispatch_eligible": True,
                    "consecutive_empty_reply_turns": 0,
                    "consecutive_failures": 0,
                    "last_success_at": checked_at,
                }
            )
        else:
            current_binding["reply_health"] = f"failed_{event['failure_class'] or run_status}"
            current_binding["dispatch_eligible"] = False
            current_binding["consecutive_failures"] = int(current_binding.get("consecutive_failures", 0) or 0) + int(new_observation)
        current["updated_at"] = today()
        workflow.atomic_write_json(registry_path, current)
        health_log = root / "logs/department-health.jsonl"
        workflow.append_jsonl_locked(health_log, event)
    payload = {
        "status": "department_health_recorded",
        "department": department,
        "dispatch_eligible": run_status == "success",
        "reply_health": "healthy_visible_reply_verified" if run_status == "success" else f"failed_{event['failure_class'] or run_status}",
        "checked_at": checked_at,
        "chat_body_stored": False,
        "event_hash": event["event_hash"],
    }
    run_id = append_run(
        root,
        "department-health-record",
        payload["status"],
        [safe_rel(root, registry_path)],
        [safe_rel(root, registry_path), safe_rel(root, health_log)],
        department=department,
        dispatch_eligible=payload["dispatch_eligible"],
    )
    payload["run_id"] = run_id
    return payload, [registry_path, health_log]


def _automation_toml_string(text: str, key: str) -> str:
    match = re.search(
        rf'(?m)^{re.escape(key)}\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', text
    )
    if not match:
        return ""
    try:
        return str(json.loads('"' + match.group(1) + '"'))
    except json.JSONDecodeError:
        return match.group(1)


def global_routing_audit(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    """Audit every local Codex automation against a hash-only ownership registry."""

    registry_path = root / "data/global-governance/automation-routing-registry.json"
    registry = read_json(registry_path)
    if not registry:
        raise OpsError("缺少 data/global-governance/automation-routing-registry.json")
    automations_root = Path(str(args.automations_root)).expanduser().resolve()
    expected_root = (Path.home() / ".codex" / "automations").resolve()
    if automations_root != expected_root:
        raise OpsError("全局审计只允许读取 ~/.codex/automations")
    live_rows: list[dict[str, Any]] = []
    live_automation_rows: list[dict[str, Any]] = []
    live_automation_snapshot_present = False
    if args.live_snapshot:
        snapshot_path_value = resolve_path(root, str(args.live_snapshot))
        snapshot_value = read_json(snapshot_path_value)
        live_rows = [row for row in snapshot_value.get("threads", []) if isinstance(row, dict)]
        live_automation_snapshot_present = "automations" in snapshot_value
        live_automation_rows = [
            row for row in snapshot_value.get("automations", []) if isinstance(row, dict)
        ]
    live_by_id = {str(row.get("thread_id") or row.get("id") or ""): row for row in live_rows}
    live_automations_by_id = {
        str(row.get("automation_id") or row.get("id") or ""): row
        for row in live_automation_rows
        if row.get("automation_id") or row.get("id")
    }
    expected_by_id = {
        str(row.get("automation_id") or ""): row
        for row in registry.get("automations", [])
        if isinstance(row, dict) and row.get("automation_id")
    }
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for config_path in sorted(automations_root.glob("*/automation.toml")):
        text_value = config_path.read_text(encoding="utf-8", errors="replace")
        automation_id = _automation_toml_string(text_value, "id") or config_path.parent.name
        name = _automation_toml_string(text_value, "name")
        status = _automation_toml_string(text_value, "status").upper()
        kind = _automation_toml_string(text_value, "kind").lower()
        target_thread_id = _automation_toml_string(text_value, "target_thread_id")
        prompt = _automation_toml_string(text_value, "prompt")
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        expected = expected_by_id.get(automation_id)
        reasons: list[str] = []
        audit_status = "pass"
        live = live_by_id.get(target_thread_id, {}) if target_thread_id else {}
        if not expected:
            audit_status = "needs_registration"
            reasons.append("automation_not_in_global_registry")
        else:
            if target_thread_id != str(expected.get("target_thread_id") or ""):
                reasons.append("target_thread_id_mismatch")
            expected_kind = str(expected.get("kind") or "").lower()
            if expected_kind and kind != expected_kind:
                reasons.append("automation_kind_mismatch")
            allowed_status = {str(item).upper() for item in expected.get("allowed_status", ["ACTIVE", "PAUSED"])}
            if status not in allowed_status:
                reasons.append("automation_status_not_allowed")
            expected_prompt_sha = str(expected.get("prompt_sha256") or "")
            if expected_prompt_sha and prompt_sha256 != expected_prompt_sha:
                reasons.append("prompt_changed_review_required")
            if target_thread_id:
                if not live:
                    reasons.append("live_target_unverified")
                else:
                    comparisons = {
                        "project_id": str(live.get("project_id") or live.get("projectId") or ""),
                        "cwd": str(live.get("cwd") or ""),
                        "title": str(live.get("title") or ""),
                    }
                    for key, actual in comparisons.items():
                        expected_value = str(expected.get(key) or "")
                        if expected_value and actual != expected_value:
                            reasons.append(f"target_{key}_mismatch")
            live_automation = live_automations_by_id.get(automation_id, {})
            if live_automation_snapshot_present:
                if not live_automation:
                    reasons.append("live_automation_unverified")
                else:
                    live_status = str(live_automation.get("status") or "").upper()
                    live_kind = str(live_automation.get("kind") or "").lower()
                    live_target_thread_id = str(live_automation.get("target_thread_id") or "")
                    if live_status not in allowed_status:
                        reasons.append("live_automation_status_not_allowed")
                    if live_target_thread_id != str(expected.get("target_thread_id") or ""):
                        reasons.append("live_target_thread_id_mismatch")
                    if expected_kind and live_kind != expected_kind:
                        reasons.append("live_automation_kind_mismatch")
                    if live_status and status != live_status:
                        reasons.append("disk_live_status_drift")
                    if target_thread_id != live_target_thread_id:
                        reasons.append("disk_live_target_thread_id_drift")
                    if kind and live_kind and kind != live_kind:
                        reasons.append("disk_live_kind_drift")
            elif args.live_snapshot and registry.get("policy", {}).get(
                "require_live_automation_snapshot", False
            ):
                reasons.append("live_automation_snapshot_missing")
            hard_mismatch = any(
                reason in {
                    "target_thread_id_mismatch",
                    "automation_kind_mismatch",
                    "target_project_id_mismatch",
                    "target_cwd_mismatch",
                    "target_title_mismatch",
                    "live_target_thread_id_mismatch",
                    "live_automation_kind_mismatch",
                    "disk_live_target_thread_id_drift",
                    "disk_live_kind_drift",
                }
                for reason in reasons
            )
            if hard_mismatch:
                audit_status = "quarantined_pending_owner_approval"
            elif reasons:
                audit_status = "review_required"
        results.append(
            {
                "automation_id": automation_id,
                "name_sha256": hashlib.sha256(name.encode("utf-8")).hexdigest(),
                "config_path_sha256": hashlib.sha256(str(config_path).encode("utf-8")).hexdigest(),
                "status": status,
                "kind": kind,
                "target_thread_id": target_thread_id,
                "live_status": str(live_automations_by_id.get(automation_id, {}).get("status") or "").upper(),
                "live_kind": str(live_automations_by_id.get(automation_id, {}).get("kind") or "").lower(),
                "live_target_thread_id": str(
                    live_automations_by_id.get(automation_id, {}).get("target_thread_id") or ""
                ),
                "prompt_sha256": prompt_sha256,
                "audit_status": audit_status,
                "reasons": reasons,
                "prompt_body_stored": False,
            }
        )
        seen_ids.add(automation_id)
    for live_id in sorted(set(live_automations_by_id) - seen_ids - set(expected_by_id)):
        live = live_automations_by_id[live_id]
        results.append(
            {
                "automation_id": live_id,
                "live_status": str(live.get("status") or "").upper(),
                "live_kind": str(live.get("kind") or "").lower(),
                "live_target_thread_id": str(live.get("target_thread_id") or ""),
                "audit_status": "needs_registration",
                "reasons": ["live_automation_not_in_global_registry"],
                "prompt_body_stored": False,
            }
        )
    for missing_id in sorted(set(expected_by_id) - seen_ids):
        results.append(
            {
                "automation_id": missing_id,
                "audit_status": "registered_automation_missing",
                "reasons": ["automation_config_not_found"],
                "prompt_body_stored": False,
            }
        )
    counts = {
        status: sum(row.get("audit_status") == status for row in results)
        for status in (
            "pass",
            "needs_registration",
            "review_required",
            "quarantined_pending_owner_approval",
            "registered_automation_missing",
        )
    }
    payload = {
        "status": "global_routing_audit_ready",
        "audited_at": timestamp(),
        "shadow_only": bool(args.shadow),
        "writes_performed": not bool(args.shadow),
        "automation_count": len(results),
        "counts": counts,
        "results": results,
        "existing_mismatch_action": "quarantine_pending_owner_approval",
        "automatic_pause_performed": False,
        "prompt_or_chat_body_stored": False,
    }
    artifacts: list[Path] = [registry_path]
    if args.live_snapshot:
        artifacts.append(resolve_path(root, str(args.live_snapshot)))
    if not args.shadow:
        latest_path = root / "data/global-governance/latest-audit.json"
        ledger_path = root / "logs/global-governance/automation-routing-ledger.jsonl"
        workflow.atomic_write_json(latest_path, payload)
        with workflow.workflow_lock(root):
            workflow.append_jsonl_locked(ledger_path, payload)
        artifacts.extend([latest_path, ledger_path])
    return payload, artifacts


def dispatch_plan(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    import human_control
    with human_control.action_gate(root):
        return _dispatch_plan_unpaused(root, args)


def _dispatch_plan_unpaused(root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[Path]]:
    """Create a deterministic, auditable department routing plan.

    This command records what should be sent to Codex department tasks. It
    deliberately does not create or message app conversations; those are
    Codex application state and must be verified in the task list separately.
    """

    request = str(args.request or "").strip()
    if not request:
        raise OpsError("分派计划需要 --request，不能用空任务生成路由")

    registry_path = root / "data/department-registry.json"
    rules_path = root / "data/department-routing-rules.json"
    contract_path = root / "data/task-contract.json"
    registry = read_json(registry_path)
    rules = read_json(rules_path)
    contract = read_json(contract_path)
    if not registry or not rules or not contract:
        raise OpsError("缺少部门注册表、路由规则或任务协议；请先确认 data/department-*.json 和 data/task-contract.json")

    normalized = request.casefold()
    matches: list[tuple[int, dict[str, Any]]] = []
    for route in rules.get("routes", []):
        terms = [str(term) for term in route.get("match_any", [])]
        exclusions = [str(term) for term in route.get("exclude_if_any", [])]
        if any(term.casefold() in normalized for term in exclusions):
            continue
        score = sum(1 for term in terms if term.casefold() in normalized)
        if score:
            matches.append((score, route))
    if matches:
        # A single owner request can contain several independent intents
        # (e.g. Ads + copy + conversion diagnosis). Merge all matching
        # routes instead of silently selecting only the highest-scoring one.
        score = sum(item[0] for item in matches)
        matched_routes = [item[1] for item in matches]
        route_ids = [str(item.get("id", "unknown")) for item in matched_routes]
        merged_dependencies: dict[str, list[str]] = {}
        for matched_route in matched_routes:
            for department, dependencies in matched_route.get("department_dependencies", {}).items():
                department_id = str(department)
                existing = merged_dependencies.setdefault(department_id, [])
                for dependency in dependencies:
                    dependency_id = str(dependency)
                    if dependency_id not in existing:
                        existing.append(dependency_id)
        route = {
            "id": route_ids[0] if len(route_ids) == 1 else "multi:" + "+".join(route_ids),
            "required_departments": list(
                dict.fromkeys(
                    str(department)
                    for item in matched_routes
                    for department in item.get("required_departments", [])
                )
            ),
            "parallel_departments": list(
                dict.fromkeys(
                    str(department)
                    for item in matched_routes
                    for department in item.get("parallel_departments", [])
                )
            ),
            "follow_up_departments": list(
                dict.fromkeys(
                    str(department)
                    for item in matched_routes
                    for department in item.get("follow_up_departments", [])
                )
            ),
            "department_dependencies": merged_dependencies,
            "approval_required": any(bool(item.get("approval_required", False)) for item in matched_routes),
        }
        route_source = "matched_multi" if len(matched_routes) > 1 else "matched"
    else:
        route = rules.get("fallback", {})
        score = 0
        route_source = "fallback"

    departments = {str(item.get("id")): item for item in registry.get("departments", [])}
    verification_ttl_hours = int(
        (registry.get("health_policy", {}) or {}).get("verification_ttl_hours", 0) or 0
    )
    required = list(dict.fromkeys(str(item) for item in route.get("required_departments", [])))
    parallel = list(dict.fromkeys(str(item) for item in route.get("parallel_departments", required)))
    follow_up = [
        item for item in dict.fromkeys(str(value) for value in route.get("follow_up_departments", []))
        if item not in parallel
    ]
    dependency_map = {
        str(department): list(dict.fromkeys(str(dependency) for dependency in dependencies))
        for department, dependencies in route.get("department_dependencies", {}).items()
    }
    for department in parallel:
        dependency_map.setdefault(department, [])
    for department in follow_up:
        dependency_map.setdefault(department, list(parallel))
    selected = list(
        dict.fromkeys(
            parallel
            + follow_up
            + list(dependency_map)
            + [dependency for dependencies in dependency_map.values() for dependency in dependencies]
        )
    )
    unknown = [department for department in selected if department not in departments]
    if unknown:
        raise OpsError(f"路由规则引用了未登记部门：{', '.join(unknown)}")
    for department, dependencies in dependency_map.items():
        if department in dependencies:
            raise OpsError(f"路由依赖不能自引用：{department}")

    execution_waves: list[list[str]] = []
    resolved: set[str] = set()
    remaining = set(selected)
    while remaining:
        ready = [
            department
            for department in selected
            if department in remaining and all(dependency in resolved for dependency in dependency_map.get(department, []))
        ]
        if not ready:
            cycle = ", ".join(department for department in selected if department in remaining)
            raise OpsError(f"路由依赖存在循环或无法解析：{cycle}")
        execution_waves.append(ready)
        resolved.update(ready)
        remaining.difference_update(ready)
    execution_wave_by_department = {
        department: index
        for index, wave in enumerate(execution_waves, start=1)
        for department in wave
    }

    task_id = str(args.task_id or "").strip()
    if not task_id:
        digest = hashlib.sha256((today() + request).encode("utf-8")).hexdigest()[:10]
        task_id = f"fc-{today().replace('-', '')}-{digest}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,100}", task_id):
        raise OpsError("--task-id 只能包含字母、数字、点、下划线和连字符")

    department_plans: list[dict[str, Any]] = []
    for department in selected:
        item = departments[department]
        binding = item.get("chat_binding", {})
        binding_status = str(binding.get("status", "unbound"))
        ui_verified = binding_status == "bound_and_visible"
        reply_health = str(binding.get("reply_health", "legacy_unspecified"))
        dispatch_eligible = binding.get("dispatch_eligible", True) is not False
        stale_health = chat_binding_is_stale(binding, verification_ttl_hours)
        chat_healthy = chat_binding_is_healthy(binding, verification_ttl_hours)
        if not ui_verified:
            dispatch_status = "blocked_ui_visibility"
        elif stale_health:
            dispatch_status = "blocked_health_stale"
        elif not chat_healthy:
            dispatch_status = "blocked_chat_health"
        else:
            dispatch_status = "ready_to_send"
        depends_on = dependency_map.get(department, [])
        phase = "parallel" if not depends_on else "follow_up"
        department_plans.append(
            {
                "department": department,
                "name": item.get("name", department),
                "phase": phase,
                "chat_title": binding.get("title", item.get("name", department)),
                "chat_binding_status": binding_status,
                "chat_reply_health": reply_health,
                "chat_health_stale": stale_health,
                "dispatch_eligible": dispatch_eligible,
                "chat_task_id": binding.get("task_id"),
                "chat_project_id": binding.get("project_id"),
                "chat_cwd": binding.get("cwd"),
                "dispatch_status": dispatch_status,
                "role_config": item.get("role_config"),
                "professional_skill": item.get("professional_skill"),
                "approved_subskills": item.get("approved_subskills", []),
                "approved_subskill_paths": item.get("approved_subskill_paths", []),
                "department_readme": item.get("department_readme"),
                "input_paths": item.get("input_paths", []),
                "output_paths": item.get("output_paths", []),
                "depends_on": depends_on,
                "execution_wave": execution_wave_by_department[department],
                "prompt_template": "prompts/department-window.md",
            }
        )

    ambiguity_blocked = route_source == "fallback" and route.get("dispatch_allowed") is False
    blocked = [item["department"] for item in department_plans if item["dispatch_status"] != "ready_to_send"]
    blocked_statuses = {item["dispatch_status"] for item in department_plans if item["dispatch_status"] != "ready_to_send"}
    if ambiguity_blocked:
        plan_status = "blocked_ambiguous_request"
    elif not blocked:
        plan_status = "ready_to_send"
    elif "blocked_health_stale" in blocked_statuses:
        plan_status = "blocked_health_stale"
    elif "blocked_chat_health" in blocked_statuses:
        plan_status = "blocked_chat_health"
    else:
        plan_status = "blocked_ui_visibility"
    specialist_departments = [department for department in selected if department != "operations"]
    controller_action = (
        "clarify_owner_request"
        if ambiguity_blocked
        else "dispatch_and_wait"
        if specialist_departments
        else "execute_controller_scope"
    )
    payload = {
        "schema_version": "1.2",
        "created_at": timestamp(),
        "task_id": task_id,
        "status": plan_status,
        "mode": "plan_only_no_chat_side_effects",
        "request": request,
        "route": {
            "id": route.get("id", "fallback"),
            "source": route_source,
            "match_score": score,
            "approval_required": bool(route.get("approval_required", False)),
        },
        "required_departments": required,
        "parallel_departments": parallel,
        "follow_up_departments": follow_up,
        "department_dependencies": dependency_map,
        "execution_waves": execution_waves,
        "departments": department_plans,
        "blocked_departments": blocked,
        "controller_action": controller_action,
        "controller_may_execute_specialist_work": False,
        "specialist_departments": specialist_departments,
        "dispatch_gate": {
            "required_before_specialist_execution": [
                "dispatch_plan_created",
                "chat_binding_verified",
                "routing_policy_allowed",
                "message_sent",
                "department_acknowledged",
            ],
            "on_failure": "blocked_no_controller_fallback",
            "sent_status_requires_message_success": True,
        },
        "shared_context": [
            "data/learning/department-inheritance.json",
            "data/learning/department-learning-registry.json",
            "data/task-contract.json",
        ],
        "completion_rule": contract.get("completion_rule", "等待聊天回传和结构化证据"),
        "safety": "本命令只生成本地分派计划，不创建聊天、不发送消息、不修改外部系统。",
    }

    try:
        workflow_snapshot, workflow_initialized = workflow.initialize_workflow(
            root,
            task_id=task_id,
            request=request,
            plan_status=plan_status,
            departments=department_plans,
            owner_approval_required=bool(route.get("approval_required", False)),
        )
    except workflow.WorkflowError as exc:
        raise OpsError(str(exc)) from exc
    payload["workflow"] = {
        "initialized": workflow_initialized,
        "current_state": workflow_snapshot.get("current_state"),
        "snapshot": safe_rel(root, workflow.snapshot_path(root, task_id)),
        "idempotent_request_hash": workflow_snapshot.get("request_hash"),
    }
    if workflow_snapshot.get("current_state") == "blocked":
        payload["status"] = workflow_snapshot["plan_status"]

    artifact_path = root / "logs/dispatch" / f"{task_id}.json"
    report_path = root / "reports" / f"{today()}-dispatch-{task_id}.md"
    write_json(artifact_path, payload)
    report_lines = [
        f"# FLASH CAST 部门分派计划：{task_id}",
        "",
        f"- 状态：`{payload['status']}`",
        f"- 路由：`{payload['route']['id']}`（{route_source}，命中 {score} 项）",
        "- 模式：只生成计划，不创建聊天、不发送消息、不修改外部系统。",
        f"- 总控动作：`{controller_action}`；允许代做专业工作：`false`。",
        f"- 原始任务：{request}",
        f"- 工作流：`{payload['workflow']['current_state']}`；幂等初始化：`{str(workflow_initialized).lower()}`",
        "",
        "## 部门任务",
        "",
    ]
    for item in department_plans:
        report_lines.extend(
            [
                f"### {item['name']}（{item['department']}）",
                "",
                f"- 阶段：`{item['phase']}`；执行波次：`wave_{item['execution_wave']}`；分派状态：`{item['dispatch_status']}`",
                f"- 聊天标题：`{item['chat_title']}`；绑定状态：`{item['chat_binding_status']}`；回复健康：`{item['chat_reply_health']}`；允许派工：`{str(item['dispatch_eligible']).lower()}`",
                f"- 项目 ID：`{item.get('chat_project_id') or '缺失'}`；cwd：`{item.get('chat_cwd') or '缺失'}`；发送前必须通过 `thread_message` 路由预检。",
                f"- 专业 Skill：`{item.get('professional_skill') or '未登记'}`",
                f"- 批准子 Skill：{', '.join(item['approved_subskills']) if item['approved_subskills'] else '无'}",
                f"- 依赖：{', '.join(item['depends_on']) if item['depends_on'] else '无'}",
                f"- 输出位置：{', '.join(item['output_paths'])}",
                "",
            ]
        )
    if blocked:
        report_lines.extend(
            [
                "## 阻断",
                "",
                "- 以下部门还没有经过 Codex 任务列表可见性验证：" + ", ".join(blocked),
                "- 在完成独立任务绑定前，总控不得回复“已分派”或“部门已回复”。",
                "",
            ]
        )
    if specialist_departments:
        report_lines.extend(
            [
                "## 总控执行门禁",
                "",
                "- 必须把任务包发送到上述固定部门任务，并等待部门在自己的聊天中确认。",
                "- 消息发送成功前不得把状态写成 `sent`，也不得由运营总控调用专业 Skill 或代做交付物。",
                "- 发送失败时状态为 `blocked_no_controller_fallback`。",
                "",
            ]
        )
    write_text(report_path, "\n".join(report_lines) + "\n")
    run_id = append_run(
        root,
        "dispatch-plan",
        payload["status"],
        [safe_rel(root, registry_path), safe_rel(root, rules_path), safe_rel(root, contract_path)],
        [safe_rel(root, artifact_path), safe_rel(root, report_path)],
        task_id=task_id,
        blocked_departments=blocked,
    )
    payload["run_id"] = run_id
    write_json(artifact_path, payload)
    return payload, [artifact_path, report_path]


def department_status(root: Path) -> tuple[dict[str, Any], list[Path]]:
    """Validate local department configuration and recorded chat bindings."""

    registry_path = root / "data/department-registry.json"
    registry = read_json(registry_path)
    if not registry:
        raise OpsError("缺少 data/department-registry.json，无法检查部门状态")
    policy = read_json(root / "data/action-policy.json")
    routing_policy = policy.get("routing_policy", {}) if isinstance(policy, dict) else {}
    expected_project_id = str(routing_policy.get("source_project_id") or "")
    expected_cwd = str(routing_policy.get("source_project_root") or "")
    verification_ttl_hours = int(
        (registry.get("health_policy", {}) or {}).get("verification_ttl_hours", 0) or 0
    )

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    errors: list[str] = []
    replacement_recovery: list[dict[str, Any]] = []
    for item in registry.get("departments", []):
        department = str(item.get("id", "")).strip()
        if not department:
            errors.append("存在没有 id 的部门")
            continue
        if department in seen_ids:
            errors.append(f"部门 id 重复：{department}")
        seen_ids.add(department)
        role_config = str(item.get("role_config", ""))
        readme = str(item.get("department_readme", ""))
        raw_binding = item.get("chat_binding", {})
        binding = raw_binding if isinstance(raw_binding, dict) else {}
        binding_status = str(binding.get("status", "unbound"))
        reply_health = str(binding.get("reply_health", "legacy_unspecified"))
        dispatch_eligible = binding.get("dispatch_eligible", True) is not False
        health_stale = chat_binding_is_stale(binding, verification_ttl_hours)
        chat_healthy = chat_binding_is_healthy(binding, verification_ttl_hours)
        missing_files = [path for path in (role_config, readme) if not (root / path).exists()]
        if missing_files:
            errors.append(f"{department} 缺少配置文件：{', '.join(missing_files)}")
        if binding_status not in {"unbound", "pending_ui_verification", "bound_and_visible", "unavailable"}:
            errors.append(f"{department} 使用了未知聊天绑定状态：{binding_status}")
        binding_project_id = str(binding.get("project_id") or "")
        binding_cwd = str(binding.get("cwd") or "")
        if binding_status == "bound_and_visible":
            if not expected_project_id or binding_project_id != expected_project_id:
                errors.append(f"{department} 的项目 ID 与路由策略不一致")
            if not expected_cwd or not binding_cwd or Path(binding_cwd).resolve() != Path(expected_cwd).resolve():
                errors.append(f"{department} 的 cwd 与路由策略不一致")
        if not chat_healthy:
            errors.append(
                f"{department} 的固定任务不可派工："
                f"binding={binding_status}, reply_health={reply_health}, dispatch_eligible={str(dispatch_eligible).lower()}"
            )
            handoff_path = str(binding.get("handoff_path") or "")
            handoff_exists = bool(handoff_path and (root / handoff_path).is_file())
            sidebar_section_id = str(binding.get("sidebar_section_id") or "")
            recovery_status = (
                "blocked_health_probe_required"
                if health_stale
                else "blocked_replacement_requires_app_capability"
            )
            replacement_recovery.append(
                {
                    "department": department,
                    "current_task_id": binding.get("task_id"),
                    "status": recovery_status,
                    "required_sidebar_section_id": sidebar_section_id,
                    "sidebar_group_id_recorded": bool(sidebar_section_id),
                    "required_handoff_path": handoff_path,
                    "handoff_exists": handoff_exists,
                    "required_live_checks": [
                        "same_project_id",
                        "same_cwd",
                        "exact_department_title",
                        "inside_registered_sidebar_group",
                        "handoff_loaded",
                        "nonempty_visible_reply",
                    ],
                    "auto_bind_allowed": False,
                    "next_legal_action": (
                        f"send_exact_health_probe_then_department_health_record:{department}"
                        if health_stale
                        else "create_or_select_candidate_then_verify_exact_group_and_visible_reply"
                    ),
                }
            )
        rows.append(
            {
                "department": department,
                "name": item.get("name", department),
                "chat_title": binding.get("title", item.get("name", department)),
                "chat_task_id": binding.get("task_id"),
                "chat_project_id": binding_project_id,
                "chat_cwd": binding_cwd,
                "chat_binding_status": binding_status,
                "chat_reply_health": reply_health,
                "chat_health_stale": health_stale,
                "effective_reply_health": "verification_stale" if health_stale else reply_health,
                "dispatch_eligible": dispatch_eligible,
                "chat_health_status": "healthy" if chat_healthy else "unhealthy",
                "sidebar_section_id": binding.get("sidebar_section_id"),
                "handoff_path": binding.get("handoff_path"),
                "local_files_status": "ready" if not missing_files else "missing",
                "missing_files": missing_files,
            }
        )

    visible = [row for row in rows if row["chat_binding_status"] == "bound_and_visible"]
    unverified = [row for row in rows if row["chat_binding_status"] != "bound_and_visible"]
    unhealthy = [row for row in rows if row["chat_health_status"] != "healthy"]
    status = "departments_ready" if not errors and not unverified else "department_setup_blocked"
    payload = {
        "generated_at": timestamp(),
        "status": status,
        "department_count": len(rows),
        "visible_chat_count": len(visible),
        "unverified_chat_count": len(unverified),
        "unhealthy_chat_count": len(unhealthy),
        "health_verification_ttl_hours": verification_ttl_hours,
        "errors": errors,
        "departments": rows,
        "replacement_recovery": replacement_recovery,
        "replacement_note": "替补任务只有在应用现场验证同项目、同 cwd、正确标题、进入登记侧边栏分组、已继承交接文件且有非空可见回复后才能绑定。",
        "verification_note": "本地命令只能检查注册表和绑定记录；Codex 任务列表/侧边栏可见性仍需通过应用状态验证。",
    }
    data_path = root / "data/department-status.json"
    report_path = root / "reports" / f"{today()}-department-status.md"
    write_json(data_path, payload)
    lines = [
        "# FLASH CAST 部门状态",
        "",
        f"- 总状态：`{status}`",
        f"- 部门数量：`{len(rows)}`",
        f"- 已验证独立聊天：`{len(visible)}`",
        f"- 未验证/不可用聊天：`{len(unverified)}`",
        f"- 不可派工/健康异常：`{len(unhealthy)}`",
        "",
        "## 部门",
        "",
    ]
    for row in rows:
        lines.append(
            f"- `{row['department']}`｜{row['name']}｜聊天：`{row['chat_binding_status']}`"
            f"｜回复健康：`{row['chat_reply_health']}`｜允许派工：`{str(row['dispatch_eligible']).lower()}`"
            f"｜本地配置：`{row['local_files_status']}`"
        )
    if replacement_recovery:
        lines.extend(["", "## 替补恢复", ""])
        for item in replacement_recovery:
            lines.extend(
                [
                    f"- `{item['department']}`：`{item['status']}`；当前任务 `{item['current_task_id']}`。",
                    f"  必须位于侧边栏分组 `{item['required_sidebar_section_id'] or '缺失'}`，并继承 `{item['required_handoff_path'] or '缺失'}`。",
                    "  未完成应用现场验证前不自动改写注册表，不会把普通子智能体冒充部门窗口。",
                ]
            )
    if errors:
        lines.extend(["", "## 错误", "", *[f"- {error}" for error in errors]])
    lines.extend(["", "- 说明：本地状态不能替代 Codex 应用侧边栏和任务导航验收。", ""])
    write_text(report_path, "\n".join(lines))
    run_id = append_run(
        root,
        "department-status",
        status,
        [safe_rel(root, registry_path)],
        [safe_rel(root, data_path), safe_rel(root, report_path)],
        visible_chat_count=len(visible),
        unverified_chat_count=len(unverified),
        unhealthy_chat_count=len(unhealthy),
        replacement_required_count=len(replacement_recovery),
        error_count=len(errors),
    )
    payload["run_id"] = run_id
    write_json(data_path, payload)
    return payload, [data_path, report_path]


def init_project(root: Path) -> tuple[dict[str, Any], list[Path]]:
    directories = [
        "data/analytics",
        "data/content",
        "data/leads",
        "data/seo",
        "data/learning",
        "data/maintenance",
        "drafts/content-studio",
        "logs/handoffs",
        "logs/approvals",
        "logs/receipts",
        "logs/delegations",
        "data/workflows",
        "backups",
        "archive/workspace",
    ]
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)
    templates = {
        root / "data/leads/lead-quality-log.csv": (
            "lead_id,date,source,campaign,service,area,contact_channel,status,qualified,quoted,won,quote_value_myr,loss_reason\n"
        ),
        root / "data/analytics/ga4-consultation-actions.csv": (
            "window_start,window_end,scope,event_name,event_page,source_medium,campaign,action_count,unique_users,sessions\n"
        ),
    }
    for template_path, template in templates.items():
        if not template_path.exists():
            write_text(template_path, template)
    config_path = root / "config/workspace-retention.json"
    if not config_path.exists():
        write_json(
            config_path,
            {
                "enabled": False,
                "preview_default": True,
                "older_than_days": 30,
                "never_delete": ["history", "backups", "accounts", "data", "logs"],
                "apply_requires": ["--apply", "--owner-approved"],
            },
        )
    payload = {
        "status": "active_ops_layer_initialized",
        "created_at": timestamp(),
        "directories": directories,
        "templates": [safe_rel(root, path) for path in templates],
        "config": safe_rel(root, config_path),
    }
    report = root / "reports" / f"{today()}-active-ops-layer-init.md"
    write_text(
        report,
        "\n".join(
            [
                "# FLASH CAST 活跃运营工具层初始化",
                "",
                "- 已建立数据、内容、SEO、学习、备份、归档和日志目录。",
                "- 已建立 GA4 咨询动作和线索质量表的空模板；空表会被质检标记为数据缺口。",
                "- 默认只读/草稿/预演。",
                "- 未连接线上广告、CMS、GA4、GSC 或客户系统。",
                f"- 配置：`{safe_rel(root, config_path)}`",
            ]
        )
        + "\n",
    )
    return payload, [config_path, report]


def print_artifacts(payload: dict[str, Any], artifacts: list[Path], root: Path) -> None:
    output = {
        "status": payload.get("status", "complete"),
        "run_id": payload.get("run_id", ""),
        "artifacts": [safe_rel(root, path) for path in artifacts],
    }
    # New workflow commands need machine-readable decisions and next actions;
    # existing commands retain their original top-level fields.
    for key in (
        "task_id",
        "route_id",
        "current_state",
        "workflow_state",
        "controller_handoff",
        "business_goal_status",
        "record_id",
        "event",
        "decision",
        "next_owner",
        "next_action",
        "missing_receipts",
        "blockers",
        "next_legal_actions",
        "owner_approval_required",
        "owner_approval_pending",
        "receipt_id",
        "approval_id",
        "decision_id",
        "result",
        "reason",
        "required_receipts",
        "routing_status",
        "routing_quarantine_mode",
        "routing_health_probe_mode",
        "target_automation_status",
        "source_project_id",
        "target_project_id",
        "target_department",
        "target_thread_id",
        "target_thread_title",
        "target_cwd",
        "target_sidebar_section_id",
        "payload_sha256",
        "message_body_stored",
        "paid_promotion_enabled",
        "shadow_only",
        "writes_performed",
        "delegation_id",
        "decision_id",
        "active_count",
        "terminal_count",
        "active",
        "terminal",
        "fixed_department_remains_owner",
        "workflow_receipts_satisfied",
        "limits",
        "department",
        "dispatch_eligible",
        "reply_health",
        "checked_at",
        "chat_body_stored",
        "event_hash",
        "reply_ref",
        "reply_sha256",
        "reply_observed_at",
        "reply_nonempty",
        "completion_matches",
        "source",
        "live_identity_check_required",
        "thread_id",
        "turn_id",
        "audited_at",
        "automation_count",
        "counts",
        "results",
        "pending_count",
        "queued_pending_count",
        "legacy_recovery_count",
        "followthrough_pending_count",
        "waiting_followthrough_count",
        "followthrough_results",
        "total_actionable_count",
        "business_goal_closed",
        "automatic_pause_performed",
        "prompt_or_chat_body_stored",
    ):
        if key in payload:
            output[key] = payload[key]
    print(json.dumps(output, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FLASH CAST active growth operations layer")
    parser.add_argument("--root", default=str(ROOT), help="项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="建立主动运营目录和安全配置")
    init_parser.set_defaults(handler=lambda root, args: init_project(root))

    source_parser = sub.add_parser("source-manifest", help="检查数据来源、日期范围和新鲜度")
    source_parser.set_defaults(handler=lambda root, args: source_manifest(root))

    migrate_parser = sub.add_parser("migrate-inputs", help="把旧 Skill 的脱敏结构化输入迁移到空 active 表")
    migrate_parser.set_defaults(handler=lambda root, args: migrate_historical_inputs(root))

    reconcile_parser = sub.add_parser("conversion-reconcile", help="对账 Ads、GA4 和真实线索")
    reconcile_parser.set_defaults(handler=lambda root, args: conversion_reconcile(root))

    action_parser = sub.add_parser("action-queue", help="生成带优先级和审批边界的行动队列")
    action_parser.set_defaults(handler=lambda root, args: action_queue(root))

    dispatch_parser = sub.add_parser("dispatch-plan", help="按路由规则生成可审计的部门分派计划")
    dispatch_parser.add_argument("--request", required=True, help="老板的原始任务描述")
    dispatch_parser.add_argument("--task-id", default="", help="可选；不填则按日期和任务内容生成")
    dispatch_parser.set_defaults(handler=lambda root, args: dispatch_plan(root, args))

    receipt_parser = sub.add_parser("receipt-record", help="记录链式部门、QA、执行或复核回执")
    receipt_parser.add_argument("--task-id", required=True)
    receipt_parser.add_argument("--receipt-type", required=True, choices=sorted(workflow.RECEIPT_TYPES))
    receipt_parser.add_argument("--department", required=True)
    receipt_parser.add_argument("--chat-task-id", default="")
    receipt_parser.add_argument("--ack-nonempty", action="store_true")
    receipt_parser.add_argument("--evidence", default="", help="多个证据路径用分号分隔")
    receipt_parser.add_argument("--idempotency-key", required=True)
    receipt_parser.add_argument("--verdict", default="", choices=["", "pass", "blocked"])
    receipt_parser.add_argument("--action-id", default="")
    receipt_parser.add_argument("--action-class", default="")
    receipt_parser.add_argument("--scope", default="")
    receipt_parser.add_argument("--approval-id", default="")
    receipt_parser.add_argument("--policy-decision-id", default="")
    receipt_parser.add_argument("--supersedes-receipt-id", default="")
    receipt_parser.add_argument("--replacement-reason", default="")
    receipt_parser.set_defaults(handler=lambda root, args: receipt_record(root, args))

    result_record_parser = sub.add_parser("result-handoff-record", help="记录部门通知送达、总控收取或决策；不改变原工作流状态")
    result_record_parser.add_argument("--input", required=True, help="本项目内的结构化结果交接 JSON 路径")
    result_record_parser.set_defaults(handler=lambda root, args: result_handoff_record(root, args))

    result_status_parser = sub.add_parser("result-handoff-status", help="查看原任务每个结果的通知与总控决策状态")
    result_status_parser.add_argument("--task-id", required=True)
    result_status_parser.set_defaults(handler=lambda root, args: result_handoff_status_command(root, args))

    result_pending_parser = sub.add_parser("result-handoff-pending", help="列出项目内待总控收取或决策的结果；不发送聊天消息")
    result_pending_parser.set_defaults(handler=lambda root, args: result_handoff_pending_command(root, args))

    approval_parser = sub.add_parser("approval-record", help="记录或撤销单次、精确范围的老板批准")
    approval_parser.add_argument("--task-id", required=True)
    approval_parser.add_argument("--action-id", required=True)
    approval_parser.add_argument("--action-class", required=True)
    approval_parser.add_argument("--scope", required=True)
    approval_parser.add_argument("--approval-id", default="")
    approval_parser.add_argument("--source-thread-id", default="")
    approval_parser.add_argument("--source-message-ref", default="")
    approval_parser.add_argument("--revoke", action="store_true")
    approval_parser.set_defaults(handler=lambda root, args: approval_record(root, args))

    policy_parser = sub.add_parser("policy-check", help="执行前检查部门、Skill、回执、批准和硬门禁")
    policy_parser.add_argument("--task-id", required=True)
    policy_parser.add_argument("--department", required=True)
    policy_parser.add_argument("--action-id", required=True)
    policy_parser.add_argument("--action-class", required=True)
    policy_parser.add_argument("--scope", required=True)
    policy_parser.add_argument("--approval-id", default="")
    policy_parser.add_argument("--skill", default="")
    policy_parser.add_argument("--consume-approval", action="store_true")
    policy_parser.add_argument("--retry-blocked-execution-receipt-id", default="", help="只恢复同一被阻断执行回执的精确动作，不重复消费批准")
    policy_parser.add_argument("--source-project-id", default="")
    policy_parser.add_argument("--target-project-id", default="")
    policy_parser.add_argument("--target-department", default="")
    policy_parser.add_argument("--target-thread-id", default="")
    policy_parser.add_argument("--target-thread-title", default="")
    policy_parser.add_argument("--target-cwd", default="")
    policy_parser.add_argument("--target-sidebar-section-id", default="")
    policy_parser.add_argument("--payload-sha256", default="", help="消息或计划任务提示词的 SHA-256；不保存正文")
    policy_parser.add_argument(
        "--target-automation-status",
        default="",
        help="自动任务隔离时必须明确为 PAUSED；普通路由留空",
    )
    policy_parser.set_defaults(handler=lambda root, args: policy_check_command(root, args))

    workflow_reconcile_parser = sub.add_parser("workflow-reconcile", help="从事件、回执和证据重建工作流状态")
    workflow_reconcile_parser.add_argument("--task-id", required=True)
    workflow_reconcile_parser.add_argument("--shadow", action="store_true", help="只读回放 V1/历史证据，不写入工作流")
    workflow_reconcile_parser.set_defaults(handler=lambda root, args: workflow_reconcile_command(root, args))

    workflow_refresh_parser = sub.add_parser(
        "workflow-refresh-bindings",
        help="在派工前把工作流中的固定部门任务 ID 刷新为已验证注册表绑定",
    )
    workflow_refresh_parser.add_argument("--task-id", required=True)
    workflow_refresh_parser.set_defaults(handler=lambda root, args: workflow_refresh_bindings_command(root, args))

    qa_rebind_parser = sub.add_parser(
        "workflow-rebind-qa",
        help="在验证替补 QA 后保留旧回执并追加绑定替换事件",
    )
    qa_rebind_parser.add_argument("--task-id", required=True)
    qa_rebind_parser.add_argument("--old-chat-task-id", required=True)
    qa_rebind_parser.add_argument("--health-event-hash", required=True)
    qa_rebind_parser.set_defaults(handler=lambda root, args: workflow_rebind_qa_command(root, args))

    department_rebind_parser = sub.add_parser(
        "workflow-rebind-department",
        help="保留旧回执并把返工中的 QA 或内容部门绑定追加迁移到已验证替补窗口",
    )
    department_rebind_parser.add_argument("--task-id", required=True)
    department_rebind_parser.add_argument("--department", required=True, choices=["qa", "content-organic-website"])
    department_rebind_parser.add_argument("--old-chat-task-id", required=True)
    department_rebind_parser.add_argument("--health-event-hash", required=True)
    department_rebind_parser.set_defaults(handler=lambda root, args: workflow_rebind_department_command(root, args))

    repair_parser = sub.add_parser("workflow-repair-plan", aliases=["repair_dispatch_plan"],
                                  help="重新核对原固定部门并恢复尚未派工的阻断计划")
    repair_parser.add_argument("--task-id", required=True)
    repair_parser.set_defaults(handler=workflow_repair_plan_command)

    correct_route_parser = sub.add_parser(
        "workflow-correct-route",
        help="仅移除 multi 路由中从未收到回执的误命中部门，保留原始计划和真实回执",
    )
    correct_route_parser.add_argument("--task-id", required=True)
    correct_route_parser.add_argument("--route-id", required=True)
    correct_route_parser.set_defaults(handler=workflow_correct_route_command)

    workflow_status_parser = sub.add_parser("workflow-status", help="查看阶段、缺失回执、阻断和下一合法动作")
    workflow_status_parser.add_argument("--task-id", required=True)
    workflow_status_parser.set_defaults(handler=lambda root, args: workflow_status_command(root, args))

    delegation_check_parser = sub.add_parser("delegation-check", help="检查固定部门的有界子智能体委派是否有收益且可并行")
    delegation_check_parser.add_argument("--task-id", required=True)
    delegation_check_parser.add_argument("--department", required=True)
    delegation_check_parser.add_argument("--benefit", required=True, choices=["parallel_latency", "specialist_capability", "context_isolation"])
    delegation_check_parser.add_argument("--work-class", required=True, choices=["read_only", "local_artifact", "specialist_internal", "external_action"])
    delegation_check_parser.add_argument("--scope", required=True, help="有界任务描述；日志只保存 SHA-256")
    delegation_check_parser.add_argument("--parent-thread-id", required=True)
    delegation_check_parser.add_argument("--parent-project-id", required=True)
    delegation_check_parser.add_argument("--parent-cwd", required=True)
    delegation_check_parser.add_argument("--requested-parallelism", type=int, default=1)
    delegation_check_parser.add_argument("--timeout-seconds", type=int, default=0)
    delegation_check_parser.add_argument("--interdependent-work", action="store_true")
    delegation_check_parser.add_argument("--overlapping-write-scope", action="store_true")
    delegation_check_parser.add_argument("--external-side-effect", action="store_true")
    delegation_check_parser.set_defaults(handler=lambda root, args: delegation_check_command(root, args))

    delegation_record_parser = sub.add_parser("delegation-record", help="记录子智能体启动、进度、停止原因和证据")
    delegation_record_parser.add_argument("--task-id", required=True)
    delegation_record_parser.add_argument("--delegation-id", required=True)
    delegation_record_parser.add_argument("--department", required=True)
    delegation_record_parser.add_argument("--status", required=True, choices=sorted(workflow.DELEGATION_STATES))
    delegation_record_parser.add_argument("--idempotency-key", required=True)
    delegation_record_parser.add_argument("--decision-id", default="")
    delegation_record_parser.add_argument("--scope", default="", help="started 时必须与 delegation-check 一致；账本只保存 SHA-256")
    delegation_record_parser.add_argument("--attempt", type=int, default=1)
    delegation_record_parser.add_argument("--stop-reason", default="")
    delegation_record_parser.add_argument("--evidence", default="", help="多个输出证据路径用分号分隔")
    delegation_record_parser.set_defaults(handler=lambda root, args: delegation_record_command(root, args))

    delegation_status_parser = sub.add_parser("delegation-status", help="重建委派账本、自动标记超时并显示停止原因")
    delegation_status_parser.add_argument("--task-id", required=True)
    delegation_status_parser.set_defaults(handler=lambda root, args: delegation_status_command(root, args))

    health_parser = sub.add_parser("department-health-record", help="登记固定部门现场身份和非空回复健康证明")
    health_parser.add_argument("--department", required=True)
    health_parser.add_argument("--task-id", required=True)
    health_parser.add_argument("--project-id", required=True)
    health_parser.add_argument("--cwd", required=True)
    health_parser.add_argument("--title", required=True)
    health_parser.add_argument("--sidebar-section-id", required=True)
    health_parser.add_argument("--reply-ref", default="")
    health_parser.add_argument("--reply-sha256", default="")
    health_parser.add_argument("--reply-nonempty", action="store_true")
    health_parser.add_argument("--reply-observed-at", default="", help="原始回复时间；不得把旧回复刷新成今天")
    health_parser.add_argument("--live-status", default="unknown")
    health_parser.add_argument("--last-run-status", default="success", choices=["success", "failed", "interrupted", "unknown"])
    health_parser.add_argument("--failure-class", default="")
    health_parser.add_argument("--next-retry-at", default="")
    health_parser.set_defaults(handler=lambda root, args: department_health_record(root, args))

    reply_parser = sub.add_parser("department-reply-check", help="只读核对固定窗口最新轮次原始回复；只输出哈希和身份")
    reply_parser.add_argument("--department", required=True)
    reply_parser.add_argument("--turn-id", required=True)
    reply_parser.add_argument("--session-path", required=True)
    reply_parser.set_defaults(handler=department_reply_check)

    global_audit_parser = sub.add_parser("global-routing-audit", help="审计所有本机 Codex 自动任务的项目和目标任务归属")
    global_audit_parser.add_argument("--automations-root", default=str(Path.home() / ".codex" / "automations"))
    global_audit_parser.add_argument("--live-snapshot", default="", help="项目内只含任务 ID、项目 ID、cwd 和标题的现场快照")
    global_audit_parser.add_argument("--shadow", action="store_true", help="只读检查，不写全局治理总账")
    global_audit_parser.set_defaults(handler=lambda root, args: global_routing_audit(root, args))

    status_parser = sub.add_parser("department-status", help="检查部门配置和独立聊天绑定记录")
    status_parser.set_defaults(handler=lambda root, args: department_status(root))

    handoff_parser = sub.add_parser("handoff", help="记录部门之间的任务交接")
    handoff_parser.add_argument("--task-id", required=True)
    handoff_parser.add_argument("--from-department", required=True)
    handoff_parser.add_argument("--to-department", required=True)
    handoff_parser.add_argument("--completed", default="")
    handoff_parser.add_argument("--unfinished", default="")
    handoff_parser.add_argument("--evidence", default="")
    handoff_parser.add_argument("--cannot-assume", default="")
    handoff_parser.add_argument("--next-action", default="")
    handoff_parser.add_argument("--owner-approval-required", action="store_true")
    handoff_parser.set_defaults(handler=lambda root, args: handoff(root, args))

    ledger_parser = sub.add_parser("run-ledger", help="汇总工具运行账本")
    ledger_parser.set_defaults(handler=lambda root, args: run_ledger_report(root))

    gate_parser = sub.add_parser("qa-gate", help="执行 Reality Checker 质检放行")
    gate_parser.add_argument("--scope", default="growth-daily")
    gate_parser.set_defaults(handler=lambda root, args: qa_gate(root, args.scope))

    daily_parser = sub.add_parser("ads-daily", help="执行 Google Ads 只读日检决策环")
    daily_parser.set_defaults(handler=lambda root, args: ads_daily(root))

    queue_parser = sub.add_parser("content-queue", help="生成 Content Studio 内容队列")
    queue_parser.add_argument("--limit", type=int, default=0)
    queue_parser.set_defaults(handler=lambda root, args: build_content_queue(root, args.limit))

    draft_parser = sub.add_parser("content-draft", help="从队列生成单页双语内容草稿包")
    draft_parser.add_argument("--target-url", default="")
    draft_parser.add_argument("--slot", type=int, default=0)
    draft_parser.set_defaults(handler=lambda root, args: create_content_draft(root, args.target_url, args.slot))

    qa_parser = sub.add_parser("content-qa", help="检查内容草稿的双语和承诺边界")
    qa_parser.add_argument("--draft-path", required=True)
    qa_parser.add_argument("--no-bilingual", action="store_true")
    qa_parser.set_defaults(handler=lambda root, args: content_qa(root, args.draft_path, not args.no_bilingual))

    seo_parser = sub.add_parser("seo-index-audit", help="执行只读 SEO 技术和索引对账")
    seo_parser.add_argument("--site", default="https://flashcast.com.my")
    seo_parser.add_argument("--remote", action="store_true", help="读取公开 sitemap 并抓取页面，只读")
    seo_parser.add_argument("--max-urls", type=int, default=80)
    seo_parser.set_defaults(handler=lambda root, args: seo_index_audit(root, args.site, args.remote, max(1, args.max_urls)))

    learning_parser = sub.add_parser("learning-record", help="追加一条学习记忆")
    learning_parser.add_argument("--memory-type", required=True)
    learning_parser.add_argument("--entity", required=True)
    learning_parser.add_argument("--signal", required=True)
    learning_parser.add_argument("--evidence", required=True)
    learning_parser.add_argument("--outcome", required=True)
    learning_parser.add_argument("--next-action", required=True)
    learning_parser.add_argument("--confidence", default="medium")
    learning_parser.add_argument("--source", default="")
    learning_parser.add_argument("--observed-at", default="")
    learning_parser.set_defaults(handler=lambda root, args: learning_record(root, args))

    department_learning_parser = sub.add_parser(
        "department-learning-record", help="记录指定部门的可继承学习经验"
    )
    department_learning_parser.add_argument("--department", required=True)
    department_learning_parser.add_argument("--task-id", required=True)
    department_learning_parser.add_argument("--memory-type", required=True)
    department_learning_parser.add_argument("--lesson", required=True)
    department_learning_parser.add_argument("--signal", required=True)
    department_learning_parser.add_argument("--evidence", required=True, help="多个路径用分号分隔")
    department_learning_parser.add_argument("--outcome", required=True)
    department_learning_parser.add_argument("--next-action", required=True)
    department_learning_parser.add_argument(
        "--confidence", default="medium", choices=["high", "medium", "low"]
    )
    department_learning_parser.add_argument(
        "--lesson-status", default="provisional", choices=["verified", "provisional", "retired"]
    )
    department_learning_parser.add_argument("--source", default="")
    department_learning_parser.add_argument("--observed-at", default="")
    department_learning_parser.add_argument("--data-window", default="", help="例如 2026-08-01..2026-08-31")
    department_learning_parser.add_argument("--last-verified-at", default="")
    department_learning_parser.add_argument("--review-after", default="", help="YYYY-MM-DD")
    department_learning_parser.add_argument("--conflicts-with", default="", help="多个 lesson_id 用分号分隔")
    department_learning_parser.add_argument("--supersedes", default="", help="多个 lesson_id 用分号分隔")
    department_learning_parser.set_defaults(handler=lambda root, args: department_learning_record(root, args))

    department_learning_status_parser = sub.add_parser(
        "department-learning-status", help="按注册表检查所有部门的学习记忆档案"
    )
    department_learning_status_parser.set_defaults(handler=lambda root, args: department_learning_status(root))

    review_parser = sub.add_parser("weekly-review", help="生成周增长复盘")
    review_parser.set_defaults(handler=lambda root, args: weekly_review(root))

    backup_parser = sub.add_parser("backup", help="为指定文件/目录创建备份")
    backup_parser.add_argument("--path", required=True)
    backup_parser.add_argument("--change-id", required=True)
    backup_parser.set_defaults(handler=lambda root, args: backup(root, args.path, args.change_id))

    change_parser = sub.add_parser("change-log", help="记录一条变更或审批状态")
    change_parser.add_argument("--change-id", required=True)
    change_parser.add_argument("--status", required=True, choices=["planned", "approved", "applied", "rolled_back", "blocked"])
    change_parser.add_argument("--summary", required=True)
    change_parser.add_argument("--files", nargs="*", default=[])
    change_parser.add_argument("--owner-approved", action="store_true")
    change_parser.set_defaults(handler=lambda root, args: change_log(root, args))

    rollback_parser = sub.add_parser("rollback", help="回滚预演；真实恢复需要人工批准")
    rollback_parser.add_argument("--change-id", required=True)
    rollback_parser.add_argument("--apply", action="store_true")
    rollback_parser.add_argument("--owner-approved", action="store_true")
    rollback_parser.set_defaults(handler=lambda root, args: rollback(root, args.change_id, args.apply, args.owner_approved))

    maintenance_parser = sub.add_parser("workspace-maintenance", help="扫描或归档旧草稿/报告")
    maintenance_parser.add_argument("--apply", action="store_true")
    maintenance_parser.add_argument("--owner-approved", action="store_true")
    maintenance_parser.add_argument("--older-than-days", type=int, default=30)
    maintenance_parser.set_defaults(handler=lambda root, args: workspace_maintenance(root, args.apply, args.owner_approved, max(1, args.older_than_days)))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        payload, artifacts = args.handler(root, args)
        print_artifacts(payload, artifacts, root)
        return 0
    except OpsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
