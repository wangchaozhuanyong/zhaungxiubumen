import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from result_handoff_key import describe_outbox, result_key


class ResultKeyTests(unittest.TestCase):
    def test_maximal_long_identity_fits_gate(self):
        key = result_key("notification_queued", "fc-" + "a" * 170,
                         "content-organic-website", "b" * 200, "c" * 64)
        self.assertLessEqual(len(key), 200)

    def test_retry_same_identity_is_stable(self):
        identity = ("notification_queued", "fc-source-v1", "publishing", "cv-v1", "c" * 64)
        self.assertEqual(result_key(*identity), result_key(*identity))

    def test_original_task_department_version_hash_and_event_are_all_distinct(self):
        baseline = ["notification_queued", "fc-source-v1", "publishing", "cv-v1", "c" * 64]
        keys = {result_key(*baseline)}
        for index, replacement in enumerate(("controller_received", "fc-source-v2",
                                              "qa", "cv-v2", "d" * 64)):
            changed = baseline.copy()
            changed[index] = replacement
            keys.add(result_key(*changed))
        self.assertEqual(len(keys), 6)

    def test_rejects_missing_identity_or_invalid_final_hash(self):
        for identity in (("unknown", "fc-source-v1", "qa", "cv-v1", "c" * 64),
                         ("notification_queued", "", "qa", "cv-v1", "c" * 64),
                         ("notification_queued", "fc-source-v1", "qa", "cv-v1", "g" * 64)):
            with self.assertRaises(ValueError):
                result_key(*identity)

    def test_reads_final_bytes_without_modifying_file_and_never_outputs_body(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            raw = json.dumps({"task_id": "fc-source-v1", "department": "qa",
                              "candidate_version": "cv-v1", "conclusion": "body not emitted"}).encode()
            path.write_bytes(raw)
            first = describe_outbox(path, "notification_queued")
            self.assertEqual(first["result_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)
            self.assertNotIn("body not emitted", json.dumps(first))
            path.write_bytes(raw + b"\n")
            second = describe_outbox(path, "notification_queued")
            self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])


if __name__ == "__main__":
    unittest.main()
