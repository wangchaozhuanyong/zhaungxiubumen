from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "music_library.py"
SPEC = importlib.util.spec_from_file_location("music_library", SCRIPT)
assert SPEC and SPEC.loader
music_library = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(music_library)


def track(track_id: str, duration: float, tags: list[str]) -> dict:
    return {
        "id": track_id,
        "file": f"{track_id}.mp3",
        "duration_seconds": duration,
        "tags": tags,
        "authorization_status": "unknown",
        "usage_scope": "internal_reference_or_same_platform_candidate",
    }


class WeightedRandomRecommendationTests(unittest.TestCase):
    def catalog(self) -> dict:
        return {
            "tracks": [
                track("t1", 24, ["全屋定制", "意式极简", "沉稳"]),
                track("t2", 22, ["全屋定制", "现代简约", "通透"]),
                track("t3", 20, ["衣柜", "意式极简", "高级感"]),
                track("t4", 18, ["儿童房", "轻快"]),
                track("t5", 16, ["生活感"]),
            ]
        }

    def recommend(self, **overrides) -> dict:
        args = {
            "catalog": self.catalog(),
            "duration": 20,
            "tags": [],
            "scope": "internal_reference",
            "limit": 5,
            "channel": None,
            "video_types": ["全屋定制"],
            "styles": ["意式极简"],
            "moods": ["沉稳"],
            "history": [],
            "history_path": None,
            "recent_window": 3,
            "seed": 7,
        }
        args.update(overrides)
        return music_library.recommend_tracks(**args)

    def test_suitability_ranking_precedes_random_selection(self) -> None:
        result = self.recommend()
        self.assertEqual([item["id"] for item in result["ranked_candidates"][:3]], ["t1", "t2", "t3"])
        self.assertGreater(result["ranked_candidates"][0]["score"], result["ranked_candidates"][1]["score"])

    def test_recent_usage_is_excluded(self) -> None:
        history = [
            {"track_id": "t2", "task_id": "old", "used_at": "2026-08-31"},
            {"track_id": "t1", "task_id": "latest", "used_at": "2026-09-01"},
        ]
        result = self.recommend(history=history)
        self.assertNotIn(result["selected"]["id"], {"t1", "t2"})
        self.assertEqual({item["id"] for item in result["recently_excluded"]}, {"t1", "t2"})

    def test_selection_never_escapes_top_three_pool(self) -> None:
        for seed in range(40):
            result = self.recommend(seed=seed)
            pool_ids = {item["id"] for item in result["top_pool"]}
            self.assertIn(result["selected"]["id"], pool_ids)
            self.assertLessEqual(result["selected"]["rank"], 3)

    def test_fixed_seed_is_reproducible(self) -> None:
        first = self.recommend(seed=20260901)
        second = self.recommend(seed=20260901)
        self.assertEqual(first["selected"]["id"], second["selected"]["id"])
        self.assertEqual(first["weights"], second["weights"])

    def test_last_used_is_never_selected_consecutively(self) -> None:
        result = self.recommend(history=[{"track_id": "t1"}], recent_window=0)
        self.assertNotEqual(result["selected"]["id"], "t1")
        self.assertEqual(result["fallback"]["last_used"], "t1")

    def test_recent_window_fallback_relaxes_older_tracks_not_last_used(self) -> None:
        small_catalog = {"tracks": self.catalog()["tracks"][:3]}
        history = [{"track_id": "t2"}, {"track_id": "t3"}, {"track_id": "t1"}]
        result = self.recommend(catalog=small_catalog, history=history, recent_window=3)
        self.assertEqual(result["fallback"]["status"], "recent_window_relaxed_last_used_still_excluded")
        self.assertIn(result["selected"]["id"], {"t2", "t3"})
        self.assertNotEqual(result["selected"]["id"], "t1")

    def test_only_last_used_candidate_blocks_safely(self) -> None:
        result = self.recommend(
            catalog={"tracks": [track("t1", 24, ["全屋定制", "意式极简", "沉稳"])]},
            history=[{"track_id": "t1"}],
        )
        self.assertIsNone(result["selected"])
        self.assertEqual(result["selection_status"], "blocked_no_non_repeating_candidate")

    def test_empty_candidate_behavior_remains_blocked(self) -> None:
        result = self.recommend(catalog={"tracks": []})
        self.assertIsNone(result["selected"])
        self.assertEqual(result["selection_status"], "blocked_no_eligible_track")

    def test_jsonl_history_load_is_read_only_and_ignores_unmounted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "history.jsonl"
            content = "\n".join(
                [
                    json.dumps({"track_id": "t1", "mounted": True}),
                    json.dumps({"track_id": "t2", "mounted": False}),
                ]
            ) + "\n"
            path.write_text(content, encoding="utf-8")
            loaded = music_library.load_usage_history(path)
            self.assertEqual([item["track_id"] for item in loaded], ["t1"])
            self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
