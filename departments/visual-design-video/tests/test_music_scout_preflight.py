from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/music_scout_preflight.py"
SPEC = importlib.util.spec_from_file_location("music_scout_preflight", SCRIPT)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class MusicScoutIdentityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc)
        self.registry = {"departments": [{"id": gate.DEPARTMENT, "chat_binding": {
            "task_id": gate.THREAD_ID, "project_id": gate.PROJECT_ID, "host_id": "local",
            "title": "FLASH CAST｜视觉设计与视频部｜2026-09", "cwd": str(gate.ROOT),
            "sidebar_section_id": "section-live", "status": "bound_and_visible"}}]}
        self.snapshot = {"source_tool": "list_threads", "observed_at": self.now.isoformat(),
            "threads": [{"id": gate.THREAD_ID, "projectId": gate.PROJECT_ID, "hostId": "local",
                "title": self.registry["departments"][0]["chat_binding"]["title"],
                "cwd": str(gate.ROOT), "kind": "codex", "status": "active"}],
            "sections": [{"sectionId": "section-live", "name": "装修公司部门",
                "itemKeys": [f"codex:thread:local:{gate.THREAD_ID}"]}]}

    def check(self, expected="BLOCKED_CROSS_PROJECT"):
        result = gate.validate(self.registry, self.snapshot, gate.ROOT, self.now)
        self.assertEqual(result["status"], expected)
        self.assertEqual(result["business_writes_allowed"], expected == "PASS")

    def test_complete_live_identity_passes(self):
        self.check("PASS")

    def test_read_thread_missing_project_is_not_accepted_as_live_list(self):
        self.snapshot["source_tool"] = "read_thread"
        del self.snapshot["threads"][0]["projectId"]
        self.check()

    def test_missing_or_wrong_live_fields_fail_closed(self):
        for key in ("id", "projectId", "hostId", "title", "cwd", "kind", "status"):
            original = deepcopy(self.snapshot)
            with self.subTest(field=key, condition="missing"):
                del self.snapshot["threads"][0][key]
                self.check()
            self.snapshot = deepcopy(original)
            with self.subTest(field=key, condition="wrong"):
                self.snapshot["threads"][0][key] = "unrelated-project"
                self.check()
            self.snapshot = original

    def test_duplicate_target_rejected(self):
        self.snapshot["threads"].append(deepcopy(self.snapshot["threads"][0]))
        self.check()

    def test_stale_and_future_snapshots_rejected(self):
        for delta in (-301, 1):
            self.snapshot["observed_at"] = (self.now + timedelta(seconds=delta)).isoformat()
            self.check()

    def test_unzoned_time_rejected(self):
        self.snapshot["observed_at"] = "2026-09-27T03:00:00"
        self.check()

    def test_missing_registry_identity_rejected(self):
        self.registry["departments"] = []
        self.check()

    def test_sidebar_name_mismatch_rejected(self):
        self.snapshot["sections"][0]["name"] = "装修公司总控"
        self.check()

    def test_duplicate_sidebar_membership_rejected(self):
        self.snapshot["sections"].append(deepcopy(self.snapshot["sections"][0]))
        self.check()

    def test_sidebar_id_only_drift_requires_recovery(self):
        self.snapshot["sections"][0]["sectionId"] = "new-runtime-id"
        self.check("STALE_SIDEBAR_BINDING")

    def test_wrong_process_cwd_rejected(self):
        self.assertEqual(gate.validate(self.registry, self.snapshot, Path("/tmp"), self.now)["status"], "BLOCKED_CROSS_PROJECT")

    def test_output_outside_project_rejected(self):
        with self.assertRaises(Exception):
            gate.project_path("/tmp/identity.json")


if __name__ == "__main__":
    unittest.main()
