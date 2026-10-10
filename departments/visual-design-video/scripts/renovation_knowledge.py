#!/usr/bin/env python3
"""Project-local renovation content rotation. Peek/simulate/verify never consume history."""
from __future__ import annotations

import argparse
import contextlib
from datetime import date
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BANK_PATH = ROOT / "data/knowledge/renovation-scenario-library-v2.json"
USAGE_NAME = "renovation-content-used-topics-v2.json"
STYLE_NAME = "whole-house-style-rotation.json"
JOURNAL_NAME = "renovation-adoption-transaction-v2.json"
PRODUCTS = ("realistic_effect_ad", "cabinet_detail_explainer", "renovation_mistake_guide", "design_plan_pitch", "concept_before_after", "brand_process_ad")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def inside(path):
    result = Path(path).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError("OUTPUT_OR_STATE_OUTSIDE_FLASHCAST_PROJECT")
    return result


def atomic_json(path, value):
    path = inside(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def style_engine():
    manifest = read(ROOT / "data/knowledge/full-house-custom-knowledge-manifest.json")
    path = Path(manifest["canonical_skill"]) / "scripts/knowledge_rotation.py"
    spec = importlib.util.spec_from_file_location("legacy_style_engine", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def usage_at(state_dir, bank):
    path = state_dir / USAGE_NAME
    return read(path) if path.exists() else {"schema_version": "2.0", "knowledge_base_id": bank["knowledge_base_id"], "used": []}


def pending(state_dir):
    path = state_dir / JOURNAL_NAME
    return path.exists() and read(path).get("status") == "prepared"


def history(bank, usage, state_dir):
    rows = list(usage["used"])
    # Legacy consumption stays in its original ledger. Aliases are observations, not new adoption.
    for alias in bank.get("legacy_aliases", []):
        old_path = state_dir / Path(alias["usage_file"]).name
        if old_path.exists():
            for entry in read(old_path).get("used", []):
                if alias["legacy_topic_id"] in (entry.get("topic_id"), entry.get("supporting_topic_id")):
                    rows.append({"task_id": entry["task_id"], "used_at": entry.get("used_at", ""), "semantic_keys": alias["semantic_keys"], "origin": "legacy_read_only"})
    # Baseline observations belong only to the real project ledger, never to test state.
    if state_dir == ROOT / "data/knowledge":
        for entry in bank.get("legacy_observations", []):
            if (ROOT / entry["source"]).is_file():
                rows.append({**entry, "used_at": entry["observed_on"], "origin": "legacy_artifact_observation"})
    # On the same legacy date, new v2 adoptions follow old artifact observations.
    # Otherwise aliases appended during reading would always dominate the recent window.
    rows.sort(key=lambda x: (x.get("used_at", ""), not x.get("origin", "").startswith("legacy")))
    distinct = {}
    for row in rows:
        keys = row.get("semantic_keys", [row.get("semantic_key", "")])
        for key in keys:
            if key:
                distinct[(row.get("task_id"), key)] = {**row, "semantic_key": key}
    return list(distinct.values())


def verify(bank):
    cards, scenes, sources = bank["cards"], bank["scenes"], bank["research_sources"]
    assert len(cards) == bank["counts"]["deep_card_count"]
    assert len(scenes) == bank["counts"]["scene_count"]
    assert len(sources) == bank["counts"]["primary_source_count"]
    assert len({x["id"] for x in cards}) == len(cards)
    assert len({x["semantic_key"] for x in cards}) == len(cards)
    assert len({x["title"] for x in cards}) == len(cards)
    source_ids = {x["id"] for x in sources}
    scene_ids = {x["id"] for x in scenes}
    for card in cards:
        assert card["scene_id"] in scene_ids
        assert card["claim_type"] == "designer_synthesis"
        assert len(set(card["design_actions"])) >= 2
        assert all(len(x) >= 8 for x in card["design_actions"])
        assert len(card["problem"]) >= 8 and len(card["acceptance_check"]) >= 8
        assert card["visual_evidence"] and card["applicability_boundary"]
        assert set(card["source_ids"]) <= source_ids and card["source_ids"]
        assert "brand_process_ad" not in card["supported_products"]
        assert set(card["supported_products"]) <= set(PRODUCTS)
        if "concept_before_after" in card["supported_products"]:
            assert len(card["before_after"]["after_changes"]) >= 2
        if "cabinet_detail_explainer" in card["supported_products"]:
            assert card["detail_rule"]
    for blueprint in bank["whole_home_blueprints"]:
        ids = {x["id"] for x in cards}
        assert blueprint["primary_topic_id"] in ids
        assert set(blueprint["supporting_topic_ids"]) <= ids
    return {"status": "PASS", "counts": bank["counts"], "product_card_counts": {p: sum(p in c["supported_products"] for c in cards) for p in PRODUCTS}, "claim_status": "source_supported_designer_synthesis_not_certified_construction_rules"}


def validate_plan(path, bank):
    plan = read(inside(path))
    if plan.get("selected_product_type") == "brand_process_ad":
        return {"status": "NOT_APPLICABLE_FIXED_COMPANY_PROCESS", "process_changed": False}
    block = plan.get("knowledge_plan", {})
    selection_path = inside(ROOT / block["selection_path"])
    if digest(selection_path) != block["selection_sha256"]:
        raise ValueError("SELECTION_FILE_HASH_MISMATCH")
    selection = read(selection_path)
    if selection["knowledge_sha256"] != digest(BANK_PATH):
        raise ValueError("KNOWLEDGE_CHANGED_RESELECT")
    if (plan.get("task_id"), plan.get("selected_product_type")) != (selection["task_id"], selection["product_type"]):
        raise ValueError("PLAN_SELECTION_TASK_PRODUCT_MISMATCH")
    topic = next(c for c in bank["cards"] if c["id"] == block["primary_topic_id"])
    if topic != selection["topic"]:
        raise ValueError("PRIMARY_TOPIC_MISMATCH")
    if selection["product_type"] not in topic["supported_products"]:
        raise ValueError("TOPIC_NOT_SUPPORTED_FOR_PRODUCT")
    actions = block.get("design_actions", [])
    if not set(topic["design_actions"]) <= set(actions):
        raise ValueError("MISSING_SPECIFIC_DESIGN_ACTIONS; generic style slogans are insufficient")
    shots = block.get("shot_evidence", [])
    for action in topic["design_actions"]:
        linked = [shot for shot in shots if shot.get("action") == action and len(shot.get("show", "")) >= 10 and shot.get("scene_id")]
        if not linked:
            raise ValueError("DESIGN_ACTION_HAS_NO_VISIBLE_SHOT_EVIDENCE")
    if selection["product_type"] == "cabinet_detail_explainer" and not any(x.get("mode") == "same_source_crop" for x in shots):
        raise ValueError("CABINET_DETAIL_NEEDS_SAME_SOURCE_CROP_PLAN")
    if selection["product_type"] == "concept_before_after":
        if len(set(block.get("changed_dimensions", []))) < 2 or not block.get("same_room_camera_locked"):
            raise ValueError("COMPARISON_NEEDS_TWO_REAL_DIMENSIONS_AND_LOCKED_ROOM")
    if selection["scope"] == "whole_home":
        spaces = block.get("supporting_topic_ids", [])
        allowed = selection["blueprint"]["supporting_topic_ids"]
        if len(set(spaces)) < 3 or not set(spaces) <= set(allowed):
            raise ValueError("WHOLE_HOME_NOT_A_ONE_ROOM_MONTAGE")
    if block.get("unverified_performance_claims") != [] or not block.get("boundary_handling"):
        raise ValueError("UNVERIFIED_CLAIMS_OR_BOUNDARY_MISSING")
    return {"status": "PASS", "task_id": plan["task_id"], "primary_topic_id": topic["id"], "scope": selection["scope"], "checked": ["selection_hash", "specific_actions", "visible_shot_plan", "scope", "truthful_boundaries"], "not_checked": ["actual_rendered_images", "actual_video", "qingdou", "independent_qa", "publication"]}


def choose(bank, usage, state_dir, product, scene=None, family=None, context="residential", scope="single_space"):
    cards = bank["cards"]
    if product == "brand_process_ad":
        return {"product_type": product, "topic": None, "style": None, "status": "FIXED_CONFIRMED_COMPANY_PROCESS_NO_ROTATION"}
    if scope == "whole_home" and (product not in ("realistic_effect_ad", "design_plan_pitch") or scene or context == "commercial"):
        raise ValueError("WHOLE_HOME_SCOPE_ONLY_FOR_RESIDENTIAL_SHOWCASE_OR_PLAN; do not silently change scope")
    scene_map = {s["id"]: s for s in bank["scenes"]}
    eligible = [c for c in cards if product in c["supported_products"] and (context == "any" or scene_map[c["scene_id"]]["context"] == context)]
    if scene:
        eligible = [c for c in eligible if scene in (c["scene_key"], c["scene_name"], c["scene_id"])]
    if family:
        eligible = [c for c in eligible if c["family"] == family]
    recipes = {b["primary_topic_id"]: b for b in bank["whole_home_blueprints"]}
    if scope == "whole_home":
        eligible = [c for c in eligible if c["id"] in recipes]
    if not eligible:
        raise ValueError("NO_COMPATIBLE_TOPIC_FOR_REQUESTED_SCOPE")
    seen = history(bank, usage, state_dir)
    recent = {x["semantic_key"] for x in seen[-30:]}
    all_seen = {x["semantic_key"] for x in seen}
    key_map = {c["semantic_key"]: c for c in cards}
    recent_families = {key_map[x["semantic_key"]]["family"] for x in seen[-3:] if x["semantic_key"] in key_map}
    recent_scenes = {key_map[x["semantic_key"]]["scene_key"] for x in seen[-4:] if x["semantic_key"] in key_map}
    eligible = [c for c in eligible if c["semantic_key"] not in recent]
    if not eligible:
        raise ValueError("CONTENT_POOL_EXHAUSTED_RESEARCH_NEW_TOPIC; never reset history or silently repeat")
    # Round-robin card tiers rather than exhausting all 3 cards of the first space.
    eligible.sort(key=lambda c: (c["id"].rsplit("-", 1)[1], c["scene_id"]))
    eligible.sort(key=lambda c: (c["semantic_key"] in all_seen, c["family"] in recent_families, c["scene_key"] in recent_scenes))
    topic = eligible[0]
    relaxed = []
    if topic["family"] in recent_families:
        relaxed.append("family_soft_window_relaxed_within_requested_scope")
    if topic["scene_key"] in recent_scenes:
        relaxed.append("scene_soft_window_relaxed_within_requested_scope")
    return {"product_type": product, "topic": topic, "scope": scope, "context": context, "scope_filters": {"scene": scene, "family": family}, "blueprint": recipes.get(topic["id"]) if scope == "whole_home" else None, "story_rules": bank["product_story_rules"][product], "dedup": {"cross_product": True, "recent_window": 30, "legacy_observations_included": True, "relaxed": relaxed}, "status": "PROPOSED_NOT_ADOPTED", "source_recheck": [s for s in bank["research_sources"] if s["id"] in topic["source_ids"]]}


def select(args, bank, usage, state_dir):
    if pending(state_dir):
        raise ValueError("PENDING_ADOPTION_RECOVERY; peek is read-only, run recover after inspection")
    old = next((x for x in usage["used"] if args.task_id and x["task_id"] == args.task_id), None)
    if old:
        if old["product_type"] != args.product_type:
            raise ValueError("TASK_PRODUCT_CONFLICT")
        return {**old["selection"], "status": "ALREADY_ADOPTED_REWORK_PRESERVES_TOPIC_STYLE"}
    selection = choose(bank, usage, state_dir, args.product_type, args.scene, args.family, args.context, args.scope)
    if selection["topic"] is None:
        return selection
    engine = style_engine()
    style, state, _ = engine.select_style(state_dir)
    mode = "automatic_rotation"
    if args.style_id:
        library, _, _ = engine.load_style_context(state_dir)
        style = next((x for x in library["styles"] if x["style_id"] == args.style_id), None)
        if style is None:
            raise ValueError("UNKNOWN_STYLE")
        variant = next(x for x in style["palette_variants"] if x["id"] == (args.variant_id or "V1"))
        style = {**style, "selected_variant": variant}
        mode = "owner_explicit_no_queue_advance"
    selection.update({"schema_version": "2.0", "task_id": args.task_id, "knowledge_base_id": bank["knowledge_base_id"], "knowledge_sha256": digest(BANK_PATH), "style": style, "style_selection_mode": mode, "state_fingerprints": {USAGE_NAME: digest(state_dir / USAGE_NAME), STYLE_NAME: digest(state_dir / STYLE_NAME)}, "selected_on": date.today().isoformat()})
    return selection


@contextlib.contextmanager
def locked(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / ".renovation-adoption-v2.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def apply_transaction(state_dir, transaction):
    for name, item in transaction["files"].items():
        if name not in (USAGE_NAME, STYLE_NAME):
            raise ValueError("INVALID_TRANSACTION_TARGET")
        current = digest(state_dir / name)
        if current == item["after_hash"]:
            continue
        if current != item["before_hash"]:
            raise ValueError("TRANSACTION_CONFLICT_KEEP_EXISTING_STATE")
        atomic_json(state_dir / name, item["after"])
    transaction["status"] = "completed"
    atomic_json(state_dir / JOURNAL_NAME, transaction)


def commit(args, bank, state_dir):
    selection = read(inside(args.selection))
    if selection.get("product_type") == "brand_process_ad" or not selection.get("topic"):
        raise ValueError("FIXED_BRAND_PROCESS_NOT_IN_CONTENT_ROTATION")
    if not args.task_id or selection.get("task_id") != args.task_id:
        raise ValueError("TASK_ID_MISMATCH")
    with locked(state_dir):
        if pending(state_dir):
            raise ValueError("PENDING_ADOPTION_RECOVERY")
        usage = usage_at(state_dir, bank)
        old = next((x for x in usage["used"] if x["task_id"] == args.task_id), None)
        if old:
            if (old["topic_id"], old["product_type"], old["style_id"], old["variant_id"]) != (selection["topic"]["id"], selection["product_type"], selection["style"]["style_id"], selection["style"]["selected_variant"]["id"]):
                raise ValueError("ADOPTION_CONFLICT_SAME_TASK")
            return {"status": "ALREADY_ADOPTED_NO_STATE_CHANGE", "topic_id": old["topic_id"]}
        if selection.get("knowledge_sha256") != digest(BANK_PATH):
            raise ValueError("KNOWLEDGE_CHANGED_RESELECT")
        if set(selection["state_fingerprints"]) != {USAGE_NAME, STYLE_NAME}:
            raise ValueError("MISSING_EXACT_STATE_FINGERPRINTS")
        for name, expected in selection["state_fingerprints"].items():
            if name not in (USAGE_NAME, STYLE_NAME) or digest(state_dir / name) != expected:
                raise ValueError("STATE_CHANGED_RESELECT")
        topic = next((c for c in bank["cards"] if c["id"] == selection["topic"]["id"]), None)
        if topic != selection["topic"] or selection["product_type"] not in topic["supported_products"]:
            raise ValueError("TOPIC_OR_PRODUCT_MISMATCH")
        evidence_path = inside(args.evidence)
        evidence = read(evidence_path)
        if (evidence.get("task_id"), evidence.get("topic_id")) != (args.task_id, topic["id"]):
            raise ValueError("ADOPTION_EVIDENCE_TASK_TOPIC_MISMATCH")
        if args.adoption_kind == "confirmed_plan":
            if evidence.get("adoption_status") != "owner_confirmed_plan" or not evidence.get("owner_confirmation_ref"):
                raise ValueError("CANDIDATE_IS_NOT_CONFIRMED_PLAN")
        else:
            if evidence.get("adoption_status") != "rendered_video" or not evidence.get("video_path"):
                raise ValueError("NO_ACTUAL_RENDERED_VIDEO")
            video = inside(evidence["video_path"])
            if video.suffix.lower() != ".mp4" or not video.is_file() or digest(video) != evidence.get("video_sha256"):
                raise ValueError("VIDEO_EVIDENCE_MISSING_OR_HASH_MISMATCH")
            if not evidence.get("qc_report_path") or not inside(evidence["qc_report_path"]).is_file():
                raise ValueError("NO_CURRENT_VIDEO_QC_EVIDENCE")
        style = selection["style"]
        entry = {"task_id": args.task_id, "product_type": selection["product_type"], "topic_id": topic["id"], "semantic_key": topic["semantic_key"], "scene_key": topic["scene_key"], "family": topic["family"], "style_id": style["style_id"], "variant_id": style["selected_variant"]["id"], "used_at": date.today().isoformat(), "adoption_kind": args.adoption_kind, "evidence_path": str(evidence_path.relative_to(ROOT)), "evidence_sha256": digest(evidence_path), "selection": selection}
        usage["used"].append(entry)
        changes = {USAGE_NAME: usage}
        if selection["style_selection_mode"] == "automatic_rotation":
            engine = style_engine()
            expected, state, _ = engine.select_style(state_dir)
            if (expected["style_id"], expected["selected_variant"]["id"]) != (style["style_id"], style["selected_variant"]["id"]):
                raise ValueError("STYLE_CHANGED_RESELECT")
            state["used"].append({k: entry[k] for k in ("task_id", "product_type", "topic_id", "style_id", "variant_id", "used_at")})
            state["used"][-1]["selection_mode"] = "automatic_rotation_content_v2"
            engine.advance_style(state)
            changes[STYLE_NAME] = state
        def encoded_hash(value):
            return hashlib.sha256((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()
        transaction = {"schema_version": "2.0", "task_id": args.task_id, "status": "prepared", "files": {name: {"before_hash": digest(state_dir / name), "after_hash": encoded_hash(value), "after": value} for name, value in changes.items()}}
        atomic_json(state_dir / JOURNAL_NAME, transaction)
        apply_transaction(state_dir, transaction)
        return {"status": "ADOPTED_ONCE", "topic_id": topic["id"], "style_queue_advanced": STYLE_NAME in changes}


def parser():
    parent = argparse.ArgumentParser()
    sub = parent.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    p = sub.add_parser("validate-plan")
    p.add_argument("--plan", required=True)
    for command in ("peek", "simulate"):
        p = sub.add_parser(command)
        p.add_argument("--product-type", choices=PRODUCTS, required=True)
        p.add_argument("--state-dir", default=str(ROOT / "data/knowledge"))
        p.add_argument("--scene")
        p.add_argument("--family")
        p.add_argument("--context", choices=("residential", "commercial", "any"), default="residential")
        p.add_argument("--scope", choices=("single_space", "whole_home"), default="single_space")
        p.add_argument("--task-id")
        p.add_argument("--style-id")
        p.add_argument("--variant-id", choices=("V1", "V2", "V3"))
        if command == "simulate":
            p.add_argument("--count", type=int, default=12)
    p = sub.add_parser("commit")
    p.add_argument("--state-dir", default=str(ROOT / "data/knowledge"))
    p.add_argument("--task-id", required=True)
    p.add_argument("--selection", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--adoption-kind", choices=("confirmed_plan", "rendered_video"), required=True)
    p = sub.add_parser("recover")
    p.add_argument("--state-dir", default=str(ROOT / "data/knowledge"))
    return parent


def main():
    args = parser().parse_args()
    bank = read(BANK_PATH)
    if args.command == "verify":
        result = verify(bank)
    elif args.command == "validate-plan":
        result = validate_plan(args.plan, bank)
    else:
        state_dir = inside(args.state_dir)
        if args.command == "recover":
            with locked(state_dir):
                if pending(state_dir):
                    apply_transaction(state_dir, read(state_dir / JOURNAL_NAME))
                    result = {"status": "RECOVERED_EXACT_PREPARED_ADOPTION"}
                else:
                    result = {"status": "NO_CHANGE_NO_PENDING_ADOPTION"}
        elif args.command == "commit":
            result = commit(args, bank, state_dir)
        else:
            usage = usage_at(state_dir, bank)
            if args.command == "peek":
                result = select(args, bank, usage, state_dir)
            else:
                if not 1 <= args.count <= 100:
                    raise ValueError("SIMULATION_COUNT_OUT_OF_RANGE")
                if args.task_id:
                    raise ValueError("SIMULATION_MUST_NOT_IMPERSONATE_REAL_TASK")
                results = []
                for n in range(args.count):
                    choice = select(args, bank, usage, state_dir)
                    if choice["topic"] is None:
                        break
                    topic = choice["topic"]
                    results.append({"topic_id": topic["id"], "title": topic["title"], "scene": topic["scene_name"], "family": topic["family"], "semantic_key": topic["semantic_key"]})
                    usage["used"].append({"task_id": f"SIMULATION-{n}", "used_at": date.today().isoformat(), "semantic_key": topic["semantic_key"]})
                result = {"status": "READ_ONLY_SIMULATION_NOT_CONSUMPTION", "product_type": args.product_type, "results": results, "style_queue_advanced": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, KeyError, OSError, StopIteration) as error:
        print(json.dumps({"status": "ERROR", "reason": str(error) or type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
