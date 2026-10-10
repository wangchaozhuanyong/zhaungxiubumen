#!/usr/bin/env python3
"""Bounded local tests; never commit to the production content/style ledger."""
import argparse
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("renovation_knowledge", HERE / "renovation_knowledge.py")
rk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rk)
BANK = rk.read(rk.BANK_PATH)
TEST_ROOT = rk.ROOT / "drafts/creative/fc-20261008-renovation-scenario-knowledge-v2/validation"


def args_for(state_dir, **changes):
    values = dict(product_type="design_plan_pitch", state_dir=str(state_dir), scene=None, family=None, context="residential", scope="single_space", task_id="LOCAL-TEST-ONLY", style_id=None, variant_id=None)
    values.update(changes)
    return argparse.Namespace(**values)


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="owned-fixtures-", dir=TEST_ROOT)
        self.state_dir = Path(self.temporary.name)
        self.usage = rk.usage_at(self.state_dir, BANK)

    def tearDown(self):
        self.temporary.cleanup()

    def prepare_adoption(self, style_id=None):
        selection = rk.select(args_for(self.state_dir, style_id=style_id), BANK, self.usage, self.state_dir)
        selection_path = self.state_dir / "selection.json"
        rk.atomic_json(selection_path, selection)
        evidence_path = self.state_dir / "confirmed-plan.json"
        rk.atomic_json(evidence_path, {"task_id": "LOCAL-TEST-ONLY", "topic_id": selection["topic"]["id"], "adoption_status": "owner_confirmed_plan", "owner_confirmation_ref": "LOCAL TEST FIXTURE NOT HUMAN APPROVAL"})
        return argparse.Namespace(state_dir=str(self.state_dir), selection=str(selection_path), evidence=str(evidence_path), adoption_kind="confirmed_plan", task_id="LOCAL-TEST-ONLY"), selection

    def test_bank_counts_and_depth(self):
        self.assertEqual(rk.verify(BANK)["status"], "PASS")
        self.assertEqual(len(BANK["cards"]), 144)

    def test_all_five_products_have_twelve_unique_topics(self):
        for product in rk.PRODUCTS[:-1]:
            usage = copy.deepcopy(self.usage)
            selections = []
            for n in range(12):
                selected = rk.choose(BANK, usage, self.state_dir, product)
                topic = selected["topic"]
                selections.append(topic)
                usage["used"].append({"task_id": f"TEST-{n}", "semantic_key": topic["semantic_key"], "used_at": "2026-10-08"})
            self.assertEqual(len({c["semantic_key"] for c in selections}), 12)
            self.assertGreaterEqual(len({c["family"] for c in selections}), 4)
            self.assertTrue(all(c["family"] != "商用空间" for c in selections))

    def test_cross_product_dedup(self):
        first = rk.choose(BANK, self.usage, self.state_dir, "realistic_effect_ad")
        self.usage["used"].append({"task_id": "SHOWCASE", "semantic_key": first["topic"]["semantic_key"], "used_at": "2026-10-08"})
        second = rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch")
        self.assertNotEqual(first["topic"]["semantic_key"], second["topic"]["semantic_key"])

    def test_family_recent_window_when_available(self):
        usage = copy.deepcopy(self.usage)
        families = []
        for n in range(12):
            topic = rk.choose(BANK, usage, self.state_dir, "design_plan_pitch")["topic"]
            self.assertNotIn(topic["family"], families[-3:])
            families.append(topic["family"])
            usage["used"].append({"task_id": str(n), "semantic_key": topic["semantic_key"], "used_at": "2026-10-08"})

    def test_requested_salon_and_commercial_context(self):
        topic = rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch", scene="salon", context="commercial")["topic"]
        self.assertEqual(topic["scene_key"], "salon")
        with self.assertRaisesRegex(ValueError, "NO_COMPATIBLE"):
            rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch", scene="salon", context="residential")

    def test_brand_process_fixed(self):
        selection = rk.choose(BANK, self.usage, self.state_dir, "brand_process_ad")
        self.assertIsNone(selection["topic"])
        self.assertIsNone(selection["style"])

    def test_whole_home_has_combination_not_one_room(self):
        selection = rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch", scope="whole_home")
        self.assertGreaterEqual(len(selection["blueprint"]["supporting_topic_ids"]), 3)
        self.assertEqual(selection["blueprint"]["scope"], "whole_home")
        with self.assertRaisesRegex(ValueError, "WHOLE_HOME_SCOPE"):
            rk.choose(BANK, self.usage, self.state_dir, "cabinet_detail_explainer", scope="whole_home")

    def test_peek_is_read_only(self):
        before = list(self.state_dir.iterdir())
        rk.select(args_for(self.state_dir), BANK, self.usage, self.state_dir)
        self.assertEqual(list(self.state_dir.iterdir()), before)

    def test_old_content_cli_rejects_migrated_project_without_writes(self):
        manifest = rk.read(rk.ROOT / "data/knowledge/full-house-custom-knowledge-manifest.json")
        rk.atomic_json(self.state_dir / "full-house-custom-knowledge-manifest.json", manifest)
        script = Path(manifest["style_helper"]["path"])
        before = {p.name: rk.digest(p) for p in self.state_dir.iterdir()}
        for command in ("peek", "commit"):
            args = [sys.executable, str(script), command, "--product-type", "design_plan_pitch", "--state-dir", str(self.state_dir)]
            if command == "commit":
                args.extend(["--task-id", "LOCAL-TEST-ONLY", "--video-title", "TEST"])
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LEGACY_CONTENT_CLI_RETIRED_FOR_PROJECT", result.stderr)
        self.assertEqual(before, {p.name: rk.digest(p) for p in self.state_dir.iterdir()})

    def test_style_helpers_still_cover_72_combinations(self):
        engine = rk.style_engine()
        library, state, _ = engine.load_style_context(self.state_dir)
        self.assertEqual(len(library["styles"]), 24)
        selected = []
        for _ in range(72):
            style, _, _ = engine.select_style(self.state_dir)
            selected.append((style["style_id"], style["selected_variant"]["id"]))
            engine.advance_style(state)
            rk.atomic_json(self.state_dir / rk.STYLE_NAME, state)
        self.assertEqual(len(set(selected)), 72)
        self.assertEqual(selected[0], (state["next_style_id"], state["variant_id"]))
        self.assertEqual(state["cycle_number"], 2)

    def test_generic_unmigrated_topic_selector_remains_read_only(self):
        engine = rk.style_engine()
        topic, _, _ = engine.select_topic("design_plan_pitch", self.state_dir)
        self.assertTrue(topic["id"])
        self.assertEqual(list(self.state_dir.iterdir()), [])

    def test_active_manifest_has_one_content_bank_and_existing_sources(self):
        manifest = rk.read(rk.ROOT / "data/knowledge/full-house-custom-knowledge-manifest.json")
        banks = [x for x in manifest["knowledge_bases"] if x["role"] == "active_deep_cards"]
        self.assertEqual(len(banks), 1)
        self.assertEqual(banks[0]["path"], manifest["active_content_library"])
        for key in ("active_content_library", "selector", "protocol", "active_usage_state", "request_examples", "retired_assets_index"):
            self.assertTrue((rk.ROOT / manifest[key]).is_file(), key)
        self.assertTrue(all((rk.ROOT / p).is_file() for p in manifest["historical_usage_inputs"]))
        self.assertTrue(Path(manifest["style_helper"]["path"]).is_file())

    def test_retired_learning_preserves_original_history(self):
        index = rk.read(rk.ROOT / "backups/fc-20261008-visual-skill-cleanup-v1/retirement-index.json")
        current = rk.read(rk.ROOT / "data/learning/departments/visual-design-video.json")
        before = rk.read(rk.ROOT / "backups/fc-20261008-visual-skill-cleanup-v1/before/project/data/learning/departments/visual-design-video.json")
        active_ids = {x["lesson_id"] for k in ("verified_lessons", "provisional_lessons") for x in current[k]}
        retired = {x["lesson_id"]: x for x in current["retired_lessons"]}
        for row in index["retired_learning"]:
            self.assertNotIn(row["lesson_id"], active_ids)
            entry = retired[row["lesson_id"]]
            original = next(x for x in before[row["original_bucket"]] if x["lesson_id"] == row["lesson_id"])
            self.assertEqual(entry["status"], "retired")
            for key, value in original.items():
                if key != "status":
                    self.assertEqual(entry[key], value, key)
        self.assertEqual(current["inherited_lessons"], before["inherited_lessons"])
        all_ids = {x["lesson_id"] for k in ("verified_lessons", "provisional_lessons", "retired_lessons") for x in current[k]}
        before_ids = {x["lesson_id"] for k in ("verified_lessons", "provisional_lessons", "retired_lessons") for x in before[k]}
        self.assertTrue(before_ids <= all_ids)

    def test_depth_plan_rejects_empty_slogans(self):
        args, selection = self.prepare_adoption()
        plan = {"task_id": "LOCAL-TEST-ONLY", "selected_product_type": "design_plan_pitch", "knowledge_plan": {"selection_path": str(Path(args.selection).relative_to(rk.ROOT)), "selection_sha256": rk.digest(args.selection), "primary_topic_id": selection["topic"]["id"], "design_actions": ["高级感，空间更美"], "shot_evidence": [], "boundary_handling": "do_not_claim_unverified_performance", "unverified_performance_claims": []}}
        path = self.state_dir / "content-plan.json"
        rk.atomic_json(path, plan)
        with self.assertRaisesRegex(ValueError, "MISSING_SPECIFIC"):
            rk.validate_plan(path, BANK)
        plan["knowledge_plan"]["design_actions"] = selection["topic"]["design_actions"]
        plan["knowledge_plan"]["shot_evidence"] = [{"action": a, "show": "具体柜体与家具的取放和开合关系可见", "scene_id": "shot-1", "mode": "full_view"} for a in selection["topic"]["design_actions"]]
        rk.atomic_json(path, plan)
        self.assertEqual(rk.validate_plan(path, BANK)["status"], "PASS")

    def test_depth_plan_requires_visible_shots(self):
        args, selection = self.prepare_adoption()
        plan = {"task_id": "LOCAL-TEST-ONLY", "selected_product_type": "design_plan_pitch", "knowledge_plan": {"selection_path": str(Path(args.selection).relative_to(rk.ROOT)), "selection_sha256": rk.digest(args.selection), "primary_topic_id": selection["topic"]["id"], "design_actions": selection["topic"]["design_actions"], "shot_evidence": [], "boundary_handling": "no_unverified_claims", "unverified_performance_claims": []}}
        path = self.state_dir / "content-plan.json"
        rk.atomic_json(path, plan)
        with self.assertRaisesRegex(ValueError, "NO_VISIBLE_SHOT"):
            rk.validate_plan(path, BANK)

    def test_legacy_recent_aliases_respected(self):
        rk.atomic_json(self.state_dir / "design-plan-used-topics.json", {"used": [{"topic_id": "B01", "task_id": "OLD", "used_at": "2026-10-08"}]})
        selection = rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch")
        self.assertNotEqual(selection["topic"]["semantic_key"], "entry:1")

    def test_recent_pool_never_silently_repeats(self):
        self.usage["used"] = [{"task_id": f"RECENT-{i}", "semantic_key": c["semantic_key"], "used_at": "2026-10-08"} for i, c in enumerate(BANK["cards"]) if c["scene_key"] == "entry"]
        with self.assertRaisesRegex(ValueError, "CONTENT_POOL_EXHAUSTED"):
            rk.choose(BANK, self.usage, self.state_dir, "design_plan_pitch", scene="entry")

    def test_commit_once_and_rework_does_not_advance(self):
        args, selection = self.prepare_adoption()
        first = rk.commit(args, BANK, self.state_dir)
        before = {name: rk.digest(self.state_dir / name) for name in (rk.USAGE_NAME, rk.STYLE_NAME)}
        second = rk.commit(args, BANK, self.state_dir)
        self.assertEqual(first["status"], "ADOPTED_ONCE")
        self.assertEqual(second["status"], "ALREADY_ADOPTED_NO_STATE_CHANGE")
        self.assertEqual(before, {name: rk.digest(self.state_dir / name) for name in before})
        old = rk.select(args_for(self.state_dir), BANK, rk.usage_at(self.state_dir, BANK), self.state_dir)
        self.assertEqual(old["topic"]["id"], selection["topic"]["id"])

    def test_explicit_style_does_not_advance_queue(self):
        args, _ = self.prepare_adoption(style_id="S09")
        result = rk.commit(args, BANK, self.state_dir)
        self.assertFalse(result["style_queue_advanced"])
        self.assertFalse((self.state_dir / rk.STYLE_NAME).exists())

    def test_stale_peek_rejected(self):
        args, _ = self.prepare_adoption()
        rk.atomic_json(self.state_dir / rk.USAGE_NAME, self.usage)
        with self.assertRaisesRegex(ValueError, "STATE_CHANGED"):
            rk.commit(args, BANK, self.state_dir)

    def test_candidate_is_not_consumption(self):
        args, _ = self.prepare_adoption()
        value = rk.read(args.evidence)
        value["adoption_status"] = "unapproved_candidate"
        rk.atomic_json(Path(args.evidence), value)
        with self.assertRaisesRegex(ValueError, "CANDIDATE_IS_NOT"):
            rk.commit(args, BANK, self.state_dir)
        self.assertFalse((self.state_dir / rk.USAGE_NAME).exists())

    def test_project_isolation(self):
        with self.assertRaisesRegex(ValueError, "OUTSIDE_FLASHCAST"):
            rk.inside("/tmp/not-flashcast/state.json")

    def test_prepared_transaction_recovery_and_conflict(self):
        value = {"used": []}
        content_hash = __import__("hashlib").sha256((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()
        transaction = {"status": "prepared", "files": {rk.USAGE_NAME: {"before_hash": None, "after_hash": content_hash, "after": value}}}
        rk.atomic_json(self.state_dir / rk.JOURNAL_NAME, transaction)
        with self.assertRaisesRegex(ValueError, "PENDING_ADOPTION"):
            rk.select(args_for(self.state_dir), BANK, self.usage, self.state_dir)
        rk.apply_transaction(self.state_dir, transaction)
        self.assertFalse(rk.pending(self.state_dir))
        conflict = copy.deepcopy(transaction)
        conflict["status"] = "prepared"
        rk.atomic_json(self.state_dir / rk.USAGE_NAME, {"used": [{"unrelated": True}]})
        with self.assertRaisesRegex(ValueError, "TRANSACTION_CONFLICT"):
            rk.apply_transaction(self.state_dir, conflict)

    def test_partial_two_file_transaction_recovers_without_double_advance(self):
        import hashlib
        content = {"used": [{"task_id": "LOCAL-TEST-ONLY"}]}
        style = {"next_sequence_index": 1, "used": [{"task_id": "LOCAL-TEST-ONLY"}]}
        files = {}
        for name, value in ((rk.USAGE_NAME, content), (rk.STYLE_NAME, style)):
            sha = hashlib.sha256((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()).hexdigest()
            files[name] = {"before_hash": None, "after_hash": sha, "after": value}
        transaction = {"status": "prepared", "files": files}
        rk.atomic_json(self.state_dir / rk.JOURNAL_NAME, transaction)
        rk.atomic_json(self.state_dir / rk.USAGE_NAME, content)
        rk.apply_transaction(self.state_dir, transaction)
        before = rk.digest(self.state_dir / rk.STYLE_NAME)
        rk.apply_transaction(self.state_dir, transaction)
        self.assertEqual(before, rk.digest(self.state_dir / rk.STYLE_NAME))
        self.assertEqual(rk.read(self.state_dir / rk.STYLE_NAME)["next_sequence_index"], 1)

    def test_empty_fingerprints_do_not_bypass_concurrency_guard(self):
        args, selection = self.prepare_adoption()
        selection["state_fingerprints"] = {}
        rk.atomic_json(Path(args.selection), selection)
        with self.assertRaisesRegex(ValueError, "MISSING_EXACT_STATE"):
            rk.commit(args, BANK, self.state_dir)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(KnowledgeTests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "details": stream.getvalue(), "production_history_written": False}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
