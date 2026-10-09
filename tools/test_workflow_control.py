from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flashcast_ops as ops
import workflow_control as workflow
import department_reply


class WorkflowControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        data = self.root / "data"
        data.mkdir(parents=True)
        (data / "human-control-state.json").write_text(json.dumps({
            "schema_version": 1, "paused": False, "revision": 1,
            "project_root": str(self.root.resolve()), "reason": "synthetic_test_fixture_only"}))
        departments = []
        for department in ("operations", "content-organic-website", "qa", "paid-growth-data"):
            approved_subskills: list[str] = []
            if department == "paid-growth-data":
                approved_subskills = ["google-ads-renovation-ppc"]
            elif department == "content-organic-website":
                approved_subskills = ["renovation-seo-geo"]
            departments.append(
                {
                    "id": department,
                    "name": department,
                    "role_config": f".codex/agents/{department}.toml",
                    "department_readme": f"departments/{department}/README.md",
                    "approved_subskills": approved_subskills,
                    "chat_binding": {
                        "title": department,
                        "status": "bound_and_visible",
                        "task_id": f"fixed-{department}",
                        "project_id": "flashcast-test-project",
                        "cwd": str(self.root),
                        "reply_health": "healthy_visible_reply_verified",
                        "dispatch_eligible": True,
                        "sidebar_section_id": "flashcast-departments",
                        "handoff_path": f"logs/handoffs/{department}.md",
                        "last_health_check_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    },
                    "input_paths": ["data/"],
                    "output_paths": ["reports/"],
                }
            )
        (data / "department-registry.json").write_text(
            json.dumps({"departments": departments}), encoding="utf-8"
        )
        (data / "department-routing-rules.json").write_text(
            json.dumps(
                {
                    "routes": [
                        {
                            "id": "content",
                            "match_any": ["网站"],
                            "required_departments": ["content-organic-website"],
                            "parallel_departments": ["content-organic-website"],
                            "follow_up_departments": ["qa"],
                            "department_dependencies": {"qa": ["content-organic-website"]},
                            "approval_required": True,
                        }
                    ],
                    "fallback": {"required_departments": ["content-organic-website"], "follow_up_departments": ["qa"]},
                }
            ),
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(
            json.dumps({"completion_rule": "chat + outbox + evidence + learning"}), encoding="utf-8"
        )
        project_policy = Path(__file__).resolve().parents[1] / "data/action-policy.json"
        policy = json.loads(project_policy.read_text(encoding="utf-8"))
        policy["routing_policy"]["source_project_id"] = "flashcast-test-project"
        policy["routing_policy"]["source_project_root"] = str(self.root)
        policy["standing_authorizations"] = []
        (data / "action-policy.json").write_text(json.dumps(policy), encoding="utf-8")
        project_delegation_policy = Path(__file__).resolve().parents[1] / "data/delegation-policy.json"
        (data / "delegation-policy.json").write_text(
            project_delegation_policy.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.routing_decisions: dict[str, str] = {}
        self.task_id = "workflow-test-001"
        self.dispatch()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def dispatch(self, request: str = "运营网站") -> dict[str, object]:
        payload, _ = ops.dispatch_plan(
            self.root, argparse.Namespace(request=request, task_id=self.task_id)
        )
        return payload

    def routing_decision(self, department: str, payload_sha256: str = "a" * 64) -> dict[str, object]:
        binding = workflow.department_registry(self.root)[department]["chat_binding"]
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id=f"dispatch-{department}",
            action_class="thread_message",
            scope=f"department:{department}",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department=department,
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256=payload_sha256,
        )
        return decision

    def delegation_decision(
        self,
        scope: str,
        *,
        department: str = "content-organic-website",
        timeout_seconds: int = 900,
        **flags: object,
    ) -> dict[str, object]:
        binding = workflow.department_registry(self.root)[department]["chat_binding"]
        decision, _ = workflow.delegation_check(
            self.root,
            task_id=self.task_id,
            department=department,
            benefit="parallel_latency",
            work_class="read_only",
            scope=scope,
            parent_thread_id=str(binding["task_id"]),
            parent_project_id=str(binding["project_id"]),
            parent_cwd=str(binding["cwd"]),
            requested_parallelism=1,
            timeout_seconds=timeout_seconds,
            **flags,
        )
        return decision

    def start_delegation(self, delegation_id: str, scope: str, decision: dict[str, object]) -> dict[str, object]:
        payload, _ = workflow.record_delegation(
            self.root,
            argparse.Namespace(
                task_id=self.task_id,
                delegation_id=delegation_id,
                department="content-organic-website",
                status="started",
                idempotency_key=f"{delegation_id}-start",
                decision_id=str(decision["decision_id"]),
                scope=scope,
                attempt=1,
                stop_reason="",
                evidence="",
            ),
        )
        return payload

    def receipt(self, receipt_type: str, department: str, key: str, **kwargs: object) -> dict[str, object]:
        defaults = {
            "task_id": self.task_id,
            "receipt_type": receipt_type,
            "department": department,
            "chat_task_id": f"fixed-{department}" if receipt_type in {"dispatch_sent", "chat_ack", "qa_verdict"} else "",
            "ack_nonempty": receipt_type == "chat_ack",
            "evidence": "",
            "idempotency_key": key,
            "verdict": "",
            "action_id": "",
            "action_class": "",
            "scope": "",
            "approval_id": "",
            "policy_decision_id": "",
            "supersedes_receipt_id": "",
            "replacement_reason": "",
        }
        defaults.update(kwargs)
        if receipt_type == "dispatch_sent" and not defaults["policy_decision_id"]:
            decision_id = self.routing_decisions.get(department)
            if not decision_id:
                decision = self.routing_decision(department)
                decision_id = str(decision["decision_id"])
                self.routing_decisions[department] = decision_id
            defaults["policy_decision_id"] = decision_id
        payload, _ = ops.receipt_record(self.root, argparse.Namespace(**defaults))
        return payload

    def write_outbox(self) -> Path:
        path = self.root / "logs/department-outbox/workflow-test-001-content.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0",
                    "task_id": f"{self.task_id}-content",
                    "department": "content-organic-website",
                    "status": "completed",
                    "conclusion": "internal draft complete",
                    "evidence": ["reports/content.md"],
                    "risks": ["not published"],
                    "next_actions": ["qa"],
                    "handoff": {"to": "qa"},
                    "approval_required": True,
                    "learning": {"status": "no_new_learning"},
                }
            ),
            encoding="utf-8",
        )
        return path

    def advance_to_qa(self) -> Path:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        outbox = self.write_outbox()
        self.receipt(
            "outbox_received",
            "content-organic-website",
            "o1",
            evidence=workflow.rel_path(self.root, outbox),
        )
        return outbox

    def prepare_qa(self) -> Path:
        self.receipt("dispatch_sent", "qa", "qa-delivery-dispatch")
        self.receipt("chat_ack", "qa", "qa-delivery-ack")
        path = self.root / "logs/department-outbox/workflow-test-001-qa.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "schema_version": "2.0",
                "task_id": self.task_id,
                "department": "qa",
                "status": "completed",
                "conclusion": "independent QA verdict recorded",
                "evidence": ["reports/qa.md"],
                "risks": [],
                "next_actions": ["review verdict"],
                "handoff": {"to": "operations"},
                "approval_required": True,
                "learning": {"status": "no_new_learning"},
            }), encoding="utf-8"
        )
        self.receipt("outbox_received", "qa", "qa-delivery-outbox", evidence=workflow.rel_path(self.root, path))
        return path

    def test_failed_dispatch_is_append_only_and_requires_real_retry(self) -> None:
        self.advance_to_qa()
        sent = self.receipt("dispatch_sent", "qa", "qa-send")
        (self.root / "reports").mkdir(exist_ok=True)
        (self.root / "reports/send-error.md").write_text("thread not found", encoding="utf-8")
        args = dict(chat_task_id="fixed-qa", evidence="reports/send-error.md",
                    supersedes_receipt_id=sent["receipt_id"], replacement_reason="thread_not_loaded")
        failed = self.receipt("dispatch_failed", "qa", "qa-failure", **args)
        self.assertEqual(failed["workflow_state"], "blocked")
        self.assertEqual(self.receipt("dispatch_failed", "qa", "qa-failure", **args)["result"], "duplicate_ignored")
        with self.assertRaises(ops.OpsError):
            self.receipt("chat_ack", "qa", "false-ack")
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "blocked")
        self.receipt("dispatch_sent", "qa", "qa-real-retry")
        restored, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(restored["current_state"], "evidence_received")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        rows, invalid = workflow._validate_receipt_chain(self.root, self.task_id)
        self.assertFalse(invalid)
        self.assertIn(sent["receipt_id"], [row["receipt_id"] for row in rows])

    def test_dispatch_failure_cannot_retract_acknowledged_or_other_dispatch(self) -> None:
        sent = self.receipt("dispatch_sent", "content-organic-website", "d-first")
        (self.root / "error.md").write_text("error", encoding="utf-8")
        args = dict(chat_task_id="fixed-content-organic-website", evidence="error.md",
                    supersedes_receipt_id=sent["receipt_id"], replacement_reason="thread_not_loaded")
        with self.assertRaises(ops.OpsError):
            self.receipt("dispatch_failed", "qa", "wrong-department", **args)
        self.receipt("chat_ack", "content-organic-website", "ack-first")
        with self.assertRaises(ops.OpsError):
            self.receipt("dispatch_failed", "content-organic-website", "too-late", **args)

    def qa_pass(self) -> Path:
        evidence = self.root / "reports/qa.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("QA PASS; external execution still requires owner approval.\n", encoding="utf-8")
        self.prepare_qa()
        self.receipt("qa_verdict", "qa", "q1", verdict="pass", evidence="reports/qa.md")
        return evidence

    def test_run_ids_are_unique_inside_same_second(self) -> None:
        first = ops.append_run(self.root, "backup", "complete", [], [])
        second = ops.append_run(self.root, "backup", "complete", [], [])
        self.assertNotEqual(first, second)

    def test_dispatch_is_idempotent_and_conflicting_request_is_blocked(self) -> None:
        second = self.dispatch()
        self.assertFalse(second["workflow"]["initialized"])
        events = [row for row in workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS) if row["task_id"] == self.task_id]
        self.assertEqual(len(events), 2)
        with self.assertRaises(ops.OpsError):
            self.dispatch("运营网站，但改成另一个任务")

    def test_same_request_can_refresh_department_route_before_dispatch(self) -> None:
        current = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        original_departments = current["departments"]
        expanded = [
            {
                "department": "paid-growth-data",
                "chat_task_id": "fixed-paid-growth-data",
                "execution_wave": 1,
                "depends_on": [],
            },
            *original_departments,
        ]
        expanded_snapshot, created = workflow.initialize_workflow(
            self.root,
            task_id=self.task_id,
            request="运营网站",
            plan_status="ready_to_send",
            departments=expanded,
            owner_approval_required=True,
        )
        self.assertFalse(created)
        self.assertEqual(expanded_snapshot["departments"], expanded)

        refreshed, created = workflow.initialize_workflow(
            self.root,
            task_id=self.task_id,
            request="运营网站",
            plan_status="ready_to_send",
            departments=original_departments,
            owner_approval_required=False,
        )
        self.assertFalse(created)
        self.assertEqual(refreshed["departments"], original_departments)
        self.assertFalse(refreshed["owner_approval_required"])
        self.assertEqual(workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id)), [])
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["departments"], original_departments)
        self.assertFalse(rebuilt["owner_approval_required"])

    def test_same_request_can_shrink_route_after_retained_dispatch_before_ack(self) -> None:
        current = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        original_departments = current["departments"]
        expanded = [
            {
                "department": "paid-growth-data",
                "chat_task_id": "fixed-paid-growth-data",
                "execution_wave": 1,
                "depends_on": [],
            },
            *original_departments,
        ]
        workflow.initialize_workflow(
            self.root,
            task_id=self.task_id,
            request="运营网站",
            plan_status="ready_to_send",
            departments=expanded,
            owner_approval_required=True,
        )
        decision = self.routing_decision("content-organic-website")
        self.receipt(
            "dispatch_sent",
            "content-organic-website",
            "retained-content-dispatch",
            policy_decision_id=str(decision["decision_id"]),
        )

        refreshed, created = workflow.initialize_workflow(
            self.root,
            task_id=self.task_id,
            request="运营网站",
            plan_status="ready_to_send",
            departments=original_departments,
            owner_approval_required=False,
        )
        self.assertFalse(created)
        self.assertEqual(refreshed["departments"], original_departments)
        self.assertFalse(refreshed["owner_approval_required"])
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        self.assertEqual([row["receipt_type"] for row in receipts], ["dispatch_sent"])

        self.receipt("chat_ack", "content-organic-website", "content-ack")
        with self.assertRaisesRegex(workflow.WorkflowError, "已有派工回执或后续状态"):
            workflow.initialize_workflow(
                self.root,
                task_id=self.task_id,
                request="运营网站",
                plan_status="ready_to_send",
                departments=expanded,
                owner_approval_required=True,
            )

    def make_false_positive_multi_route(self) -> None:
        self.task_id = "route-correction-test"
        rules_path = self.root / "data/department-routing-rules.json"
        rules = workflow.read_json(rules_path)
        rules["routes"][0]["approval_required"] = False
        rules["routes"].insert(0, {
            "id": "paid-keyword",
            "match_any": ["关键词"],
            "required_departments": ["paid-growth-data"],
            "parallel_departments": ["paid-growth-data"],
            "follow_up_departments": ["qa"],
            "department_dependencies": {"qa": ["paid-growth-data"]},
            "approval_required": True,
        })
        workflow.atomic_write_json(rules_path, rules)
        plan = self.dispatch("网站关键词内容")
        self.assertEqual(plan["route"]["id"], "multi:paid-keyword+content")

    def test_false_positive_route_correction_keeps_real_ack_and_rebuilds(self) -> None:
        self.make_false_positive_multi_route()
        self.advance_to_qa()
        self.receipt("dispatch_sent", "qa", "qa-dispatch")
        self.receipt("chat_ack", "qa", "qa-ack")
        before = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        corrected, _ = workflow.correct_false_positive_route(self.root, self.task_id, "content")
        self.assertEqual(corrected["status"], "workflow_route_corrected")
        self.assertEqual(corrected["current_state"], "evidence_received")
        self.assertFalse(corrected["owner_approval_required"])
        self.assertEqual(before, workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id)))
        again, _ = workflow.correct_false_positive_route(self.root, self.task_id, "content")
        self.assertEqual(again["status"], "duplicate_ignored")
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual({item["department"] for item in rebuilt["departments"]},
                         {"content-organic-website", "qa"})
        self.assertFalse(rebuilt["owner_approval_required"])
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        self.assertEqual(
            workflow.read_json(self.root / f"logs/dispatch/{self.task_id}.json")["route"]["id"],
            "multi:paid-keyword+content",
        )

    def test_false_positive_route_correction_rejects_paid_receipt(self) -> None:
        self.make_false_positive_multi_route()
        self.receipt("dispatch_sent", "paid-growth-data", "paid-sent")
        with self.assertRaisesRegex(workflow.WorkflowError, "已有真实回执"):
            workflow.correct_false_positive_route(self.root, self.task_id, "content")

    def blocked_plan(self) -> None:
        self.task_id = "blocked-recovery-test"
        p = self.root / "data/department-registry.json"
        registry = workflow.read_json(p)
        registry["health_policy"] = {"verification_ttl_hours": 26}
        registry["departments"][1]["chat_binding"]["last_health_check_at"] = "2000-01-01T00:00:00+00:00"
        workflow.atomic_write_json(p, registry)
        self.dispatch()
        for name in ("content-organic-website", "qa"):
            handoff = self.root / f"logs/handoffs/{name}.md"
            handoff.parent.mkdir(exist_ok=True, parents=True)
            handoff.write_text("test handoff", encoding="utf-8")

    def restore_test_health(self) -> None:
        p = self.root / "data/department-registry.json"
        registry = workflow.read_json(p)
        registry["departments"][1]["chat_binding"]["last_health_check_at"] = workflow.utc_timestamp()
        workflow.atomic_write_json(p, registry)

    def test_blocked_plan_rechecks_health_without_receipts_or_duplicate_events(self) -> None:
        self.blocked_plan()
        result, _ = workflow.repair_dispatch_plan(self.root, self.task_id)
        self.assertEqual(result["current_state"], "blocked")
        self.assertIn("content-organic-website:target_thread_unhealthy_or_dispatch_ineligible", result["blockers"])
        self.restore_test_health()
        result, _ = workflow.repair_dispatch_plan(self.root, self.task_id)
        self.assertEqual(result["current_state"], "dispatch_ready")
        events = (self.root / workflow.WORKFLOW_EVENTS).read_bytes()
        workflow.repair_dispatch_plan(self.root, self.task_id)
        self.assertEqual(events, (self.root / workflow.WORKFLOW_EVENTS).read_bytes())
        self.assertEqual(workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id)), [])
        self.assertTrue(result["owner_approval_required"])
        self.assertFalse(result["paid_promotion_enabled"])

    def test_dispatch_rerun_recovers_original_blocked_task(self) -> None:
        self.blocked_plan()
        self.restore_test_health()
        result = self.dispatch()
        self.assertFalse(result["workflow"]["initialized"])
        self.assertEqual(result["workflow"]["current_state"], "dispatch_ready")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_plan_recovery_event_rebuilds_missing_snapshot(self) -> None:
        self.blocked_plan()
        self.restore_test_health()
        workflow.repair_dispatch_plan(self.root, self.task_id)
        workflow.snapshot_path(self.root, self.task_id).unlink()
        result, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(result["plan_status"], "ready_to_send")
        self.assertEqual(result["current_state"], "dispatch_ready")

    def test_plan_recovery_survives_interrupt_between_event_and_snapshot(self) -> None:
        self.blocked_plan()
        self.restore_test_health()
        with mock.patch.object(workflow, "atomic_write_json", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                workflow.repair_dispatch_plan(self.root, self.task_id)
        result, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(result["current_state"], "dispatch_ready")
        count = result["event_count"]
        result, _ = workflow.repair_dispatch_plan(self.root, self.task_id)
        self.assertEqual(result["event_count"], count)

    def test_plan_recovery_rejects_receipts_and_terminal_states(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        with self.assertRaises(workflow.WorkflowError):
            workflow.repair_dispatch_plan(self.root, self.task_id)
        self.blocked_plan()
        p = workflow.snapshot_path(self.root, self.task_id)
        snapshot = workflow.read_json(p)
        snapshot["current_state"] = "cancelled"
        workflow.atomic_write_json(p, snapshot)
        with self.assertRaises(workflow.WorkflowError):
            workflow.repair_dispatch_plan(self.root, self.task_id)

    def test_plan_recovery_keeps_identity_and_requires_handoff(self) -> None:
        self.blocked_plan()
        self.restore_test_health()
        p = self.root / "data/department-registry.json"
        original = workflow.read_json(p)
        for key, value in (("task_id", "other-task"), ("project_id", "other-project"),
                           ("cwd", "/tmp/other-project"), ("handoff_path", "missing.md")):
            with self.subTest(key=key):
                changed = json.loads(json.dumps(original))
                changed["departments"][1]["chat_binding"][key] = value
                workflow.atomic_write_json(p, changed)
                result, _ = workflow.repair_dispatch_plan(self.root, self.task_id)
                self.assertEqual(result["current_state"], "blocked")
                self.assertEqual(result["departments"][0]["chat_task_id"], "fixed-content-organic-website")
        workflow.atomic_write_json(p, original)

    def test_plan_recovery_rejects_tampered_event_chain(self) -> None:
        self.blocked_plan()
        p = self.root / workflow.WORKFLOW_EVENTS
        rows = workflow.read_jsonl(p)
        rows[-1]["event_hash"] = "0" * 64
        p.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "链无效"):
            workflow.repair_dispatch_plan(self.root, self.task_id)

    def health_args(self, observed_at: str = "") -> argparse.Namespace:
        return argparse.Namespace(department="content-organic-website", task_id="fixed-content-organic-website",
            project_id="flashcast-test-project", cwd=str(self.root), title="content-organic-website",
            sidebar_section_id="flashcast-departments", reply_ref="msg-health-test", reply_sha256="e" * 64,
            reply_nonempty=True, reply_observed_at=observed_at, live_status="idle", last_run_status="success",
            failure_class="", next_retry_at="")

    def test_same_health_observation_is_idempotent(self) -> None:
        args = self.health_args(workflow.utc_timestamp())
        ops.department_health_record(self.root, args)
        p = self.root / "logs/department-health.jsonl"
        before = p.read_bytes()
        result, _ = ops.department_health_record(self.root, args)
        self.assertEqual(result["status"], "department_health_unchanged")
        self.assertEqual(p.read_bytes(), before)

    def test_health_rejects_expired_reply_and_keeps_actual_reply_time(self) -> None:
        with self.assertRaisesRegex(ops.OpsError, "过期"):
            ops.department_health_record(self.root, self.health_args("2000-01-01T00:00:00Z"))
        observed = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        ops.department_health_record(self.root, self.health_args(observed))
        binding = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        self.assertEqual(binding["last_health_check_at"], observed)

    def test_recovery_cli_alias_is_executable(self) -> None:
        args = ops.build_parser().parse_args(["repair_dispatch_plan", "--task-id", self.task_id])
        self.assertIs(args.handler, ops.workflow_repair_plan_command)

    def test_illegal_jump_and_fixed_chat_mismatch_are_blocked(self) -> None:
        outbox = self.write_outbox()
        with self.assertRaisesRegex(ops.OpsError, "非法越级"):
            self.receipt("outbox_received", "content-organic-website", "early", evidence=workflow.rel_path(self.root, outbox))
        with self.assertRaisesRegex(ops.OpsError, "chat_task_id"):
            self.receipt("dispatch_sent", "content-organic-website", "bad-chat", chat_task_id="wrong-task")

    def test_refresh_bindings_updates_replacement_and_rebuilds_from_events(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["departments"][1]["chat_binding"]["task_id"] = "replacement-content"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        refreshed, _ = workflow.refresh_workflow_bindings(self.root, self.task_id)

        self.assertEqual(refreshed["status"], "workflow_bindings_refreshed")
        self.assertEqual(refreshed["changes"][0]["new_chat_task_id"], "replacement-content")
        snapshot = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        planned = {item["department"]: item for item in snapshot["departments"]}
        self.assertEqual(planned["content-organic-website"]["chat_task_id"], "replacement-content")

        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        rebuilt_plan = {item["department"]: item for item in rebuilt["departments"]}
        self.assertEqual(rebuilt_plan["content-organic-website"]["chat_task_id"], "replacement-content")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_refresh_bindings_is_blocked_after_first_receipt(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        with self.assertRaisesRegex(workflow.WorkflowError, "dispatch_ready"):
            workflow.refresh_workflow_bindings(self.root, self.task_id)

    def test_rebind_qa_after_dispatch_preserves_receipts_and_rebuilds(self) -> None:
        self.advance_to_qa()
        self.receipt("dispatch_sent", "qa", "old-qa-dispatch")
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"] if row["id"] == "qa")
        binding["task_id"] = "replacement-qa"
        binding["replacement_of_task_id"] = "fixed-qa"
        binding["last_reply_sha256"] = "e" * 64
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        health = {
            "department": "qa", "task_id": "replacement-qa",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        health["event_hash"] = workflow.sha256_value(health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", health)

        with self.assertRaisesRegex(workflow.WorkflowError, "健康事件不存在"):
            workflow.rebind_qa_after_replacement(self.root, self.task_id, "fixed-qa", "f" * 64)
        result, _ = workflow.rebind_qa_after_replacement(
            self.root, self.task_id, "fixed-qa", health["event_hash"]
        )
        self.assertEqual(result["new_chat_task_id"], "replacement-qa")
        self.assertEqual(result["current_state"], "evidence_received")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        self.assertEqual(len(workflow._validate_receipt_chain(self.root, self.task_id)[0]), 4)
        self.routing_decisions.pop("qa", None)
        self.receipt("dispatch_sent", "qa", "replacement-qa-dispatch", chat_task_id="replacement-qa")
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        qa = next(row for row in rebuilt["departments"] if row["department"] == "qa")
        self.assertEqual(qa["chat_task_id"], "replacement-qa")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_rebind_qa_before_qa_dispatch_preserves_content_receipts(self) -> None:
        self.advance_to_qa()
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"] if row["id"] == "qa")
        binding.update(task_id="replacement-qa", replacement_of_task_id="fixed-qa",
                       last_reply_sha256="e" * 64)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        health = {
            "department": "qa", "task_id": "replacement-qa",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        health["event_hash"] = workflow.sha256_value(health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", health)
        result, _ = workflow.rebind_qa_after_replacement(
            self.root, self.task_id, "fixed-qa", health["event_hash"]
        )
        self.assertEqual(result["current_state"], "evidence_received")
        self.assertEqual(len(workflow._validate_receipt_chain(self.root, self.task_id)[0]), 3)
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        qa = next(row for row in rebuilt["departments"] if row["department"] == "qa")
        self.assertEqual(qa["chat_task_id"], "replacement-qa")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_rebind_historical_qa_before_dispatch_requires_old_identity_proof(self) -> None:
        old_plan = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        workflow.append_workflow_event(self.root, self.task_id, "dispatch_ready", {
            "plan_refresh": True, "request_hash": old_plan["request_hash"],
            "plan_status": "ready_to_send", "plan_blockers": [],
            "departments": old_plan["departments"],
        })
        self.advance_to_qa()
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"] if row["id"] == "qa")
        binding.update(task_id="replacement-qa", replacement_of_task_id="intermediate-qa",
                       last_reply_sha256="e" * 64)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        current_health = {
            "department": "qa", "task_id": "replacement-qa",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        current_health["event_hash"] = workflow.sha256_value(current_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", current_health)
        with self.assertRaisesRegex(workflow.WorkflowError, "历史固定部门窗口无可验证健康记录"):
            workflow.rebind_qa_after_replacement(
                self.root, self.task_id, "fixed-qa", current_health["event_hash"]
            )

        old_health = {
            "department": "qa", "task_id": "fixed-qa",
            "project_id": "flashcast-test-project", "sidebar_section_id": "old-sidebar",
            "title_sha256": hashlib.sha256(b"qa").hexdigest(),
            "cwd_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "d" * 64,
        }
        old_health["event_hash"] = workflow.sha256_value(old_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", old_health)
        result, _ = workflow.rebind_qa_after_replacement(
            self.root, self.task_id, "fixed-qa", current_health["event_hash"]
        )
        self.assertEqual(result["new_chat_task_id"], "replacement-qa")
        self.assertEqual(result["current_state"], "evidence_received")
        events = [row for row in workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)
                  if row.get("task_id") == self.task_id]
        self.assertTrue(events[-1]["details"]["historical_qa_pre_dispatch"])
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        qa = next(row for row in rebuilt["departments"] if row["department"] == "qa")
        self.assertEqual(qa["chat_task_id"], "replacement-qa")

    def test_rebind_content_during_qa_rework_preserves_history(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        evidence = self.root / "reports/qa-blocked.md"
        evidence.write_text("QA BLOCKED\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "qa-blocked-content-rework", verdict="blocked",
                     evidence="reports/qa-blocked.md")
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"]
                       if row["id"] == "content-organic-website")
        binding.update(task_id="replacement-content", replacement_of_task_id="fixed-content-organic-website",
                       last_reply_sha256="e" * 64)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        health = {
            "department": "content-organic-website", "task_id": "replacement-content",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        health["event_hash"] = workflow.sha256_value(health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", health)

        with self.assertRaisesRegex(workflow.WorkflowError, "旧部门派工状态"):
            workflow.rebind_department_after_replacement(
                self.root, self.task_id, "content-organic-website", "wrong-old-id", health["event_hash"]
            )
        result, _ = workflow.rebind_department_after_replacement(
            self.root, self.task_id, "content-organic-website",
            "fixed-content-organic-website", health["event_hash"]
        )
        self.assertEqual(result["new_chat_task_id"], "replacement-content")
        self.assertEqual(result["current_state"], "qa_blocked")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        self.assertEqual(len(workflow._validate_receipt_chain(self.root, self.task_id)[0]), 7)
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        content = next(row for row in rebuilt["departments"] if row["department"] == "content-organic-website")
        self.assertEqual(content["chat_task_id"], "replacement-content")

    def test_rebind_historical_content_during_qa_rework_requires_old_proof(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        evidence = self.root / "reports/qa-historical-content-blocked.md"
        evidence.write_text("QA BLOCKED\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "historical-content-blocked", verdict="blocked",
                     evidence="reports/qa-historical-content-blocked.md")
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"]
                       if row["id"] == "content-organic-website")
        binding.update(task_id="current-content", replacement_of_task_id="intermediate-content",
                       last_reply_sha256="e" * 64)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        current_health = {
            "department": "content-organic-website", "task_id": "current-content",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        current_health["event_hash"] = workflow.sha256_value(current_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", current_health)
        with self.assertRaisesRegex(workflow.WorkflowError, "历史固定部门窗口无可验证健康记录"):
            workflow.rebind_department_after_replacement(
                self.root, self.task_id, "content-organic-website",
                "fixed-content-organic-website", current_health["event_hash"],
            )
        old_health = {
            "department": "content-organic-website", "task_id": "fixed-content-organic-website",
            "project_id": "flashcast-test-project", "sidebar_section_id": "old-sidebar",
            "title_sha256": hashlib.sha256(b"content-organic-website").hexdigest(),
            "cwd_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "d" * 64,
        }
        old_health["event_hash"] = workflow.sha256_value(old_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", old_health)
        rebound, _ = workflow.rebind_department_after_replacement(
            self.root, self.task_id, "content-organic-website",
            "fixed-content-organic-website", current_health["event_hash"],
        )
        self.assertEqual(rebound["new_chat_task_id"], "current-content")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(next(row["chat_task_id"] for row in rebuilt["departments"]
                              if row["department"] == "content-organic-website"), "current-content")

    def test_rebind_historical_unacknowledged_content_dispatch_requires_new_dispatch(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "old-content-dispatch")
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"]
                       if row["id"] == "content-organic-website")
        binding.update(task_id="current-content", replacement_of_task_id="intermediate-content",
                       last_reply_sha256="e" * 64)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        current_health = {
            "department": "content-organic-website", "task_id": "current-content",
            "project_id": "flashcast-test-project", "sidebar_section_id": "flashcast-departments",
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "e" * 64,
        }
        current_health["event_hash"] = workflow.sha256_value(current_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", current_health)

        with self.assertRaisesRegex(workflow.WorkflowError, "历史固定部门窗口无可验证健康记录"):
            workflow.rebind_department_after_replacement(
                self.root, self.task_id, "content-organic-website",
                "fixed-content-organic-website", current_health["event_hash"],
            )
        old_health = {
            "department": "content-organic-website", "task_id": "fixed-content-organic-website",
            "project_id": "flashcast-test-project", "sidebar_section_id": "old-sidebar",
            "title_sha256": hashlib.sha256(b"content-organic-website").hexdigest(),
            "cwd_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
            "last_run_status": "success", "reply_nonempty": True, "reply_sha256": "d" * 64,
        }
        old_health["event_hash"] = workflow.sha256_value(old_health)
        workflow.append_jsonl_locked(self.root / "logs/department-health.jsonl", old_health)
        rebound, _ = workflow.rebind_department_after_replacement(
            self.root, self.task_id, "content-organic-website",
            "fixed-content-organic-website", current_health["event_hash"],
        )
        self.assertEqual(rebound["current_state"], "dispatched")
        self.assertEqual(rebound["new_chat_task_id"], "current-content")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        self.assertEqual(len(workflow._validate_receipt_chain(self.root, self.task_id)[0]), 1)
        with self.assertRaisesRegex(ops.OpsError, "重新派工"):
            self.receipt("chat_ack", "content-organic-website", "ack-without-new-dispatch",
                         chat_task_id="current-content")

        self.routing_decisions.pop("content-organic-website", None)
        self.receipt("dispatch_sent", "content-organic-website", "new-content-dispatch",
                     chat_task_id="current-content")
        self.receipt("chat_ack", "content-organic-website", "new-content-ack",
                     chat_task_id="current-content")
        outbox = self.write_outbox()
        self.receipt("outbox_received", "content-organic-website", "new-content-outbox",
                     evidence=workflow.rel_path(self.root, outbox))
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "evidence_received")
        self.assertEqual(next(row["chat_task_id"] for row in rebuilt["departments"]
                              if row["department"] == "content-organic-website"), "current-content")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_rebind_unacknowledged_dispatch_rejects_unhealthy_replacement(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "old-content-dispatch")
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = next(row["chat_binding"] for row in registry["departments"]
                       if row["id"] == "content-organic-website")
        binding.update(task_id="replacement-content", replacement_of_task_id="fixed-content-organic-website",
                       reply_health="failed_empty_visible_reply", dispatch_eligible=False)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "未通过当前健康门禁"):
            workflow.rebind_department_after_replacement(
                self.root, self.task_id, "content-organic-website",
                "fixed-content-organic-website", "f" * 64,
            )

    def test_rebind_department_rejects_other_department(self) -> None:
        with self.assertRaisesRegex(workflow.WorkflowError, "仅支持"):
            workflow.rebind_department_after_replacement(
                self.root, self.task_id, "paid-growth-data", "fixed-paid-growth-data", "e" * 64
            )

    def test_exact_registered_thread_routing_is_allowed(self) -> None:
        decision = self.routing_decision("content-organic-website")
        self.assertEqual(decision["status"], "allow")
        self.assertEqual(decision["routing_status"], "routing_allowed")
        self.assertFalse(decision["message_body_stored"])

    def test_sidebar_mismatch_and_controller_self_target_are_blocked(self) -> None:
        binding = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        wrong_sidebar, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="dispatch-content-wrong-sidebar",
            action_class="thread_message",
            scope="department:content-organic-website",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="content-organic-website",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id="another-section",
            payload_sha256="b" * 64,
        )
        self.assertEqual(wrong_sidebar["status"], "deny")
        self.assertIn("target_sidebar_section_id_mismatch", wrong_sidebar["reason"])

        controller = workflow.department_registry(self.root)["operations"]["chat_binding"]
        self_target, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="dispatch-controller-to-itself",
            action_class="thread_message",
            scope="department:operations",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="operations",
            target_thread_id=str(controller["task_id"]),
            target_thread_title=str(controller["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(controller["sidebar_section_id"]),
            payload_sha256="c" * 64,
        )
        self.assertEqual(self_target["status"], "deny")
        self.assertIn("operations_controller_cannot_be_thread_message_target", self_target["reason"])

    def test_department_result_notification_is_durable_inbox_only(self) -> None:
        controller = workflow.department_registry(self.root)["operations"]["chat_binding"]
        self.receipt("dispatch_sent", "content-organic-website", "result-notify-dispatch")
        self.receipt("chat_ack", "content-organic-website", "result-notify-ack")
        result, _ = workflow.policy_check(
            self.root, task_id=self.task_id, department="content-organic-website",
            action_id="notify-operations-result-v1", action_class="thread_message",
            scope=f"department_result:{self.task_id}:content-organic-website",
            source_project_id="flashcast-test-project", target_project_id="flashcast-test-project",
            target_department="operations", target_thread_id=str(controller["task_id"]),
            target_thread_title=str(controller["title"]), target_cwd=str(self.root),
            target_sidebar_section_id=str(controller["sidebar_section_id"]),
            payload_sha256="a" * 64,
        )
        self.assertEqual(result["status"], "deny")
        self.assertIn("department_result_uses_durable_inbox", result["reason"])

    def _result_handoff_fixture(self) -> tuple[dict[str, object], dict[str, object]]:
        self.receipt("dispatch_sent", "content-organic-website", "handoff-dispatch")
        self.receipt("chat_ack", "content-organic-website", "handoff-ack")
        path = self.root / "logs/department-outbox/workflow-test-001-content-organic-website-result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": "2.0", "task_id": self.task_id,
            "department": "content-organic-website",
            "fixed_chat_task_id": "fixed-content-organic-website",
            "candidate_version": "candidate-v1",
            "status": "needs_input", "conclusion": "partial result",
            "evidence": {}, "risks": ["source unavailable"],
            "next_actions": ["obtain source"], "handoff": {"receiver": "operations"},
            "approval_required": False, "learning": {"status": "no_new_learning"},
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True},
        }), encoding="utf-8")
        result_sha = workflow.file_digest(self.root, workflow.rel_path(self.root, path))["sha256"]
        base: dict[str, object] = {
            "task_id": self.task_id, "sender_department": "content-organic-website",
            "candidate_version": "candidate-v1", "result_sha256": result_sha,
            "outbox_path": workflow.rel_path(self.root, path),
        }
        # Historical pre-change delivery receipt: preserve verification of old
        # notification_sent rows without reopening the now-denied send route.
        policy = {
            "decision_id": "legacy-result-notification-policy", "status": "allow",
            "routing_status": "routing_allowed", "task_id": self.task_id,
            "department": "content-organic-website", "action_class": "thread_message",
            "action_id": "notify-operations-handoff-v1", "target_department": "operations",
            "target_thread_id": "fixed-operations",
            "scope": f"department_result:{self.task_id}:content-organic-website",
            "payload_sha256": "a" * 64,
        }
        policy_path = self.root / "logs/policy-decisions.jsonl"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        with policy_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(policy) + "\n")
        return base, policy

    def test_scheduled_daily_result_queues_without_fabricated_dispatch(self) -> None:
        task_id = "fc-20260930-website-growth-daily"
        contract_path = self.root / "data/task-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["department_output_gates"] = {
            "content_organic_website_daily": {
                "task_id_pattern": "fc-YYYYMMDD-website-growth-daily"
            }
        }
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        path = self.root / "logs/department-outbox/daily-result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": "2.0", "task_id": task_id,
            "department": "content-organic-website",
            "fixed_chat_task_id": "fixed-content-organic-website",
            "candidate_version": "daily-check-v1", "status": "blocked",
            "reported_at_myt": "2026-09-30T10:30:00+08:00",
            "conclusion": "source unavailable", "evidence": {},
            "risks": ["source unavailable"], "next_actions": ["obtain source"],
            "handoff": {"receiver": "operations"}, "approval_required": False,
            "learning": {"status": "no_new_learning"},
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True},
        }), encoding="utf-8")
        base = {
            "task_id": task_id, "sender_department": "content-organic-website",
            "candidate_version": "daily-check-v1",
            "result_sha256": workflow.file_digest(self.root, "logs/department-outbox/daily-result.json")["sha256"],
            "outbox_path": "logs/department-outbox/daily-result.json",
        }
        queued = {**base, "event": "notification_queued", "idempotency_key": "daily-queue-v1",
                  "source_mode": "scheduled_run", "source_automation_id": "flash-cast-4",
                  # Runtime-generated synthetic UUID; never a private native turn.
                  "source_turn_id": str(uuid.UUID(int=1)),
                  "source_thread_id": "fixed-content-organic-website",
                  "source_reply_sha256": "a" * 64,
                  "reply_observed_at": "2026-09-30T02:35:00+00:00",
                  "evidence_paths": ["data/task-contract.json"]}
        error = "每日自动任务入队须有合同匹配、原固定聊天完成轮次和同日本地V2结果"
        with self.assertRaisesRegex(workflow.WorkflowError, error):
            workflow.record_result_handoff(self.root, {**queued, "source_automation_id": "other"})
        with self.assertRaisesRegex(workflow.WorkflowError, error):
            workflow.record_result_handoff(self.root, {**queued, "reply_observed_at": "2026-10-01T02:35:00+00:00"})
        contract["department_output_gates"]["content_organic_website_daily"]["task_id_pattern"] = "other-pattern"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, error):
            workflow.record_result_handoff(self.root, queued)
        contract["department_output_gates"]["content_organic_website_daily"]["task_id_pattern"] = "fc-YYYYMMDD-website-growth-daily"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        self.assertFalse(workflow.result_handoff_path(self.root, task_id).exists())
        first, _ = workflow.record_result_handoff(self.root, queued)
        self.assertEqual(first["source_mode"], "scheduled_run")
        self.assertEqual(first["evidence"], [workflow.file_digest(self.root, "data/task-contract.json")])
        self.assertEqual(workflow.record_result_handoff(self.root, queued)[0]["result"], "duplicate_ignored")
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 1)
        self.assertFalse((self.root / "data/workflows" / f"{task_id}.json").exists())
        self.assertFalse(workflow.receipts_path(self.root, task_id).exists())
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "daily-received-v1", "intake_mode": "queue",
            "source_reply_sha256": "a" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": "2026-09-30T02:35:00+00:00"})
        report = self.root / "reports/daily-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Wait for the source owner.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "daily-decision-v1", "decision": "wait_external",
            "next_owner": "operations", "next_action": "request lawful source",
            "unblock_condition": "custodian provides source", "evidence_paths": ["reports/daily-decision.md"]})
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 0)

    def test_registered_daily_result_requires_exact_completed_native_run(self) -> None:
        """Synthetic native readback inputs exercise the real generic consumer."""
        now = dt.datetime.now(dt.timezone.utc)
        role = "paid-growth-data"
        binding = workflow.department_registry(self.root)[role]["chat_binding"]
        task = "fc-" + now.strftime("%Y%m%d") + "-paid-growth-daily"
        outbox_path = "logs/department-outbox/synthetic-registered-daily.json"
        path = self.root / outbox_path
        path.parent.mkdir(parents=True, exist_ok=True)
        box = {
            "schema_version": "2.0", "task_id": task, "department": role,
            "fixed_chat_task_id": binding["task_id"], "candidate_version": "synthetic-daily-v1",
            "status": "blocked", "conclusion": "synthetic source unavailable", "evidence": {},
            "risks": ["source unavailable"], "next_actions": ["obtain source"],
            "handoff": {"receiver": "operations"}, "approval_required": False,
            "learning": {"status": "no_new_learning"},
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True,
                           "sha256": "a" * 64, "ref": "synthetic-fixed-reply"},
        }
        path.write_text(json.dumps(box), encoding="utf-8")
        proof = workflow.file_digest(self.root, outbox_path)
        run_path = "logs/native-readbacks/synthetic-daily-run.json"
        native = self.root / run_path
        native.parent.mkdir(parents=True, exist_ok=True)
        run = {
            "source": "native_automation_run_readback", "completed": True,
            "trusted_native_readback": True, "task_id": task, "department": role,
            "thread_id": binding["task_id"], "project_id": binding["project_id"],
            "cwd": binding["cwd"], "automation_id": "synthetic-daily-automation",
            "turn_id": str(uuid.UUID(int=2)), "reply_sha256": "a" * 64,
            "reply_ref": box["chat_reply"]["ref"], "outbox": proof,
            "observed_at": (now - dt.timedelta(seconds=10)).isoformat(),
        }
        queued = {
            "task_id": task, "sender_department": role, "candidate_version": box["candidate_version"],
            "result_sha256": proof["sha256"], "outbox_path": outbox_path,
            "event": "notification_queued", "idempotency_key": "synthetic-daily-queue-v1",
            "source_mode": "scheduled_run", "source_automation_id": run["automation_id"],
            "source_turn_id": run["turn_id"], "source_thread_id": binding["task_id"],
            "source_reply_sha256": run["reply_sha256"],
            "reply_observed_at": (now - dt.timedelta(seconds=30)).isoformat(),
        }

        def request_for(value):
            native.write_text(json.dumps(value), encoding="utf-8")
            return {**queued, "native_run": workflow.file_digest(self.root, run_path)}

        changes = {
            "source": "caller_assertion", "completed": False, "trusted_native_readback": False,
            "task_id": "other-task", "department": "content-organic-website",
            "thread_id": "other-fixed-chat", "project_id": "other-project", "cwd": str(self.root / "other"),
            "automation_id": "other-automation", "turn_id": "other-turn", "reply_sha256": "b" * 64,
            "reply_ref": "other-reply", "outbox": {**proof, "sha256": "b" * 64},
            "observed_at": (now + dt.timedelta(minutes=1)).isoformat(),
        }
        for field, value in changes.items():
            with self.subTest(native_field=field):
                with self.assertRaisesRegex(workflow.WorkflowError, "exact completed native run and fixed-chat result required"):
                    workflow.record_result_handoff(self.root, request_for({**run, field: value}))
                self.assertFalse(workflow.result_handoff_path(self.root, task).exists())
        stale = request_for({**run, "observed_at": (now - dt.timedelta(minutes=6)).isoformat()})
        stale["reply_observed_at"] = (now - dt.timedelta(minutes=7)).isoformat()
        with self.assertRaisesRegex(workflow.WorkflowError, "exact completed native run and fixed-chat result required"):
            workflow.record_result_handoff(self.root, stale)
        for reply_at in ("not-a-time", (now + dt.timedelta(minutes=1)).isoformat()):
            with self.subTest(reply_observed_at=reply_at):
                with self.assertRaisesRegex(workflow.WorkflowError, "exact completed native run and fixed-chat result required"):
                    workflow.record_result_handoff(self.root, {**request_for(run), "reply_observed_at": reply_at})
        bad_pin = request_for(run)
        bad_pin["native_run"] = {**bad_pin["native_run"], "sha256": "b" * 64}
        with self.assertRaisesRegex(workflow.WorkflowError, "exact native run pin required"):
            workflow.record_result_handoff(self.root, bad_pin)
        with self.assertRaisesRegex(workflow.WorkflowError, "每日自动任务入队须有合同匹配"):
            workflow.record_result_handoff(self.root, queued)
        valid = request_for(run)
        first, _ = workflow.record_result_handoff(self.root, valid)
        self.assertEqual(first["native_run"], valid["native_run"])
        self.assertEqual(first["outbox"], proof)
        self.assertEqual(first["source_reply_sha256"], box["chat_reply"]["sha256"])
        self.assertEqual(workflow.record_result_handoff(self.root, valid)[0]["result"], "duplicate_ignored")
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 1)
        self.assertFalse(workflow.snapshot_path(self.root, task).exists())
        self.assertFalse(workflow.receipts_path(self.root, task).exists())

    def test_legacy_received_result_can_register_external_followthrough(self) -> None:
        base, _ = self._result_handoff_fixture()
        path = self.root / str(base["outbox_path"])
        outbox = json.loads(path.read_text(encoding="utf-8"))
        outbox.pop("fixed_chat_task_id")
        path.write_text(json.dumps(outbox), encoding="utf-8")
        base["result_sha256"] = workflow.file_digest(self.root, str(base["outbox_path"]))["sha256"]
        self.receipt("outbox_received", "content-organic-website", "legacy-outbox", evidence=str(base["outbox_path"]))
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "legacy-received-v1", "intake_mode": "fallback",
            "fallback_reason": "old result had no durable queue",
            "source_reply_sha256": "a" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/legacy-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Await authorized source.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "legacy-decision-v1", "decision": "wait_external",
            "next_owner": "operations", "next_action": "obtain legal source",
            "unblock_condition": "custodian supplies source",
            "evidence_paths": ["reports/legacy-decision.md"]})
        row, _ = workflow.record_result_handoff(self.root, {**base,
            "event": "controller_followthrough", "idempotency_key": "legacy-wait-v1",
            "followthrough_status": "external_wait_registered",
            "unblock_condition": "custodian supplies source",
            "next_check_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat(),
            "evidence_paths": ["reports/legacy-decision.md"]})
        self.assertEqual(row["result"], "recorded")

    def test_result_handoff_preserves_uppercase_candidate_version(self) -> None:
        base, _ = self._result_handoff_fixture()
        candidate = "artistic-coating-v7p2-current-native-read-v3-exact-Chrome-tab-20261006"
        outbox_path = str(base["outbox_path"])
        outbox_file = self.root / outbox_path
        outbox = json.loads(outbox_file.read_text(encoding="utf-8"))
        outbox["candidate_version"] = candidate
        outbox_file.write_text(json.dumps(outbox), encoding="utf-8")
        base["candidate_version"] = candidate
        base["result_sha256"] = workflow.file_digest(self.root, outbox_path)["sha256"]

        queued = {**base, "event": "notification_queued", "idempotency_key": "uppercase-candidate-v1"}
        row, _ = workflow.record_result_handoff(self.root, queued)
        self.assertEqual(row["candidate_version"], candidate)
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 1)

    def test_result_handoff_queue_preserves_active_work_and_deduplicates(self) -> None:
        base, _ = self._result_handoff_fixture()
        queued = {**base, "event": "notification_queued", "idempotency_key": "queued-result-v1"}
        first, _ = workflow.record_result_handoff(self.root, queued)
        self.assertEqual(first["delivery_mode"], "durable_inbox")
        self.assertFalse(first["interrupts_active_thread"])
        self.assertEqual(workflow.record_result_handoff(self.root, queued)[0]["result"], "duplicate_ignored")
        with self.assertRaisesRegex(workflow.WorkflowError, "已记录"):
            workflow.record_result_handoff(self.root, {**queued, "idempotency_key": "queued-twice"})
        pending = workflow.result_handoff_pending(self.root)
        self.assertEqual(pending["pending_count"], 1)
        self.assertFalse(pending["results"][0]["received"])
        self.assertEqual(workflow.result_handoff_status(self.root, self.task_id)["results"][0]["notification"], "queued")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "queue-received-v1", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        self.assertTrue(workflow.result_handoff_pending(self.root)["results"][0]["received"])
        report = self.root / "reports/queue-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Continue original scope.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "queue-decided-v1", "decision": "continue",
            "next_owner": "content-organic-website", "next_action": "continue original scope",
            "evidence_paths": ["reports/queue-decision.md"]})
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 0)
        self.assertEqual(workflow.result_handoff_pending(self.root)["followthrough_pending_count"], 1)
        self.assertFalse(workflow.result_handoff_status(self.root, self.task_id)["business_goal_closed"])

    def test_decision_remains_actionable_until_external_wait_is_registered(self) -> None:
        base, _ = self._result_handoff_fixture()
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "external-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "external-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/external-wait.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Waiting for authorized source.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "external-decision", "decision": "wait_external",
            "next_owner": "operations", "next_action": "request source from custodian",
            "unblock_condition": "custodian supplies source",
            "evidence_paths": ["reports/external-wait.md"]})
        pending = workflow.result_handoff_pending(self.root)
        self.assertEqual(pending["pending_count"], 0)
        self.assertEqual(pending["followthrough_pending_count"], 1)
        self.assertEqual(pending["total_actionable_count"], 1)
        next_check = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        followthrough = {**base, "event": "controller_followthrough",
            "idempotency_key": "external-followthrough", "followthrough_status": "external_wait_registered",
            "next_check_at": next_check, "unblock_condition": "custodian supplies source",
            "evidence_paths": ["reports/external-wait.md"]}
        workflow.record_result_handoff(self.root, followthrough)
        self.assertEqual(workflow.result_handoff_pending(self.root)["followthrough_pending_count"], 0)
        self.assertEqual(workflow.record_result_handoff(self.root, followthrough)[0]["result"], "duplicate_ignored")
        self.assertFalse(workflow.result_handoff_status(self.root, self.task_id)["business_goal_closed"])

    def test_followthrough_rejects_a_dispatch_that_predates_controller_decision(self) -> None:
        base, _ = self._result_handoff_fixture()
        prior_dispatch = next(row for row in workflow._validate_receipt_chain(self.root, self.task_id)[0]
                              if row.get("receipt_type") == "dispatch_sent")
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "dispatch-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "dispatch-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/dispatch-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Continue with the original owner.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "dispatch-decision", "decision": "continue",
            "next_owner": "content-organic-website", "next_action": "send bounded continuation",
            "evidence_paths": ["reports/dispatch-decision.md"]})
        with self.assertRaisesRegex(workflow.WorkflowError, "晚于决策"):
            workflow.record_result_handoff(self.root, {**base, "event": "controller_followthrough",
                "idempotency_key": "old-dispatch-is-not-followthrough",
                "followthrough_status": "dispatch_sent", "linked_task_id": self.task_id,
                "action_receipt_id": prior_dispatch["receipt_id"],
                "evidence_paths": ["reports/dispatch-decision.md"]})

    def test_prior_delivery_reconciliation_requires_matching_owner_and_outbox_receipt(self) -> None:
        base, _ = self._result_handoff_fixture()
        original_task_id = self.task_id
        linked_task_id = "workflow-test-002"
        self.task_id = linked_task_id
        self.routing_decisions = {}
        self.dispatch()
        self.receipt("dispatch_sent", "content-organic-website", "prior-dispatch")
        self.receipt("chat_ack", "content-organic-website", "prior-ack")
        linked_path = self.root / "logs/department-outbox/prior-result.json"
        linked_path.write_text(json.dumps({
            "schema_version": "2.0", "task_id": linked_task_id,
            "department": "content-organic-website",
            "fixed_chat_task_id": "fixed-content-organic-website",
            "candidate_version": "prior-v2", "status": "completed",
            "conclusion": "Already delivered read-only follow-up",
            "evidence": {}, "risks": [], "next_actions": [],
            "handoff": {"receiver": "operations"},
            "approval_required": False, "learning": {"status": "no_new_learning"},
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True},
        }), encoding="utf-8")
        linked_rel = workflow.rel_path(self.root, linked_path)
        receipt = self.receipt("outbox_received", "content-organic-website",
                               "prior-outbox", evidence=linked_rel)
        time.sleep(1.05)  # Receipt timestamps use whole seconds; keep strict prior ordering.
        self.task_id = original_task_id
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "prior-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "prior-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/prior-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Existing bounded task delivered before late decision.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "prior-decision", "decision": "continue",
            "next_owner": "content-organic-website", "next_action": "reconcile delivered v2",
            "evidence_paths": ["reports/prior-decision.md"]})
        followthrough = {**base, "event": "controller_followthrough",
            "idempotency_key": "prior-verified", "followthrough_status": "prior_action_verified",
            "linked_task_id": linked_task_id, "action_receipt_id": receipt["receipt_id"],
            "linked_outbox_path": linked_rel,
            "evidence_paths": ["reports/prior-decision.md", linked_rel]}
        with self.assertRaisesRegex(workflow.WorkflowError, "准确 outbox"):
            workflow.record_result_handoff(self.root, {**followthrough,
                "linked_outbox_path": str(base["outbox_path"])})
        row, _ = workflow.record_result_handoff(self.root, followthrough)
        self.assertTrue(row["action_before_decision"])
        self.assertEqual(workflow.record_result_handoff(self.root, followthrough)[0]["result"],
                         "duplicate_ignored")
        self.assertEqual(workflow.result_handoff_pending(self.root)["followthrough_pending_count"], 0)
        self.assertFalse(workflow.result_handoff_status(self.root, original_task_id)["business_goal_closed"])

    def test_prior_same_task_qa_is_linked_without_repeating_dispatch(self) -> None:
        base, _ = self._result_handoff_fixture()
        self.receipt("dispatch_sent", "qa", "prior-qa-dispatch")
        self.receipt("chat_ack", "qa", "prior-qa-ack")
        path = self.root / "logs/department-outbox/prior-same-task-qa.json"
        path.write_text(json.dumps({"schema_version": "2.0", "task_id": self.task_id,
                                    "department": "qa", "candidate_version": "candidate-v1",
                                    "status": "completed", "conclusion": "scoped review complete",
                                    "evidence": ["reports/qa.md"], "risks": [],
                                    "next_actions": ["review verdict"],
                                    "handoff": {"to": "operations"}, "approval_required": True,
                                    "learning": {"status": "no_new_learning"}}),
                        encoding="utf-8")
        rel = workflow.rel_path(self.root, path)
        receipt = self.receipt("outbox_received", "qa", "prior-qa-outbox", evidence=rel)
        time.sleep(1.05)  # Keep the prior QA receipt strictly before the late decision.
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "same-qa-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "same-qa-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/prior-same-qa.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Same-task QA was already delivered.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "same-qa-decision", "decision": "send_qa",
            "next_owner": "qa", "next_action": "reconcile the existing exact QA",
            "evidence_paths": ["reports/prior-same-qa.md"]})
        followthrough = {**base, "event": "controller_followthrough",
            "idempotency_key": "same-qa-prior-verified",
            "followthrough_status": "prior_action_verified", "linked_task_id": self.task_id,
            "action_receipt_id": receipt["receipt_id"], "linked_outbox_path": rel,
            "evidence_paths": ["reports/prior-same-qa.md", rel]}
        row, _ = workflow.record_result_handoff(self.root, followthrough)
        self.assertTrue(row["action_before_decision"])
        self.assertEqual(workflow.record_result_handoff(self.root, followthrough)[0]["result"],
                         "duplicate_ignored")
        self.assertEqual(workflow.result_handoff_pending(self.root)["followthrough_pending_count"], 0)

    def test_prior_same_task_qa_rejects_wrong_candidate_version(self) -> None:
        base, _ = self._result_handoff_fixture()
        self.receipt("dispatch_sent", "qa", "wrong-prior-qa-dispatch")
        self.receipt("chat_ack", "qa", "wrong-prior-qa-ack")
        path = self.root / "logs/department-outbox/prior-wrong-version-qa.json"
        path.write_text(json.dumps({"schema_version": "2.0", "task_id": self.task_id,
                                    "department": "qa", "candidate_version": "different-v2",
                                    "status": "completed", "conclusion": "wrong version review",
                                    "evidence": ["reports/qa.md"], "risks": [],
                                    "next_actions": ["review verdict"],
                                    "handoff": {"to": "operations"}, "approval_required": True,
                                    "learning": {"status": "no_new_learning"}}),
                        encoding="utf-8")
        rel = workflow.rel_path(self.root, path)
        receipt = self.receipt("outbox_received", "qa", "wrong-prior-qa-outbox", evidence=rel)
        time.sleep(1.05)
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "wrong-qa-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "wrong-qa-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/prior-wrong-qa.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Wrong QA version must not close the action.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "wrong-qa-decision", "decision": "send_qa",
            "next_owner": "qa", "next_action": "verify the exact version",
            "evidence_paths": ["reports/prior-wrong-qa.md"]})
        with self.assertRaisesRegex(workflow.WorkflowError, "准确候选版本"):
            workflow.record_result_handoff(self.root, {**base, "event": "controller_followthrough",
                "idempotency_key": "wrong-qa-prior-verified",
                "followthrough_status": "prior_action_verified", "linked_task_id": self.task_id,
                "action_receipt_id": receipt["receipt_id"], "linked_outbox_path": rel,
                "evidence_paths": ["reports/prior-wrong-qa.md", rel]})

    def _inflight_result_fixture(self, *, linked_task: bool = False, ack: bool = True,
                                 candidate: str = "candidate-v1", parent: bool = True,
                                 verdict: bool = True, decision_owner: str = "qa",
                                 dispatch_after: bool = False,
                                 parent_field: str = "parent_task_id",
                                 conflicting_parent: bool = False,
                                 reference_only: bool = False) -> dict[str, object]:
        base, _ = self._result_handoff_fixture()
        original = self.task_id
        self.receipt("outbox_received", "content-organic-website", "inflight-source-outbox",
                     evidence=str(base["outbox_path"]))
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "inflight-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "inflight-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        owner = "content-organic-website" if linked_task else "qa"
        if linked_task:
            self.task_id = "workflow-test-child"
            self.routing_decisions = {}
            self.dispatch()
        linked = self.task_id
        at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        t0, t1, t2 = [(at + dt.timedelta(seconds=i)).isoformat() for i in range(3)]
        with mock.patch.object(workflow, "utc_timestamp", return_value=t2 if dispatch_after else t0):
            if not ack:
                self.receipt("dispatch_sent", owner, "inflight-old-dispatch")
                self.receipt("chat_ack", owner, "inflight-old-ack")
            dispatch = self.receipt("dispatch_sent", owner, "inflight-dispatch")
            if ack:
                self.receipt("chat_ack", owner, "inflight-ack")
        report = self.root / "reports/inflight-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Reconcile only a genuine task already in flight.\n", encoding="utf-8")
        with mock.patch.object(workflow, "utc_timestamp", return_value=t1):
            workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
                "idempotency_key": "inflight-decision", "decision": "continue",
                "next_owner": owner if linked_task else decision_owner,
                "next_action": "verify the existing exact result without duplicate dispatch",
                "evidence_paths": ["reports/inflight-decision.md"]})
        path = self.root / "logs/department-outbox/inflight-result.json"
        outbox = {"schema_version": "2.0", "task_id": linked,
                  "department": owner, "fixed_chat_task_id": f"fixed-{owner}",
                  "candidate_version": candidate, "status": "completed",
                  "conclusion": "Scoped result; no publication", "evidence": {},
                  "risks": [], "next_actions": ["review remaining scope"],
                  "handoff": {"receiver": "operations"}, "approval_required": False,
                  "learning": {"status": "no_new_learning"},
                  "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True}}
        if linked_task and parent:
            outbox[parent_field] = original
        if conflicting_parent:
            outbox["parent_task_id"] = "unrelated-parent"
        if reference_only:
            outbox["original_task_refs"] = [original]
        path.write_text(json.dumps(outbox), encoding="utf-8")
        rel = workflow.rel_path(self.root, path)
        with mock.patch.object(workflow, "utc_timestamp", return_value=t2):
            result = self.receipt("outbox_received", owner, "inflight-outbox", evidence=rel)
            if owner == "qa" and verdict and ack:
                self.receipt("qa_verdict", "qa", "inflight-qa-verdict",
                             verdict="blocked", evidence=rel, action_class="local_read",
                             action_id="inflight-exact-qa", scope="project:inflight-review")
        self.task_id = original
        return {**base, "event": "controller_followthrough", "idempotency_key": "inflight-verified",
                "followthrough_status": "inflight_result_verified", "linked_task_id": linked,
                "linked_dispatch_receipt_id": dispatch["receipt_id"],
                "action_receipt_id": result["receipt_id"], "linked_outbox_path": rel,
                "evidence_paths": ["reports/inflight-decision.md", rel]}

    def test_inflight_qa_result_links_once_without_closing_business_goal(self) -> None:
        request = self._inflight_result_fixture()
        row, _ = workflow.record_result_handoff(self.root, request)
        self.assertTrue(row["dispatch_before_decision"])
        self.assertTrue(row["result_after_decision"])
        self.assertFalse(row["business_goal_closed"])
        self.assertEqual(workflow.record_result_handoff(self.root, request)[0]["result"], "duplicate_ignored")
        self.assertEqual(workflow.result_handoff_pending(self.root)["followthrough_pending_count"], 0)
        self.assertFalse(workflow.result_handoff_status(self.root, self.task_id)["business_goal_closed"])

    def test_inflight_child_result_requires_explicit_original_parent(self) -> None:
        request = self._inflight_result_fixture(linked_task=True)
        row, _ = workflow.record_result_handoff(self.root, request)
        self.assertEqual(row["linked_task_id"], "workflow-test-child")
        self.assertFalse(row["business_goal_closed"])

    def test_inflight_child_accepts_exact_original_business_parent(self) -> None:
        request = self._inflight_result_fixture(
            linked_task=True, parent_field="original_business_task_id")
        row, _ = workflow.record_result_handoff(self.root, request)
        self.assertTrue(row["dispatch_before_decision"])
        self.assertTrue(row["result_after_decision"])
        self.assertFalse(row["business_goal_closed"])
        self.assertEqual(workflow.record_result_handoff(self.root, request)[0]["result"],
                         "duplicate_ignored")

    def test_inflight_child_rejects_conflicting_explicit_parents(self) -> None:
        request = self._inflight_result_fixture(
            linked_task=True, parent_field="original_business_task_id", conflicting_parent=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "原父任务"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_child_rejects_reference_list_without_parent(self) -> None:
        request = self._inflight_result_fixture(linked_task=True, parent=False, reference_only=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "原父任务"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_result_rejects_missing_ack(self) -> None:
        request = self._inflight_result_fixture(ack=False)
        with self.assertRaisesRegex(workflow.WorkflowError, "非空接单"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_result_rejects_wrong_dispatch(self) -> None:
        request = self._inflight_result_fixture()
        with self.assertRaisesRegex(workflow.WorkflowError, "真实派工"):
            workflow.record_result_handoff(self.root, {**request, "linked_dispatch_receipt_id": "unrelated"})

    def test_inflight_result_rejects_wrong_owner(self) -> None:
        request = self._inflight_result_fixture(decision_owner="content-organic-website")
        with self.assertRaisesRegex(workflow.WorkflowError, "真实派工"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_qa_rejects_wrong_candidate(self) -> None:
        request = self._inflight_result_fixture(candidate="different-v2")
        with self.assertRaisesRegex(workflow.WorkflowError, "准确候选版本"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_qa_rejects_missing_independent_verdict(self) -> None:
        request = self._inflight_result_fixture(verdict=False)
        with self.assertRaisesRegex(workflow.WorkflowError, "独立 QA"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_result_rejects_unrelated_child(self) -> None:
        request = self._inflight_result_fixture(linked_task=True, parent=False)
        with self.assertRaisesRegex(workflow.WorkflowError, "原父任务"):
            workflow.record_result_handoff(self.root, request)

    def test_inflight_result_rejects_dispatch_after_decision(self) -> None:
        request = self._inflight_result_fixture(dispatch_after=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "决策前"):
            workflow.record_result_handoff(self.root, request)

    def test_blocked_followthrough_can_be_rechecked_and_then_dispatched(self) -> None:
        base, _ = self._result_handoff_fixture()
        workflow.record_result_handoff(self.root, {**base, "event": "notification_queued",
            "idempotency_key": "blocked-queued"})
        workflow.record_result_handoff(self.root, {**base, "event": "controller_received",
            "idempotency_key": "blocked-received", "intake_mode": "queue",
            "source_reply_sha256": "d" * 64,
            "source_thread_id": "fixed-content-organic-website",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        report = self.root / "reports/blocked-decision.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Owner must regain access.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
            "idempotency_key": "blocked-decision", "decision": "continue",
            "next_owner": "content-organic-website", "next_action": "dispatch once available",
            "evidence_paths": ["reports/blocked-decision.md"]})
        check1 = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()
        blocked = {**base, "event": "controller_followthrough",
            "idempotency_key": "blocked-first", "followthrough_status": "blocked_with_owner",
            "next_check_at": check1, "unblock_condition": "fixed chat becomes loadable",
            "evidence_paths": ["reports/blocked-decision.md"]}
        workflow.record_result_handoff(self.root, blocked)
        state = workflow.result_handoff_status(self.root, self.task_id)
        self.assertEqual(state["status"], "waiting_followthrough_review")
        self.assertEqual(state["waiting_followthrough_count"], 1)
        with self.assertRaisesRegex(workflow.WorkflowError, "新的项目内证据"):
            workflow.record_result_handoff(self.root, {**blocked,
                "idempotency_key": "blocked-same-evidence",
                "next_check_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat()})
        recheck = self.root / "reports/blocked-recheck.md"
        recheck.write_text("Still unavailable on second check.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**blocked,
            "idempotency_key": "blocked-second",
            "next_check_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(),
            "evidence_paths": ["reports/blocked-recheck.md"]})
        self.assertEqual(workflow.result_handoff_status(self.root, self.task_id)["waiting_followthrough_count"], 1)
        # The subsequent real dispatch closes this control step; it does not
        # erase the two historical failed attempts or close the business goal.
        import time
        time.sleep(1.05)  # receipt timestamps have second precision
        receipt = self.receipt("dispatch_sent", "content-organic-website", "restored-dispatch")
        dispatch_evidence = self.root / "reports/restored-dispatch.md"
        dispatch_evidence.write_text("Fixed chat restored and real dispatch receipt recorded.\n", encoding="utf-8")
        workflow.record_result_handoff(self.root, {**base, "event": "controller_followthrough",
            "idempotency_key": "blocked-restored", "followthrough_status": "dispatch_sent",
            "linked_task_id": self.task_id, "action_receipt_id": receipt["receipt_id"],
            "evidence_paths": ["reports/restored-dispatch.md"]})
        state = workflow.result_handoff_status(self.root, self.task_id)
        self.assertEqual(state["status"], "decided_scope_only")
        self.assertEqual(state["followthrough_pending_count"], 0)
        self.assertFalse(state["business_goal_closed"])

    def test_pending_discovers_legacy_outbox_missing_from_result_queue(self) -> None:
        base, _ = self._result_handoff_fixture()
        self.receipt("outbox_received", "content-organic-website", "legacy-delivery-received",
                     evidence=str(base["outbox_path"]))

        pending = workflow.result_handoff_pending(self.root)

        self.assertEqual(pending["status"], "recovery_required")
        self.assertEqual(pending["pending_count"], 1)
        self.assertEqual(pending["queued_pending_count"], 0)
        self.assertEqual(pending["legacy_recovery_count"], 1)
        candidate = pending["results"][0]
        self.assertTrue(candidate["recovery_required"])
        self.assertTrue(candidate["requires_live_reply_verification"])
        self.assertEqual(candidate["intake_mode"], "fallback")
        self.assertFalse(candidate["received"])
        self.assertFalse(candidate["decided"])

        # Discovery is derived and idempotent: it does not write a fake queue
        # event or silently mark the old result as received.
        self.assertFalse((self.root / workflow.RESULT_HANDOFF_DIR / f"{self.task_id}.jsonl").exists())
        self.assertEqual(workflow.result_handoff_pending(self.root)["pending_count"], 1)

    def test_pending_discovers_v2_outbox_missing_from_delivery_receipt(self) -> None:
        self._result_handoff_fixture()

        pending = workflow.result_handoff_pending(self.root)

        self.assertEqual(pending["legacy_recovery_count"], 1)
        candidate = pending["results"][0]
        self.assertEqual(candidate["recovery_reason"], "legacy_v2_outbox_without_result_queue_receipt")
        self.assertTrue(candidate["requires_live_reply_verification"])
        self.assertFalse(candidate["received"])

    def test_pending_keeps_controller_decision_due_after_fallback_intake(self) -> None:
        base, _ = self._result_handoff_fixture()
        self.receipt("outbox_received", "content-organic-website", "legacy-delivery-received",
                     evidence=str(base["outbox_path"]))
        received = {**base, "event": "controller_received", "idempotency_key": "legacy-fallback-intake",
                    "intake_mode": "fallback", "fallback_reason": "legacy queue omission",
                    "source_reply_sha256": "e" * 64,
                    "source_thread_id": "fixed-content-organic-website",
                    "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        workflow.record_result_handoff(self.root, received)

        pending = workflow.result_handoff_pending(self.root)

        self.assertEqual(pending["pending_count"], 1)
        self.assertFalse(pending["results"][0]["decided"])
        self.assertTrue(pending["results"][0]["received"])
        self.assertFalse(pending["results"][0].get("recovery_required", False))

    def test_legacy_recovery_is_limited_to_checkpoint_and_open_backlog(self) -> None:
        base, _ = self._result_handoff_fixture()
        self.receipt("outbox_received", "content-organic-website", "legacy-delivery-received",
                     evidence=str(base["outbox_path"]))
        checkpoint = self.root / "logs/handoffs/current-checkpoint.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({"active_department_tasks": ["another-open-task"],
                                          "pending_qa": []}), encoding="utf-8")
        policy_path = self.root / "data/content/organic-execution-policy.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps({"keyword_content_coverage_acceptance": {
            "controller_checkpoint": "logs/handoffs/current-checkpoint.json"}}), encoding="utf-8")
        backlog_path = self.root / "data/content/organic-growth-backlog.json"
        backlog_path.write_text(json.dumps({"items": [
            {"status": "ready_for_qa", "original_task_id": "another-open-task"},
            {"status": "closed", "task_id": self.task_id},
        ]}), encoding="utf-8")

        pending = workflow.result_handoff_pending(self.root)

        self.assertEqual(pending["pending_count"], 0)
        self.assertEqual(pending["legacy_recovery_count"], 0)

    def test_result_handoff_sent_received_decided_once(self) -> None:
        base, policy = self._result_handoff_fixture()
        sent = {**base, "event": "notification_sent", "idempotency_key": "result-sent-v1",
                "policy_decision_id": policy["decision_id"], "message_sha256": "a" * 64,
                "message_ref": "codex-send-success-001"}
        with self.assertRaisesRegex(workflow.WorkflowError, "候选版本必须"):
            workflow.record_result_handoff(self.root, {**sent, "candidate_version": "wrong-version"})
        with self.assertRaisesRegex(workflow.WorkflowError, "放行决定"):
            workflow.record_result_handoff(self.root, {**sent, "message_sha256": "b" * 64})
        recorded, _ = workflow.record_result_handoff(self.root, sent)
        self.assertEqual(recorded["result"], "recorded")
        self.assertEqual(workflow.record_result_handoff(self.root, sent)[0]["result"], "duplicate_ignored")
        controller = workflow.department_registry(self.root)["operations"]["chat_binding"]
        repeated_route, _ = workflow.policy_check(
            self.root, task_id=self.task_id, department="content-organic-website",
            action_id="notify-operations-handoff-repeat", action_class="thread_message",
            scope=f"department_result:{self.task_id}:content-organic-website",
            source_project_id="flashcast-test-project", target_project_id="flashcast-test-project",
            target_department="operations", target_thread_id=str(controller["task_id"]),
            target_thread_title=str(controller["title"]), target_cwd=str(self.root),
            target_sidebar_section_id=str(controller["sidebar_section_id"]),
            payload_sha256="a" * 64,
        )
        self.assertEqual(repeated_route["routing_status"], "blocked_route_invalid")
        self.assertIn("department_result_uses_durable_inbox", repeated_route["reason"])
        with self.assertRaisesRegex(workflow.WorkflowError, "已记录"):
            workflow.record_result_handoff(self.root, {**sent, "idempotency_key": "attempt-duplicate"})
        received = {**base, "event": "controller_received", "idempotency_key": "result-received-v1",
                    "intake_mode": "notification", "source_reply_sha256": "b" * 64,
                    "source_thread_id": "fixed-content-organic-website",
                    "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        workflow.record_result_handoff(self.root, received)
        evidence = self.root / "reports/decision.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("Needs external source.\n", encoding="utf-8")
        decided = {**base, "event": "controller_decision", "idempotency_key": "result-decision-v1",
                   "decision": "wait_external", "next_owner": "operations",
                   "next_action": "identify the actual source custodian",
                   "unblock_condition": "source custodian supplies verified input",
                   "evidence_paths": ["reports/decision.md"]}
        workflow.record_result_handoff(self.root, decided)
        state = workflow.result_handoff_status(self.root, self.task_id)
        self.assertEqual(state["status"], "decided_followthrough_pending")
        self.assertFalse(state["business_goal_closed"])
        self.assertEqual(workflow.workflow_status(self.root, self.task_id)[0]["business_goal_status"],
                         "not_inferred_from_workflow_state")
        with self.assertRaisesRegex(workflow.WorkflowError, "已记录"):
            workflow.record_result_handoff(self.root, {**decided, "idempotency_key": "decision-again"})

    def test_result_handoff_blocked_fallback_and_qa_gate(self) -> None:
        base, _ = self._result_handoff_fixture()
        workflow.record_result_handoff(self.root, {**base, "event": "notification_blocked",
            "idempotency_key": "notify-blocked", "block_reason": "target_health_stale"})
        received = {**base, "event": "controller_received", "idempotency_key": "fallback-intake",
                    "intake_mode": "fallback", "fallback_reason": "notification blocked; daily intake",
                    "source_reply_sha256": "c" * 64,
                    "source_thread_id": "fixed-content-organic-website",
                    "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        workflow.record_result_handoff(self.root, received)
        # Fallback intake blocks a second send in the policy preflight itself.
        controller = workflow.department_registry(self.root)["operations"]["chat_binding"]
        policy, _ = workflow.policy_check(self.root, task_id=self.task_id,
            department="content-organic-website", action_id="notify-operations-late",
            action_class="thread_message",
            scope=f"department_result:{self.task_id}:content-organic-website",
            source_project_id="flashcast-test-project", target_project_id="flashcast-test-project",
            target_department="operations", target_thread_id=str(controller["task_id"]),
            target_thread_title=str(controller["title"]), target_cwd=str(self.root),
            target_sidebar_section_id=str(controller["sidebar_section_id"]), payload_sha256="a" * 64)
        self.assertIn("department_result_uses_durable_inbox", policy["reason"])
        with self.assertRaisesRegex(workflow.WorkflowError, "放行决定"):
            workflow.record_result_handoff(self.root, {**base, "event": "notification_sent",
                "idempotency_key": "late-send", "policy_decision_id": policy["decision_id"],
                "message_sha256": "a" * 64, "message_ref": "late"})
        report = self.root / "reports/rework.md"
        report.write_text("QA needs a new candidate.\n", encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "当前 QA PASS"):
            workflow.record_result_handoff(self.root, {**base, "event": "controller_decision",
                "idempotency_key": "premature-release", "decision": "release_gate",
                "next_owner": "content-organic-website", "next_action": "publish",
                "qa_status": "pass", "evidence_paths": ["reports/rework.md"]})
        result, _ = workflow.record_result_handoff(self.root, {**base,
            "event": "controller_decision", "idempotency_key": "rework-decision",
            "decision": "rework", "next_owner": "content-organic-website",
            "next_action": "submit a corrected candidate to QA",
            "evidence_paths": ["reports/rework.md"]})
        self.assertEqual(result["decision"], "rework")
        self.assertFalse(result["business_goal_closed"])

    def test_legacy_outbox_without_chat_id_allows_only_verified_fallback(self) -> None:
        base, policy = self._result_handoff_fixture()
        path = self.root / str(base["outbox_path"])
        outbox = json.loads(path.read_text(encoding="utf-8"))
        del outbox["fixed_chat_task_id"]
        path.write_text(json.dumps(outbox), encoding="utf-8")
        base["result_sha256"] = workflow.file_digest(self.root, str(base["outbox_path"]))["sha256"]
        sent = {**base, "event": "notification_sent", "idempotency_key": "legacy-send",
                "policy_decision_id": policy["decision_id"], "message_sha256": "a" * 64,
                "message_ref": "would-be-send"}
        with self.assertRaisesRegex(workflow.WorkflowError, "旧 outbox 缺固定聊天绑定"):
            workflow.record_result_handoff(self.root, sent)
        self.receipt("outbox_received", "content-organic-website", "legacy-outbox-received",
                     evidence=str(base["outbox_path"]))
        received = {**base, "event": "controller_received", "idempotency_key": "legacy-fallback",
                    "intake_mode": "fallback", "fallback_reason": "old result missed notification",
                    "source_reply_sha256": "d" * 64,
                    "source_thread_id": "fixed-content-organic-website",
                    "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        self.assertEqual(workflow.record_result_handoff(self.root, received)[0]["result"], "recorded")

    def test_stale_binding_blocks_dispatch_but_exact_health_probe_is_allowed(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["departments"][1]["chat_binding"]["last_health_check_at"] = "2000-01-01T00:00:00+00:00"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        ordinary = self.routing_decision("content-organic-website")
        self.assertEqual(ordinary["status"], "deny")
        self.assertIn("target_thread_unhealthy_or_dispatch_ineligible", ordinary["reason"])

        binding = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        probe, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="health-probe-content",
            action_class="thread_message",
            scope="department_health_probe:content-organic-website",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="content-organic-website",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256="d" * 64,
        )
        self.assertEqual(probe["status"], "allow")
        self.assertTrue(probe["routing_health_probe_mode"])

    def test_department_health_record_restores_exact_registered_binding(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = registry["departments"][1]["chat_binding"]
        binding["reply_health"] = "failed_usage_limit"
        binding["dispatch_eligible"] = False
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        payload, artifacts = ops.department_health_record(
            self.root,
            argparse.Namespace(
                department="content-organic-website",
                task_id="fixed-content-organic-website",
                project_id="flashcast-test-project",
                cwd=str(self.root),
                title="content-organic-website",
                sidebar_section_id="flashcast-departments",
                reply_ref="msg-content-health-001",
                reply_sha256="e" * 64,
                reply_nonempty=True,
                live_status="idle",
                last_run_status="success",
                failure_class="",
                next_retry_at="",
            ),
        )
        self.assertTrue(payload["dispatch_eligible"])
        self.assertFalse(payload["chat_body_stored"])
        saved = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        self.assertEqual(saved["reply_health"], "healthy_visible_reply_verified")
        self.assertTrue(all(path.exists() for path in artifacts))

    def test_ambiguous_request_stays_with_controller_and_is_not_dispatched(self) -> None:
        rules_path = self.root / "data/department-routing-rules.json"
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        rules["fallback"] = {
            "id": "ambiguous-owner-request",
            "required_departments": ["operations"],
            "parallel_departments": ["operations"],
            "follow_up_departments": [],
            "department_dependencies": {"operations": []},
            "dispatch_allowed": False,
            "ask_user_if_ambiguous": True,
        }
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(request="帮我处理一下这个事情", task_id="ambiguous-test-001"),
        )
        self.assertEqual(payload["status"], "blocked_ambiguous_request")
        self.assertEqual(payload["required_departments"], ["operations"])
        self.assertEqual(payload["controller_action"], "clarify_owner_request")

    def test_explicit_qa_only_existing_deliverable_route(self) -> None:
        rules_path = self.root / "data/department-routing-rules.json"
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        rules["routes"].insert(0, {
            "id": "existing-deliverable-qa-only-review",
            "match_any": ["固定质检部只读复验", "既有交付 QA-only 复验"],
            "required_departments": ["qa"],
            "parallel_departments": ["qa"],
            "follow_up_departments": [],
            "department_dependencies": {"qa": []},
            "approval_required": False,
        })
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="固定质检部只读复验已存在的 Bathroom FAQ 公开对账资产，不修改内容",
                task_id="qa-only-existing-deliverable-001",
            ),
        )
        self.assertEqual(payload["status"], "ready_to_send")
        self.assertEqual(payload["required_departments"], ["qa"])
        self.assertEqual(payload["route"]["id"], "existing-deliverable-qa-only-review")

    def test_global_routing_audit_quarantines_mismatch_without_pausing(self) -> None:
        governance = self.root / "data/global-governance"
        governance.mkdir(parents=True)
        (governance / "automation-routing-registry.json").write_text(
            json.dumps(
                {
                    "automations": [
                        {
                            "automation_id": "daily-content",
                            "kind": "heartbeat",
                            "target_thread_id": "expected-thread",
                            "project_id": "flashcast-test-project",
                            "cwd": str(self.root),
                            "title": "content-organic-website",
                            "allowed_status": ["ACTIVE"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        live_snapshot = governance / "live.json"
        live_snapshot.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_id": "wrong-thread",
                            "project_id": "another-project",
                            "cwd": "/tmp/another-project",
                            "title": "wrong task",
                        }
                    ],
                    "automations": [
                        {
                            "automation_id": "daily-content",
                            "status": "ACTIVE",
                            "kind": "heartbeat",
                            "target_thread_id": "wrong-thread",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        fake_home = self.root / "home"
        automation_dir = fake_home / ".codex/automations/daily-content"
        automation_dir.mkdir(parents=True)
        (automation_dir / "automation.toml").write_text(
            'id = "daily-content"\n'
            'name = "Daily content"\n'
            'status = "ACTIVE"\n'
            'target_thread_id = "wrong-thread"\n'
            'prompt = "audit only"\n',
            encoding="utf-8",
        )
        with mock.patch.object(Path, "home", return_value=fake_home):
            payload, _ = ops.global_routing_audit(
                self.root,
                argparse.Namespace(
                    automations_root=str(fake_home / ".codex/automations"),
                    live_snapshot=str(live_snapshot),
                    shadow=False,
                ),
            )
        self.assertEqual(payload["counts"]["quarantined_pending_owner_approval"], 1)
        self.assertIn("live_target_thread_id_mismatch", payload["results"][0]["reasons"])
        self.assertFalse(payload["automatic_pause_performed"])
        self.assertFalse(payload["prompt_or_chat_body_stored"])
        self.assertTrue((governance / "latest-audit.json").exists())

    def test_department_status_checks_registered_project_identity(self) -> None:
        ready, _ = ops.department_status(self.root)
        self.assertFalse(any("项目 ID" in item or "cwd" in item for item in ready["errors"]))
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["departments"][0]["chat_binding"]["project_id"] = "external-project"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        blocked, _ = ops.department_status(self.root)
        self.assertEqual(blocked["status"], "department_setup_blocked")
        self.assertTrue(any("项目 ID" in item for item in blocked["errors"]))

    def test_department_status_blocks_explicitly_unhealthy_visible_window(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["departments"][2]["chat_binding"]["reply_health"] = "unhealthy_three_consecutive_empty_completed_turns"
        registry["departments"][2]["chat_binding"]["dispatch_eligible"] = False
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        blocked, _ = ops.department_status(self.root)

        self.assertEqual(blocked["status"], "department_setup_blocked")
        self.assertEqual(blocked["unhealthy_chat_count"], 1)
        self.assertEqual(blocked["replacement_recovery"][0]["department"], "qa")
        self.assertEqual(
            blocked["replacement_recovery"][0]["status"],
            "blocked_replacement_requires_app_capability",
        )
        self.assertFalse(blocked["replacement_recovery"][0]["auto_bind_allowed"])

    def test_routing_precheck_rejects_unhealthy_window_even_if_dispatch_flag_is_true(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["departments"][1]["chat_binding"]["reply_health"] = "unhealthy_no_visible_reply"
        registry["departments"][1]["chat_binding"]["dispatch_eligible"] = True
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        decision = self.routing_decision("content-organic-website")

        self.assertEqual(decision["status"], "deny")
        self.assertIn("target_thread_unhealthy_or_dispatch_ineligible", decision["reason"])

        binding = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        quarantine, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="pause-unhealthy-content-automation",
            action_class="automation_update",
            scope="automation_quarantine:test-content-daily",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="content-organic-website",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256="f" * 64,
            target_automation_status="PAUSED",
        )
        self.assertEqual(quarantine["status"], "allow")
        self.assertTrue(quarantine["routing_quarantine_mode"])
        self.assertEqual(quarantine["target_automation_status"], "PAUSED")

        unsafe_quarantine, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="mutate-unhealthy-content-automation",
            action_class="automation_update",
            scope="automation_quarantine:test-content-daily",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="content-organic-website",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            payload_sha256="e" * 64,
            target_automation_status="ACTIVE",
        )
        self.assertEqual(unsafe_quarantine["status"], "deny")
        self.assertIn("automation_quarantine_requires_paused_status", unsafe_quarantine["reason"])

    def test_delegation_requires_benefit_healthy_parent_and_no_parallel_veto(self) -> None:
        before_ack = self.delegation_decision("audit titles before ack")
        self.assertEqual(before_ack["status"], "deny")
        self.assertIn("fixed_department_chat_ack_required", before_ack["reason"])
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        allowed = self.delegation_decision("audit titles")
        self.assertEqual(allowed["status"], "allow")
        self.assertFalse(allowed["workflow_receipts_satisfied"])

        denied = self.delegation_decision(
            "audit and publish",
            interdependent_work=True,
            overlapping_write_scope=True,
            external_side_effect=True,
        )
        self.assertEqual(denied["status"], "deny")
        self.assertIn("interdependent_work_must_run_sequentially", denied["reason"])
        self.assertIn("overlapping_write_scope_must_not_run_in_parallel", denied["reason"])
        self.assertIn("external_side_effect_must_not_be_delegated", denied["reason"])

    def test_delegation_ledger_enforces_capacity_and_does_not_advance_workflow(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        first_scope = "audit titles set one"
        second_scope = "audit titles set two"
        first = self.delegation_decision(first_scope)
        second = self.delegation_decision(second_scope)
        first_start = self.start_delegation("title-audit-1", first_scope, first)
        second_start = self.start_delegation("title-audit-2", second_scope, second)
        self.assertEqual(first_start["status"], "started")
        self.assertEqual(second_start["status"], "started")

        at_capacity = self.delegation_decision("audit titles set three")
        self.assertEqual(at_capacity["status"], "deny")
        self.assertIn("department_concurrency_capacity_exceeded", at_capacity["reason"])

        evidence = self.root / "reports/title-audit-1.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("internal evidence\n", encoding="utf-8")
        completed, _ = workflow.record_delegation(
            self.root,
            argparse.Namespace(
                task_id=self.task_id,
                delegation_id="title-audit-1",
                department="content-organic-website",
                status="completed",
                idempotency_key="title-audit-1-complete",
                decision_id="",
                scope="",
                attempt=1,
                stop_reason="completed",
                evidence="reports/title-audit-1.md",
            ),
        )
        self.assertEqual(completed["status"], "completed")
        rows, invalid = workflow._validate_delegation_chain(self.root, self.task_id)
        self.assertEqual(invalid, [])
        self.assertEqual(len(rows), 3)
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "acknowledged")

    def test_delegation_reconcile_marks_timeout_with_stop_reason(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        scope = "bounded timeout check"
        decision = self.delegation_decision(scope, timeout_seconds=1)
        started = self.start_delegation("timeout-worker-1", scope, decision)
        future = dt.datetime.fromisoformat(str(started["deadline_at"])) + dt.timedelta(seconds=1)

        status, _ = workflow.reconcile_delegations(self.root, self.task_id, now=future)

        self.assertEqual(status["active_count"], 0)
        self.assertEqual(status["terminal_count"], 1)
        self.assertEqual(status["terminal"][0]["status"], "timed_out")
        self.assertEqual(status["terminal"][0]["stop_reason"], "timeout")

    def test_delegation_retry_limit_and_idempotency_are_enforced(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        scope = "bounded retry check"
        first = self.delegation_decision(scope)
        started = self.start_delegation("retry-worker-1", scope, first)
        duplicate = self.start_delegation("retry-worker-1", scope, first)
        self.assertEqual(started["event_hash"], duplicate["event_hash"])
        self.assertEqual(duplicate["result"], "duplicate_ignored")
        workflow.record_delegation(
            self.root,
            argparse.Namespace(
                task_id=self.task_id,
                delegation_id="retry-worker-1",
                department="content-organic-website",
                status="failed",
                idempotency_key="retry-worker-1-failed-1",
                decision_id="",
                scope="",
                attempt=1,
                stop_reason="task_failed",
                evidence="",
            ),
        )
        second = self.delegation_decision(scope)
        workflow.record_delegation(
            self.root,
            argparse.Namespace(
                task_id=self.task_id,
                delegation_id="retry-worker-1",
                department="content-organic-website",
                status="started",
                idempotency_key="retry-worker-1-start-2",
                decision_id=str(second["decision_id"]),
                scope=scope,
                attempt=2,
                stop_reason="",
                evidence="",
            ),
        )
        workflow.record_delegation(
            self.root,
            argparse.Namespace(
                task_id=self.task_id,
                delegation_id="retry-worker-1",
                department="content-organic-website",
                status="failed",
                idempotency_key="retry-worker-1-failed-2",
                decision_id="",
                scope="",
                attempt=2,
                stop_reason="no_progress",
                evidence="",
            ),
        )
        third = self.delegation_decision(scope)
        with self.assertRaisesRegex(workflow.WorkflowError, "重试次数超过上限"):
            workflow.record_delegation(
                self.root,
                argparse.Namespace(
                    task_id=self.task_id,
                    delegation_id="retry-worker-1",
                    department="content-organic-website",
                    status="started",
                    idempotency_key="retry-worker-1-start-3",
                    decision_id=str(third["decision_id"]),
                    scope=scope,
                    attempt=3,
                    stop_reason="",
                    evidence="",
                ),
            )

    def test_current_vendure_incident_is_blocked_as_cross_project(self) -> None:
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="incident-shadow-replay",
            action_class="thread_message",
            scope="vendure-release-monitor",
            source_project_id="flashcast-test-project",
            target_project_id="<LOCAL_NATIVE_ID>",
            target_department="vendure",
            target_thread_id="<LOCAL_NATIVE_ID>",
            target_thread_title="恢复后台用户工具2FA",
            target_cwd="<USER_HOME>/Desktop/源码文件夹/vendure开源",
            payload_sha256="b" * 64,
        )
        self.assertEqual(decision["status"], "deny")
        self.assertEqual(decision["routing_status"], "blocked_cross_project")
        self.assertTrue(any("target_project_id_mismatch" in item for item in decision["reason"]))

    def test_matching_title_cannot_override_external_project_identity(self) -> None:
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="title-is-not-identity",
            action_class="thread_message",
            scope="department:content-organic-website",
            source_project_id="flashcast-test-project",
            target_project_id="external-shopping-project",
            target_department="content-organic-website",
            target_thread_id="fixed-content-organic-website",
            target_thread_title="content-organic-website",
            target_cwd=str(self.root),
            payload_sha256="c" * 64,
        )
        self.assertEqual(decision["status"], "deny")
        self.assertEqual(decision["routing_status"], "blocked_cross_project")

    def test_automation_update_requires_exact_registered_target(self) -> None:
        binding = workflow.department_registry(self.root)["qa"]["chat_binding"]
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="update-qa-automation",
            action_class="automation_update",
            scope="automation:qa-daily",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="qa",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256="d" * 64,
        )
        self.assertEqual(decision["status"], "allow")

    def test_cross_project_access_action_is_always_denied(self) -> None:
        binding = workflow.department_registry(self.root)["qa"]["chat_binding"]
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="cross-project-probe",
            action_class="cross_project_access",
            scope="external-project",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="qa",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            payload_sha256="e" * 64,
        )
        self.assertEqual(decision["status"], "deny")
        self.assertIn("cross_project_access_hard_deny", decision["reason"])

    def test_dispatch_receipt_requires_allowed_routing_decision(self) -> None:
        with self.assertRaisesRegex(ops.OpsError, "路由预检"):
            ops.receipt_record(
                self.root,
                argparse.Namespace(
                    task_id=self.task_id,
                    receipt_type="dispatch_sent",
                    department="content-organic-website",
                    chat_task_id="fixed-content-organic-website",
                    ack_nonempty=False,
                    evidence="",
                    idempotency_key="missing-routing-decision",
                    verdict="",
                    action_id="",
                    action_class="",
                    scope="",
                    approval_id="",
                    policy_decision_id="",
                ),
            )

    def test_receipt_chain_and_idempotency(self) -> None:
        first = self.receipt("dispatch_sent", "content-organic-website", "d1")
        duplicate = self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.assertEqual(first["result"], "recorded")
        self.assertEqual(duplicate["result"], "duplicate_ignored")
        second = self.receipt("chat_ack", "content-organic-website", "a1")
        self.assertEqual(second["previous_hash"], first["receipt_hash"])
        receipts, invalid = workflow._validate_receipt_chain(self.root, self.task_id)
        self.assertEqual(len(receipts), 2)
        self.assertEqual(invalid, [])

    def test_qa_verdict_requires_its_own_visible_reply_and_outbox(self) -> None:
        self.advance_to_qa()
        report = self.root / "reports/qa-prerequisites.md"
        report.write_text("QA candidate\n", encoding="utf-8")
        verdict = dict(verdict="blocked", evidence="reports/qa-prerequisites.md")
        with self.assertRaisesRegex(ops.OpsError, "质检部 dispatch_sent"):
            self.receipt("qa_verdict", "qa", "qa-prereq-verdict", **verdict)
        self.receipt("dispatch_sent", "qa", "qa-delivery-dispatch")
        with self.assertRaisesRegex(ops.OpsError, "非空 chat_ack"):
            self.receipt("qa_verdict", "qa", "qa-prereq-verdict", **verdict)
        self.receipt("chat_ack", "qa", "qa-delivery-ack")
        with self.assertRaisesRegex(ops.OpsError, "outbox_received"):
            self.receipt("qa_verdict", "qa", "qa-prereq-verdict", **verdict)
        self.prepare_qa()
        recorded = self.receipt("qa_verdict", "qa", "qa-prereq-verdict", **verdict)
        self.assertEqual(recorded["result"], "recorded")
        self.assertEqual(recorded["workflow_state"], "qa_blocked")

        self.receipt("dispatch_sent", "qa", "qa-rework-dispatch")
        with self.assertRaisesRegex(ops.OpsError, "本次 QA 派工后"):
            self.receipt("qa_verdict", "qa", "qa-rework-verdict", **verdict)
        self.receipt("chat_ack", "qa", "qa-rework-ack")
        with self.assertRaisesRegex(ops.OpsError, "本次 QA 回复后"):
            self.receipt("qa_verdict", "qa", "qa-rework-verdict", **verdict)
        self.receipt(
            "outbox_received", "qa", "qa-rework-outbox",
            evidence="logs/department-outbox/workflow-test-001-qa.json",
        )
        self.assertEqual(
            self.receipt("qa_verdict", "qa", "qa-rework-verdict", **verdict)["result"],
            "recorded",
        )

    def test_outbox_missing_fields_learning_or_path_is_blocked(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        with self.assertRaisesRegex(ops.OpsError, "不存在"):
            self.receipt(
                "outbox_received",
                "content-organic-website",
                "missing-path",
                evidence="logs/department-outbox/missing.json",
            )
        outbox = self.write_outbox()
        value = json.loads(outbox.read_text(encoding="utf-8"))
        del value["learning"]
        del value["risks"]
        outbox.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ops.OpsError, "缺少 V2 必填字段"):
            self.receipt(
                "outbox_received",
                "content-organic-website",
                "bad-fields",
                evidence=workflow.rel_path(self.root, outbox),
            )

    def test_content_daily_completed_requires_real_growth_delivery(self) -> None:
        outbox = self.root / "logs/department-outbox/content-daily.json"
        outbox.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "task_id": "fc-20260906-website-growth-daily",
            "department": "content-organic-website",
            "status": "completed",
            "conclusion": "health check only",
            "evidence": {},
            "risks": [],
            "next_actions": [],
            "handoff": {"receiver": "qa"},
            "approval_required": False,
            "learning": {"status": "no_new_learning"},
        }
        outbox.write_text(json.dumps(value), encoding="utf-8")
        evidence = [workflow.file_digest(self.root, workflow.rel_path(self.root, outbox))]
        with self.assertRaisesRegex(workflow.WorkflowError, "promotion_gap_matrix"):
            workflow.validate_outbox(
                self.root,
                evidence,
                "content-organic-website",
                "fc-20260906-website-growth-daily",
            )

    def test_content_daily_growth_delivery_requires_state_change_and_artifact(self) -> None:
        artifact = self.root / "drafts/seo/daily-brief.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# Daily growth brief\n", encoding="utf-8")
        artifact_rel = workflow.rel_path(self.root, artifact)
        matrix = {key: "checked" for key in workflow.PROMOTION_GAP_CATEGORIES}
        outbox = self.root / "logs/department-outbox/content-daily.json"
        outbox.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "task_id": "fc-20260906-website-growth-daily",
            "department": "content-organic-website",
            "status": "completed",
            "conclusion": "growth brief complete",
            "evidence": {"growth_artifact": artifact_rel},
            "promotion_gap_matrix": matrix,
            "growth_delivery": {
                "backlog_item_id": "ORG-003",
                "previous_status": "validated",
                "current_status": "validated",
                "artifact_type": "page_brief",
                "artifact_path": artifact_rel,
                "qa_handoff_status": "ready_for_qa",
            },
            "risks": [],
            "next_actions": ["qa"],
            "handoff": {"receiver": "qa"},
            "approval_required": False,
            "learning": {"status": "no_new_learning"},
        }
        outbox.write_text(json.dumps(value), encoding="utf-8")
        evidence = [workflow.file_digest(self.root, workflow.rel_path(self.root, outbox))]
        with self.assertRaisesRegex(workflow.WorkflowError, "状态必须真实推进"):
            workflow.validate_outbox(
                self.root,
                evidence,
                "content-organic-website",
                "fc-20260906-website-growth-daily",
            )
        value["growth_delivery"]["current_status"] = "ready_for_qa"
        outbox.write_text(json.dumps(value), encoding="utf-8")
        evidence = [workflow.file_digest(self.root, workflow.rel_path(self.root, outbox))]
        workflow.validate_outbox(
            self.root,
            evidence,
            "content-organic-website",
            "fc-20260906-website-growth-daily",
        )

    def test_same_idempotency_key_with_changed_evidence_is_blocked(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        self.receipt("chat_ack", "content-organic-website", "a1")
        outbox = self.write_outbox()
        relative = workflow.rel_path(self.root, outbox)
        self.receipt("outbox_received", "content-organic-website", "outbox-key", evidence=relative)
        value = json.loads(outbox.read_text(encoding="utf-8"))
        value["conclusion"] = "changed conclusion"
        outbox.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ops.OpsError, "幂等键"):
            self.receipt("outbox_received", "content-organic-website", "outbox-key", evidence=relative)

    def test_evidence_change_downgrades_to_blocked(self) -> None:
        outbox = self.advance_to_qa()
        outbox.write_text(outbox.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        payload, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(payload["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("evidence_changed" in item for item in payload["blockers"]))

    def test_evidence_replacement_rebaselines_only_the_changed_path(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        qa_evidence = self.root / "reports/qa-blocked.md"
        qa_evidence.write_text("blocked pending environment\n", encoding="utf-8")
        qa_receipt = self.receipt(
            "qa_verdict", "qa", "qa-blocked-v1", verdict="blocked", evidence="reports/qa-blocked.md"
        )
        qa_evidence.write_text("blocked pending verified environment\n", encoding="utf-8")
        blocked, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(blocked["current_state"], "blocked_evidence_invalid")

        replacement = self.receipt(
            "evidence_replacement",
            "qa",
            "qa-blocked-evidence-replacement-v1",
            evidence="reports/qa-blocked.md",
            supersedes_receipt_id=str(qa_receipt["receipt_id"]),
            replacement_reason="verified_manifest_correction",
        )
        self.assertEqual(replacement["workflow_state"], "qa_blocked")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "qa_blocked")
        self.assertEqual(status["blockers"], ["qa_verdict_blocked"])

        qa_evidence.write_text("changed again\n", encoding="utf-8")
        changed_again, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(changed_again["current_state"], "blocked_evidence_invalid")

    def test_evidence_replacement_supports_sequential_rework(self) -> None:
        outbox = self.advance_to_qa()
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        original = next(row for row in receipts if row["receipt_type"] == "outbox_received")

        first = json.loads(outbox.read_text(encoding="utf-8"))
        first["conclusion"] = "first QA rework"
        outbox.write_text(json.dumps(first), encoding="utf-8")
        replacement_one = self.receipt(
            "evidence_replacement",
            "content-organic-website",
            "outbox-replacement-v1",
            evidence=workflow.rel_path(self.root, outbox),
            supersedes_receipt_id=str(original["receipt_id"]),
            replacement_reason="first_qa_rework",
        )
        self.assertEqual(replacement_one["workflow_state"], "evidence_received")

        second = json.loads(outbox.read_text(encoding="utf-8"))
        second["conclusion"] = "second QA rework"
        outbox.write_text(json.dumps(second), encoding="utf-8")
        blocked, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(blocked["current_state"], "blocked_evidence_invalid")

        replacement_two = self.receipt(
            "evidence_replacement",
            "content-organic-website",
            "outbox-replacement-v2",
            evidence=workflow.rel_path(self.root, outbox),
            supersedes_receipt_id=str(replacement_one["receipt_id"]),
            replacement_reason="second_qa_rework",
        )
        self.assertEqual(replacement_two["workflow_state"], "evidence_received")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "evidence_received")
        self.assertEqual(status["blockers"], [])

    def test_evidence_replacement_rejects_unrelated_evidence(self) -> None:
        outbox = self.advance_to_qa()
        receipts = workflow.read_jsonl(self.root / workflow.RECEIPTS_DIR / f"{self.task_id}.jsonl")
        target = next(row for row in receipts if row["receipt_type"] == "outbox_received")
        outbox.write_text(outbox.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        unrelated = self.root / "reports/unrelated.md"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_text("not the changed evidence\n", encoding="utf-8")
        with self.assertRaisesRegex(ops.OpsError, "精确覆盖"):
            self.receipt(
                "evidence_replacement",
                "content-organic-website",
                "unrelated-replacement",
                evidence="reports/unrelated.md",
                supersedes_receipt_id=str(target["receipt_id"]),
                replacement_reason="verified_manifest_correction",
            )

    def test_event_order_regression_is_blocked(self) -> None:
        with workflow.workflow_lock(self.root):
            workflow.append_workflow_event(self.root, self.task_id, "dispatched", {"test": True})
            workflow.append_workflow_event(self.root, self.task_id, "dispatch_ready", {"test": True})
        payload, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(payload["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("event_order:regression" in item for item in payload["blockers"]))

    def test_cache_execution_stage_ack_requires_prior_exact_qa_approval_and_route(self) -> None:
        stamp = "2026-09-26T07:33:38+00:00"
        scope = "flashcast.com.my:cache:exact-frozen-set"
        for fault in ("", "qa_blocked", "wrong_approval", "wrong_scope", "wrong_route"):
            with self.subTest(fault=fault):
                task_id = "cache-stage-" + (fault or "valid")
                qa_department = {"department": "qa", "chat_task_id": "fixed-qa", "execution_wave": 1, "depends_on": []}
                with mock.patch.object(workflow, "utc_timestamp", return_value=stamp):
                    snapshot, _ = workflow.initialize_workflow(
                        self.root, task_id=task_id, request="QA-only exact cache candidate",
                        plan_status="ready_to_send", departments=[qa_department], owner_approval_required=True)
                    for state in ("dispatched", "acknowledged", "evidence_received", "qa_passed", "waiting_owner_approval"):
                        workflow.append_workflow_event(self.root, task_id, state, {"reconciled": True})
                    workflow.append_workflow_event(self.root, task_id, "waiting_owner_approval", {
                        "plan_refresh": True, "request_hash": snapshot["request_hash"],
                        "refresh_reason": "qa_only_review_completed_add_exact_authorized_execution_stage",
                        "routing_policy_decision_id": f"routing-{task_id}",
                        "departments": [qa_department, {"department": "content-organic-website",
                            "chat_task_id": "fixed-content", "execution_wave": 2, "depends_on": ["qa"]}]})
                    workflow.append_workflow_event(self.root, task_id, "acknowledged", {"reconciled": True})
                    workflow.append_workflow_event(self.root, task_id, "evidence_received", {"reconciled": True})
                    workflow.append_workflow_event(self.root, task_id, "qa_passed", {
                        "reconciled": True, "qa_receipt_id": f"qa-{task_id}", "qa_receipt_hash": "exact-qa-hash"})
                qa = {"task_id": task_id, "receipt_type": "qa_verdict", "department": "qa",
                      "receipt_id": f"qa-{task_id}", "receipt_hash": "exact-qa-hash",
                      "action_class": "site_cache_candidate", "action_id": "cache-action", "scope": scope,
                      "verdict": "blocked" if fault == "qa_blocked" else "pass", "created_at": stamp}
                approval = {"task_id": task_id, "approval_id": "wrong" if fault == "wrong_approval" else "exact-approval",
                            "status": "consumed", "action_id": "cache-action", "action_class": "site_cache_invalidation", "scope": scope}
                routing = {"decision_id": f"routing-{task_id}", "status": "allow", "routing_status": "routing_allowed",
                           "task_id": task_id, "action_class": "thread_message", "target_department": "content-organic-website",
                           "target_thread_id": "wrong" if fault == "wrong_route" else "fixed-content", "checked_at": stamp}
                execution_policy = {"decision_id": "execute", "status": "allow", "task_id": task_id,
                                    "department": "content-organic-website", "action_id": "cache-action",
                                    "action_class": "site_cache_invalidation", "scope": "other" if fault == "wrong_scope" else scope,
                                    "approval_id": "exact-approval", "checked_at": stamp}
                original_reader = workflow.read_jsonl
                def reader(path):
                    if path == workflow.receipts_path(self.root, task_id):
                        return [qa]
                    if path == self.root / workflow.APPROVAL_LEDGER:
                        return [approval]
                    if path == self.root / "logs/policy-decisions.jsonl":
                        return [routing, execution_policy]
                    return original_reader(path)
                with mock.patch.object(workflow, "read_jsonl", side_effect=reader):
                    invalid = workflow.validate_workflow_events(self.root, task_id)
                if fault:
                    self.assertIn("event_order:regression:acknowledged", invalid)
                else:
                    self.assertEqual(invalid, [])

    def test_historical_qa_postcheck_recovery_requires_exact_current_receipt(self) -> None:
        departments = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))["departments"]

        def build(task_id: str, correction_scope: str, include_qa_replacement: bool) -> list[str]:
            old_at = "2026-09-20T15:24:46+00:00"
            blocked_at = "2026-09-21T05:50:57+00:00"
            recovered_at = "2026-09-25T14:43:44+00:00"
            scope = f"project:flashcast:seo:{task_id}:r0-plan-closeout"
            with mock.patch.object(workflow, "utc_timestamp", return_value=old_at):
                workflow.initialize_workflow(
                    self.root, task_id=task_id, request="Legacy R0 plan",
                    plan_status="ready_to_send", departments=departments,
                    owner_approval_required=True,
                )
                for state in (
                    "dispatched", "acknowledged", "evidence_received", "qa_passed",
                    "waiting_owner_approval", "owner_approved", "execution_completed",
                    "verified", "closed",
                ):
                    workflow.append_workflow_event(self.root, task_id, state, {"reconciled": True})
            with mock.patch.object(workflow, "utc_timestamp", return_value=blocked_at):
                workflow.append_workflow_event(
                    self.root, task_id, "blocked_evidence_invalid", {"reconciled": True}
                )
            rows = [
                {
                    "receipt_id": f"{task_id}-execution", "receipt_type": "execution_result",
                    "department": "content-organic-website", "created_at": old_at,
                    "action_id": "accept-r0-plan", "action_class": "internal_artifact_write",
                    "scope": scope, "verdict": "", "evidence": [{"path": "reports/plan.md", "sha256": "old"}],
                },
                {
                    "receipt_id": f"{task_id}-old-qa", "receipt_type": "postcheck",
                    "department": "qa", "created_at": old_at, "verdict": "",
                    "action_id": "", "action_class": "", "scope": "",
                    "evidence": [{"path": "reports/old-qa.md", "sha256": "old"}],
                },
                {
                    "receipt_type": "evidence_replacement", "created_at": recovered_at,
                    "supersedes_receipt_id": f"{task_id}-execution",
                },
            ]
            if include_qa_replacement:
                rows.append({
                    "receipt_type": "evidence_replacement", "created_at": recovered_at,
                    "supersedes_receipt_id": f"{task_id}-old-qa",
                })
            rows.append({
                "receipt_id": f"{task_id}-current-qa", "receipt_type": "postcheck",
                "department": "qa", "created_at": recovered_at, "verdict": "pass",
                "action_id": "accept-r0-plan", "action_class": "internal_artifact_write",
                "scope": correction_scope, "evidence": [{"path": "reports/current-qa.md", "sha256": "new"}],
            })
            for row in rows:
                workflow.append_jsonl_locked(workflow.receipts_path(self.root, task_id), row)
            with mock.patch.object(workflow, "utc_timestamp", return_value=recovered_at):
                workflow.append_workflow_event(self.root, task_id, "verified", {"reconciled": True})
                workflow.append_workflow_event(self.root, task_id, "closed", {"reconciled": True})
            return workflow.validate_workflow_events(self.root, task_id)

        valid_id = "historical-qa-postcheck-valid"
        self.assertEqual(build(
            valid_id, f"project:flashcast:seo:{valid_id}:r0-plan-closeout", True
        ), [])
        wrong_id = "historical-qa-postcheck-wrong-scope"
        self.assertTrue(any(
            "event_order:regression" in item
            for item in build(wrong_id, "project:flashcast:seo:other:r0-plan-closeout", True)
        ))
        missing_id = "historical-qa-postcheck-missing-replacement"
        self.assertTrue(any(
            "event_order:regression" in item
            for item in build(
                missing_id, f"project:flashcast:seo:{missing_id}:r0-plan-closeout", False
            )
        ))

    def test_closed_evidence_replacement_resumes_without_replaying_dispatch(self) -> None:
        departments = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))["departments"]
        self.task_id = "internal-recovery-test"
        workflow.initialize_workflow(
            self.root, task_id=self.task_id, request="Internal review",
            plan_status="ready_to_send", departments=departments,
            owner_approval_required=False,
        )
        path = workflow.snapshot_path(self.root, self.task_id)
        self.advance_to_qa()
        evidence = self.qa_pass()
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        qa = next(row for row in receipts if row["receipt_type"] == "qa_verdict")
        evidence.write_text(evidence.read_text() + "Audit reference added.\n", encoding="utf-8")
        blocked, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(blocked["current_state"], "blocked_evidence_invalid")
        original_events = (self.root / workflow.WORKFLOW_EVENTS).read_bytes()
        result = self.receipt(
            "evidence_replacement", "qa", "closed-evidence-fix",
            evidence="reports/qa.md", supersedes_receipt_id=qa["receipt_id"],
            replacement_reason="audit_reference_added",
        )
        self.assertEqual(result["workflow_state"], "closed")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "closed")
        self.assertEqual(status["blockers"], [])
        self.assertTrue((self.root / workflow.WORKFLOW_EVENTS).read_bytes().startswith(original_events))
        events = workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)
        self.assertEqual(sum(row["state"] == "planned" and row["task_id"] == self.task_id for row in events), 1)
        self.assertTrue(events[-1]["details"]["evidence_revalidated"])
        count = len(events)
        path.unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "closed")
        self.assertEqual(len(workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)), count)

    def test_evidence_archive_preserves_mutable_ledger_version(self) -> None:
        self.test_closed_evidence_replacement_resumes_without_replaying_dispatch()
        evidence = self.root / "reports/qa.md"
        archive = self.root / "backups/internal-recovery-test/payload/reports/qa.md"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(evidence.read_bytes())
        replacement = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))[-1]
        recorded = self.receipt(
            "evidence_archive", "qa", "qa-evidence-archive-v1",
            scope="reports/qa.md",
            evidence=workflow.rel_path(self.root, archive),
            supersedes_receipt_id=replacement["receipt_id"],
            replacement_reason="rolling_ledger_version_preserved",
        )
        self.assertEqual(recorded["workflow_state"], "closed")
        evidence.write_text(evidence.read_text() + "New current version.\n", encoding="utf-8")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "closed")
        self.assertEqual(status["blockers"], [])
        archive.write_text(archive.read_text() + "Tampered archive.\n", encoding="utf-8")
        invalid, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(invalid["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("evidence_changed" in item for item in invalid["blockers"]))

    def test_evidence_archive_rejects_wrong_bytes_or_owner(self) -> None:
        self.test_closed_evidence_replacement_resumes_without_replaying_dispatch()
        replacement = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))[-1]
        archive = self.root / "backups/internal-recovery-test/payload/reports/qa.md"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text("Wrong historical version\n", encoding="utf-8")
        kwargs = {
            "scope": "reports/qa.md",
            "evidence": workflow.rel_path(self.root, archive),
            "supersedes_receipt_id": replacement["receipt_id"],
            "replacement_reason": "rolling_ledger_version_preserved",
        }
        with self.assertRaisesRegex(ops.OpsError, "SHA-256"):
            self.receipt("evidence_archive", "qa", "wrong-archive", **kwargs)
        archive.write_bytes((self.root / "reports/qa.md").read_bytes())
        with self.assertRaisesRegex(ops.OpsError, "所属部门"):
            self.receipt("evidence_archive", "content-organic-website", "wrong-owner", **kwargs)

    def test_legacy_evidence_replay_requires_exact_batch_and_replacement_receipt(self) -> None:
        self.test_closed_evidence_replacement_resumes_without_replaying_dispatch()
        receipt_path = workflow.receipts_path(self.root, self.task_id)
        replacement = workflow.read_jsonl(receipt_path)[-1]
        stamp = replacement["created_at"]
        with mock.patch.object(workflow, "utc_timestamp", return_value=stamp):
            with workflow.workflow_lock(self.root):
                workflow.append_workflow_event(self.root, self.task_id, "blocked_evidence_invalid", {"reconciled": True})
                for state in workflow._state_sequence("blocked_evidence_invalid", "closed", False, False):
                    workflow.append_workflow_event(self.root, self.task_id, state, {"reconciled": True})
        original = (self.root / workflow.WORKFLOW_EVENTS).read_bytes()
        payload, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(payload["current_state"], "closed")
        self.assertEqual(payload["blockers"], [])
        self.assertTrue((self.root / workflow.WORKFLOW_EVENTS).read_bytes().startswith(original))
        # A visually identical restart without a same-batch replacement is not
        # the legacy recovery bug and must remain an illegal regression.
        with mock.patch.object(workflow, "utc_timestamp", return_value="2099-01-01T00:00:00+00:00"):
            with workflow.workflow_lock(self.root):
                workflow.append_workflow_event(self.root, self.task_id, "blocked_evidence_invalid", {"reconciled": True})
                for state in workflow._state_sequence("blocked_evidence_invalid", "closed", False, False):
                    workflow.append_workflow_event(self.root, self.task_id, state, {"reconciled": True})
        invalid, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(invalid["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("event_order:regression" in item for item in invalid["blockers"]))

    def test_qa_pass_only_enters_owner_review(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "waiting_owner_approval")
        self.assertTrue(status["owner_approval_required"])
        self.assertTrue(status["owner_approval_pending"])
        states = [row["state"] for row in workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)]
        self.assertNotIn("owner_approved", states)
        self.assertNotIn("execution_completed", states)

    def test_recovered_closed_workflow_still_blocks_new_evidence_changes(self) -> None:
        self.test_closed_evidence_replacement_resumes_without_replaying_dispatch()
        evidence = self.root / "reports/qa.md"
        evidence.write_text(evidence.read_text() + "Unrecorded change.\n", encoding="utf-8")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("evidence_changed" in item for item in status["blockers"]))

    def test_malformed_legacy_replay_is_not_accepted(self) -> None:
        self.test_closed_evidence_replacement_resumes_without_replaying_dispatch()
        stamp = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))[-1]["created_at"]
        with mock.patch.object(workflow, "utc_timestamp", return_value=stamp):
            with workflow.workflow_lock(self.root):
                for state in ("blocked_evidence_invalid", "planned", "dispatched", "closed"):
                    workflow.append_workflow_event(self.root, self.task_id, state, {"reconciled": True})
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("event_order:regression" in item for item in status["blockers"]))

    def test_qa_blocked_can_resume_from_evidence_after_new_pass(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        blocked_evidence = self.root / "reports/qa-blocked.md"
        blocked_evidence.parent.mkdir(parents=True, exist_ok=True)
        blocked_evidence.write_text("QA BLOCKED\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "qa-blocked-1", verdict="blocked", evidence="reports/qa-blocked.md")
        blocked, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(blocked["current_state"], "qa_blocked")
        self.assertTrue(blocked["owner_approval_required"])
        self.assertFalse(blocked["owner_approval_pending"])
        pass_evidence = self.root / "reports/qa-pass-after-fix.md"
        pass_evidence.write_text("QA PASS\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "qa-pass-2", verdict="pass", evidence="reports/qa-pass-after-fix.md")
        resumed, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(resumed["current_state"], "waiting_owner_approval")
        self.assertFalse(any("event_order" in item for item in resumed["blockers"]))

    def test_qa_rework_after_owner_approval_preserves_event_order(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        workflow.record_approval(
            self.root, task_id=self.task_id, action_id="publish-page-1",
            action_class="site_publish", scope="/zh/service/kitchen",
            source_message_ref="owner-msg-1",
        )
        self.assertEqual(workflow.workflow_status(self.root, self.task_id)[0]["current_state"], "owner_approved")
        blocked = self.root / "reports/qa-rework-blocked.md"
        blocked.write_text("QA blocked revised release path\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "qa-rework-blocked", verdict="blocked",
                     evidence="reports/qa-rework-blocked.md")
        self.assertEqual(workflow.workflow_status(self.root, self.task_id)[0]["current_state"], "qa_blocked")
        passed = self.root / "reports/qa-rework-passed.md"
        passed.write_text("QA passed repaired release path\n", encoding="utf-8")
        self.receipt("qa_verdict", "qa", "qa-rework-passed", verdict="pass",
                     evidence="reports/qa-rework-passed.md")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "owner_approved")
        self.assertEqual(status["blockers"], [])
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "owner_approved")
        self.assertEqual(rebuilt["blockers"], [])

    def test_unbacked_qa_block_does_not_authorize_event_regression(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        workflow.record_approval(
            self.root, task_id=self.task_id, action_id="publish-page-1",
            action_class="site_publish", scope="/zh/service/kitchen",
            source_message_ref="owner-msg-1",
        )
        with workflow.workflow_lock(self.root):
            workflow.append_workflow_event(self.root, self.task_id, "qa_blocked", {"reconciled": True})
            workflow.append_workflow_event(self.root, self.task_id, "qa_passed", {"reconciled": True})
        status, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(status["current_state"], "blocked_evidence_invalid")
        self.assertTrue(any("event_order:regression" in item for item in status["blockers"]))

    def test_legacy_qa_block_event_recovers_after_eight_second_delay(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        workflow.record_approval(
            self.root, task_id=self.task_id, action_id="publish-page-1",
            action_class="site_publish", scope="/zh/service/kitchen",
            source_message_ref="owner-msg-1",
        )
        blocked = self.root / "reports/delayed-qa-block.md"
        blocked.write_text("QA blocked\n", encoding="utf-8")
        passed = self.root / "reports/delayed-qa-pass.md"
        passed.write_text("QA passed\n", encoding="utf-8")
        start = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        clock = {"value": start.isoformat()}
        original_append = workflow.append_workflow_event

        def delayed_legacy_event(root: Path, task_id: str, state: str, details: dict | None = None) -> dict:
            if state == "qa_blocked":
                clock["value"] = (start + dt.timedelta(seconds=8)).isoformat()
                details = {"reconciled": True}  # historical event without receipt ID
            return original_append(root, task_id, state, details)

        with mock.patch.object(workflow, "utc_timestamp", side_effect=lambda: clock["value"]), \
             mock.patch.object(workflow, "append_workflow_event", side_effect=delayed_legacy_event):
            self.receipt("qa_verdict", "qa", "delayed-block", verdict="blocked",
                         evidence="reports/delayed-qa-block.md")
            clock["value"] = (start + dt.timedelta(seconds=16)).isoformat()
            self.receipt("qa_verdict", "qa", "delayed-pass", verdict="pass",
                         evidence="reports/delayed-qa-pass.md")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "owner_approved")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_internal_read_only_qa_pass_closes_without_approval_states(self) -> None:
        snapshot_path = workflow.snapshot_path(self.root, self.task_id)
        snapshot = workflow.read_json(snapshot_path)
        snapshot["owner_approval_required"] = False
        workflow.atomic_write_json(snapshot_path, snapshot)
        self.advance_to_qa()
        self.qa_pass()
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "closed")
        self.assertFalse(status["owner_approval_required"])
        self.assertFalse(status["owner_approval_pending"])
        states = [row["state"] for row in workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)]
        self.assertIn("verified", states)
        self.assertNotIn("waiting_owner_approval", states)
        self.assertNotIn("owner_approved", states)

    def test_closed_shared_task_cms_policy_requires_its_exact_current_qa(self) -> None:
        snapshot = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        snapshot["current_state"] = "closed"
        workflow.atomic_write_json(workflow.snapshot_path(self.root, self.task_id), snapshot)
        path = self.root / "logs/department-outbox/exact-row.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {"task_id": self.task_id, "department": "qa", "action_id": "row-action",
                  "action_class": "cms_content_candidate", "scope": "flashcast.com.my:row:content_en"}
        path.write_text(json.dumps({**fields, "risk_level": "R1"}))
        qa = {**fields, "receipt_type": "qa_verdict", "verdict": "pass",
              "chat_task_id": "fixed-qa", "evidence": [workflow.file_digest(self.root, "logs/department-outbox/exact-row.json")]}
        sibling = {**qa, "action_id": "completed-home-action", "action_class": "site_code_candidate"}
        policy_path = self.root / "data/action-policy.json"
        policy = workflow.read_json(policy_path)
        policy["standing_authorizations"] = [{"authorization_id": "test-standing", "status": "active",
             "source_message_ref": "test-owner", "department": "content-organic-website",
             "action_classes": ["cms_write"], "allowed_scope_prefixes": ["flashcast.com.my:"]}]
        policy_path.write_text(json.dumps(policy))
        def check(receipts: list[dict], invalid: list[str] | None = None, **overrides: str) -> dict:
            arguments = dict(task_id=self.task_id, department="content-organic-website",
                             action_id=fields["action_id"], action_class="cms_write", scope=fields["scope"])
            arguments.update(overrides)
            with mock.patch.object(workflow, "read_jsonl", return_value=receipts), \
                 mock.patch.object(workflow, "_validate_receipt_chain", return_value=(receipts, invalid or [])):
                return workflow.policy_check(self.root, **arguments)[0]
        allowed = check([qa, sibling])
        self.assertEqual(allowed["status"], "allow")
        self.assertEqual(allowed["qa_risk_level"], "R1")
        self.assertEqual(check([sibling])["status"], "deny")
        self.assertEqual(check([qa, {**qa, "verdict": "blocked"}, sibling])["status"], "deny")
        self.assertEqual(check([qa, sibling], ["receipt_hash_mismatch"])["status"], "deny")
        self.assertEqual(check([qa, sibling], scope="flashcast.com.my:wrong-row:content_en")["status"], "deny")
        self.assertEqual(check([qa, sibling], action_class="site_publish")["status"], "deny")
        path.write_text(json.dumps({**fields, "risk_level": "R3"}))
        qa["evidence"] = [workflow.file_digest(self.root, "logs/department-outbox/exact-row.json")]
        self.assertEqual(check([qa, sibling])["status"], "deny")

    def test_release_candidate_reopens_internal_workflow_and_enforces_publication_route(self) -> None:
        snapshot_path = workflow.snapshot_path(self.root, self.task_id)
        snapshot = workflow.read_json(snapshot_path)
        snapshot["owner_approval_required"] = False
        workflow.atomic_write_json(snapshot_path, snapshot)
        self.advance_to_qa()
        self.qa_pass()
        closed, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(closed["current_state"], "closed")

        qa_evidence = self.root / "reports/qa-site-code-release.md"
        qa_evidence.write_text("QA PASS for site code release handoff\n", encoding="utf-8")
        self.receipt(
            "qa_verdict",
            "qa",
            "q-site-code-release",
            verdict="pass",
            evidence="reports/qa-site-code-release.md",
            action_class="site_code_rework_candidate",
            scope="flashcast.com.my:blog-link-runtime-fix",
        )
        reopened, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(reopened["current_state"], "qa_passed")
        self.assertEqual(reopened["next_legal_actions"], ["policy-check:standing_authorization"])
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["standing_authorizations"] = [
            {
                "authorization_id": "owner-standing-flashcast-site-publish-test",
                "status": "active",
                "source_message_ref": "owner-test-message",
                "department": "content-organic-website",
                "action_classes": ["site_publish", "cms_write"],
                "allowed_scope_prefixes": ["flashcast.com.my:"],
            }
        ]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")

        wrong_route, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-runtime-fix",
            action_class="cms_write",
            scope="flashcast.com.my:blog-link-runtime-fix:commit",
            consume_approval=True,
        )
        self.assertEqual(wrong_route["status"], "deny")
        self.assertIn("qa_release_route_mismatch:expected_site_publish", wrong_route["reason"])

        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-runtime-fix",
            action_class="site_publish",
            scope="flashcast.com.my:blog-link-runtime-fix:commit",
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "allow")
        self.assertEqual(decision["approval_basis"], "standing_authorization")

        execution = self.root / "reports/site-code-execution.md"
        execution.write_text("deployed\n", encoding="utf-8")
        executed = self.receipt(
            "execution_result",
            "content-organic-website",
            "site-code-execution",
            evidence="reports/site-code-execution.md",
            action_id="publish-runtime-fix",
            action_class="site_publish",
            scope="flashcast.com.my:blog-link-runtime-fix:commit",
            approval_id=str(decision["approval_id"]),
            policy_decision_id=str(decision["decision_id"]),
        )
        self.assertEqual(executed["workflow_state"], "execution_completed")

        postcheck = self.root / "reports/site-code-postcheck.md"
        postcheck.write_text("verified\n", encoding="utf-8")
        verified = self.receipt(
            "postcheck",
            "content-organic-website",
            "site-code-postcheck",
            evidence="reports/site-code-postcheck.md",
        )
        self.assertEqual(verified["workflow_state"], "closed")
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_completed_cms_action_does_not_close_next_qa_approved_action(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        qa_report = self.root / "reports/qa-multi-action.md"
        qa_report.write_text("Two independent CMS rows passed QA.\n", encoding="utf-8")
        kitchen_action = "publish-kitchen-cms-row"
        design_action = "publish-design-cms-row"
        kitchen_scope = "flashcast.com.my:services/kitchen-row"
        design_scope = "flashcast.com.my:services/design-row"
        for action, scope in ((kitchen_action, kitchen_scope), (design_action, design_scope)):
            self.receipt(
                "qa_verdict", "qa", f"qa-{action}", verdict="pass",
                evidence="reports/qa-multi-action.md", action_id=action,
                action_class="cms_content_candidate", scope=scope,
            )
            workflow.append_jsonl_locked(self.root / workflow.APPROVAL_LEDGER, {
                "approval_id": f"apr-{action}", "task_id": self.task_id,
                "action_id": action, "action_class": "cms_write", "scope": scope,
                "status": "active", "granted_at": workflow.utc_timestamp(),
            })
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        kitchen_execution = {
            "receipt_type": "execution_result", "action_id": kitchen_action,
            "action_class": "cms_write", "scope": kitchen_scope, "verdict": "pass",
        }
        kitchen_postcheck = {
            "receipt_type": "postcheck", "action_id": kitchen_action,
            "action_class": "cms_write", "scope": kitchen_scope, "verdict": "pass",
        }
        snapshot = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        pending = workflow._derive_state(self.root, snapshot, receipts + [kitchen_execution, kitchen_postcheck])
        self.assertEqual(pending["state"], "owner_approved")
        self.assertIn("execution_result", pending["missing"])
        design_execution = {
            "receipt_type": "execution_result", "action_id": design_action,
            "action_class": "cms_write", "scope": design_scope, "verdict": "pass",
        }
        executed = workflow._derive_state(self.root, snapshot, receipts + [kitchen_execution, kitchen_postcheck, design_execution])
        self.assertEqual(executed["state"], "execution_completed")
        design_postcheck = {
            "receipt_type": "postcheck", "action_id": design_action,
            "action_class": "cms_write", "scope": design_scope, "verdict": "pass",
        }
        closed = workflow._derive_state(self.root, snapshot, receipts + [kitchen_execution, kitchen_postcheck, design_execution, design_postcheck])
        self.assertEqual(closed["state"], "closed")

    def test_postcheck_failure_and_old_pass_cannot_close_current_execution(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        report = self.root / "reports/qa-postcheck-projection.md"
        report.write_text("Candidate passed; production still needs acceptance.\n", encoding="utf-8")
        action = "publish-exact-page"
        scope = "flashcast.com.my:services/exact-page"
        self.receipt(
            "qa_verdict", "qa", "qa-postcheck-projection", verdict="pass",
            evidence="reports/qa-postcheck-projection.md", action_id=action,
            action_class="site_code_candidate", scope=scope,
        )
        workflow.append_jsonl_locked(self.root / workflow.APPROVAL_LEDGER, {
            "approval_id": "apr-postcheck-projection", "task_id": self.task_id,
            "action_id": action, "action_class": "site_publish", "scope": scope,
            "status": "active", "granted_at": workflow.utc_timestamp(),
        })
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        snapshot = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        execution = {
            "receipt_type": "execution_result", "department": "content-organic-website",
            "action_id": action, "action_class": "site_publish", "scope": scope,
            "verdict": "pass",
        }
        passed = {
            "receipt_type": "postcheck", "department": "qa",
            "action_id": action, "action_class": "site_publish", "scope": scope,
            "verdict": "pass",
        }
        blocked = {**passed, "verdict": "blocked"}
        with self.subTest("failed_acceptance"):
            state = workflow._derive_state(self.root, snapshot, receipts + [execution, blocked])
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(state["blockers"], ["postcheck_blocked"])
        with self.subTest("old_pass_before_new_execution"):
            state = workflow._derive_state(self.root, snapshot, receipts + [execution, passed, execution.copy()])
            self.assertEqual(state["state"], "execution_completed")
            self.assertIn("postcheck", state["missing"])
        with self.subTest("latest_failure_supersedes_old_pass"):
            state = workflow._derive_state(self.root, snapshot, receipts + [execution, passed, blocked])
            self.assertEqual(state["state"], "blocked")
        with self.subTest("new_real_pass_resolves_failure"):
            state = workflow._derive_state(self.root, snapshot, receipts + [execution, blocked, passed])
            self.assertEqual(state["state"], "closed")

    def test_legacy_unscoped_postcheck_binds_only_one_successful_execution(self) -> None:
        self.advance_to_qa()
        self.prepare_qa()
        qa_report = self.root / "reports/qa-legacy-postcheck.md"
        qa_report.write_text("CMS action passed QA.\n", encoding="utf-8")
        action_id = "publish-bathroom-cms-row"
        scope = "flashcast.com.my:services/bathroom-row:faqs_en,faqs_zh"
        self.receipt(
            "qa_verdict", "qa", "qa-legacy-postcheck", verdict="pass",
            evidence="reports/qa-legacy-postcheck.md", action_id=action_id,
            action_class="cms_content_candidate", scope=scope,
        )
        workflow.append_jsonl_locked(self.root / workflow.APPROVAL_LEDGER, {
            "approval_id": "apr-legacy-postcheck", "task_id": self.task_id,
            "action_id": action_id, "action_class": "cms_write", "scope": scope,
            "status": "active", "granted_at": workflow.utc_timestamp(),
        })
        snapshot = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        receipts = workflow.read_jsonl(workflow.receipts_path(self.root, self.task_id))
        blocked_execution = {
            "receipt_type": "execution_result", "department": "content-organic-website",
            "action_id": action_id, "action_class": "cms_write", "scope": scope,
            "verdict": "blocked",
        }
        successful_execution = {**blocked_execution, "verdict": "pass"}
        legacy_postcheck = {
            "receipt_type": "postcheck", "department": "content-organic-website",
            "action_id": "", "action_class": "", "scope": "", "verdict": "pass",
        }
        historical = receipts + [blocked_execution, successful_execution, legacy_postcheck]
        self.assertEqual(workflow._derive_state(self.root, snapshot, historical)["state"], "closed")
        other_execution = {**successful_execution, "action_id": "another-action"}
        with_other_action = historical + [other_execution]
        self.assertEqual(
            workflow._derive_state(self.root, snapshot, with_other_action)["state"], "execution_completed"
        )
        unbound_postcheck = {**legacy_postcheck, "department": "paid-growth-data"}
        self.assertEqual(
            workflow._derive_state(
                self.root, snapshot, receipts + [blocked_execution, successful_execution, unbound_postcheck]
            )["state"],
            "execution_completed",
        )

    def test_premature_internal_close_needs_later_action_bound_qa_and_exact_approval(self) -> None:
        snapshot_path = workflow.snapshot_path(self.root, self.task_id)
        snapshot = workflow.read_json(snapshot_path)
        snapshot["owner_approval_required"] = False
        workflow.atomic_write_json(snapshot_path, snapshot)
        self.advance_to_qa()
        with mock.patch.object(workflow, "utc_timestamp", return_value="2099-01-01T00:00:00+00:00"):
            self.qa_pass()
        self.assertEqual(workflow.workflow_status(self.root, self.task_id)[0]["current_state"], "closed")

        evidence = self.root / "reports/qa-corrected-release.md"
        evidence.write_text("QA PASS: exact site code action\n", encoding="utf-8")
        action_id = "repair-managed-cms-targets"
        scope = "flashcast.com.my:managed-cms-targets:sha:no-cms-write"
        with mock.patch.object(workflow, "utc_timestamp", return_value="2099-01-01T00:00:01+00:00"):
            with mock.patch.object(workflow, "reconcile_workflow", return_value=({"current_state": "closed"}, [])):
                self.receipt(
                    "qa_verdict", "qa", "q-corrected-release", verdict="pass",
                    evidence="reports/qa-corrected-release.md", action_id=action_id,
                    action_class="site_code_rework_candidate", scope=scope,
                )
        with mock.patch.object(workflow, "utc_timestamp", return_value="2099-01-01T00:00:02+00:00"):
            with workflow.workflow_lock(self.root):
                workflow.append_workflow_event(self.root, self.task_id, "owner_approved", {"reconciled": True})
        self.assertIn("event_order:regression:owner_approved", workflow.validate_workflow_events(self.root, self.task_id))

        workflow.append_jsonl_locked(self.root / workflow.APPROVAL_LEDGER, {
            "approval_id": "exact-corrected-release", "task_id": self.task_id,
            "action_id": action_id, "action_class": "site_publish", "scope": scope,
            "status": "active", "granted_at": "2099-01-01T00:00:02+00:00",
        })
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])
        workflow.append_jsonl_locked(self.root / workflow.APPROVAL_LEDGER, {
            "approval_id": "exact-corrected-release", "task_id": self.task_id,
            "action_id": action_id, "action_class": "site_publish", "scope": scope,
            "status": "revoked", "granted_at": "2099-01-01T00:00:02+00:00",
            "changed_at": "2099-01-01T00:00:03+00:00",
        })
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_approval_before_qa_is_blocked(self) -> None:
        with self.assertRaisesRegex(workflow.WorkflowError, "必须先通过 QA"):
            workflow.record_approval(
                self.root,
                task_id=self.task_id,
                action_id="early-approval",
                action_class="site_publish",
                scope="/zh/early",
                source_message_ref="owner-msg-early",
            )

    def test_approval_is_exact_and_single_use(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-1",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            source_message_ref="owner-msg-1",
        )
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-1",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "allow")
        second, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-1",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        self.assertEqual(second["status"], "deny")
        wrong_scope, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-1",
            action_class="site_publish",
            scope="/en/service/kitchen",
            approval_id=str(approval["approval_id"]),
        )
        self.assertEqual(wrong_scope["status"], "deny")

    def test_maps_write_requires_exact_frozen_fields_qa_and_single_use_owner_approval(self) -> None:
        action = "gbp-description-and-services-test"
        scope = "google-business-profile:15562370346948107212:description-and-services:test-v2"
        request_path = self.root / "reports/gbp-request.json"
        candidate_path = self.root / "reports/gbp-candidate.json"
        request_path.parent.mkdir(exist_ok=True)
        candidate_path.write_text(json.dumps({"description": "Fact checked candidate", "services": ["D01"]}))
        payload_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        request_path.write_text(json.dumps({
            "original_task_id": self.task_id, "first_scope": scope,
            "exact_profile_resource_id": "15562370346948107212",
            "candidate_version": "test-v2",
            "candidate_path": "reports/gbp-candidate.json", "candidate_sha256": payload_hash,
            "first_allowed_field_request": ["description:D01", "services:S01,S02,S03,S04,S05,S06,S07,S08,S09"],
        }))
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text())
        policy["action_classes"]["google_business_profile_write"]["exact_requests"] = [{
            "task_id": self.task_id, "action_id": action, "scope": scope,
            "department": "content-organic-website", "request_path": "reports/gbp-request.json",
            "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        }]
        policy_path.write_text(json.dumps(policy))
        common = dict(task_id=self.task_id, department="content-organic-website", action_id=action,
                      action_class="google_business_profile_write", scope=scope, payload_sha256=payload_hash)
        denied, _ = workflow.policy_check(self.root, **common)
        self.assertEqual(denied["status"], "deny")
        self.assertIn("gbp_current_exact_valid_qa_required", denied["reason"])
        self.advance_to_qa()
        prepared = self.prepare_qa()
        payload = json.loads(prepared.read_text())
        payload.update(action_id=action, action_class="google_business_profile_candidate", scope=scope, risk_level="R3")
        payload.update(candidate_version="test-v2", candidate_path="reports/gbp-candidate.json",
                       candidate_sha256=payload_hash)
        qa_outbox = self.root / "logs/department-outbox/gbp-qa.json"
        qa_outbox.write_text(json.dumps(payload))
        self.receipt("outbox_received", "qa", "gbp-qa-outbox", evidence=workflow.rel_path(self.root, qa_outbox))
        self.receipt("qa_verdict", "qa", "gbp-qa-pass", verdict="pass", action_id=action,
                     action_class="google_business_profile_candidate", scope=scope, evidence=workflow.rel_path(self.root, qa_outbox))
        no_approval, _ = workflow.policy_check(self.root, **common)
        self.assertEqual(no_approval["status"], "deny")
        approval, _ = workflow.record_approval(self.root, task_id=self.task_id, action_id=action,
            action_class="google_business_profile_write", scope=scope, source_thread_id="fixed-operations",
            source_message_ref="owner-authorized-exact-maps-fields")
        allowed, _ = workflow.policy_check(self.root, **common, approval_id=str(approval["approval_id"]))
        self.assertEqual(allowed["status"], "allow")
        for changes in ({"scope": scope + ":hours"}, {"department": "operations"},
                        {"department": "local-seo-maps"}, {"payload_sha256": "a" * 64}):
            result, _ = workflow.policy_check(self.root, **{**common, **changes}, approval_id=str(approval["approval_id"]))
            self.assertEqual(result["status"], "deny")
        original_candidate = candidate_path.read_bytes()
        candidate_path.write_text("{}")
        mutated, _ = workflow.policy_check(self.root, **common, approval_id=str(approval["approval_id"]))
        self.assertEqual(mutated["status"], "deny")
        self.assertIn("gbp_exact_frozen_request_payload_and_field_scope_required", mutated["reason"])
        candidate_path.write_bytes(original_candidate)
        consumed, _ = workflow.policy_check(self.root, **common, approval_id=str(approval["approval_id"]), consume_approval=True)
        self.assertEqual(consumed["status"], "allow")
        repeated, _ = workflow.policy_check(self.root, **common, approval_id=str(approval["approval_id"]), consume_approval=True)
        self.assertEqual(repeated["status"], "deny")

    def test_maps_qa_artifact_must_match_same_frozen_candidate(self) -> None:
        cases = [({}, "allow"),
                 ({"candidate_version": "older"}, "deny"),
                 ({"candidate_version": None}, "deny"),
                 ({"candidate_path": "reports/unrelated.json"}, "deny"),
                 ({"candidate_path": None}, "deny"),
                 ({"candidate_sha256": "0" * 64}, "deny"),
                 ({"candidate_sha256": None}, "deny"),
                 ({"risk_level": "R1"}, "deny"),
                 ({"risk_level": "R3", "candidate_path": "reports/./candidate.json"}, "allow")]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                fixture = WorkflowControlTests()
                fixture.setUp()
                try:
                    root, task = fixture.root, fixture.task_id
                    action, scope = "gbp-exact-test", "google-business-profile:15562370346948107212:test-v2"
                    candidate = root / "reports/candidate.json"
                    candidate.parent.mkdir(exist_ok=True)
                    candidate.write_text('{"description":"synthetic only"}')
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    request = {"original_task_id": task, "first_scope": scope,
                               "exact_profile_resource_id": "15562370346948107212",
                               "candidate_version": "test-v2", "candidate_path": "reports/candidate.json",
                               "candidate_sha256": digest, "first_allowed_field_request": [
                                   "description:D01", "services:S01,S02,S03,S04,S05,S06,S07,S08,S09"]}
                    request_path = root / "reports/request.json"
                    request_path.write_text(json.dumps(request))
                    policy_path = root / "data/action-policy.json"
                    policy = json.loads(policy_path.read_text())
                    policy["action_classes"]["google_business_profile_write"]["exact_requests"] = [{
                        "task_id": task, "action_id": action, "scope": scope,
                        "department": "content-organic-website", "request_path": "reports/request.json",
                        "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest()}]
                    policy_path.write_text(json.dumps(policy))
                    fixture.advance_to_qa()
                    prepared = fixture.prepare_qa()
                    outbox = json.loads(prepared.read_text())
                    outbox.update(action_id=action, action_class="google_business_profile_candidate", scope=scope,
                                  risk_level="R3", candidate_version="test-v2",
                                  candidate_path="reports/candidate.json", candidate_sha256=digest)
                    outbox.update(changes)
                    qa_path = root / "logs/department-outbox/maps-exact-qa.json"
                    qa_path.write_text(json.dumps(outbox))
                    fixture.receipt("outbox_received", "qa", "exact-artifact", evidence=workflow.rel_path(root, qa_path))
                    fixture.receipt("qa_verdict", "qa", "exact-pass", verdict="pass", action_id=action,
                                    action_class="google_business_profile_candidate", scope=scope,
                                    evidence=workflow.rel_path(root, qa_path))
                    approval, _ = workflow.record_approval(root, task_id=task, action_id=action,
                        action_class="google_business_profile_write", scope=scope,
                        source_thread_id="fixed-operations", source_message_ref="synthetic-only")
                    result, _ = workflow.policy_check(root, task_id=task, department="content-organic-website",
                        action_id=action, action_class="google_business_profile_write", scope=scope,
                        payload_sha256=digest, approval_id=str(approval["approval_id"]))
                    self.assertEqual(result["status"], expected)
                    if expected == "deny":
                        self.assertIn("gbp_current_exact_valid_qa_required", result["reason"])
                finally:
                    fixture.tearDown()

    def test_cache_repair_requires_frozen_urls_qa_and_single_use_exact_approval(self) -> None:
        action = "exact-cache-repair-test"
        scope = "flashcast.com.my:cache:old-house-exact-test"
        request_path = self.root / "reports/cache-request.json"
        request_path.parent.mkdir(exist_ok=True)
        url = "https://flashcast.com.my/images/before-after/old-terrace/kitchen-after.webp"
        request_path.write_text(json.dumps({
            "allowed_urls": [url], "expected_sha256_by_url": {url: "a" * 64},
        }), encoding="utf-8")
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        binding = {
            "task_id": self.task_id, "action_id": action, "scope": scope,
            "department": "content-organic-website", "request_path": "reports/cache-request.json",
            "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        }
        policy["action_classes"]["site_cache_invalidation"]["exact_requests"] = [binding]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        common = dict(task_id=self.task_id, department="content-organic-website",
                      action_id=action, action_class="site_cache_invalidation", scope=scope)
        denied, _ = workflow.policy_check(self.root, **common)
        self.assertEqual(denied["status"], "deny")
        self.advance_to_qa()
        prepared_qa = self.prepare_qa()
        qa_payload = json.loads(prepared_qa.read_text(encoding="utf-8"))
        qa_outbox = self.root / "logs/department-outbox/cache-qa.json"
        qa_payload.update(action_id=action, action_class="site_cache_candidate", scope=scope, risk_level="R3")
        qa_outbox.write_text(json.dumps(qa_payload), encoding="utf-8")
        self.receipt("outbox_received", "qa", "cache-qa-updated-outbox", evidence=workflow.rel_path(self.root, qa_outbox))
        self.receipt("qa_verdict", "qa", "cache-qa-pass", verdict="pass", action_id=action,
                     action_class="site_cache_candidate", scope=scope, evidence=workflow.rel_path(self.root, qa_outbox))
        no_approval, _ = workflow.policy_check(self.root, **common)
        self.assertEqual(no_approval["status"], "deny")
        approval, _ = workflow.record_approval(
            self.root, task_id=self.task_id, action_id=action, action_class="site_cache_invalidation",
            scope=scope, source_thread_id="fixed-operations", source_message_ref="bounded-owner-cache-repair",
        )
        approval_id = str(approval["approval_id"])
        allowed, _ = workflow.policy_check(self.root, **common, approval_id=approval_id)
        self.assertEqual(allowed["status"], "allow")
        for overrides in ({"scope": "flashcast.com.my:cache:purge-everything"},
                          {"department": "operations"}, {"action_class": "site_publish"}):
            with self.subTest(overrides=overrides):
                result, _ = workflow.policy_check(self.root, **(common | overrides), approval_id=approval_id)
                self.assertEqual(result["status"], "deny")
        original = request_path.read_bytes()
        request_path.write_text("{}", encoding="utf-8")
        changed, _ = workflow.policy_check(self.root, **common, approval_id=approval_id)
        self.assertEqual(changed["status"], "deny")
        self.assertIn("cache_exact_frozen_request_required", changed["reason"])
        request_path.write_bytes(original)
        for bad_url in ("https://other.example/images/image.webp", "https://flashcast.com.my/images/../image.webp",
                        "https://flashcast.com.my/images/image.webp?bypass=1"):
            with self.subTest(url=bad_url):
                request_path.write_text(json.dumps({"allowed_urls": [bad_url],
                                                   "expected_sha256_by_url": {bad_url: "a" * 64}}), encoding="utf-8")
                binding["request_sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
                policy_path.write_text(json.dumps(policy), encoding="utf-8")
                bad, _ = workflow.policy_check(self.root, **common, approval_id=approval_id)
                self.assertEqual(bad["status"], "deny")
                self.assertIn("cache_request_urls_or_expected_hashes_invalid", bad["reason"])
        request_path.write_bytes(original)
        binding["request_sha256"] = hashlib.sha256(original).hexdigest()
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        consumed, _ = workflow.policy_check(self.root, **common, approval_id=approval_id, consume_approval=True)
        self.assertEqual(consumed["status"], "allow")
        again, _ = workflow.policy_check(self.root, **common, approval_id=approval_id, consume_approval=True)
        self.assertEqual(again["status"], "deny")

    def test_cache_repair_denies_wrong_or_mutated_qa_before_approval_consumption(self) -> None:
        for case in ("wrong_action", "wrong_scope", "changed_outbox", "outbox_identity_mismatch"):
            with self.subTest(case=case):
                fixture = WorkflowControlTests("test_cache_repair_requires_frozen_urls_qa_and_single_use_exact_approval")
                fixture.setUp()
                try:
                    action, scope = "cache-exact-regression", "flashcast.com.my:cache:exact-regression"
                    url = "https://flashcast.com.my/images/old-house-safe.webp"
                    request = fixture.root / "reports/request.json"
                    request.parent.mkdir(exist_ok=True)
                    request.write_text(json.dumps({"allowed_urls": [url],
                                                   "expected_sha256_by_url": {url: "b" * 64}}), encoding="utf-8")
                    policy_path = fixture.root / "data/action-policy.json"
                    policy = json.loads(policy_path.read_text(encoding="utf-8"))
                    policy["action_classes"]["site_cache_invalidation"]["exact_requests"] = [{
                        "task_id": fixture.task_id, "action_id": action, "scope": scope,
                        "department": "content-organic-website", "request_path": "reports/request.json",
                        "request_sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
                    }]
                    policy_path.write_text(json.dumps(policy), encoding="utf-8")
                    fixture.advance_to_qa()
                    prepared = fixture.prepare_qa()
                    payload = json.loads(prepared.read_text(encoding="utf-8"))
                    qa_action = "different-reviewed-action" if case == "wrong_action" else action
                    qa_scope = "flashcast.com.my:cache:different-reviewed-scope" if case == "wrong_scope" else scope
                    payload.update(action_id=qa_action, action_class="site_cache_candidate", scope=qa_scope, risk_level="R3")
                    if case == "outbox_identity_mismatch":
                        payload["action_id"] = "wrong-outbox-identity"
                    qa_outbox = fixture.root / "logs/department-outbox/exact-cache-probe.json"
                    qa_outbox.write_text(json.dumps(payload), encoding="utf-8")
                    fixture.receipt("outbox_received", "qa", "negative-cache-outbox", evidence=workflow.rel_path(fixture.root, qa_outbox))
                    fixture.receipt("qa_verdict", "qa", "negative-cache-qa", verdict="pass", action_id=qa_action,
                                    action_class="site_cache_candidate", scope=qa_scope, evidence=workflow.rel_path(fixture.root, qa_outbox))
                    approval, _ = workflow.record_approval(
                        fixture.root, task_id=fixture.task_id, action_id=action, action_class="site_cache_invalidation",
                        scope=scope, source_thread_id="fixed-operations", source_message_ref="fixture-only-bounded-request",
                    )
                    if case == "changed_outbox":
                        payload["conclusion"] = "mutated after receipt"
                        qa_outbox.write_text(json.dumps(payload), encoding="utf-8")
                    result, _ = workflow.policy_check(
                        fixture.root, task_id=fixture.task_id, department="content-organic-website", action_id=action,
                        action_class="site_cache_invalidation", scope=scope, approval_id=str(approval["approval_id"]),
                        consume_approval=True,
                    )
                    self.assertEqual(result["status"], "deny")
                    self.assertIn("cache_current_exact_valid_qa_required", result["reason"])
                    self.assertEqual(workflow.effective_approvals(fixture.root)[str(approval["approval_id"])]["status"], "active")
                finally:
                    fixture.tearDown()

    def test_standing_site_authorization_materializes_consumable_exact_approval(self) -> None:
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["standing_authorizations"] = [
            {
                "authorization_id": "owner-standing-flashcast-site-publish-test",
                "status": "active",
                "source_message_ref": "owner-test-message",
                "department": "content-organic-website",
                "action_classes": ["site_publish", "cms_write"],
                "allowed_scope_prefixes": ["flashcast.com.my:"],
            }
        ]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.advance_to_qa()
        self.qa_pass()
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-bilingual-kitchen",
            action_class="site_publish",
            scope="flashcast.com.my:/zh/services/kitchen|/en/services/kitchen",
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "allow")
        self.assertEqual(decision["approval_basis"], "standing_authorization")
        self.assertEqual(decision["approval_status"], "consumed")
        self.assertTrue(str(decision["approval_id"]).startswith("apr-standing-"))

        execution = self.root / "reports/standing-execution.md"
        execution.write_text("published\n", encoding="utf-8")
        result = self.receipt(
            "execution_result",
            "content-organic-website",
            "standing-execution-1",
            evidence="reports/standing-execution.md",
            action_id="publish-bilingual-kitchen",
            action_class="site_publish",
            scope="flashcast.com.my:/zh/services/kitchen|/en/services/kitchen",
            approval_id=str(decision["approval_id"]),
            policy_decision_id=str(decision["decision_id"]),
        )
        self.assertEqual(result["workflow_state"], "execution_completed")

    def test_verified_r3_qa_overrides_stale_plan_and_rejects_standing_approval(self) -> None:
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["standing_authorizations"] = [
            {
                "authorization_id": "owner-standing-flashcast-site-publish-test",
                "status": "active",
                "source_message_ref": "older-r2-owner-message",
                "department": "content-organic-website",
                "action_classes": ["site_publish"],
                "allowed_scope_prefixes": ["flashcast.com.my:"],
            }
        ]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        current = workflow.read_json(workflow.snapshot_path(self.root, self.task_id))
        workflow.initialize_workflow(
            self.root,
            task_id=self.task_id,
            request="运营网站",
            plan_status="ready_to_send",
            departments=current["departments"],
            owner_approval_required=False,
        )
        self.advance_to_qa()
        qa_outbox = self.root / "logs/department-outbox/r3-qa.json"
        qa_outbox.write_text(
            json.dumps({
                "task_id": self.task_id,
                "department": "qa",
                "action_id": "r3-permit-release",
                "action_class": "site_code_candidate",
                "scope": "flashcast.com.my:r3-permit-release",
                "risk_level": "R3",
            }),
            encoding="utf-8",
        )
        self.prepare_qa()
        self.receipt(
            "qa_verdict",
            "qa",
            "r3-qa-pass",
            verdict="pass",
            action_id="r3-permit-release",
            action_class="site_code_candidate",
            scope="flashcast.com.my:r3-permit-release",
            evidence=workflow.rel_path(self.root, qa_outbox),
        )
        snapshot, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(snapshot["current_state"], "waiting_owner_approval")
        self.assertTrue(snapshot["owner_approval_required"])
        self.assertEqual(snapshot["owner_approval_source"], "verified_qa_risk:R3")
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "waiting_owner_approval")
        self.assertTrue(rebuilt["owner_approval_required"])

        denied, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="r3-permit-release",
            action_class="site_publish",
            scope="flashcast.com.my:r3-permit-release",
        )
        self.assertEqual(denied["status"], "deny")
        self.assertIn("r3_exact_owner_approval_required", denied["reason"])
        self.assertEqual(denied["approval_id"], "")

        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="r3-permit-release",
            action_class="site_publish",
            scope="flashcast.com.my:r3-permit-release",
            source_thread_id="fixed-operations",
            source_message_ref="owner-explicit-r3-message",
        )
        allowed, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="r3-permit-release",
            action_class="site_publish",
            scope="flashcast.com.my:r3-permit-release",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        self.assertEqual(allowed["status"], "allow")
        self.assertEqual(allowed["approval_basis"], "single_use_exact")
        self.assertEqual(allowed["approval_status"], "consumed")

    def test_standing_site_authorization_rejects_other_site_scope(self) -> None:
        policy_path = self.root / "data/action-policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["standing_authorizations"] = [
            {
                "authorization_id": "owner-standing-flashcast-site-publish-test",
                "status": "active",
                "department": "content-organic-website",
                "action_classes": ["site_publish"],
                "allowed_scope_prefixes": ["flashcast.com.my:"],
            }
        ]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.advance_to_qa()
        self.qa_pass()
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="wrong-site",
            action_class="site_publish",
            scope="shopping.example:/products",
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "deny")
        self.assertIn(
            "exact_active_owner_approval_or_standing_scope_required",
            decision["reason"],
        )

    def test_content_department_can_manage_its_own_registered_automation(self) -> None:
        binding = workflow.department_registry(self.root)["content-organic-website"]["chat_binding"]
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="create-site-publisher",
            action_class="automation_create",
            scope="automation:flashcast-site-publisher",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="content-organic-website",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256="c" * 64,
        )
        self.assertEqual(decision["status"], "allow")

    def test_operations_can_update_its_own_automation_for_recovery_when_health_is_stale(self) -> None:
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        binding = registry["departments"][0]["chat_binding"]
        binding["last_health_check_at"] = "2000-01-01T00:00:00+00:00"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="update-operations-recovery-rule",
            action_class="automation_update",
            scope="automation:flashcast-ops",
            source_project_id="flashcast-test-project",
            target_project_id="flashcast-test-project",
            target_department="operations",
            target_thread_id=str(binding["task_id"]),
            target_thread_title=str(binding["title"]),
            target_cwd=str(self.root),
            target_sidebar_section_id=str(binding["sidebar_section_id"]),
            payload_sha256="f" * 64,
        )
        self.assertEqual(decision["status"], "allow")
        self.assertNotIn("target_thread_unhealthy_or_dispatch_ineligible", decision["reason"])

    def test_approval_can_be_revoked(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-2",
            action_class="site_publish",
            scope="/zh/service/bathroom",
            source_message_ref="owner-msg-2",
        )
        workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-2",
            action_class="site_publish",
            scope="/zh/service/bathroom",
            approval_id=str(approval["approval_id"]),
            revoke=True,
        )
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-2",
            action_class="site_publish",
            scope="/zh/service/bathroom",
            approval_id=str(approval["approval_id"]),
        )
        self.assertEqual(decision["status"], "deny")

    def test_execution_and_postcheck_close_with_verified_event(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-3",
            action_class="site_publish",
            scope="/zh/service/office",
            source_message_ref="owner-msg-3",
        )
        workflow.workflow_status(self.root, self.task_id)
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-3",
            action_class="site_publish",
            scope="/zh/service/office",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        execution = self.root / "reports/execution.md"
        execution.write_text("execution result\n", encoding="utf-8")
        self.receipt(
            "execution_result",
            "content-organic-website",
            "execution-1",
            evidence="reports/execution.md",
            verdict="pass",
            action_id="publish-page-3",
            action_class="site_publish",
            scope="/zh/service/office",
            approval_id=str(approval["approval_id"]),
            policy_decision_id=str(decision["decision_id"]),
        )
        postcheck = self.root / "reports/postcheck.md"
        postcheck.write_text("verified\n", encoding="utf-8")
        blocked = self.receipt(
            "postcheck", "content-organic-website", "postcheck-failed-before-pass",
            evidence="reports/postcheck.md", verdict="blocked",
            action_id="publish-page-3", action_class="site_publish",
            scope="/zh/service/office",
        )
        self.assertEqual(blocked["workflow_state"], "blocked")
        self.assertEqual(
            workflow.workflow_status(self.root, self.task_id)[0]["blockers"],
            ["postcheck_blocked"],
        )
        result = self.receipt(
            "postcheck",
            "content-organic-website",
            "postcheck-1",
            evidence="reports/postcheck.md",
            verdict="pass",
        )
        self.assertEqual(result["workflow_state"], "closed")
        states = [row["state"] for row in workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)]
        self.assertIn("execution_completed", states)
        self.assertIn("verified", states)
        self.assertEqual(states[-1], "closed")

        # An older unscoped postcheck could already have closed a published
        # action before an exact identity correction accidentally replayed the
        # terminal pair. Accept that historical pair only with matching proof.
        correction_stamp = "2099-01-01T00:00:00+00:00"
        with mock.patch.object(workflow, "utc_timestamp", return_value=correction_stamp):
            corrected = self.receipt(
                "postcheck", "content-organic-website", "postcheck-action-identity-correction",
                evidence="reports/postcheck.md", verdict="pass",
                action_id="publish-page-3", action_class="site_publish",
                scope="/zh/service/office",
            )
            self.assertEqual(corrected["workflow_state"], "closed")
            with workflow.workflow_lock(self.root):
                workflow.append_workflow_event(self.root, self.task_id, "verified", {"reconciled": True})
                workflow.append_workflow_event(self.root, self.task_id, "closed", {"reconciled": True})
        self.assertEqual(workflow.validate_workflow_events(self.root, self.task_id), [])

    def test_duplicate_terminal_events_without_exact_postcheck_correction_are_rejected(self) -> None:
        snapshot_path = workflow.snapshot_path(self.root, self.task_id)
        snapshot = workflow.read_json(snapshot_path)
        snapshot["owner_approval_required"] = False
        workflow.atomic_write_json(snapshot_path, snapshot)
        self.advance_to_qa()
        self.qa_pass()
        self.assertEqual(workflow.workflow_status(self.root, self.task_id)[0]["current_state"], "closed")
        with mock.patch.object(workflow, "utc_timestamp", return_value="2099-01-01T00:00:00+00:00"):
            with workflow.workflow_lock(self.root):
                workflow.append_workflow_event(self.root, self.task_id, "verified", {"reconciled": True})
                workflow.append_workflow_event(self.root, self.task_id, "closed", {"reconciled": True})
        self.assertIn("event_order:regression:verified", workflow.validate_workflow_events(self.root, self.task_id))

    def test_blocked_execution_does_not_look_ready_for_postcheck(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            source_message_ref="owner-msg-blocked",
        )
        workflow.workflow_status(self.root, self.task_id)
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        execution = self.root / "reports/blocked-execution.md"
        execution.write_text("Pages live; Edge protected gate blocked\n", encoding="utf-8")
        result = self.receipt(
            "execution_result",
            "content-organic-website",
            "execution-blocked-1",
            evidence="reports/blocked-execution.md",
            verdict="blocked",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            policy_decision_id=str(decision["decision_id"]),
        )
        self.assertEqual(result["workflow_state"], "blocked")
        status, _ = workflow.workflow_status(self.root, self.task_id)
        self.assertEqual(status["current_state"], "blocked")
        self.assertEqual(status["blockers"], ["execution_result_blocked"])
        self.assertNotIn("receipt-record:postcheck", status["next_legal_actions"])

        ordinary_retry, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
        )
        self.assertEqual(ordinary_retry["status"], "deny")

        retry_args = dict(
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            retry_blocked_execution_receipt_id=str(result["receipt_id"]),
        )
        wrong_receipt, _ = workflow.policy_check(
            self.root, **{**retry_args, "retry_blocked_execution_receipt_id": "missing-receipt"}
        )
        self.assertEqual(wrong_receipt["status"], "deny")
        wrong_scope, _ = workflow.policy_check(
            self.root, **{**retry_args, "scope": "/en/service/kitchen"}
        )
        self.assertEqual(wrong_scope["status"], "deny")
        reconsume, _ = workflow.policy_check(
            self.root, **retry_args, consume_approval=True
        )
        self.assertEqual(reconsume["status"], "deny")

        retry, _ = workflow.policy_check(self.root, **retry_args)
        self.assertEqual(retry["status"], "allow", retry)
        self.assertEqual(retry["approval_status"], "consumed")
        self.assertEqual(retry["approval_basis"], "blocked_execution_retry")
        self.assertEqual(retry["retry_source_receipt_id"], result["receipt_id"])
        duplicate, _ = workflow.policy_check(self.root, **retry_args)
        self.assertEqual(duplicate["status"], "deny")
        self.assertIn("blocked_execution_retry_already_authorized_or_state_changed", duplicate["reason"])

    def test_completed_retry_replay_requires_exact_consumed_policy_and_receipts(self) -> None:
        for variant in ("valid", "missing_policy", "wrong_scope"):
            with self.subTest(variant=variant):
                task = f"retry-replay-{variant}"
                fields = dict(task_id=task, department="content-organic-website",
                              action_id="publish-reviewed", action_class="site_publish",
                              scope="flashcast.com.my:/reviewed", approval_id="apr-exact")
                failed = dict(fields, receipt_type="execution_result", receipt_id="failed",
                              verdict="blocked", created_at="2026-01-01T00:00:01+00:00")
                successful = dict(fields, receipt_type="execution_result", receipt_id="success",
                                  verdict="pass", policy_decision_id=f"pol-{variant}",
                                  created_at="2026-01-01T00:00:03+00:00")
                qa = dict(fields, receipt_type="qa_verdict", receipt_id="qa-exact", department="qa",
                          action_class="site_code_rework_candidate", verdict="pass", receipt_hash="qa-hash",
                          created_at="2026-01-01T00:00:02+00:00")
                workflow.append_jsonl_locked(workflow.receipts_path(self.root, task), failed)
                workflow.append_jsonl_locked(workflow.receipts_path(self.root, task), qa)
                workflow.append_jsonl_locked(workflow.receipts_path(self.root, task), successful)
                if variant != "missing_policy":
                    policy = dict(fields, decision_id=f"pol-{variant}", status="allow",
                                  approval_status="consumed", approval_basis="blocked_execution_retry",
                                  retry_source_receipt_id="failed", checked_at="2026-01-01T00:00:02+00:00")
                    if variant == "wrong_scope":
                        policy["scope"] = "flashcast.com.my:/another"
                    workflow.append_jsonl_locked(self.root / "logs/policy-decisions.jsonl", policy)
                with mock.patch.object(workflow, "utc_timestamp", return_value="2026-01-01T00:00:01+00:00"):
                    workflow.append_workflow_event(self.root, task, "planned")
                    workflow.append_workflow_event(self.root, task, "owner_approved")
                    workflow.append_workflow_event(self.root, task, "blocked", {"reconciled": True})
                with mock.patch.object(workflow, "utc_timestamp", return_value="2026-01-01T00:00:03+00:00"):
                    for state in ("dispatched", "acknowledged", "evidence_received", "qa_passed",
                                  "waiting_owner_approval", "owner_approved", "execution_completed"):
                        details = {"reconciled": True}
                        if state == "qa_passed":
                            details.update(qa_receipt_id="qa-exact", qa_receipt_hash="qa-hash")
                        workflow.append_workflow_event(self.root, task, state, details)
                invalid = workflow.validate_workflow_events(self.root, task)
                if variant == "valid":
                    self.assertEqual(invalid, [])
                else:
                    self.assertTrue(any("event_order:regression" in item for item in invalid))

    def test_blocked_execution_retry_rejects_changed_evidence(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            source_message_ref="owner-msg-blocked",
        )
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        execution = self.root / "reports/blocked-execution.md"
        execution.write_text("blocked evidence\n", encoding="utf-8")
        blocked = self.receipt(
            "execution_result", "content-organic-website", "execution-blocked-evidence",
            evidence="reports/blocked-execution.md", verdict="blocked",
            action_id="publish-page-blocked", action_class="site_publish",
            scope="/zh/service/kitchen", approval_id=str(approval["approval_id"]),
            policy_decision_id=str(decision["decision_id"]),
        )
        execution.write_text("changed evidence\n", encoding="utf-8")
        retry, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="publish-page-blocked",
            action_class="site_publish",
            scope="/zh/service/kitchen",
            approval_id=str(approval["approval_id"]),
            retry_blocked_execution_receipt_id=str(blocked["receipt_id"]),
        )
        self.assertEqual(retry["status"], "deny")
        self.assertIn("blocked_execution_retry_identity_or_evidence_invalid", retry["reason"])

    def test_paid_promotion_hard_gate_overrides_approval(self) -> None:
        self.advance_to_qa()
        self.qa_pass()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="enable-ads",
            action_class="ads_write",
            scope="campaign-123",
            source_message_ref="owner-msg-ads",
        )
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="enable-ads",
            action_class="ads_write",
            scope="campaign-123",
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "deny")
        self.assertIn("paid_promotion_disabled_hard_gate", decision["reason"])

    def _synthetic_google_ads_read_scope(self) -> str:
        """Configure only this test's isolated policy, without real account IDs."""
        path = self.root / "data/action-policy.json"
        policy = json.loads(path.read_text(encoding="utf-8"))
        prefix = "google-ads:synthetic-account:readonly:"
        policy["action_classes"]["account_read"]["allowed_scope_prefixes"] = [prefix]
        path.write_text(json.dumps(policy), encoding="utf-8")
        return prefix + "campaign-consolidation"

    def test_exact_owner_approved_google_ads_account_read_is_allowed_without_enabling_paid(self) -> None:
        scope = self._synthetic_google_ads_read_scope()
        approval, _ = workflow.record_approval(
            self.root,
            task_id=self.task_id,
            action_id="inspect-campaigns",
            action_class="account_read",
            scope=scope,
            source_message_ref="owner-msg-readonly-ads",
        )
        decision, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="paid-growth-data",
            action_id="inspect-campaigns",
            action_class="account_read",
            scope=scope,
            approval_id=str(approval["approval_id"]),
            consume_approval=True,
        )
        self.assertEqual(decision["status"], "allow")
        self.assertFalse(decision["paid_promotion_enabled"])
        self.assertIn("owner_approval:exact_scope", decision["required_receipts"])

    def test_google_ads_account_read_rejects_missing_approval_wrong_scope_and_wrong_department(self) -> None:
        scope = self._synthetic_google_ads_read_scope()
        missing_approval, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="paid-growth-data",
            action_id="inspect-campaigns",
            action_class="account_read",
            scope=scope,
        )
        self.assertEqual(missing_approval["status"], "deny")
        self.assertEqual(missing_approval["reason"], ["exact_active_owner_approval_or_standing_scope_required"])

        approval, _ = workflow.record_approval(
            self.root, task_id=self.task_id, action_id="inspect-campaigns",
            action_class="account_read", scope=scope,
            source_message_ref="synthetic-owner-msg-readonly-ads",
        )
        approval_id = str(approval["approval_id"])
        wrong_approval_scope, _ = workflow.policy_check(
            self.root, task_id=self.task_id, department="paid-growth-data",
            action_id="inspect-campaigns", action_class="account_read",
            scope=scope + "-expanded", approval_id=approval_id, consume_approval=True,
        )
        self.assertEqual(wrong_approval_scope["status"], "deny")
        self.assertEqual(wrong_approval_scope["reason"], ["exact_active_owner_approval_or_standing_scope_required"])

        wrong_scope, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="paid-growth-data",
            action_id="inspect-campaigns",
            action_class="account_read",
            scope="google-ads:synthetic-other-account:readonly:campaign-consolidation",
            approval_id=approval_id,
            consume_approval=True,
        )
        self.assertEqual(wrong_scope["status"], "deny")
        self.assertEqual(wrong_scope["reason"], ["account_read_scope_not_allowed", "exact_active_owner_approval_or_standing_scope_required"])

        wrong_department, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="inspect-campaigns",
            action_class="account_read",
            scope=scope,
            approval_id=approval_id,
            consume_approval=True,
        )
        self.assertEqual(wrong_department["status"], "deny")
        self.assertEqual(wrong_department["reason"], ["account_read_department_not_allowed"])
        self.assertEqual(workflow.effective_approvals(self.root)[approval_id]["status"], "active")
        for decision in (missing_approval, wrong_approval_scope, wrong_scope, wrong_department):
            self.assertFalse(decision["paid_promotion_enabled"])

    def test_operations_and_skill_whitelist_are_enforced(self) -> None:
        denied, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="operations",
            action_id="specialist-1",
            action_class="specialist_delivery",
            scope="content audit",
        )
        self.assertEqual(denied["status"], "deny")
        wrong_skill, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="read-1",
            action_class="local_read",
            scope="reports/",
            skill="google-ads-renovation-ppc",
        )
        self.assertEqual(wrong_skill["status"], "deny")
        generic_subagent_policy, _ = workflow.policy_check(
            self.root,
            task_id=self.task_id,
            department="content-organic-website",
            action_id="subagent-1",
            action_class="subagent_delegation",
            scope="bounded audit",
        )
        self.assertEqual(generic_subagent_policy["status"], "deny")
        self.assertIn("use_delegation_check_and_delegation_record", generic_subagent_policy["reason"])

    def test_interrupted_snapshot_is_rebuilt_from_events(self) -> None:
        self.receipt("dispatch_sent", "content-organic-website", "d1")
        workflow.snapshot_path(self.root, self.task_id).unlink()
        rebuilt, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertTrue(rebuilt["recovered_from_events"])
        self.assertEqual(rebuilt["current_state"], "dispatched")
        self.assertTrue(workflow.snapshot_path(self.root, self.task_id).exists())
        event_count = len(workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS))
        second, _ = workflow.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(second["current_state"], "dispatched")
        self.assertEqual(len(workflow.read_jsonl(self.root / workflow.WORKFLOW_EVENTS)), event_count)

    def test_legacy_shadow_replay_is_read_only_and_stops_without_chat_ack_or_qa(self) -> None:
        legacy_id = "legacy-shadow-001"
        legacy_dispatch = self.root / f"logs/dispatch/{legacy_id}.json"
        legacy_dispatch.parent.mkdir(parents=True, exist_ok=True)
        outbox = self.root / f"logs/department-outbox/{legacy_id}-content.json"
        outbox.parent.mkdir(parents=True, exist_ok=True)
        outbox.write_text(
            json.dumps(
                {
                    "task_id": f"{legacy_id}-content",
                    "department": "content-organic-website",
                    "status": "completed",
                    "learning": {"status": "provisional"},
                }
            ),
            encoding="utf-8",
        )
        legacy_dispatch.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "task_id": legacy_id,
                    "status": "blocked_no_controller_fallback",
                    "parallel_departments": ["content-organic-website"],
                    "dispatch_events": [{"department": "content-organic-website", "status": "sent"}],
                    "departments": [
                        {
                            "department": "content-organic-website",
                            "outbox_evidence": workflow.rel_path(self.root, outbox),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        payload, _ = workflow.reconcile_workflow(self.root, task_id=legacy_id, shadow=True)
        self.assertEqual(payload["status"], "shadow_replay_blocked")
        self.assertEqual(payload["current_state"], "dispatched")
        self.assertIn("chat_ack_nonempty:content-organic-website", payload["missing_receipts"])
        self.assertIn("qa_verdict:qa", payload["missing_receipts"])
        self.assertFalse(workflow.snapshot_path(self.root, legacy_id).exists())

    def test_learning_v2_marks_stale_and_keeps_legacy_visible(self) -> None:
        registry = self.root / "data/learning/department-learning-registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            json.dumps(
                {
                    "departments": [
                        {
                            "id": "content-organic-website",
                            "name": "content",
                            "memory_path": "data/learning/departments/content.json",
                            "professional_skill": "",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        memory = self.root / "data/learning/departments/content.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_text(
            json.dumps(
                {
                    "inherited_lessons": [{"lesson": "legacy lesson"}],
                    "verified_lessons": [],
                    "provisional_lessons": [],
                    "retired_lessons": [],
                    "blocked_patterns": [],
                }
            ),
            encoding="utf-8",
        )
        evidence = self.root / "reports/evidence.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("evidence\n", encoding="utf-8")
        args = argparse.Namespace(
            department="content-organic-website",
            task_id="learning-001",
            memory_type="seo",
            lesson="freshness matters",
            signal="old window",
            evidence="reports/evidence.md",
            outcome="review",
            next_action="refresh",
            confidence="medium",
            lesson_status="provisional",
            source="test",
            observed_at="2026-08-01T00:00:00+00:00",
            data_window="2026-07-01..2026-07-31",
            last_verified_at="2026-08-01",
            review_after="2026-08-02",
            conflicts_with="",
            supersedes="",
        )
        ops.department_learning_record(self.root, args)
        status, _ = ops.department_learning_status(self.root)
        row = status["departments"][0]
        self.assertEqual(row["stale_count"], 1)
        self.assertEqual(row["legacy_provisional_count"], 1)
        saved = ops.read_json(memory)
        self.assertEqual(saved["schema_version"], "2.0")
        self.assertEqual(saved["provisional_lessons"][0]["freshness_status"], "stale")


if __name__ == "__main__":
    unittest.main()
