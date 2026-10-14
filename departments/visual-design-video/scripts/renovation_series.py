#!/usr/bin/env python3
"""Read-only editorial queue; actual consumption stays in the existing knowledge ledger."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "data/knowledge/renovation-pain-100-episodes-v1.json"
USAGE = ROOT / "data/knowledge/renovation-content-used-topics-v2.json"
BANK = ROOT / "data/knowledge/renovation-scenario-library-v2.json"


def read(path):
    path = Path(path).resolve()
    if ROOT not in path.parents:
        raise ValueError("SERIES_PATH_OUTSIDE_PROJECT")
    return json.loads(path.read_text(encoding="utf-8"))


def verify(plan):
    episodes = plan["episodes"]
    if len(episodes) != 100 or plan.get("planned_count") != 100:
        raise ValueError("EXACTLY_100_PLANNED_EPISODES_REQUIRED")
    for key in ("id", "title", "semantic_key", "production_task_id", "order"):
        if len({e[key] for e in episodes}) != 100:
            raise ValueError("DUPLICATE_EPISODE_" + key.upper())
    if [e["order"] for e in episodes] != list(range(1, 101)):
        raise ValueError("EPISODE_ORDER_MUST_BE_CONTIGUOUS")
    domains = {d["id"] for d in plan["domains"]}
    if len(domains) != 25 or any(sum(e["domain_id"] == d for e in episodes) != 4 for d in domains):
        raise ValueError("25_DOMAINS_WITH_FOUR_DISTINCT_QUESTIONS_REQUIRED")
    source_ids = {s["id"] for s in plan["research_sources"]}
    if len(source_ids) != len(plan["research_sources"]):
        raise ValueError("DUPLICATE_SOURCE_ID")
    for i, episode in enumerate(episodes):
        if not episode["source_anchor_ids"] or not set(episode["source_anchor_ids"]) <= source_ids:
            raise ValueError("EPISODE_SOURCE_ANCHOR_MISSING")
        if not episode["core_question"] or not episode["visual_brief"]:
            raise ValueError("QUESTION_AND_VISIBLE_INFORMATION_REQUIRED")
        if episode["voice_profile_id"] != "A" or episode["target_duration_seconds"] != [45, 60]:
            raise ValueError("OWNER_APPROVED_NARRATION_MODE_REQUIRED")
        if episode["domain_id"] in {e["domain_id"] for e in episodes[max(0, i-24):i]}:
            raise ValueError("DOMAIN_INTERLEAVING_FAILED")
    return {"status": "PASS_EDITORIAL_STRUCTURE_ONLY", "episodes": 100, "domains": 25,
            "source_pages": len(source_ids), "production_ready_claimed": False}


def actual_series_rows(plan, usage):
    planned = {e["production_task_id"]: e for e in plan["episodes"]}
    rows = []
    seen = set()
    for item in usage.get("used", []):
        if item.get("task_id") not in planned or item.get("adoption_kind") != "rendered_video":
            continue
        if item["task_id"] in seen:
            raise ValueError("DUPLICATE_SERIES_ADOPTION_IN_CANONICAL_LEDGER")
        episode = planned[item["task_id"]]
        if item.get("semantic_key") != episode["semantic_key"]:
            raise ValueError("ADOPTED_EPISODE_SEMANTIC_KEY_MISMATCH")
        evidence_path = (ROOT / item["evidence_path"]).resolve()
        evidence = read(evidence_path)
        if hashlib.sha256(evidence_path.read_bytes()).hexdigest() != item["evidence_sha256"]:
            raise ValueError("SERIES_ADOPTION_EVIDENCE_CHANGED")
        video = (ROOT / evidence["video_path"]).resolve()
        if ROOT not in video.parents or not video.is_file():
            raise ValueError("ACTUAL_SERIES_VIDEO_MISSING")
        if hashlib.sha256(video.read_bytes()).hexdigest() != evidence["video_sha256"]:
            raise ValueError("ACTUAL_SERIES_VIDEO_CHANGED")
        metadata = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json", str(video)], text=True))
        streams = metadata.get("streams", [])
        if not (45 <= float(metadata["format"]["duration"]) <= 60
                and any(s.get("codec_type") == "video" and (s.get("width"), s.get("height")) == (1080, 1920) for s in streams)
                and any(s.get("codec_type") == "audio" for s in streams)):
            raise ValueError("ACTUAL_SERIES_NARRATION_VIDEO_STREAMS_OR_DURATION_INVALID")
        if evidence.get("task_id") != item["task_id"] or evidence.get("topic_id") != item["topic_id"]:
            raise ValueError("SERIES_ADOPTION_IDENTITY_MISMATCH")
        qc = read(ROOT / evidence["qc_report_path"])
        if not isinstance(qc, dict) or not qc:
            raise ValueError("CURRENT_VIDEO_QC_REQUIRED")
        rows.append(item)
        seen.add(item["task_id"])
    return rows


def next_episode(plan, usage, bank, day, exclude=()):
    verify(plan)
    day = date.fromisoformat(day).isoformat()
    rows = actual_series_rows(plan, usage)
    done = {r["task_id"] for r in rows}
    if len(done) == 100:
        return {"status": "SERIES_RENDERING_COMPLETE_STOP_SCHEDULE", "rendered_count": 100,
                "independent_acceptance": "NOT_INFERRED", "published": False}
    if day < plan["schedule"]["start_date"]:
        return {"status": "NOT_STARTED", "rendered_count": len(done)}
    today = [r["task_id"] for r in rows if r.get("used_at", "")[:10] == day]
    if today:
        return {"status": "NO_CHANGE_DATE_ALREADY_RENDERED", "task_ids": today,
                "rendered_count": len(done), "do_not_create_second_video_today": True}
    ids = {e["id"] for e in plan["episodes"]}
    if not set(exclude) <= ids:
        raise ValueError("UNKNOWN_EXCLUDED_EPISODE")
    candidates = [e for e in plan["episodes"] if e["production_task_id"] not in done and e["id"] not in exclude]
    if not candidates:
        return {"status": "NO_ELIGIBLE_EPISODE_THIS_RUN", "rendered_count": len(done),
                "exclusions_are_not_consumption": True}
    episode = candidates[0]
    cards = [c for c in bank["cards"] if c["semantic_key"] == episode["semantic_key"]]
    if len(cards) > 1:
        raise ValueError("AMBIGUOUS_ADMITTED_SERIES_TOPIC")
    return {"status": "NEXT_EDITORIAL_EPISODE", "episode": episode,
            "source_anchors": [s for s in plan["research_sources"] if s["id"] in episode["source_anchor_ids"]],
            "rendered_count": len(done), "admitted_topic_id": cards[0]["id"] if cards else None,
            "research_admission_required": not bool(cards), "daily_source_revalidation_required": True,
            "exclusions_this_run": list(exclude), "no_state_mutation": True,
            "independent_acceptance": "NOT_INFERRED", "published": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    nxt = sub.add_parser("next")
    nxt.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(), help="Asia/Shanghai local date")
    nxt.add_argument("--exclude", action="append", default=[], help="Held episode this run; never marks it used")
    args = parser.parse_args()
    plan = read(PLAN)
    result = verify(plan) if args.command == "verify" else next_episode(plan, read(USAGE), read(BANK), args.date, args.exclude)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "BLOCKED_SERIES_INPUT", "reason": str(exc)}, ensure_ascii=False))
        sys.exit(1)
