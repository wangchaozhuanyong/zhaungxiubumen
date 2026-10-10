"""Bounded owner v42 completion; never opens the global Google Ads gate."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = "<PROJECT_ROOT>"
PROJECT = "<LOCAL_PROJECT_ID>"
SOURCE = "<LOCAL_TASK_ID>"
QA = "<LOCAL_TASK_ID>"
TASK = "fc-20260920-google-ads-rm100-budget-plan"
PREFIX = "owner_paid_completion:example-ads-account:v42:"
AUTH = 'synthetic-evidence-not-native'
FUNDS_AUTH = 'synthetic-evidence-not-native'
CAMPAIGNS = []
ACTIONS = {}


def check(root: Path, policy: dict, departments: dict, request: dict, healthy) -> list[str]:
    raise ValueError("public_template_has_no_native_authorization")
    raise ValueError("public_template_has_no_native_authorization")
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    def path(value):
        require(isinstance(value, str) and bool(value), "path_required")
        p = (root / value).resolve()
        require(p != root.resolve() and p.is_relative_to(root.resolve()), "project_path_required")
        return p

    def pin(value):
        p = path(value["path"])
        require(hashlib.sha256(p.read_bytes()).hexdigest() == value["sha256"], "frozen_pin_changed")
        return p

    def json_pin(value):
        return json.loads(pin(value).read_text())

    try:
        require(str(root.resolve()) == ROOT, "project_root_required")
        routing = policy["routing_policy"]
        require(routing["source_project_id"] == PROJECT and routing["source_project_root"] == ROOT,
                "project_binding_required")
        key = request["scope"].removeprefix(PREFIX)
        require(request["scope"].startswith(PREFIX) and key in ACTIONS, "exact_action_required")
        cls, aid, dept, tid = ACTIONS[key]
        require(request["task_id"] == TASK and request["department"] == "paid-growth-data"
                and request["action_class"] == cls and request["action_id"] == aid,
                "exact_action_tuple_required")
        require(not request.get("skill") or request["skill"] == "google-ads-renovation-ppc",
                "approved_skill_required")
        rule = policy["owner_paid_completion_v42"]
        require(rule["status"] == "owner_approved_exact_completion", "exact_rule_required")
        pack = json_pin(rule["packet"])
        require(pack["original_task_id"] == TASK and pack["candidate_version"] == "paid-owner-completion-v42"
                and pack["account_id"] == "example-ads-account" and pack["campaign_ids"] == CAMPAIGNS
                and [pack["group_count"], pack["exact_keyword_count"], pack["rsa_count"]] == [6, 40, 6]
                and pack["total_ad_fee_each_myr"] == 1350 and pack["gross_spend_ceiling_myr"] == 3000
                and pack["dates_myt"] == ["2026-10-08", "2026-10-14"]
                and pack["hours_myt"] == "MON-SUN10:00-22:00" and pack["shop_hours_unchanged"] is True,
                "frozen_launch_scope_required")
        for value in pack["frozen_inputs"]:
            pin(value)
        auth = json_pin(pack["owner_authorization"])
        require(auth["source_thread_id"] == SOURCE and auth["source_method"] == "mcp__codex_app__read_thread",
                "native_owner_source_required")
        messages = {m["id"]: m for m in auth["messages"]}
        require(messages[AUTH]["type"] == "userMessage" and messages[AUTH]["content"][0]["text"].strip() == "允许",
                "native_exact_owner_approval_required")
        require(messages[FUNDS_AUTH]["type"] == "userMessage"
                and messages[FUNDS_AUTH]["content"][0]["text"].strip() == pack["funds_owner_message"],
                "native_owner_fpx_and_enable_required")
        question = auth["preceding_question"]
        require(question["id"] == "msg_04e57c709d781d12016ac70327c8bc87d0b41943ba051fdba5"
                and "固定质检部仅复核这次FPX确认" in question["text"]
                and "两套新广告启用＋本聊天四小时监控" in question["text"], "exact_permission_question_required")
        now = dt.datetime.now(dt.timezone.utc)
        require(now <= dt.datetime(2026, 10, 14, 14, tzinfo=dt.timezone.utc), "campaign_window_expired")
        live = json.loads(path(pack["live_identity_path"]).read_text())
        observed = dt.datetime.fromisoformat(live["observed_at"].replace("Z", "+00:00"))
        require(observed.tzinfo is not None and 0 <= (now - observed).total_seconds() <= 300,
                "fresh_native_app_identity_required")
        require(live["source_method"] == "mcp__codex_app__list_threads", "native_app_identity_required")
        threads = {t["id"]: t for t in live["threads"]}
        required = [("paid-growth-data", SOURCE)] + ([("qa", QA)] if key == "funds-qa" else [])
        sections = [s for s in live["sections"] if s["name"] == "装修公司部门"]
        require(len(sections) == 1, "unique_native_section_required")
        for did, thread_id in required:
            require(sum(t["id"] == thread_id for t in live["threads"]) == 1, "unique_native_thread_required")
            binding = departments[did]["chat_binding"]
            require(healthy(binding, verification_ttl_hours=26), "registered_health_required")
            require(binding["task_id"] == thread_id and binding["project_id"] == PROJECT and binding["cwd"] == ROOT,
                    "registered_identity_required")
            t = threads[thread_id]
            require(t["projectId"] == PROJECT and t["cwd"] == ROOT and t["title"] == binding["title"]
                    and "codex:thread:local:" + thread_id in sections[0]["itemKeys"], "native_identity_required")
        require(request["source_project_id"] == PROJECT and request["target_project_id"] == PROJECT
                and request["target_department"] == dept and request["target_thread_id"] == tid
                and request["target_thread_title"] == threads[tid]["title"] and request["target_cwd"] == ROOT
                and request["target_sidebar_section_id"] == sections[0]["sectionId"], "native_target_tuple_required")
        action = pack["actions"][key]
        payload_path = pin(action["payload"])
        require(request["payload_sha256"] == action["payload"]["sha256"], "exact_payload_required")
        if key != "monitor-read":
            require(not path(action["attempt_path"]).exists(), "single_use_attempt_already_recorded")
        if key == "funds-qa":
            require(threads[QA]["status"] == "idle", "fixed_qa_must_be_idle")
        if key == "monitor-update":
            update = json.loads(payload_path.read_text())
            require(update["id"] == "flash-cast-3" and update["mode"] == "update" and update["kind"] == "heartbeat"
                    and update["targetThreadId"] == SOURCE and update["status"] == "ACTIVE"
                    and update["rrule"] == "RRULE:FREQ=DAILY;BYHOUR=10,14,18,22;BYMINUTE=0;BYSECOND=0",
                    "exact_heartbeat_update_required")
        if key == "enable-two-new-search":
            require(request["consume_approval"] is True, "consume_exact_enable_permit_required")
            proof = json.loads(path(pack["final_qa_proof_path"]).read_text())
            outbox = json_pin(proof["outbox"])
            native = proof["native_reply"]
            require(native["thread_id"] == QA and native["turn_status"] == "completed"
                    and native["message_id"] and native["nonempty"] is True, "actual_independent_qa_reply_required")
            require(outbox["department"] == "qa" and outbox["qa_verdict"] == "pass"
                    and outbox["candidate_version"] == pack["candidate_version"]
                    and outbox["identity"]["chat_task_id"] == QA
                    and outbox["chat_reply"]["message_id"] == native["message_id"]
                    and outbox["chat_reply"]["body_sha256"] == native["body_sha256"], "exact_final_qa_pass_required")
            require(any(e["path"] == rule["packet"]["path"] and e["sha256"] == rule["packet"]["sha256"]
                        for e in outbox["evidence"]), "qa_must_bind_this_packet")
            pin(proof["report"])
        return []
    except (KeyError, ValueError, TypeError, OSError, IndexError) as exc:
        return ["owner_paid_completion_denied:" + str(exc)]
