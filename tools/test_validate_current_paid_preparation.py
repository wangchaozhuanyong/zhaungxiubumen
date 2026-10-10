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

    def test_current_and_three_historical_versions(self):
        versions = [self.current]
        for name in ("current-preparation-bilingual160-before-English-acceptance.json",
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
            ("enable", lambda r: r["group_states"][0].update(final_url="https://flashcast.com.my/zh/quote")),
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


if __name__ == "__main__":
    unittest.main()
