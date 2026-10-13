"""Read-only regressions: current evidence cannot grant platform permissions."""
import copy
import json
import unittest
from unittest.mock import patch

import validate_current_paid_preparation as paid


class CurrentPaidPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads((paid.ROOT / paid.INDEX).read_text())

    def cleanup_index(self):
        # Exercise the actual saved native receipt even before the main agent
        # adopts its pointer. This test fixture does not write the business index.
        index = copy.deepcopy(self.current)
        receipt = json.loads((paid.ROOT / paid.RULE_CLEANUP_RECEIPT).read_text())
        if "latest_rule_cleanup" not in index:
            index["latest_rule_cleanup"] = {
                "candidate_version": receipt["candidate_version"],
                "status": "RUNTIME_RULES_CLEANED_NATIVE_PROMPT_READBACK_VERIFIED",
                "native_receipt": paid.RULE_CLEANUP_RECEIPT,
                "native_receipt_sha256": paid.RULE_CLEANUP_RECEIPT_SHA256,
                "before_prompt_sha256": index["latest_monitor_policy"]["native_prompt_sha256"],
                "after_prompt_sha256": receipt["new_prompt_sha256"],
                "owner_message_id": receipt["owner_message_id"],
                "source_turn_id": receipt["source_turn_id"],
            }
        return index

    def test_current_and_four_historical_versions(self):
        versions = [self.current]
        for name in ("current-preparation-before-old-two-removal.json",
                     "current-preparation-bilingual160-before-English-acceptance.json",
                     "current-preparation-Chinese120-before-bilingual.json",
                     "current-preparation-v42-before-expansion.json"):
            versions.append(json.loads((paid.ROOT / "logs/handoffs/2026-10-10-owner-direct-paid" / name).read_text()))
        for version in versions:
            with self.subTest(version=version["candidate_version"]):
                result = paid.validate(paid.ROOT, version)
                self.assertFalse(result["independent_qa"])
                self.assertFalse(result["machine_enable_permit"])

    def test_current_boundary_mutations_rejected(self):
        cases = [
            (("account_id",), "OTHER"), (("task_id",), "NEW_TASK"),
            (("budget", "combined_ad_fee_myr"), 3000), (("budget", "gross_business_cap_myr"), 5000),
            (("ad_hours_myt",), "ALL_DAY"), (("shop_hours_myt",), "10-22"),
            (("payments",), True), (("recharges",), True),
            (("current_plan_rules", "global_paid_write_flag_still_false"), False),
            (("current_plan_rules", "serial_independent_qa_required_this_owner_batch"), True),
            (("current_bilingual_execution", "English_enabled"), False),
            (("current_bilingual_execution", "keyword_receipt_sha256"), "WRONG"),
            (("current_bilingual_execution", "current_owner_batch_QA_claim"), True),
            (("English_acceptance_execution", "independent_qa"), True),
            (("English_acceptance_execution", "machine_enable_permit"), True),
            (("English_acceptance_execution", "new_global_permission"), True),
            (("English_acceptance_execution", "business_result"), "CUSTOMER_WON"),
            (("English_acceptance_execution", "forms", "sha256"), "WRONG"),
            (("English_form_release", "Ads_live_receipt"), "GOOGLE_CONVERSION_VERIFIED"),
            (("historical_bilingual160_index", "sha256"), "WRONG"),
            (("daily_learning", "current_monitor_save_receipt"), "OTHER"),
            (("current_native_execution", "counts_enabled", "exact_keywords"), 200),
        ]
        for path, value in cases:
            changed = copy.deepcopy(self.current)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises((ValueError, KeyError)):
                paid.validate(paid.ROOT, changed)

    def test_receipt_claims_cannot_replace_actual_bindings(self):
        original_loads = json.loads
        cases = [
            ("forms", lambda r: r.update(owner_received_answer="NOT_RECEIVED")),
            ("forms", lambda r: r["forms"][0].update(source_path="/en/quote")),
            ("forms", lambda r: r["forms"][0].update(submit_count=2)),
            ("forms", lambda r: r["forms"][0].update(url="https://other.invalid/en/quote")),
            ("forms", lambda r: r["formal_statistics_exclusion"].update(both_match_published_STORED_ACCEPTANCE_PATTERN=False)),
            ("forms", lambda r: r["measurement"].update(actual_English_customer_conversion_observed=True)),
            ("Presence", lambda r: r.update(batches_examined=54)),
            ("Presence", lambda r: r.update(current_radio_directly_read=True)),
            ("Presence", lambda r: r.update(later_conflicting_location_option_change_found=True)),
            ("languages", lambda r: r["campaigns"][0].update(languages_native="简体中文")),
            ("enable", lambda r: r["group_states"][0].update(status="PAUSED")),
            ("enable", lambda r: r["group_states"][0].update(rsa_policy="未获批准")),
            ("enable", lambda r: r["group_states"][0].update(final_url="https://company.example/zh/quote")),
            ("enable", lambda r: r.update(new_global_permission=True)),
        ]
        paths = {key: (paid.ROOT / "logs/handoffs/2026-10-10-owner-direct-paid" / value[0]).read_text()
                 for key, value in paid.ACCEPTANCE_RECEIPTS.items()}
        for kind, mutation in cases:
            def altered_loads(text, *args, **kwargs):
                result = original_loads(text, *args, **kwargs)
                if text == paths[kind]:
                    mutation(result)
                return result
            with self.subTest(kind=kind), patch.object(paid.json, "loads", side_effect=altered_loads):
                with self.assertRaises((ValueError, KeyError)):
                    paid.validate(paid.ROOT, self.current)

    def test_current_overlays_do_not_rewrite_historical_boundaries(self):
        changed = copy.deepcopy(self.current)
        changed.pop("latest_rule_cleanup", None)
        changed.pop("latest_monitor_policy", None)
        changed.pop("latest_schedule_change", None)
        changed["ad_hours_myt"] = "MON-SUN10:00-22:00"
        changed["platform_deletion_executed"] = False
        changed.pop("old_two_removal_scope_closed", None)
        result = paid.validate(paid.ROOT, changed)
        self.assertFalse(result["current_schedule24_overlay_verified"])
        self.assertFalse(result["current_night_monitor_overlay_verified"])
        self.assertFalse(result["exact_old_two_removal_overlay_verified"])
        self.assertFalse(result["new_write_permission"])

    def test_current_overlay_index_mutations_rejected(self):
        cases = [
            (("latest_schedule_change", "status"), "PREPARED"),
            (("latest_schedule_change", "campaign_ids"), ["00057225103", "OTHER"]),
            (("latest_schedule_change", "owner_message_id"), "UNAUTHORIZED"),
            (("latest_schedule_change", "native_receipt_sha256"), "WRONG"),
            (("latest_schedule_change", "native_schedule"), "09:45-24:00"),
            (("latest_schedule_change", "shop_hours_unchanged"), False),
            (("latest_schedule_change", "end_date_unchanged"), "2026-10-20"),
            (("latest_monitor_policy", "monitor_times_myt"), [10, 14, 18, 22]),
            (("latest_monitor_policy", "owner_clarification_message_id"), "OTHER"),
            (("latest_monitor_policy", "automation_id"), "NEW_AUTOMATION"),
            (("latest_monitor_policy", "native_prompt_sha256"), "WRONG"),
            (("latest_monitor_policy", "bid_policy"), "All keywords platform-minimum RM0.01; automatic increase allowed"),
            (("latest_monitor_policy", "minimum_sample_is_internal_not_Google"), False),
            (("latest_monitor_policy", "future_unbounded_writes_authorized"), True),
            (("latest_monitor_policy", "overnight_human_watch"), "24H_CONFIRMED"),
            (("old_two_removal_receipt",), "OTHER"),
            (("old_two_removal_scope_closed",), False),
            (("platform_deletion_executed",), False),
        ]
        for path, value in cases:
            changed = copy.deepcopy(self.current)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises((ValueError, KeyError)):
                paid.validate(paid.ROOT, changed)
        changed = copy.deepcopy(self.current)
        changed.pop("latest_schedule_change")
        with self.assertRaisesRegex(ValueError, "without current native overlay"):
            paid.validate(paid.ROOT, changed)

    def test_overlay_native_receipt_semantic_mutations_rejected(self):
        original_loads = json.loads
        cases = [
            (paid.SCHEDULE24_RECEIPT, lambda r: r["campaigns"][0].update(id="OTHER")),
            (paid.SCHEDULE24_RECEIPT, lambda r: r["campaigns"][0].update(hours_per_day=12)),
            (paid.SCHEDULE24_RECEIPT, lambda r: r["campaigns"][1].update(total_budget_myr=1500)),
            (paid.SCHEDULE24_RECEIPT, lambda r: r.update(save_success_native="NOT_SAVED")),
            (paid.SCHEDULE24_RECEIPT, lambda r: r.update(custom_schedule_rows_after_reload=1)),
            (paid.SCHEDULE24_RECEIPT, lambda r: r["protected"].update(payment_actions=1)),
            (paid.SCHEDULE24_AUTHORITY, lambda r: r.update(message_id="NOT_OWNER")),
            (paid.MONITOR2H_RECEIPT, lambda r: r["final_config"].update(rrule="RRULE:FREQ=HOURLY")),
            (paid.MONITOR2H_RECEIPT, lambda r: r["final_config"].update(target_thread_id="OTHER")),
            (paid.MONITOR2H_RECEIPT, lambda r: r["checks"].update(mode_view_success=False)),
            (paid.MONITOR2H_RECEIPT, lambda r: r["execution_counts"].update(ads_bid_writes=1)),
            (paid.MONITOR2H_AUTHORITY, lambda r: r.update(owner_clarification="daytime every2hours")),
            (paid.OLD_TWO_REMOVAL_RECEIPT, lambda r: r["execution"]["removed"][0].update(name="SEARCH_ZH_CORE_CUSTOM_7D")),
            (paid.OLD_TWO_REMOVAL_RECEIPT, lambda r: r["human_authorization"].update(message_id="NOT_OWNER")),
            (paid.OLD_TWO_REMOVAL_RECEIPT, lambda r: r.update(campaign_removals=3)),
            (paid.OLD_TWO_REMOVAL_RECEIPT, lambda r: r.update(budget_writes=1)),
        ]
        for relative, mutation in cases:
            source = (paid.ROOT / relative).read_text()
            def altered_loads(text, *args, **kwargs):
                result = original_loads(text, *args, **kwargs)
                if text == source:
                    mutation(result)
                return result
            with self.subTest(relative=relative), patch.object(paid.json, "loads", side_effect=altered_loads):
                with self.assertRaises((ValueError, KeyError)):
                    paid.validate(paid.ROOT, self.current)

    def test_overlay_evidence_byte_drift_rejected(self):
        original_digest = paid.digest
        for relative in (paid.SCHEDULE24_RECEIPT, paid.SCHEDULE24_AUTHORITY,
                         paid.MONITOR2H_RECEIPT, paid.MONITOR2H_AUTHORITY, paid.OLD_TWO_REMOVAL_RECEIPT):
            expected_path = (paid.ROOT / relative).resolve()
            def altered_digest(path):
                return "WRONG" if path == expected_path else original_digest(path)
            with self.subTest(relative=relative), patch.object(paid, "digest", side_effect=altered_digest):
                with self.assertRaisesRegex(ValueError, "overlay evidence bytes drift"):
                    paid.validate(paid.ROOT, self.current)

    def test_prompt_cleanup_overlay_verifies_without_new_authority(self):
        result = paid.validate(paid.ROOT, self.cleanup_index())
        self.assertTrue(result["current_rule_cleanup_overlay_verified"])
        self.assertTrue(result["current_night_monitor_overlay_verified"])
        self.assertFalse(result["new_write_permission"])
        self.assertFalse(result["independent_qa"])
        self.assertFalse(result["machine_enable_permit"])

    def test_prompt_cleanup_index_mutations_rejected(self):
        cases = {
            "candidate_version": "OTHER", "status": "PREPARED",
            "native_receipt_sha256": "WRONG", "before_prompt_sha256": "WRONG",
            "after_prompt_sha256": "WRONG", "owner_message_id": "NOT_OWNER",
            "source_turn_id": "OTHER",
        }
        for field, value in cases.items():
            index = self.cleanup_index()
            index["latest_rule_cleanup"][field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                paid.validate(paid.ROOT, index)

    def test_prompt_cleanup_receipt_cannot_change_protected_fields(self):
        source = (paid.ROOT / paid.RULE_CLEANUP_RECEIPT).read_text()
        original_loads = json.loads
        cases = [
            lambda r: r["after_config"].update(rrule="RRULE:FREQ=HOURLY"),
            lambda r: r["after_config"].update(status="PAUSED"),
            lambda r: r["after_config"].update(target_thread_id="OTHER"),
            lambda r: r["after_config"].update(name="OTHER"),
            lambda r: r["after_config"].update(id="NEW_AUTOMATION"),
            lambda r: r["after_config"].update(prompt="Automatically raise every keyword to RM10"),
            lambda r: r["before_config"].update(prompt="historical prompt overwritten"),
            lambda r: r.update(no_new_schedule_or_bid_authority=False),
            lambda r: r.update(ads_bid_writes=1),
            lambda r: r.update(account_writes=1),
            lambda r: r.update(owner_message_id="NOT_OWNER"),
        ]
        for mutation in cases:
            index = self.cleanup_index()
            def altered_loads(text, *args, **kwargs):
                result = original_loads(text, *args, **kwargs)
                if text == source:
                    mutation(result)
                return result
            with self.subTest(mutation=mutation), patch.object(paid.json, "loads", side_effect=altered_loads):
                with self.assertRaises((ValueError, KeyError)):
                    paid.validate(paid.ROOT, index)
        original_digest = paid.digest
        expected_path = (paid.ROOT / paid.RULE_CLEANUP_RECEIPT).resolve()
        def altered_digest(path):
            return "WRONG" if path == expected_path else original_digest(path)
        with patch.object(paid, "digest", side_effect=altered_digest):
            with self.assertRaisesRegex(ValueError, "overlay evidence bytes drift"):
                paid.validate(paid.ROOT, self.cleanup_index())


if __name__ == "__main__":
    unittest.main()
