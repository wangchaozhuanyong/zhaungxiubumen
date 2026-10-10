"""One human-approved paid department -> fixed QA message; never Ads authority."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = "<PROJECT_ROOT>"
PROJECT = "<LOCAL_PROJECT_ID>"
SOURCE = "<LOCAL_TASK_ID>"
TARGET = "<LOCAL_TASK_ID>"
TASK = "fc-20260920-google-ads-rm100-budget-plan"
SCOPE = "owner_paid_final_qa:example-ads-account:v39"
ACTION = "send-owner-approved-paid-final-qa-v39"
AUTH_MESSAGE = 'synthetic-evidence-not-native'
AUTH_TURN = 'synthetic-evidence-not-native'
QUESTION = '["request_user_input_async","call_f5866b81d4e647b5be446beef8092795",0]'
REWORK_SCOPE = "owner_paid_final_qa:example-ads-account:v40"


def check(root, policy, departments, requested, healthy):
    """Return route-specific reasons; callers retain ordinary project/health checks."""
    raise ValueError("public_template_has_no_native_authorization")
    raise ValueError("public_template_has_no_native_authorization")
    def require(value, reason):
        if not value:
            raise ValueError(reason)

    def path(value):
        require(isinstance(value, str) and bool(value), "path_required")
        p = (root / value).resolve()
        require(p != root.resolve() and p.is_relative_to(root.resolve()), "path_outside_project")
        return p

    def read_pin(pin):
        p = path(pin["path"])
        require(hashlib.sha256(p.read_bytes()).hexdigest() == pin["sha256"], "frozen_pin_mismatch")
        return json.loads(p.read_text())

    try:
        routing = policy["routing_policy"]
        require(str(root.resolve()) == ROOT and routing["source_project_id"] == PROJECT
                and routing["source_project_root"] == ROOT, "project_identity_mismatch")
        is_rework = requested.get("scope") == REWORK_SCOPE
        route_key = "owner_paid_final_qa_v40" if is_rework else "owner_paid_final_qa"
        expected_scope = REWORK_SCOPE if is_rework else SCOPE
        expected_action = "send-owner-approved-paid-final-qa-v40" if is_rework else ACTION
        expected_message = "example-native-adf7260eec4d7fa4" if is_rework else AUTH_MESSAGE
        expected_question = '["request_user_input_async","call_069fad82e4124364937056ba893db163",0]' if is_rework else QUESTION
        expected_answer = "批准降预算及一次定向复验" if is_rework else "允许一次准确独立审核"
        expected_candidate = "paid-final-qa-v39-rework1" if is_rework else "paid-final-qa-v39"
        rule = routing[route_key]
        require(rule["status"] == "approved_single_use", "exact_route_not_approved")
        request = read_pin({"path": rule["request_path"], "sha256": rule["request_sha256"]})
        exact = {"task_id": TASK, "action_id": expected_action, "scope": expected_scope,
                 "action_class": "thread_message", "sender_department": "paid-growth-data",
                 "source_project_id": PROJECT, "target_project_id": PROJECT,
                 "target_department": "qa", "target_thread_id": TARGET,
                 "target_thread_title": "FLASH CAST｜质检与Reality Checker部｜2026-09",
                 "target_cwd": ROOT}
        require(all(request.get(k) == v and requested.get(k) == v for k, v in exact.items()),
                "exact_route_tuple_mismatch")
        require(all(requested.get(k) == request.get(k) for k in
                    ["target_sidebar_section_id", "payload_sha256"]), "exact_payload_or_section_mismatch")
        require(request["review_only"] is True and request["ads_write_allowed"] is False
                and request["production_authority_granted"] is False, "review_only_required")
        auth = read_pin(request["owner_authorization"])
        require(auth["source_thread_id"] == SOURCE and auth["turn_id"] == AUTH_TURN
                and auth["message_id"] == expected_message and auth["source_method"] == "mcp__codex_app__read_thread",
                "native_owner_authorization_required")
        msg = auth["user_message"]
        require(msg["type"] == "userMessage" and msg["id"] == expected_message, "human_message_required")
        raw = msg["content"][0]["text"]
        replies = json.loads(raw.split("<send_user_message_question_reply>", 1)[1]
                             .split("</send_user_message_question_reply>", 1)[0])
        require(len(replies) == 1 and replies[0]["questionItemId"] == expected_question
                and replies[0]["answer"] == expected_answer, "exact_human_answer_required")
        packet = read_pin(request["packet"])
        require(packet["original_task_id"] == TASK and packet["candidate_version"] == expected_candidate
                and packet["account_id"] == "example-ads-account"
                and packet["campaign_ids"] == ["00057225103", "00063878462"]
                and packet["group_count"] == 6 and packet["exact_keyword_count"] == 40
                and packet["gross_spend_ceiling_myr"] == 3000, "exact_packet_scope_required")
        if is_rework:
            require(packet["total_ad_fee_each_myr"] == 1350
                    and packet["dates_myt"] == ["2026-10-08", "2026-10-14"]
                    and packet["hours_myt"] == "MON-SUN10:00-22:00"
                    and packet["shop_hours_unchanged"] is True
                    and packet["review_only"] is True, "exact_rework_scope_required")
        for pin in packet["frozen_inputs"]:
            p = path(pin["path"])
            require(hashlib.sha256(p.read_bytes()).hexdigest() == pin["sha256"], "candidate_input_drift")
        payload = path(request["payload_path"]).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == request["payload_sha256"], "payload_pin_mismatch")
        live = json.loads(path(request["live_identity_path"]).read_text())
        now = dt.datetime.now(dt.timezone.utc)
        observed = dt.datetime.fromisoformat(live["observed_at"].replace("Z", "+00:00"))
        require(observed.tzinfo is not None and 0 <= (now - observed).total_seconds() <= 300,
                "fresh_native_identity_required")
        threads = {x["id"]: x for x in live["threads"]}
        require(all(sum(x["id"] == tid for x in live["threads"]) == 1 for tid in [SOURCE, TARGET]),
                "unique_native_threads_required")
        for did, tid in [("paid-growth-data", SOURCE), ("qa", TARGET)]:
            b = departments[did]["chat_binding"]
            require(healthy(b, verification_ttl_hours=26), "registered_health_required")
            require(b["task_id"] == tid and b["project_id"] == PROJECT and b["cwd"] == ROOT,
                    "registered_identity_required")
            t = threads[tid]
            require(t["projectId"] == PROJECT and t["cwd"] == ROOT and t["title"] == b["title"],
                    "native_identity_mismatch")
        require(threads[TARGET]["status"] == "idle", "target_must_be_idle")
        sections = [s for s in live["sections"] if s["name"] == "装修公司部门"]
        require(len(sections) == 1 and sections[0]["sectionId"] == request["target_sidebar_section_id"]
                and all("codex:thread:local:" + tid in sections[0]["itemKeys"] for tid in [SOURCE, TARGET]),
                "unique_native_section_required")
        for key in ["native_attempt_receipt_path", "native_send_receipt_path"]:
            require(not path(request[key]).exists(), "single_use_already_attempted_or_sent")
        return []
    except (KeyError, ValueError, TypeError, OSError) as exc:
        return ["owner_paid_final_qa_denied:" + str(exc)]
