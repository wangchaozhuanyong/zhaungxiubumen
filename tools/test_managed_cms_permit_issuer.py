import unittest
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib
import os
import subprocess
import tempfile
from unittest.mock import patch

from tools import managed_cms_permit_issuer as issuer


class ManagedCmsPermitIssuerTests(unittest.TestCase):
    def setUp(self):
        self.target = issuer.TARGETS["builtin-whole-house-custom-v1"]
        self.now = datetime(2026, 9, 21, 12, 15, tzinfo=timezone.utc)
        self.operations = {
            "department": "operations", "operations_chat_task_id": issuer.OPERATIONS_THREAD_ID,
            "decision": "AUTO_RELEASE", "operation": "publish",
            "task_id": self.target["task_id"], "action_id": self.target["action_id"],
            "action_class": "cms_write", "scope": self.target["scope"],
            "candidate_version": self.target["candidate_version"], "record_id": self.target["record_id"],
            "payload_sha256": "a" * 64, "qa_receipt_id": "qa-123", "decision_id": "ops-123",
            "decided_at": "2026-09-21T12:05:00Z",
        }
        self.policy = {
            "status": "allow", "department": "content-organic-website",
            "task_id": self.target["task_id"], "action_id": self.target["action_id"],
            "action_class": "cms_write", "scope": self.target["scope"],
            "payload_sha256": "a" * 64, "approval_status": "consumed",
            "decision_id": "pol-123", "checked_at": "2026-09-21T12:10:00Z",
        }

    def test_missing_qa_receipt_is_blocked_before_any_issue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "data/workflows" / f"{self.target['task_id']}.json").write_text(
                json.dumps({"current_state": "evidence_received"}))
            with self.assertRaisesRegex(issuer.PermitEvidenceError, r"no current (?:exact )?QA PASS"):
                issuer.validate_qa(root, self.target, "publish")

    def test_blocked_retry_requires_latest_exact_execution_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            snapshot = {"current_state": "blocked", "blockers": ["execution_result_blocked"],
                        "resume_from": "owner_approved"}
            (root / "data/workflows" / f"{self.target['task_id']}.json").write_text(json.dumps(snapshot))
            receipt = {"receipt_type": "execution_result", "receipt_id": "blocked-123",
                       "verdict": "blocked", "department": "content-organic-website",
                       "task_id": self.target["task_id"], "action_id": self.target["action_id"],
                       "action_class": "cms_write", "scope": self.target["scope"],
                       "approval_id": "apr-123"}
            policy = {**self.policy, "approval_id": "apr-123",
                      "approval_basis": "blocked_execution_retry",
                      "retry_source_receipt_id": "blocked-123"}
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=([receipt], [])):
                issuer.validate_retry_state(root, self.target, "publish", policy)
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "latest exact blocked execution"):
                    issuer.validate_retry_state(root, self.target, "publish",
                                                {**policy, "retry_source_receipt_id": "older-122"})
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "latest exact blocked execution"):
                    issuer.validate_retry_state(root, self.target, "publish",
                                                {**policy, "approval_id": "other-approval"})
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact execution retry policy"):
                    issuer.validate_retry_state(root, self.target, "publish",
                                                {**policy, "approval_basis": "standing_authorization"})
            snapshot["current_state"] = "owner_approved"
            (root / "data/workflows" / f"{self.target['task_id']}.json").write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(issuer.PermitEvidenceError, "original blocked workflow"):
                issuer.validate_retry_state(root, self.target, "publish", policy)

    def test_fixed_qa_receipt_must_bind_exact_candidate_and_release_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "logs/department-outbox").mkdir(parents=True)
            (root / "data/workflows" / f"{self.target['task_id']}.json").write_text('{"current_state":"qa_passed"}')
            path = "logs/department-outbox/exact-qa.json"
            outbox = {"department": "qa", "task_id": self.target["task_id"],
                      "status": "completed", "gate_status": "PASS_FOR_AUTO_RELEASE", "blockers": [],
                      "candidate_version": self.target["candidate_version"], "verdict": "pass",
                      "release_boundary": {"scope": self.target["scope"], "publish_authorized": True}}
            (root / path).write_text(json.dumps(outbox))
            qa = {"receipt_type": "qa_verdict", "department": "qa", "verdict": "pass",
                  "chat_task_id": issuer.QA_THREAD_ID, "task_id": self.target["task_id"],
                  "scope": self.target["scope"], "action_class": "cms_content_candidate",
                  "action_id": self.target["action_id"],
                  "evidence": [{"path": path}], "receipt_id": "qa-123"}
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=([qa], [])):
                self.assertEqual(issuer.validate_qa(root, self.target, "publish")["receipt_id"], "qa-123")
                workflow = root / "data/workflows" / f"{self.target['task_id']}.json"
                workflow.write_text('{"current_state":"closed"}')
                self.assertEqual(issuer.validate_qa(root, self.target, "publish")["receipt_id"], "qa-123")
                with patch.object(issuer.wc, "_validate_receipt_chain", return_value=(
                        [qa, {**qa, "receipt_id": "newer-blocked", "verdict": "blocked"}], [])):
                    with self.assertRaisesRegex(issuer.PermitEvidenceError, "Latest fixed QA"):
                        issuer.validate_qa(root, self.target, "publish")
                with patch.object(issuer.wc, "_validate_receipt_chain", return_value=(
                        [qa, {**qa, "verdict": "blocked"}, {**qa, "receipt_id": "newest-pass"}], [])):
                    self.assertEqual(issuer.validate_qa(root, self.target, "publish")["receipt_id"], "newest-pass")
                qa["action_id"] = "unrelated-completed-sibling"
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, self.target, "publish")
                qa["action_id"] = self.target["action_id"]
                (root / path).write_text(json.dumps({**outbox, "candidate_version": "forged-version"}))
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_qa(root, self.target, "publish")
                (root / path).write_text(json.dumps(outbox))
                workflow.write_text(json.dumps({"current_state": "blocked",
                                                "blockers": ["execution_result_blocked"],
                                                "resume_from": "owner_approved"}))
                self.assertEqual(issuer.validate_qa(root, self.target, "publish", allow_blocked_retry=True)["receipt_id"], "qa-123")
                workflow.write_text(json.dumps({"current_state": "blocked",
                                                "blockers": ["qa_verdict_blocked"],
                                                "resume_from": "owner_approved"}))
                with self.assertRaisesRegex(issuer.PermitEvidenceError, r"no current (?:exact )?QA PASS"):
                    issuer.validate_qa(root, self.target, "publish", allow_blocked_retry=True)
                workflow.write_text('{"current_state":"qa_passed"}')
                qa["action_id"] = f"rollback-{self.target['candidate_version']}"
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, self.target, "publish")
                qa["action_id"] = self.target["action_id"]
                (root / path).write_text(json.dumps({**outbox, "candidate_version": "forged-version"}))
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_qa(root, self.target, "publish")
                (root / path).write_text(json.dumps({**outbox, "release_boundary": {"scope": self.target["scope"], "publish_authorized": False}}))
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_qa(root, self.target, "publish")

    def test_shared_content_task_selects_the_exact_kitchen_or_design_qa_receipt(self):
        targets = [issuer.TARGETS[name] for name in (
            "kitchen-r1-cms-row-20260924-v1", "design-r1-cms-row-20260924-v1",
            "selangor-service-area-r1-v4")]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "logs/department-outbox").mkdir(parents=True)
            receipts = []
            for index, target in enumerate(targets):
                task_id = target["task_id"]
                (root / "data/workflows" / f"{task_id}.json").write_text('{"current_state":"owner_approved"}')
                path = f"logs/department-outbox/candidate-{index}.json"
                outbox = {
                    "department": "qa", "task_id": task_id, "status": "completed",
                    "gate_status": "PASS_FOR_AUTO_RELEASE", "qa_verdict": "pass",
                    "scope": target["scope"], "action_id": target["action_id"],
                    "candidate": {"row_id": target["record_id"], "slug": target["slug"],
                                  "candidate_row_sha256": target["candidate"][1]},
                }
                if index != 2:
                    outbox["candidate_version"] = target["candidate_version"]
                (root / path).write_text(json.dumps(outbox))
                receipts.append({"receipt_type": "qa_verdict", "department": "qa", "verdict": "pass",
                                 "chat_task_id": issuer.QA_THREAD_ID, "task_id": task_id,
                                 "scope": target["scope"], "action_class": "cms_content_candidate",
                                 "action_id": target["action_id"],
                                 "evidence": [{"path": path}], "receipt_id": f"qa-{index}"})
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=(receipts, [])):
                self.assertEqual(issuer.validate_qa(root, targets[0], "publish")["receipt_id"], "qa-0")
                self.assertEqual(issuer.validate_qa(root, targets[1], "publish")["receipt_id"], "qa-1")
                self.assertEqual(issuer.validate_qa(root, targets[2], "publish")["receipt_id"], "qa-2")
                path = root / "logs/department-outbox/candidate-0.json"
                row = json.loads(path.read_text())
                row["candidate"]["candidate_row_sha256"] = "0" * 64
                path.write_text(json.dumps(row))
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "QA PASS evidence"):
                    issuer.validate_qa(root, targets[0], "publish")

    def test_rollback_requires_its_own_action_bound_qa_receipt(self):
        target = issuer.TARGETS["kitchen-r1-cms-row-20260924-v1"]
        rollback_action = f"rollback-{target['candidate_version']}"
        rollback_version = f"{target['candidate_version']}-rollback-v1"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "logs/department-outbox").mkdir(parents=True)
            (root / "data/workflows" / f"{target['task_id']}.json").write_text('{"current_state":"qa_passed"}')
            publish_path = "logs/department-outbox/publish-qa.json"
            rollback_path = "logs/department-outbox/rollback-qa.json"
            candidate = {"row_id": target["record_id"], "slug": target["slug"],
                         "candidate_row_sha256": target["candidate"][1]}
            base = {"department": "qa", "task_id": target["task_id"], "status": "completed",
                    "gate_status": "PASS_FOR_AUTO_RELEASE", "verdict": "pass",
                    "scope": target["scope"], "blockers": [], "candidate": candidate}
            (root / publish_path).write_text(json.dumps({**base, "action_id": target["action_id"],
                                                          "candidate_version": target["candidate_version"]}))
            publish_qa = {"receipt_type": "qa_verdict", "department": "qa", "verdict": "pass",
                          "chat_task_id": issuer.QA_THREAD_ID, "task_id": target["task_id"],
                          "scope": target["scope"], "action_class": "cms_content_candidate",
                          "action_id": target["action_id"], "evidence": [{"path": publish_path}],
                          "receipt_id": "publish-qa"}
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=([publish_qa], [])) as chain:
                self.assertEqual(issuer.validate_qa(root, target, "publish")["receipt_id"], "publish-qa")
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, target, "rollback")
                # Model an append-only evidence replacement that makes the old publish outbox
                # look like a rollback outbox while the original QA receipt stays unchanged.
                (root / publish_path).write_text(json.dumps({**base, "action_id": rollback_action,
                                                              "candidate_version": rollback_version}))
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, target, "rollback")
                chain.return_value = ([publish_qa], ["receipt_1:evidence_changed"])
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "receipt chain invalid"):
                    issuer.validate_qa(root, target, "rollback")
                chain.return_value = ([publish_qa], [])

                (root / rollback_path).write_text(json.dumps({**base, "action_id": rollback_action,
                                                               "candidate_version": rollback_version}))
                rollback_qa = {**publish_qa, "action_id": rollback_action,
                               "evidence": [{"path": rollback_path}], "receipt_id": "rollback-qa"}
                chain.return_value = ([publish_qa, rollback_qa], [])
                self.assertEqual(issuer.validate_qa(root, target, "rollback")["receipt_id"], "rollback-qa")
                (root / rollback_path).write_text(json.dumps({**base, "action_id": rollback_action,
                                                               "candidate_version": "wrong-version"}))
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact candidate and scope"):
                    issuer.validate_qa(root, target, "rollback")
                (root / rollback_path).write_text(json.dumps({**base, "action_id": rollback_action,
                                                               "candidate_version": rollback_version,
                                                               "candidate": {**candidate, "row_id": "wrong-row"}}))
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact candidate and scope"):
                    issuer.validate_qa(root, target, "rollback")

    def test_exact_operations_and_consumed_policy_are_required(self):
        issuer.validate_operations(self.operations, self.target, "publish", "a" * 64, "qa-123", self.now)
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.validate_operations({**self.operations, "operations_chat_task_id": "01a0ba3a-b994-7a23-b059-29bd4e7772cd"},
                                       self.target, "publish", "a" * 64, "qa-123", self.now)
        issuer.validate_policy(self.policy, self.target, "publish", "a" * 64, self.operations, self.now)
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.validate_operations({**self.operations, "scope": "flashcast.com.my:other"},
                                       self.target, "publish", "a" * 64, "qa-123", self.now)
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.validate_operations({**self.operations, "payload_sha256": "b" * 64},
                                       self.target, "publish", "a" * 64, "qa-123", self.now)
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.validate_policy({**self.policy, "approval_status": "active"},
                                   self.target, "publish", "a" * 64, self.operations, self.now)
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.validate_policy({**self.policy, "checked_at": "2026-09-21T11:00:00Z"},
                                   self.target, "publish", "a" * 64, self.operations, self.now)

    def test_exact_original_candidate_and_rollback_files_unchanged(self):
        self.assertTrue(issuer.exact_file(issuer.ROOT, self.target["candidate"]).is_file())
        self.assertTrue(issuer.exact_file(issuer.ROOT, self.target["rollback"]).is_file())
        with self.assertRaises(issuer.PermitEvidenceError):
            issuer.exact_file(issuer.ROOT, (self.target["candidate"][0], "0" * 64))
        for name in ("kitchen-r1-cms-row-20260924-v1", "design-r1-cms-row-20260924-v1",
                     "selangor-service-area-r1-v4", "org-017-bathroom-faq-parity-reconciliation-v4"):
            target = issuer.TARGETS[name]
            self.assertTrue(issuer.exact_file(target["evidence_root"], target["candidate"]).is_file())
            self.assertTrue(issuer.exact_file(target["evidence_root"], target["rollback"]).is_file())

    def test_four_protected_targets_pin_original_files_and_qa(self):
        names = ("office-service-scope-r1-v1", *sorted(issuer.BLOG_TARGETS))
        self.assertEqual(len(names), 4)
        self.assertEqual(len({issuer.TARGETS[name]["record_id"] for name in names}), 4)
        for name in names:
            target = issuer.TARGETS[name]
            self.assertTrue(target["scope"].startswith("flashcast.com.my:"))
            self.assertTrue(target["qa_candidate_only"])
            for field in ("candidate", "rollback", "qa_outbox"):
                self.assertTrue(issuer.exact_file(issuer.ROOT, target[field]).is_file())
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "Evidence file changed"):
                    issuer.exact_file(issuer.ROOT, (target[field][0], "0" * 64))
        office = issuer.TARGETS["office-service-scope-r1-v1"]
        self.assertTrue(office["scope"].endswith(":content_en,content_zh"))

    def test_blog_rollback_binds_completed_parent_run_and_other_targets_do_not_expand(self):
        for name in issuer.BLOG_TARGETS:
            self.assertEqual(issuer.rollback_parent_binding(name, "rollback", "permit-1", 123),
                             {"parentPermitId": "permit-1", "parentRunId": 123})
            for permit, run in ((None, 123), ("permit-1", None), ("permit-1", 0),
                                ("permit-1", -1)):
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "completed parent permit and run"):
                    issuer.rollback_parent_binding(name, "rollback", permit, run)
        self.assertEqual(issuer.rollback_parent_binding("office-service-scope-r1-v1", "rollback", "permit-1", 123),
                         {"parentPermitId": "permit-1"})
        self.assertEqual(issuer.rollback_parent_binding("office-service-scope-r1-v1", "publish", None, None),
                         {"parentPermitId": None})
        with self.assertRaisesRegex(issuer.PermitEvidenceError, "cannot reuse a rollback parent"):
            issuer.rollback_parent_binding("office-service-scope-r1-v1", "publish", "permit-1", 123)

    def test_blog_parent_status_must_be_completed_exact_publish_run(self):
        target = issuer.TARGETS["blog-renovation-quotation-links-r1-v1"]
        status = {"permitId": "parent-123", "status": "completed", "operation": "publish",
                  "taskId": target["task_id"], "actionId": target["action_id"],
                  "candidateVersion": target["candidate_version"], "githubRunId": 123,
                  "savedId": target["record_id"], "savedUpdatedAt": "2026-09-25T12:00:00Z"}
        issuer.validate_completed_parent_status(status, target, "parent-123", 123)
        for key, bad_value in (("permitId", "other-parent"), ("status", "issued"),
                               ("operation", "rollback"), ("taskId", "other-task"),
                               ("actionId", "other-blog-action"),
                               ("candidateVersion", "other-blog-version"),
                               ("githubRunId", 124), ("savedId", "other-row"),
                               ("savedUpdatedAt", None)):
            with self.subTest(key=key), self.assertRaisesRegex(issuer.PermitEvidenceError, "completed exact publish run"):
                issuer.validate_completed_parent_status({**status, key: bad_value}, target, "parent-123", 123)

    def test_pinned_qa_outbox_may_precede_exact_qa_verdict_without_rewriting_history(self):
        original = issuer.TARGETS["blog-renovation-quotation-links-r1-v1"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "logs/department-outbox").mkdir(parents=True)
            (root / "data/workflows" / f"{original['task_id']}.json").write_text('{"current_state":"qa_passed"}')
            path = "logs/department-outbox/quotation-qa.json"
            outbox = {"department": "qa", "task_id": original["task_id"],
                      "status": "completed", "gate_status": "PASS_FOR_AUTO_RELEASE",
                      "qa_verdict": "pass", "scope": original["scope"],
                      "action_id": original["action_id"],
                      "candidate_version": original["candidate_version"]}
            (root / path).write_text(json.dumps(outbox))
            digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
            target = {**original, "qa_outbox": (path, digest)}
            outbox_receipt = {"receipt_id": "outbox-1", "receipt_type": "outbox_received",
                              "department": "qa", "chat_task_id": issuer.QA_THREAD_ID,
                              "task_id": original["task_id"],
                              "evidence": [{"path": path, "sha256": digest}]}
            qa_receipt = {"receipt_id": "qa-1", "receipt_type": "qa_verdict", "department": "qa",
                          "verdict": "pass", "chat_task_id": issuer.QA_THREAD_ID,
                          "task_id": original["task_id"], "scope": original["scope"],
                          "action_class": "cms_content_candidate", "action_id": original["action_id"],
                          "evidence": [{"path": "reports/shared-qa.md", "sha256": "f" * 64}]}
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=([outbox_receipt, qa_receipt], [])) as chain:
                self.assertEqual(issuer.validate_qa(root, target, "publish")["receipt_id"], "qa-1")
                chain.return_value = ([{**outbox_receipt, "evidence": [{"path": path, "sha256": "0" * 64}]}, qa_receipt], [])
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact candidate and scope"):
                    issuer.validate_qa(root, target, "publish")
                chain.return_value = ([outbox_receipt, {**qa_receipt, "action_id": "other-blog"}], [])
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, target, "publish")
                chain.return_value = ([qa_receipt, outbox_receipt], [])
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact candidate and scope"):
                    issuer.validate_qa(root, target, "publish")

    def test_bathroom_requires_pinned_v4_qa_and_exact_two_field_request(self):
        original = issuer.TARGETS["org-017-bathroom-faq-parity-reconciliation-v4"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data/workflows").mkdir(parents=True)
            (root / "logs/department-outbox").mkdir(parents=True)
            (root / "data/workflows" / f"{original['task_id']}.json").write_text('{"current_state":"qa_passed"}')
            def pin(relative, value):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
                return relative, hashlib.sha256(path.read_bytes()).hexdigest()
            baseline = {"id": original["record_id"], "slug": original["slug"],
                        "updated_at": "2026-09-24T01:00:00+00:00",
                        "faqs_en": [{"q": "Old?", "a": "Old."}],
                        "faqs_zh": [{"q": "旧？", "a": "旧。"}], "title_en": "Bathroom"}
            desired = {**baseline, "faqs_en": [*baseline["faqs_en"], {"q": "New?", "a": "New."}],
                       "faqs_zh": [*baseline["faqs_zh"], {"q": "新？", "a": "新。"}]}
            candidate = pin("candidate.json", desired)
            rollback = pin("rollback.json", baseline)
            request = pin("request.json", {"mode": "dry-run", "contentType": "service",
                                            "record": desired, "expectedUpdatedAt": baseline["updated_at"]})
            qa_path = "logs/department-outbox/bathroom-qa.json"
            qa_outbox = {"department": "qa", "task_id": original["task_id"], "status": "completed",
                         "gate_status": "PASS_FOR_AUTO_RELEASE", "verdict": "pass", "blockers": [],
                         "candidate_version": original["candidate_version"],
                         "action_id": original["action_id"], "scope": original["scope"]}
            qa_file = pin(qa_path, qa_outbox)
            target = {**original, "evidence_root": root, "candidate": candidate, "rollback": rollback,
                      "qa_request": request, "qa_outbox": qa_file}
            receipt = {"receipt_type": "qa_verdict", "department": "qa", "verdict": "pass",
                       "chat_task_id": issuer.QA_THREAD_ID, "task_id": original["task_id"],
                       "scope": original["scope"], "action_class": "cms_content_candidate",
                       "action_id": original["action_id"], "evidence": [{"path": qa_path}], "receipt_id": "qa-v4"}
            with patch.object(issuer.wc, "_validate_receipt_chain", return_value=([receipt], [])):
                self.assertEqual(issuer.validate_qa(root, target, "publish")["receipt_id"], "qa-v4")
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "exact release PASS"):
                    issuer.validate_qa(root, target, "rollback")
                bad_request = pin("bad-request.json", {"mode": "dry-run", "contentType": "service",
                                                   "record": {**desired, "title_en": "Changed"},
                                                   "expectedUpdatedAt": baseline["updated_at"]})
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "two-field V4 scope"):
                    issuer.validate_qa(root, {**target, "qa_request": bad_request}, "publish")
                (root / qa_path).write_text(json.dumps({**qa_outbox, "action_id": "forged"}))
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_qa(root, target, "publish")

    def test_wrong_project_endpoint_rejected_before_network(self):
        with self.assertRaisesRegex(issuer.PermitEvidenceError, "Wrong Supabase project"):
            issuer.endpoint_request({}, "test-only", "https://example.com/rbsnyexjifounogswrjp.supabase.co")

    def test_protected_issuer_secret_prefers_injected_value(self):
        with patch.dict(os.environ, {"MANAGED_CMS_PERMIT_ISSUER_SECRET": "x" * 48}):
            with patch.object(issuer.subprocess, "run") as run:
                self.assertEqual(issuer.load_protected_issuer_secret(), "x" * 48)
                run.assert_not_called()

    def test_protected_issuer_secret_reads_exact_keychain_item_without_logging_value(self):
        with patch.dict(os.environ, {"MANAGED_CMS_PERMIT_ISSUER_SECRET": ""}), \
                patch.object(issuer.sys, "platform", "darwin"), \
                patch.object(issuer.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, stdout="y" * 48 + "\n", stderr="")) as run:
            self.assertEqual(issuer.load_protected_issuer_secret(), "y" * 48)
            self.assertEqual(run.call_args.args[0], [
                "/usr/bin/security", "find-generic-password", "-a", issuer.KEYCHAIN_ACCOUNT,
                "-s", issuer.KEYCHAIN_SERVICE, "-w",
            ])
            self.assertEqual(run.call_args.kwargs["capture_output"], True)

    def test_protected_issuer_secret_fails_closed_on_missing_or_short_value(self):
        with patch.dict(os.environ, {"MANAGED_CMS_PERMIT_ISSUER_SECRET": ""}), \
                patch.object(issuer.sys, "platform", "darwin"):
            with patch.object(issuer.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 44, stdout="", stderr="item not found")):
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "not configured in Keychain"):
                    issuer.load_protected_issuer_secret()
            with patch.object(issuer.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, stdout="short\n", stderr="")):
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "too short"):
                    issuer.load_protected_issuer_secret()

    def test_dry_run_artifact_requires_server_verified_matching_oidc_run(self):
        run_id = 12345
        run = {"id": run_id, "event": "workflow_dispatch", "head_branch": "main",
               "conclusion": "success", "name": "Approved website content publish",
               "path": ".github/workflows/content-publish-approved.yml", "head_sha": "a" * 40,
               "actor": {"id": 98765}, "run_attempt": 1}
        receipt = {"http_status": 200, "dry_run": True, "performed_write": False,
                   "external_writes": 0, "row_unchanged_after_dry_run": True}
        probe = {"ok": True, "dry_run": True, "performed_write": False,
                 "identity": {"runId": run_id, "runAttempt": 1, "repositoryId": 1248188229,
                              "workflowRef": f"{issuer.REPOSITORY}/.github/workflows/content-publish-approved.yml@refs/heads/main",
                              "actorId": 98765, "workflowSha": "a" * 40}}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)

            def download(command, **_):
                target = Path(command[-1]) / "builtin-whole-house-custom-v1"
                target.mkdir(parents=True, exist_ok=True)
                (target / "locked-dry-run-receipt.json").write_text(json.dumps(receipt))
                (target / "managed-payload-digest.json").write_text('{"payload_sha256":"' + "b" * 64 + '"}')
                (target / "managed-identity-probe.json").write_text(json.dumps(probe))
                (target / "backup.json").write_text('{"record":{}}')

            with patch.object(issuer, "gh_json", return_value=run), patch.object(issuer.subprocess, "run", side_effect=download):
                issuer.artifact_for_run(run_id, "builtin-whole-house-custom-v1", folder)
                probe["identity"]["actorId"] = 123
                with self.assertRaisesRegex(issuer.PermitEvidenceError, "OIDC identity probe"):
                    issuer.artifact_for_run(run_id, "builtin-whole-house-custom-v1", folder)

    def test_blog_media_targets_pin_rows_three_fields_and_unpublished_candidates(self):
        from copy import deepcopy
        self.assertEqual(len(issuer.BLOG_MEDIA_TARGETS), 2)
        for name in issuer.BLOG_MEDIA_TARGETS:
            target = issuer.TARGETS[name]
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            issuer.validate_candidate_binding(candidate, target)
            self.assertFalse(target["rollback_allowed"])
            self.assertEqual(set(target["changed_fields"]), {"cover_image_url", "alt_en", "alt_zh"})
            self.assertTrue(issuer.exact_file(issuer.ROOT, target["rollback"]).is_file())
            wrong_changes = [
                {"cms_row_id": "other-row"}, {"action_id": "body-only-action"},
                {"candidate_version": "other-version"}, {"scope": "flashcast.com.my:other"},
                {"external_write_executed": True}, {"cms_saved_id": "saved"},
                {"body_and_links_unchanged": False},
                {"allowed_fields": [*candidate["allowed_fields"], "content_zh"]},
            ]
            for change in wrong_changes:
                with self.subTest(name=name, change=change), self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding({**candidate, **change}, target)
            wrong = deepcopy(candidate)
            wrong["field_diff"]["cover_image_url"]["after"] = "/images/unverified.webp"
            with self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(wrong, target)
            self.assertEqual(issuer.rollback_parent_binding(name, "rollback", "permit-1", 123),
                             {"parentPermitId": "permit-1", "parentRunId": 123})

    def test_blog_media_structured_qa_rejects_wrong_scope_digest_and_blockers(self):
        for name in issuer.BLOG_MEDIA_TARGETS:
            target = issuer.TARGETS[name]
            row = {"department": "qa", "task_id": target["task_id"], "status": "completed",
                   "gate_status": "PASS_FOR_AUTO_RELEASE", "qa_verdict": "pass",
                   "action_id": target["action_id"], "candidate_version": target["candidate_version"],
                   "candidate_sha256": target["candidate"][1], "scope": target["scope"], "blockers": []}
            self.assertTrue(issuer.structured_qa_outbox_matches(row, target))
            for changes in ({"scope": "flashcast.com.my:other"},
                            {"candidate_sha256": "0" * 64},
                            {"blockers": [{"priority": "P1"}]}):
                self.assertFalse(issuer.structured_qa_outbox_matches({**row, **changes}, target))

    def test_blog_media_owner_review_preserves_r3_and_exact_policy_requirement(self):
        for name in issuer.BLOG_MEDIA_TARGETS:
            target = issuer.TARGETS[name]
            row = {"department": "qa", "task_id": target["task_id"], "status": "completed",
                   "gate_status": "PASS_FOR_OWNER_REVIEW", "risk_level": "R3",
                   "approval_required": True, "qa_verdict": "pass", "blockers": [],
                   "action_id": target["action_id"], "candidate_version": target["candidate_version"],
                   "candidate_sha256": target["candidate"][1], "scope": target["scope"]}
            self.assertTrue(issuer.structured_qa_outbox_matches(row, target))
            for changes in ({"risk_level": "R1"}, {"approval_required": False},
                            {"gate_status": "PASS_FOR_AUTO_RELEASE"},
                            {"scope": "flashcast.com.my:other"},
                            {"candidate_sha256": "0" * 64},
                            {"qa_verdict": "blocked"}, {"blockers": [{"priority": "P1"}]}):
                with self.subTest(name=name, changes=changes):
                    self.assertFalse(issuer.structured_qa_outbox_matches({**row, **changes}, target))
            self.assertFalse(issuer.structured_qa_outbox_matches(
                row, {**target, "candidate_shape": "record_key"}))
            operations = {"decided_at": "2026-09-26T08:20:00Z"}
            policy = {"status": "allow", "department": "content-organic-website",
                      "task_id": target["task_id"], "action_id": target["action_id"],
                      "action_class": "cms_write", "scope": target["scope"],
                      "payload_sha256": "a" * 64, "decision_id": "pol-exact-test",
                      "approval_status": "consumed", "checked_at": "2026-09-26T08:21:00Z"}
            now = issuer.datetime(2026, 9, 26, 8, 22, tzinfo=issuer.timezone.utc)
            self.assertEqual(issuer.validate_policy(policy, target, "publish", "a" * 64,
                                                    operations, now), policy)
            for changes in ({"approval_status": "active"}, {"scope": "flashcast.com.my:other"}):
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_policy({**policy, **changes}, target, "publish", "a" * 64,
                                           operations, now)

    def test_retired_colliding_service_targets_cannot_issue_new_permits(self):
        for name in ("org026-warehouse-media-r1-v5", "org026-office-renovation-media-r1-v5"):
            target = issuer.TARGETS[name]
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            issuer.validate_candidate_binding(candidate, target)
            with self.assertRaisesRegex(issuer.PermitEvidenceError, "retired"):
                issuer.validate_new_permit_target(target)
        for name in ("kl-location-intent-r1-v2", "org026-builtin-media-r1-v5",
                     "blog-kitchen-cabinet-media-r1-v1", "blog-office-checklist-media-r1-v1"):
            issuer.validate_new_permit_target(issuer.TARGETS[name])

    def test_org020_exact_source_bindings_and_distinct_execution_identities(self):
        targets = issuer.ORG020_TARGETS
        self.assertEqual(len(targets), 28)
        identities = {(t["task_id"], t["action_id"], t["candidate_version"]) for t in targets.values()}
        self.assertEqual(len(identities), 28)
        self.assertEqual(sum(t["table"] == "faqs" for t in targets.values()), 3)
        self.assertEqual(sum(t["table"] == "service_areas" for t in targets.values()), 18)
        for name, target in targets.items():
            with self.subTest(name=name):
                candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
                issuer.validate_candidate_binding(candidate, target)
                self.assertFalse(target["rollback_allowed"])
                self.assertTrue(issuer.exact_file(issuer.ROOT, target["source_frozen_candidate"]).is_file())

    def test_org020_wrong_tuple_fields_cas_payload_and_extra_writes_are_rejected(self):
        from copy import deepcopy
        for name, target in issuer.ORG020_TARGETS.items():
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            for change in ({"task_id": "other-project-task"}, {"action_id": "other-action"},
                           {"candidate_version": "other-version"}, {"record_id": "other-row"},
                           {"scope": "flashcast.com.my:other"}, {"production_write_executed": True},
                           {"changed_fields": [*target["changed_fields"], "status"]},
                           {"desired_fields_sha256": "0" * 64}):
                with self.subTest(name=name, change=change), self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding({**candidate, **change}, target)
            for key, value in (("mode", "publish"), ("expectedUpdatedAt", "stale"),
                               ("contentType", "homepage"), ("nextStatus", "draft")):
                bad = deepcopy(candidate)
                bad["request"][key] = value
                with self.subTest(name=name, request_key=key), self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding(bad, target)
            bad = deepcopy(candidate)
            bad["request"]["record"][target["changed_fields"][0]] = "unapproved content"
            with self.subTest(name=name, changed_payload=True), self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(bad, target)
            bad = deepcopy(candidate)
            bad["request"]["record"]["unexpected_field"] = "must not write"
            with self.subTest(name=name, extra_field=True), self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(bad, target)

    def test_org020_faq_adapter_preserves_frozen_source_and_existing_row(self):
        from copy import deepcopy
        for name, target in issuer.ORG020_TARGETS.items():
            if target["table"] != "faqs":
                continue
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            self.assertEqual(set(target["changed_fields"]), {"answer_en", "answer_zh"})
            for change in ({"source_frozen_candidate_sha256": "0" * 64},
                           {"source_frozen_candidate_path": "other.json"},
                           {"original_candidate_version": "other"},
                           {"original_action_id": "other"}, {"content_unchanged_from_frozen_v7": False}):
                with self.subTest(name=name, change=change), self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding({**candidate, **change}, target)
            for key in ("page_key", "question_en", "question_zh", "sort_order", "status", "id"):
                bad = deepcopy(candidate)
                bad["request"]["record"][key] = "changed unrelated FAQ field"
                with self.subTest(name=name, key=key), self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding(bad, target)
            bad = deepcopy(candidate)
            bad["request"]["managedCandidate"]["actionId"] = candidate["original_action_id"]
            with self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(bad, target)
            with self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(candidate, {**target, "slug": "home"})

    def test_org020_structured_qa_is_exact_and_unpinned_targets_cannot_issue(self):
        for name, target in issuer.ORG020_TARGETS.items():
            row = {"department": "qa", "task_id": target["task_id"], "status": "completed",
                   "gate_status": "PASS_FOR_AUTO_RELEASE", "risk_level": "R1", "qa_verdict": "pass",
                   "action_id": target["action_id"], "candidate_version": target["candidate_version"],
                   "candidate_sha256": target["candidate"][1], "scope": target["scope"], "blockers": []}
            self.assertTrue(issuer.structured_qa_outbox_matches(row, target))
            for change in ({"scope": "flashcast.com.my:other"}, {"action_id": "other"},
                           {"candidate_version": "other"}, {"candidate_sha256": "0" * 64},
                           {"qa_verdict": "blocked"}, {"blockers": [{"priority": "P1"}]}):
                with self.subTest(name=name, change=change):
                    self.assertFalse(issuer.structured_qa_outbox_matches({**row, **change}, target))
            with self.assertRaisesRegex(issuer.PermitEvidenceError, "no pinned actual fixed QA"):
                issuer.validate_new_permit_target({**target, "qa_outbox": None})

    def test_row_successors_have_distinct_active_action_keys_and_exact_candidates(self):
        names = ("org026-builtin-media-r1-v5", "org026-warehouse-media-r1-v6",
                 "org026-office-renovation-media-r1-v6")
        targets = [issuer.TARGETS[name] for name in names]
        keys = [(target["task_id"], target["action_id"], target["candidate_version"])
                for target in targets]
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(len({target["task_id"] for target in targets}), 1)
        for target in targets[1:]:
            issuer.validate_new_permit_target(target)
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            issuer.validate_candidate_binding(candidate, target)
            self.assertEqual(len(candidate["items"]), 1)
            for change in ({"action_id": "org026-service-media-cms-fields-r1-v4"},
                           {"candidate_version": "service-media-fields-r1-v5"},
                           {"modified_fields": ["image_url", "alt_en", "alt_zh", "content_en"]}):
                with self.assertRaises(issuer.PermitEvidenceError):
                    issuer.validate_candidate_binding({**candidate, **change}, target)
            wrong = {**candidate, "items": [{**candidate["items"][0],
                                             "scope": targets[0]["scope"]}]}
            with self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_candidate_binding(wrong, target)

    def test_row_successors_reject_legacy_shared_qa(self):
        old_qa = json.loads(issuer.exact_file(
            issuer.ROOT, issuer.TARGETS["org026-builtin-media-r1-v5"]["qa_outbox"]).read_text())
        for name in ("org026-warehouse-media-r1-v6", "org026-office-renovation-media-r1-v6"):
            self.assertFalse(issuer.structured_qa_outbox_matches(old_qa, issuer.TARGETS[name]))

    def test_new_kl_and_media_targets_bind_exact_candidate_rows_and_fields(self):
        names = (
            "kl-location-intent-r1-v2",
            "org026-builtin-media-r1-v5",
            "org026-warehouse-media-r1-v5",
            "org026-office-renovation-media-r1-v5",
        )
        for name in names:
            target = issuer.TARGETS[name]
            candidate = json.loads(issuer.exact_file(issuer.ROOT, target["candidate"]).read_text())
            issuer.validate_candidate_binding(candidate, target)
            with self.assertRaisesRegex(issuer.PermitEvidenceError, "candidate"):
                issuer.validate_candidate_binding({**candidate, "published": True}, target)
            if target["candidate_shape"] == "record_key":
                wrong = {**candidate, "record_key": {**candidate["record_key"], "id": "other-row"}}
            else:
                wrong = {**candidate, "items": [
                    {**item, "scope": "flashcast.com.my:other-row"} if item["cms_row_id"] == target["record_id"] else item
                    for item in candidate["items"]
                ]}
            with self.assertRaisesRegex(issuer.PermitEvidenceError, "candidate"):
                issuer.validate_candidate_binding(wrong, target)

    def test_new_qa_outboxes_reject_cross_row_and_candidate_drift(self):
        names = (
            "kl-location-intent-r1-v2",
            "org026-builtin-media-r1-v5",
            "org026-warehouse-media-r1-v5",
            "org026-office-renovation-media-r1-v5",
        )
        for name in names:
            target = issuer.TARGETS[name]
            outbox = json.loads(issuer.exact_file(issuer.ROOT, target["qa_outbox"]).read_text())
            self.assertTrue(issuer.structured_qa_outbox_matches(outbox, target), name)
            self.assertFalse(issuer.structured_qa_outbox_matches(
                {**outbox, "candidate_sha256": "0" * 64}, target))
            self.assertFalse(issuer.structured_qa_outbox_matches(
                {**outbox, "blockers": [{"priority": "P1"}]}, target))
            if target["candidate_shape"] == "items":
                self.assertFalse(issuer.structured_qa_outbox_matches(
                    {**outbox, "qa_subactions": [item for item in outbox["qa_subactions"]
                                                   if item["record_id"] != target["record_id"]]}, target))
        media = [issuer.TARGETS[name] for name in names[1:]]
        self.assertEqual(len({item["record_id"] for item in media}), 3)
        self.assertTrue(all(item["rollback_allowed"] is False for item in media))
        self.assertEqual(issuer.rollback_parent_binding("kl-location-intent-r1-v2", "rollback", "permit-1", 123),
                         {"parentPermitId": "permit-1", "parentRunId": 123})


if __name__ == "__main__":
    unittest.main()
