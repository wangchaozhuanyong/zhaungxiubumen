from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flashcast_ops as ops


class FlashcastOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_content_queue_draft_and_qa(self) -> None:
        inventory = self.root / "data/content/content-publishing-system-map.csv"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            "target_url,paired_url,language,page_type,content_priority,content_package,rich_media_slots,owner_input_required\n"
            "https://example.com/en/services/kitchen,https://example.com/zh/services/kitchen,en,service,high,service package,hero concept,owner facts\n"
            "https://example.com/zh/services/kitchen,https://example.com/en/services/kitchen,zh,service,high,service package,hero concept,owner facts\n",
            encoding="utf-8",
        )
        payload, _ = ops.build_content_queue(self.root)
        self.assertEqual(payload["queue_count"], 1)
        self.assertEqual(payload["source_state"], "active")

        package, artifacts = ops.create_content_draft(self.root, slot=1)
        self.assertEqual(package["pipeline"], "rich-content")
        self.assertTrue(all(path.exists() for path in artifacts))
        qa, _ = ops.content_qa(self.root, str(artifacts[0]))
        self.assertEqual(qa["status"], "ready_for_owner_review")

    def test_content_qa_blocks_unsupported_price(self) -> None:
        draft = self.root / "draft.md"
        draft.write_text("## 中文页面建议文案\n## English page suggested copy\n价格 RM1000 起。\n", encoding="utf-8")
        payload, _ = ops.content_qa(self.root, str(draft))
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any(item["code"] == "unsupported_claim" for item in payload["findings"]))

    def test_learning_record_is_append_only_and_deduplicated(self) -> None:
        args = argparse.Namespace(
            observed_at="2026-08-30T00:00:00+00:00",
            source="test",
            memory_type="paid_search_review",
            entity="campaign-a",
            signal="clicks without primary conversions",
            evidence="data/google-ads/export.csv",
            outcome="do not scale yet",
            next_action="verify conversion tracking",
            confidence="high",
        )
        first, _ = ops.learning_record(self.root, args)
        second, _ = ops.learning_record(self.root, args)
        self.assertEqual(first["event_count"], 1)
        self.assertEqual(second["event_count"], 1)
        self.assertEqual(len(ops.read_jsonl(self.root / ops.LEARNING_EVENTS)), 1)

    def test_department_learning_record_updates_own_memory_and_deduplicates(self) -> None:
        registry = self.root / "data/learning/department-learning-registry.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            json.dumps(
                {
                    "departments": [
                        {
                            "id": "tracking",
                            "name": "转化追踪部",
                            "memory_path": "data/learning/departments/tracking.json",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        memory = self.root / "data/learning/departments/tracking.json"
        memory.parent.mkdir(parents=True)
        memory.write_text(
            json.dumps(
                {
                    "department": "tracking",
                    "inherited_lessons": [],
                    "verified_lessons": [],
                    "provisional_lessons": [],
                    "blocked_patterns": [],
                    "event_count": 0,
                }
            ),
            encoding="utf-8",
        )
        evidence = self.root / "data/analytics/evidence.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}\n", encoding="utf-8")
        args = argparse.Namespace(
            department="tracking",
            task_id="tracking-learning-001",
            memory_type="conversion_mapping",
            lesson="按钮点击不能直接当作有效线索",
            signal="GA4 有行为动作但销售真值缺失",
            evidence="data/analytics/evidence.json",
            outcome="维持对账阻断",
            next_action="下次先核对事件映射和销售回传",
            confidence="high",
            lesson_status="verified",
            source="test",
            observed_at="2026-08-31T00:00:00+00:00",
        )

        first, artifacts = ops.department_learning_record(self.root, args)
        second, _ = ops.department_learning_record(self.root, args)
        saved = ops.read_json(memory)

        self.assertEqual(first["status"], "department_learning_recorded")
        self.assertEqual(second["status"], "department_learning_duplicate_ignored")
        self.assertEqual(saved["event_count"], 1)
        self.assertEqual(len(saved["verified_lessons"]), 1)
        self.assertTrue(all(path.exists() for path in artifacts))

        status, status_artifacts = ops.department_learning_status(self.root)
        self.assertEqual(status["status"], "department_learning_ready")
        self.assertEqual(status["ready_count"], 1)
        self.assertTrue(all(path.exists() for path in status_artifacts))

    def test_backup_and_rollback_dry_run_then_apply(self) -> None:
        target = self.root / "reports/example.md"
        target.parent.mkdir(parents=True)
        target.write_text("original\n", encoding="utf-8")
        manifest, _ = ops.backup(self.root, "reports/example.md", "test-change-001")
        self.assertEqual(len(manifest["items"]), 1)
        target.write_text("changed\n", encoding="utf-8")
        dry_run, _ = ops.rollback(self.root, "test-change-001", False, False)
        self.assertEqual(dry_run["status"], "rollback_dry_run_ready")
        self.assertEqual(target.read_text(encoding="utf-8"), "changed\n")
        applied, _ = ops.rollback(self.root, "test-change-001", True, True)
        self.assertEqual(applied["status"], "rollback_completed")
        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    def test_workspace_preview_protects_evidence(self) -> None:
        ordinary = self.root / "reports/old-report.md"
        evidence = self.root / "reports/old-rollback-report.md"
        ordinary.parent.mkdir(parents=True)
        ordinary.write_text("old\n", encoding="utf-8")
        evidence.write_text("protected\n", encoding="utf-8")
        old_time = 1
        os.utime(ordinary, (old_time, old_time))
        os.utime(evidence, (old_time, old_time))
        payload, _ = ops.workspace_maintenance(self.root, False, False, 1)
        paths = {item["path"] for item in payload["candidates"]}
        self.assertIn("reports/old-report.md", paths)
        self.assertNotIn("reports/old-rollback-report.md", paths)
        self.assertGreaterEqual(payload["protected_count"], 1)

    def test_local_seo_audit_flags_non_indexable_page(self) -> None:
        inventory = self.root / "data/seo/site-index-inventory.csv"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            "url,language,page_type,http_status,final_url,redirected,robots_allowed,meta_robots,indexable,canonical_url,canonical_self,hreflang_pair,sitemap_included\n"
            "https://example.com/en/test,en,page,200,https://example.com/en/test,no,yes,noindex, no,https://example.com/en/test,yes,no,yes\n".replace("indexable,", "indexable,").replace("noindex, no", "noindex,no"),
            encoding="utf-8",
        )
        payload, _ = ops.seo_index_audit(self.root, "https://example.com", False, 10)
        self.assertEqual(payload["counts"]["with_issues"], 1)
        self.assertIn("noindex_or_not_indexable", payload["rows"][0]["priority_issue"])

    def write_ads_campaign_export(self) -> Path:
        current_data_date = ops.now_utc().date().isoformat()
        path = self.root / f"data/google-ads/{current_data_date}_campaigns.csv"
        path.parent.mkdir(parents=True)
        path.write_text(
            "广告系列,广告系列状态,展示次数,点击次数,费用,转化次数\n"
            "Search - Renovation,已暂停,1000,25,50.00,0\n"
            "总计：广告系列,--,1000,25,50.00,0\n"
            "总计：经理账号,--,1000,25,50.00,0\n",
            encoding="utf-8",
        )
        return path

    def write_historical_lead_log(self) -> Path:
        path = self.root / "data/leads/lead-quality-log.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "lead_id,date,status,qualified,quoted,won\n"
            "lead-anon-1,2026-01-01,low,no,no,no\n",
            encoding="utf-8",
        )
        return path

    def write_sales_funnel_readback(self, submissions_30d: int = 0, observed_at: str | None = None) -> Path:
        observed = observed_at or ops.now_utc().isoformat(timespec="seconds")
        current_date = ops.today()
        path = self.root / ops.SALES_FUNNEL_READBACK
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "observed_at,window_end,source,mode,period_days,submissions,inquiries,quote_requests,contacted,site_visits,quoted,won,total_amount_myr,last_non_test_submission_local,last_non_test_submission_data_date_utc,pii_stored\n"
            f"{observed},{current_date},FLASH CAST admin lead reports,read_only,30,{submissions_30d},0,0,0,0,0,0,0,2026-01-02T00:00:00+08:00,2026-01-01,no\n"
            f"{observed},{current_date},FLASH CAST admin lead reports,read_only,90,{submissions_30d},0,0,0,0,0,0,0,2026-01-02T00:00:00+08:00,2026-01-01,no\n",
            encoding="utf-8",
        )
        return path

    def test_source_manifest_marks_empty_templates_as_gaps(self) -> None:
        ops.init_project(self.root)
        self.write_ads_campaign_export()
        payload, artifacts = ops.source_manifest(self.root)
        self.assertEqual(payload["status"], "growth_source_manifest_ready")
        sources = {row["source"]: row for row in payload["sources"]}
        self.assertEqual(sources["Google Ads campaigns"]["status"], "ready_fresh")
        self.assertEqual(sources["Google Ads campaigns"]["freshness_basis"], "filename_data_end")
        self.assertEqual(sources["GA4 consultation actions"]["status"], "empty")
        self.assertEqual(sources["Lead quality log"]["status"], "empty")
        self.assertEqual(sources["Google Ads conversion actions"]["status"], "missing")
        self.assertTrue(sources["Google Ads conversion actions"]["required_for_core_decision"])
        self.assertEqual(sources["GA4 organic traffic"]["status"], "missing")
        self.assertEqual(sources["Google Search Console organic performance"]["status"], "missing")
        health = ops.read_json(self.root / "data/data-health.json")
        self.assertEqual(health["status"], "data_health_blocked")
        self.assertTrue(any("conversion actions" in item for item in health["blockers"]))
        self.assertFalse(any("conversion actions" in item for item in health["warnings"]))
        self.assertTrue(all(path.exists() for path in artifacts))

    def test_source_manifest_prefers_latest_data_end_over_newer_mtime(self) -> None:
        analytics = self.root / "data/analytics"
        analytics.mkdir(parents=True)
        historical = analytics / "2026-08-21_2026-09-17_gsc-organic-performance.csv"
        current = analytics / "2026-08-26_2026-09-22_gsc-organic-performance.csv"
        csv_text = "clicks,window_start,window_end,extracted_at\n1,2026-01-01,2026-01-02,2026-09-25T10:00:00+00:00\n"
        historical.write_text(csv_text, encoding="utf-8")
        current.write_text(csv_text, encoding="utf-8")
        os.utime(current, (1000, 1000))
        os.utime(historical, (2000, 2000))

        selected = ops.source_files(
            self.root, Path("data/analytics"), ("gsc-organic-performance",)
        )
        self.assertEqual(selected[0], current)

        payload, _ = ops.source_manifest(self.root)
        sources = {row["source"]: row for row in payload["sources"]}
        self.assertEqual(
            sources["Google Search Console organic performance"]["path"],
            "data/analytics/2026-08-26_2026-09-22_gsc-organic-performance.csv",
        )
        self.assertEqual(
            sources["Google Search Console organic performance"]["data_end"],
            "2026-09-22",
        )

    def test_source_files_same_data_end_prefers_explicit_extraction_time(self) -> None:
        analytics = self.root / "data/analytics"
        analytics.mkdir(parents=True)
        earlier_extract = analytics / "2026-09-01_2026-09-22_gsc-organic-performance-a.csv"
        later_extract = analytics / "2026-09-01_2026-09-22_gsc-organic-performance-b.csv"
        earlier_extract.write_text(
            "clicks,extracted_at\n1,2026-09-25T10:00:00+00:00\n", encoding="utf-8"
        )
        later_extract.write_text(
            "clicks,extracted_at\n1,2026-09-25T12:00:00+00:00\n", encoding="utf-8"
        )
        os.utime(later_extract, (1000, 1000))
        os.utime(earlier_extract, (2000, 2000))

        selected = ops.source_files(
            self.root, Path("data/analytics"), ("gsc-organic-performance",)
        )
        self.assertEqual(selected[0], later_extract)

    def test_source_files_without_data_dates_fall_back_to_mtime(self) -> None:
        analytics = self.root / "data/analytics"
        analytics.mkdir(parents=True)
        older = analytics / "gsc-organic-performance-a.csv"
        newer = analytics / "gsc-organic-performance-b.csv"
        older.write_text("clicks\n1\n", encoding="utf-8")
        newer.write_text("clicks\n2\n", encoding="utf-8")
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))

        selected = ops.source_files(
            self.root, Path("data/analytics"), ("gsc-organic-performance",)
        )
        self.assertEqual(selected[0], newer)

    def test_source_files_isolates_unreadable_archive_but_selected_bad_file_is_invalid(self) -> None:
        analytics = self.root / "data/analytics"
        analytics.mkdir(parents=True)
        archived = analytics / "2026-08-21_2026-09-17_gsc-organic-performance.csv"
        current = analytics / "2026-08-26_2026-09-22_gsc-organic-performance.csv"
        archived.write_bytes(b"\xff\xfe\x80")
        current.write_text(
            "clicks,window_start,window_end\n1,2026-08-26,2026-09-22\n",
            encoding="utf-8",
        )
        os.utime(archived, (1000, 1000))
        os.utime(current, (2000, 2000))

        selected = ops.source_files(
            self.root, Path("data/analytics"), ("gsc-organic-performance",)
        )
        self.assertEqual(selected[0], current)

        selected_bad = analytics / "2026-09-01_2026-09-24_gsc-organic-performance.csv"
        selected_bad.write_bytes(b"\xff\xfe\x80")
        payload, _ = ops.source_manifest(self.root)
        sources = {row["source"]: row for row in payload["sources"]}
        gsc = sources["Google Search Console organic performance"]
        self.assertEqual(gsc["path"], selected_bad.relative_to(self.root).as_posix())
        self.assertEqual(gsc["status"], "invalid")
        self.assertFalse(gsc["decision_usable"])

    def test_source_manifest_accepts_fresh_zero_activity_sales_readback(self) -> None:
        self.write_historical_lead_log()
        self.write_sales_funnel_readback(submissions_30d=0)

        payload, _ = ops.source_manifest(self.root)
        sources = {row["source"]: row for row in payload["sources"]}

        self.assertEqual(sources["Sales funnel live readback"]["status"], "ready_fresh")
        self.assertTrue(sources["Sales funnel live readback"]["decision_usable"])
        self.assertEqual(sources["Lead quality log"]["status"], "ready_stale")
        self.assertFalse(sources["Lead quality log"]["required_for_core_decision"])
        self.assertIn("0 new submissions", sources["Lead quality log"]["decision_use"])

    def test_conversion_reconcile_uses_fresh_zero_activity_readback_without_rewriting_last_lead_date(self) -> None:
        self.write_historical_lead_log()
        self.write_sales_funnel_readback(submissions_30d=0)

        payload, _ = ops.conversion_reconcile(self.root)

        self.assertTrue(payload["lead_truth"]["truth_current"])
        self.assertEqual(payload["lead_truth"]["decision_freshness_basis"], "sales_funnel_live_readback")
        self.assertEqual(payload["lead_truth"]["decision_age_days"], 0)
        self.assertEqual(payload["lead_truth"]["live_readback"]["new_submissions_30d"], 0.0)
        self.assertEqual(payload["lead_truth"]["data_end"], "2026-01-01")
        self.assertFalse(any("销售漏斗现场回读" in item for item in payload["blockers"]))
        self.assertFalse(any("销售线索真值已过期" in item for item in payload["blockers"]))

    def test_conversion_reconcile_blocks_missing_readback_or_unclassified_new_submissions(self) -> None:
        self.write_historical_lead_log()
        missing_payload, _ = ops.conversion_reconcile(self.root)
        self.assertTrue(any("销售漏斗现场回读缺失" in item for item in missing_payload["blockers"]))

        self.write_sales_funnel_readback(submissions_30d=2)
        new_submission_payload, _ = ops.conversion_reconcile(self.root)
        self.assertTrue(any("新增提交" in item for item in new_submission_payload["blockers"]))

    def test_conversion_reconcile_does_not_turn_missing_data_into_zero(self) -> None:
        self.write_ads_campaign_export()
        payload, _ = ops.conversion_reconcile(self.root)
        self.assertEqual(payload["status"], "conversion_reconciliation_blocked")
        self.assertEqual(payload["ads"]["clicks"], 25.0)
        self.assertEqual(payload["ads"]["spend_myr"], 50.0)
        self.assertEqual(len(payload["ads"]["campaigns"]), 1)
        self.assertIsNone(payload["ga4"]["actions"])
        self.assertIsNone(payload["lead_truth"]["lead_count"])
        self.assertTrue(any("0 个主要转化" in item for item in payload["blockers"]))

    def test_ga4_summary_uses_latest_window_and_exposes_key_event_gap(self) -> None:
        path = self.root / "data/analytics/ga4-consultation-actions.csv"
        path.parent.mkdir(parents=True)
        path.write_text(
            "window_start,window_end,scope,event_name,source_medium,action_count,unique_users,sessions,key_event_status\n"
            "2026-08-02,2026-08-31,all_website_union,all_consultation_events,,11,9,9,\n"
            "2026-08-02,2026-08-31,source_campaign_union,all_consultation_events,google / cpc,4,4,4,\n"
            "2026-08-23,2026-09-19,all_website_union,all_consultation_events,,11,,,not_marked\n"
            "2026-08-23,2026-09-19,all_website_by_event,quote_form_success,,10,10,,not_marked\n"
            "2026-08-23,2026-09-19,all_website_by_event,whatsapp_click,,1,1,,not_marked\n"
            "2026-08-23,2026-09-19,source_campaign_union,all_consultation_events,google / cpc,0,0,,not_marked\n",
            encoding="utf-8",
        )
        ga4 = ops.summarize_ga4(self.root)
        self.assertEqual(ga4["actions"], 11.0)
        self.assertEqual(ga4["by_event"]["quote_form_success"], 10.0)
        self.assertEqual(ga4["paid_search_actions"], 0.0)
        self.assertEqual(ga4["paid_search_actions_by_window"]["2026-08-02..2026-08-31"], 4.0)
        self.assertFalse(ga4["key_events_configured"])
        self.assertEqual(ga4["data_end"], "2026-09-19")

    def test_ads_conversion_actions_expose_primary_tracking_issues(self) -> None:
        data_end = ops.now_utc().date().isoformat()
        path = self.root / f"data/google-ads/{data_end}_conversion-actions.csv"
        path.parent.mkdir(parents=True)
        path.write_text(
            "window_start,window_end,Conversion action,Status,Source,Tracking status,Action optimization,Count,Click-through conversion window,Included in account-level goals,Conversions,Conversion value,Conversion action ID,Destination\n"
            f"2026-08-21,{data_end},FLASH CAST - Quote Form Success,Enabled,Website,Needs attention,Primary,Once,90 days,Yes,0,0,7697661488,AW-18205206146\n"
            f"2026-08-21,{data_end},Calls from ads,Enabled,Calls directly from ads,No recent conversions,Primary,Every,30 days,Yes,0,0,,\n"
            f"2026-08-21,{data_end},FLASH CAST - WhatsApp Click,Enabled,Website,Needs attention,Secondary,Once,90 days,No,0,0,,\n",
            encoding="utf-8",
        )

        summary = ops.summarize_ads_conversion_actions(self.root)
        self.assertEqual(summary["action_count"], 3)
        self.assertEqual(summary["primary_action_count"], 2)
        self.assertEqual(summary["primary_tracking_issue_count"], 1)
        self.assertEqual(summary["primary_actions_needing_attention"], ["FLASH CAST - Quote Form Success"])
        self.assertEqual(summary["actions"][0]["conversion_action_id"], "7697661488")
        self.assertEqual(summary["actions"][0]["destination"], "AW-18205206146")

        payload, _ = ops.conversion_reconcile(self.root)
        self.assertTrue(any("Quote Form Success" in item for item in payload["blockers"]))

    def test_action_queue_creates_p0_for_tracking_and_data_gaps(self) -> None:
        self.write_ads_campaign_export()
        payload, artifacts = ops.action_queue(self.root)
        self.assertGreaterEqual(payload["action_count"], 2)
        self.assertTrue(any(item["priority"] == "P0" for item in payload["actions"]))
        self.assertTrue(all(path.exists() for path in artifacts))

    def test_handoff_and_run_ledger_keep_department_evidence(self) -> None:
        args = argparse.Namespace(
            task_id="ads-daily-test",
            from_department="analytics",
            to_department="ads",
            completed="完成本地数据检查",
            unfinished="等待负责人确认",
            evidence="data/source-manifest.json",
            cannot_assume="导出不等于实时状态",
            next_action="审核行动队列",
            owner_approval_required=True,
        )
        payload, artifacts = ops.handoff(self.root, args)
        self.assertEqual(payload["status"], "waiting_receiver_action")
        self.assertTrue(all(path.exists() for path in artifacts))
        ledger, ledger_artifacts = ops.run_ledger_report(self.root)
        self.assertGreaterEqual(ledger["run_count"], 1)
        self.assertTrue(all(path.exists() for path in ledger_artifacts))

    def test_dispatch_plan_routes_minimum_departments_and_blocks_unverified_chats(self) -> None:
        data = self.root / "data"
        data.mkdir(parents=True)
        (data / "department-registry.json").write_text(
            """{
              "departments": [
                {"id": "analytics", "name": "数据部", "role_config": ".codex/agents/analytics.toml", "department_readme": "departments/analytics/README.md", "chat_binding": {"title": "数据部", "status": "pending_ui_verification", "task_id": null}, "input_paths": ["data/"], "output_paths": ["logs/department-outbox/"]},
                {"id": "ads", "name": "广告部", "role_config": ".codex/agents/ads.toml", "department_readme": "departments/ads/README.md", "chat_binding": {"title": "广告部", "status": "bound_and_visible", "task_id": "ads-task"}, "input_paths": ["data/google-ads/"], "output_paths": ["reports/"]},
                {"id": "qa", "name": "质检部", "role_config": ".codex/agents/qa.toml", "department_readme": "departments/qa/README.md", "chat_binding": {"title": "质检部", "status": "pending_ui_verification", "task_id": null}, "input_paths": ["reports/"], "output_paths": ["reports/"]}
              ]
            }""",
            encoding="utf-8",
        )
        (data / "department-routing-rules.json").write_text(
            """{
              "routes": [{"id": "google-ads-audit", "match_any": ["Google Ads", "关键词"], "required_departments": ["analytics", "ads"], "parallel_departments": ["analytics", "ads"], "follow_up_departments": ["qa"], "approval_required": true}],
              "fallback": {"required_departments": ["analytics"], "follow_up_departments": ["qa"]}
            }""",
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(
            '{"completion_rule":"chat + outbox + evidence"}\n',
            encoding="utf-8",
        )
        args = argparse.Namespace(request="分析 Google Ads 关键词", task_id="dispatch-test-001")

        payload, artifacts = ops.dispatch_plan(self.root, args)

        self.assertEqual(payload["status"], "blocked_ui_visibility")
        self.assertEqual(payload["parallel_departments"], ["analytics", "ads"])
        self.assertEqual(payload["follow_up_departments"], ["qa"])
        self.assertEqual(payload["blocked_departments"], ["analytics", "qa"])
        self.assertTrue(all(path.exists() for path in artifacts))
        saved = ops.read_json(self.root / "logs/dispatch/dispatch-test-001.json")
        self.assertEqual(saved["route"]["id"], "google-ads-audit")
        self.assertEqual(saved["mode"], "plan_only_no_chat_side_effects")

    def test_dispatch_plan_merges_multiple_intents(self) -> None:
        data = self.root / "data"
        data.mkdir(parents=True)
        registry = []
        for department in ["analytics", "ads", "content", "tracking", "website", "qa"]:
            registry.append(
                {
                    "id": department,
                    "name": department,
                    "role_config": f".codex/agents/{department}.toml",
                    "department_readme": f"departments/{department}/README.md",
                    "chat_binding": {"title": department, "status": "bound_and_visible", "task_id": f"{department}-task"},
                    "input_paths": ["data/"],
                    "output_paths": ["reports/"]
                }
            )
        (data / "department-registry.json").write_text(json.dumps({"departments": registry}), encoding="utf-8")
        (data / "department-routing-rules.json").write_text(
            json.dumps(
                {
                    "routes": [
                        {"id": "ads", "match_any": ["Google Ads"], "required_departments": ["analytics", "ads"], "parallel_departments": ["analytics", "ads"], "follow_up_departments": ["qa"]},
                        {"id": "content", "match_any": ["广告文案", "旧屋翻新"], "required_departments": ["content"], "parallel_departments": ["content"], "follow_up_departments": ["qa"]},
                        {"id": "conversion", "match_any": ["没有主要转化"], "required_departments": ["analytics", "tracking", "website"], "parallel_departments": ["analytics", "tracking", "website"], "follow_up_departments": ["qa"]}
                    ],
                    "fallback": {"required_departments": ["analytics"], "follow_up_departments": ["qa"]}
                }
            ),
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(json.dumps({"completion_rule": "all"}), encoding="utf-8")

        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="分析 Google Ads；写旧屋翻新广告文案；检查为什么没有主要转化",
                task_id="dispatch-multi-001",
            ),
        )

        self.assertEqual(payload["route"]["source"], "matched_multi")
        self.assertEqual(
            payload["parallel_departments"],
            ["analytics", "ads", "content", "tracking", "website"],
        )
        self.assertEqual(payload["follow_up_departments"], ["qa"])

    def test_dispatch_plan_blocks_visible_chat_with_failed_reply_health(self) -> None:
        data = self.root / "data"
        data.mkdir(parents=True)
        (data / "department-registry.json").write_text(
            json.dumps(
                {
                    "departments": [
                        {
                            "id": "content",
                            "name": "内容部",
                            "role_config": ".codex/agents/content.toml",
                            "department_readme": "departments/content/README.md",
                            "chat_binding": {
                                "title": "内容部",
                                "status": "bound_and_visible",
                                "task_id": "content-task",
                                "reply_health": "degraded_empty_assistant_turns",
                                "dispatch_eligible": False,
                            },
                            "input_paths": ["data/"],
                            "output_paths": ["reports/"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (data / "department-routing-rules.json").write_text(
            json.dumps(
                {
                    "routes": [
                        {
                            "id": "content",
                            "match_any": ["文案"],
                            "required_departments": ["content"],
                            "parallel_departments": ["content"],
                            "follow_up_departments": [],
                        }
                    ],
                    "fallback": {"required_departments": ["content"], "follow_up_departments": []},
                }
            ),
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(
            json.dumps({"completion_rule": "all"}),
            encoding="utf-8",
        )

        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(request="制作公司文案", task_id="dispatch-health-001"),
        )

        self.assertEqual(payload["status"], "blocked_chat_health")
        self.assertEqual(payload["blocked_departments"], ["content"])
        self.assertEqual(payload["departments"][0]["dispatch_status"], "blocked_chat_health")
        self.assertEqual(payload["departments"][0]["chat_reply_health"], "degraded_empty_assistant_turns")
        self.assertFalse(payload["departments"][0]["dispatch_eligible"])

    def test_old_house_lead_video_routes_only_to_visual_then_qa(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        data = self.root / "data"
        data.mkdir(parents=True)
        registry = []
        for department in [
            "operations",
            "paid-growth-data",
            "content-organic-website",
            "visual-design-video",
            "sales",
            "qa",
        ]:
            registry.append(
                {
                    "id": department,
                    "name": department,
                    "role_config": f".codex/agents/{department}.toml",
                    "department_readme": f"departments/{department}/README.md",
                    "professional_skill": f"departments/{department}/SKILL.md",
                    "chat_binding": {
                        "title": department,
                        "status": "bound_and_visible",
                        "task_id": f"{department}-task",
                    },
                    "input_paths": ["data/"],
                    "output_paths": ["reports/"],
                }
            )
        (data / "department-registry.json").write_text(
            json.dumps({"departments": registry}),
            encoding="utf-8",
        )
        (data / "department-routing-rules.json").write_text(
            (project_root / "data/department-routing-rules.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(
            (project_root / "data/task-contract.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="给装修公司做一条能够获取吉隆坡旧屋翻新客户的视频，其他你们自己决定。",
                task_id="dispatch-video-001",
            ),
        )

        self.assertEqual(payload["route"]["id"], "visual-video-production")
        self.assertEqual(payload["required_departments"], ["visual-design-video"])
        self.assertEqual(payload["parallel_departments"], ["visual-design-video"])
        self.assertEqual(payload["follow_up_departments"], ["qa"])
        self.assertEqual(payload["controller_action"], "dispatch_and_wait")
        self.assertFalse(payload["controller_may_execute_specialist_work"])
        self.assertEqual(payload["specialist_departments"], ["visual-design-video", "qa"])
        self.assertEqual(payload["dispatch_gate"]["on_failure"], "blocked_no_controller_fallback")

    def test_content_and_cro_routes_do_not_pull_paid_without_measurement_intent(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        data = self.root / "data"
        data.mkdir(parents=True)
        registry = []
        for department, subskills in [
            ("content-organic-website", ["renovation-seo-geo"]),
            ("paid-growth-data", ["google-ads-renovation-ppc"]),
            ("qa", []),
        ]:
            registry.append(
                {
                    "id": department,
                    "name": department,
                    "role_config": f".codex/agents/{department}.toml",
                    "department_readme": f"departments/{department}/README.md",
                    "professional_skill": f"departments/{department}/SKILL.md",
                    "approved_subskills": subskills,
                    "approved_subskill_paths": [f"/skills/{name}/SKILL.md" for name in subskills],
                    "chat_binding": {
                        "title": department,
                        "status": "bound_and_visible",
                        "task_id": f"{department}-task",
                    },
                    "input_paths": ["data/"],
                    "output_paths": ["reports/"],
                }
            )
        (data / "department-registry.json").write_text(
            json.dumps({"departments": registry}),
            encoding="utf-8",
        )
        (data / "department-routing-rules.json").write_text(
            (project_root / "data/department-routing-rules.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (data / "task-contract.json").write_text(
            json.dumps({"completion_rule": "all"}),
            encoding="utf-8",
        )

        payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(request="写一版旧屋翻新广告文案", task_id="dispatch-content-wave-001"),
        )

        self.assertEqual(payload["route"]["id"], "content-campaign")
        self.assertEqual(
            payload["execution_waves"],
            [["content-organic-website"], ["qa"]],
        )
        plans = {item["department"]: item for item in payload["departments"]}
        self.assertEqual(plans["content-organic-website"]["approved_subskills"], ["renovation-seo-geo"])
        self.assertNotIn("paid-growth-data", plans)
        self.assertEqual(plans["qa"]["depends_on"], ["content-organic-website"])

        cro_payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="SEO 页面制作报价表单隐私提示和可访问成功失败状态草案，不修改网站，不调用付费部门",
                task_id="dispatch-content-cro-001",
            ),
        )

        self.assertEqual(cro_payload["parallel_departments"], ["content-organic-website"])
        self.assertEqual(cro_payload["follow_up_departments"], ["qa"])
        self.assertNotIn("paid-growth-data", cro_payload["specialist_departments"])

        measurement_payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="核对 GA4 和 GTM 表单送达追踪、事件去重与归因",
                task_id="dispatch-measurement-001",
            ),
        )

        self.assertEqual(
            measurement_payload["parallel_departments"],
            ["paid-growth-data", "content-organic-website"],
        )
        self.assertEqual(measurement_payload["follow_up_departments"], ["qa"])

        source_payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request=(
                    "FLASH CAST 转化数据来源补数收口：付费增长与转化数据部核对 GSC/GA4 自然搜索脱敏来源；"
                    "内容、SEO与网站增长部复核日报，固定 QA 检查；不修改广告、预算或网站。"
                ),
                task_id="dispatch-organic-source-readonly-001",
            ),
        )
        self.assertEqual(source_payload["route"]["id"], "organic-measurement-source-refresh-readonly")
        self.assertEqual(source_payload["parallel_departments"], ["paid-growth-data", "content-organic-website"])
        self.assertEqual(source_payload["follow_up_departments"], ["qa"])
        self.assertFalse(source_payload["route"]["approval_required"])

        unsafe_payload, _ = ops.dispatch_plan(
            self.root,
            argparse.Namespace(
                request="诊断 GA4 转化追踪和广告预算异常",
                task_id="dispatch-conversion-sensitive-001",
            ),
        )
        self.assertTrue(unsafe_payload["route"]["approval_required"])

    def test_qa_gate_blocks_external_action_when_evidence_is_incomplete(self) -> None:
        self.write_ads_campaign_export()
        ops.source_manifest(self.root)
        ops.conversion_reconcile(self.root)
        ops.action_queue(self.root)
        payload, artifacts = ops.qa_gate(self.root, "google-ads-daily")
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["checks"]["content_qa"])
        self.assertTrue(any("GA4" in item or "线索" in item for item in payload["blockers"]))
        self.assertTrue(all(path.exists() for path in artifacts))

    def test_secret_scan_avoids_skill_name_false_positive(self) -> None:
        document = self.root / "logs/notes.md"
        document.parent.mkdir(parents=True)
        document.write_text("历史目录 skill-zhuangxiuseogeo 只读保留。\n", encoding="utf-8")
        self.assertEqual(ops.scan_active_secrets(self.root), [])
        document.write_text("api_key=not-a-real-key-but-flagged\n", encoding="utf-8")
        self.assertEqual(ops.scan_active_secrets(self.root), ["logs/notes.md"])

    def test_secret_scan_ignores_generated_node_modules_docs(self) -> None:
        document = self.root / "drafts/generated/node_modules/dotenv/README.md"
        document.parent.mkdir(parents=True)
        document.write_text("api_key=example-only\n", encoding="utf-8")
        self.assertEqual(ops.scan_active_secrets(self.root), [])

    def test_secret_scan_public_signature_does_not_mask_private_material(self) -> None:
        document = self.root / "logs/commit.json"
        document.parent.mkdir(parents=True)
        public_signature = "-----BEGIN PGP SIGNATURE-----\npublic-fixture\n-----END PGP SIGNATURE-----"
        document.write_text(json.dumps({"verification": {"signature": public_signature}}), encoding="utf-8")
        self.assertEqual(ops.scan_active_secrets(self.root), [])
        for sensitive_fixture in (
            "-----BEGIN PRIVATE KEY-----\nsynthetic-fixture",
            "-----BEGIN RSA PRIVATE KEY-----\nsynthetic-fixture",
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsynthetic-fixture",
            "-----BEGIN PGP SIGNATURE PRIVATE KEY-----\nsynthetic-fixture",
            "api_key=synthetic-credential-fixture",
            "sk-proj-" + "x" * 24,
            "AIza" + "x" * 24,
        ):
            with self.subTest(kind=sensitive_fixture.split("\\n")[0][:40]):
                document.write_text(json.dumps({"verification": {"signature": public_signature}, "other": sensitive_fixture}), encoding="utf-8")
                self.assertEqual(ops.scan_active_secrets(self.root), ["logs/commit.json"])

    def test_migrate_historical_inputs_only_fills_empty_active_tables(self) -> None:
        history = self.root / "history/skill-zhuangxiuseogeo/seo-workspace/data"
        history.mkdir(parents=True)
        (history / "ga4-consultation-actions.csv").write_text(
            "window_start,window_end,scope,event_name,source_medium,action_count,unique_users,sessions\n"
            "2026-08-02,2026-08-31,all_website_union,all_consultation_events,,11,9,9\n"
            "2026-08-02,2026-08-31,all_website_by_event,phone_click,,6,5,5\n"
            "2026-08-02,2026-08-31,source_campaign_union,all_consultation_events,google / cpc,4,4,4\n",
            encoding="utf-8",
        )
        (history / "lead-quality-log.csv").write_text(
            "lead_ref,date,source,service_type,service_area,contact_channel,lead_quality,quoted,won,revenue_myr\n"
            "lead-old,2026-08-04,website,residential_renovation,kuala_lumpur,quote,low,no,no,0\n",
            encoding="utf-8",
        )
        ops.init_project(self.root)
        payload, artifacts = ops.migrate_historical_inputs(self.root)
        self.assertEqual(payload["status"], "historical_inputs_migrated")
        self.assertEqual(len(payload["migrated"]), 2)
        self.assertEqual(len(ops.read_csv(self.root / "data/analytics/ga4-consultation-actions.csv")), 3)
        ga4 = ops.summarize_ga4(self.root)
        self.assertEqual(ga4["actions"], 11.0)
        self.assertEqual(ga4["by_event"]["phone_click"], 6.0)
        self.assertEqual(ga4["paid_search_actions"], 4.0)
        leads = ops.read_csv(self.root / "data/leads/lead-quality-log.csv")
        self.assertEqual(leads[0]["lead_id"], "lead-old")
        self.assertEqual(leads[0]["qualified"], "no")
        self.assertTrue(all(path.exists() for path in artifacts))


if __name__ == "__main__":
    unittest.main()
