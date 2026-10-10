"""Read-only integrity check for the owner's current paid preparation index.

No login, platform actions, policy writes, QA verdict, or enable permission.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = "data/google-ads/current-preparation.json"
NATIVE_EXPANSION_VERSION = "paid-owner-direct-native-expansion-20261010"
HISTORICAL_V42_SHA256 = "24ec3b3f76217e0c188e1129a1ca141f7ec42cf83fddb1f99bfc928a28757018"
NATIVE_120_PRICE_SHA256 = "6e8cc2ffd86bcd49ead60783ba0a0989dd2a3c9fa9e57aa707133955fb29caf9"
NATIVE_120_RECEIPT = "logs/handoffs/2026-10-10-owner-direct-paid/keywords-120-native-readback.json"
NATIVE_OWNER_AUTHORITY = "logs/handoffs/2026-10-10-owner-direct-paid/authority-and-execution.json"
BILINGUAL_NATIVE_VERSION = "paid-owner-direct-bilingual-native-20261010"
HISTORICAL_CHINESE120_SHA256 = "ce490f6d07806c223c6ba4fb06410de560750096c51ce851f2291844d00de54c"
HISTORICAL_CHINESE120_INDEX = "logs/handoffs/2026-10-10-owner-direct-paid/current-preparation-Chinese120-before-bilingual.json"
ENGLISH40_RECEIPT = "logs/handoffs/2026-10-10-owner-direct-paid/keywords-English40-native-readback.json"
ENGLISH40_RECEIPT_SHA256 = "2683eaba1cfce2f7cfaac01bdebf4459efd88fea4f449e7a2de33735c4c141ea"
ENGLISH40_PRICE_SHA256 = "1076accd6bd40a3997c0063ebc48212393c55f5e4b42fa065b09b85e94e26b9c"
BILINGUAL_ASSET_RECEIPT = "logs/handoffs/2026-10-10-owner-direct-paid/bilingual-assets-native-readback.json"
BILINGUAL_ASSET_SHA256 = "771cbefcdf08a4e79e6934aa1ba8537bd877afa26a3434642918cdca52edbe23"
BILINGUAL_ASSET_SCOPE = "logs/handoffs/2026-10-10-owner-direct-paid/bilingual-association-execution-scope.json"
BILINGUAL_ASSET_SCOPE_SHA256 = "2eb3187f131668a82ceb351261531ed3b6225804824e08f3c1aee471fcefa879"
ENGLISH_ENABLED_VERSION = "paid-owner-direct-English-enabled-20261010"
BILINGUAL160_SNAPSHOT = "logs/handoffs/2026-10-10-owner-direct-paid/current-preparation-bilingual160-before-English-acceptance.json"
BILINGUAL160_SNAPSHOT_SHA256 = "69dd0b089ba75d4a5fe2dd13be9aa987ae063a75f88235b76920828e805e6f6d"
ACCEPTANCE_RECEIPTS = {
    "languages": ("bilingual-campaign-language-native-readback.json", "3902e6f3f10d6097eb28ecce7e7b9b60fa7d8a6a0f2a859a7075e89538ee8c51"),
    "Presence": ("renovation-Presence-history-acceptance.json", "63653a8c8e3243bc87a62752280ed0d6b43544a7a8d5cb7f376934d22a368c1c"),
    "forms": ("English-two-form-production-acceptance.json", "0de953b3e7e6e97537d466f5228ed8525d1dac623bc776bad5d441887834758d"),
    "enable": ("English-six-groups-enable-native-readback.json", "503848430693f142bab7be6794f0e85615907f9a567ff2654711eeab805ee2dc"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def project_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(root.resolve() in path.parents, "reference leaves project")
    require(path.is_file(), f"missing reference: {relative}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def keyword_rows(path: Path) -> list[dict[str, str]]:
    # Native Ads CSV exports have two report-title/date lines before the header.
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[2:]))))
    # Totals appended by Ads are aggregate rows, never activation inputs.
    return [row for row in rows if row.get("关键字", "").strip()]


def validate_native_launch(root: Path, current: dict) -> None:
    """Validate the recorded exact V42 execution, never issue a new write permit."""
    require(current["candidate_version"] == "paid-owner-completion-v42", "unknown launch version")
    rules = current["current_plan_rules"]
    require(rules["execution_released"] and rules["whole_launch_complete"], "incomplete launch flags")
    require(rules["global_paid_write_flag_still_false"], "global paid guard must remain closed")
    receipt = json.loads(project_file(root, rules["native_execution_receipt"]).read_text())
    require(receipt["status"] == "ACTUALLY_ENABLED_NATIVE_READBACK_VERIFIED"
            and receipt["source_method"] == "cua_repl_native_google_ads_ui"
            and receipt["account_id"] == current["account_id"], "actual exact-account readback required")
    require(receipt["policy_decision_id"] == rules["policy_decision_id"] == "pol-df978512f57a3653b708"
            and receipt["scope"] == "owner_paid_completion:example-ads-account:v42:enable-two-new-search", "exact historical permit mismatch")
    require([c["id"] for c in receipt["campaigns"]] == [c["id"] for c in current["campaigns"]]
            and all(c["status"] == "ENABLED" and c["total_ad_fee_myr"] == 1350 for c in receipt["campaigns"]), "native campaign identity or state mismatch")
    require([x["sequence"] for x in receipt["operations"]] == [1, 2, 3, 4]
            and receipt["operations"][-1]["action"] == "ENABLE_ONLY_TWO_NEW_PARENT_CAMPAIGNS_LAST", "parent-last execution missing")
    require(len(receipt["groups"]) == 6 and all(x["status"] == "ENABLED" for x in receipt["groups"])
            and receipt["rsa"]["enabled_count"] == receipt["rsa"]["eligible_count"] == 6, "child enable readback missing")
    require(len(receipt["old_campaigns"]) == 2 and all(x["status"] == "PAUSED" and not x["changed"] for x in receipt["old_campaigns"]), "old campaign isolation drift")
    require(not receipt["payments"] and not receipt["recharges"] and not receipt["campaigns_removed"], "financial or removal scope drift")
    proof = json.loads(project_file(root, rules["independent_qa_native_proof"]).read_text())
    qa_path = project_file(root, proof["outbox"]["path"])
    require(digest(qa_path) == proof["outbox"]["sha256"], "independent QA outbox drift")
    qa = json.loads(qa_path.read_text())
    require(qa["department"] == "qa" and qa["qa_verdict"] == "pass"
            and qa["candidate_version"] == current["candidate_version"], "independent exact-version PASS missing")
    reply = proof["native_reply"]
    require(reply["turn_status"] == "completed" and reply["nonempty"]
            and reply["thread_id"] == "<LOCAL_TASK_ID>"
            and reply["message_id"] == qa["chat_reply"]["message_id"], "native independent completion missing")
    readback = json.loads(project_file(root, receipt["keywords"]["readback"]).read_text())
    actual = readback["keywords"]
    require(len(actual) == 40 and len({(x["campaign"], x["group"], x["keyword"]) for x in actual}) == 40, "actual40 distinct keywords required")
    require(all(x["status"] == "ENABLED" and x["match_type"] == "EXACT" and x["max_cpc_myr"] == 3 for x in actual), "keyword enable/match/bid drift")
    prefix = "logs/handoffs/2026-10-08-owner-direct-preparation/"
    for campaign, name in zip(current["campaigns"], ["actual-core-keywords.csv", "actual-renovation-keywords.csv"]):
        expected = {(row["广告组"], row["关键字"].strip("[]")) for row in keyword_rows(project_file(root, prefix + name))}
        observed = {(x["group"], x["keyword"]) for x in actual if x["campaign"] == campaign["name"]}
        require(expected == observed, "frozen and actual keyword binding drift")
    monitor = json.loads(project_file(root, receipt["monitor"]["save_receipt"]).read_text())
    require(monitor["status"] == "VERIFIED_SAVED" and monitor["native_status"] == "ACTIVE"
            and monitor["times_myt"] == ["10:00", "14:00", "18:00", "22:00"]
            and monitor["target_thread_id"] == "<LOCAL_TASK_ID>", "monitor save mismatch")


def validate_native_expansion(root: Path, current: dict) -> dict:
    """Check a recorded Chinese-only expansion, not QA or a platform/write permit.

    The immutable V42 index first passes the existing full historical validator.
    Current evidence is then bound separately; old QA/permits never become an
    expansion verdict, and the recorded owner IDs are not a live authentication.
    """
    require(current["candidate_version"] == NATIVE_EXPANSION_VERSION, "unknown expansion version")
    historical = current["historical_launch_index"]
    baseline_path = project_file(root, historical["path"])
    require(historical["sha256"] == HISTORICAL_V42_SHA256
            and digest(baseline_path) == HISTORICAL_V42_SHA256, "immutable V42 index drift")
    baseline = json.loads(baseline_path.read_text())
    require(baseline["candidate_version"] == "paid-owner-completion-v42", "historical V42 index required")
    historical_result = validate(root, index=baseline)

    require(current["task_id"] == baseline["task_id"] == "fc-20260920-google-ads-rm100-budget-plan"
            and current["account_id"] == baseline["account_id"] == "example-ads-account"
            and current["department"] == baseline["department"] == "paid-growth-data", "expansion identity drift")
    expected_counts = {"campaigns": 2, "groups": 6, "exact_keywords": 120, "original_rsa": 6}
    require(current["counts"] == expected_counts, "Chinese120 counts required")
    campaigns = current["campaigns"]
    require(len(campaigns) == 2 and [c["keyword_count"] for c in campaigns] == [80, 40], "Chinese120 campaign split drift")
    for campaign, original in zip(campaigns, baseline["campaigns"]):
        require(all(campaign[key] == original[key] for key in
                    ("id", "name", "ad_groups", "total_ad_fee_myr", "status")), "unchanged campaign/group/budget/state required")
    for key in ("budget", "dates_myt", "ad_hours_myt", "shop_hours_myt"):
        require(current[key] == baseline[key], f"expansion changed frozen {key}")
    require(current["payments"] == baseline["payments"] == 0
            and current["recharges"] == baseline["recharges"] == 0, "expansion financial action outside scope")
    require(current["ads_enabled"] is True, "recorded existing Chinese campaigns must remain enabled")

    rules = current["current_plan_rules"]
    require(rules["global_paid_write_flag_still_false"] is True
            and rules["whole_launch_complete"] is False
            and rules["expansion_complete"] is False
            and rules["original40_launch_complete"] is True, "partial Chinese expansion cannot claim whole promotion complete")
    for key in ("authorization_source", "budget_preparation_authorization_source",
                "independent_qa_source", "independent_qa_native_proof",
                "exact_completion_authority_source", "exact_completion_packet",
                "policy_decision_id", "approval_id"):
        require(rules[key] == baseline["current_plan_rules"][key], "historical QA/approval/permit reference drift")
    policy = json.loads(project_file(root, "data/action-policy.json").read_text())
    require(policy["paid_promotion_enabled"] is False, "read-only index cannot relax global paid guard")

    execution = current["current_native_execution"]
    require(execution["receipt"] == NATIVE_120_RECEIPT
            and rules["native_execution_receipt"] == NATIVE_120_RECEIPT, "exact native120 receipt required")
    receipt_path = project_file(root, execution["receipt"])
    require(digest(receipt_path) == execution["receipt_sha256"], "native120 receipt bytes drift")
    receipt = json.loads(receipt_path.read_text())
    require(receipt["task_id"] == current["task_id"] and receipt["account_id"] == current["account_id"]
            and receipt["source_method"] == "cua_repl_native_google_ads_ui"
            and receipt["recorded_date_myt"] == receipt["native_date_window"] == "2026-10-10", "native120 source identity/date drift")
    require(receipt["native_table_total"] == receipt["native_collected_unique"] == 120
            and execution["counts_enabled"] == expected_counts, "native120 readback counts drift")
    rows = receipt["keywords"]
    tuple_fields = {"keyword", "campaign", "group", "match_type", "max_cpc_myr"}
    require(len(rows) == 120 and all(set(row) == tuple_fields for row in rows), "120 exact native keyword tuples required")
    require(len({(row["campaign"], row["group"], row["keyword"]) for row in rows}) == 120, "duplicate native120 keyword tuple")
    group_campaigns = {group: campaign["name"] for campaign in campaigns for group in campaign["ad_groups"]}
    require(len(group_campaigns) == 6 and all(
        row["group"] in group_campaigns and row["campaign"] == group_campaigns[row["group"]]
        and isinstance(row["keyword"], str) and bool(row["keyword"].strip())
        and row["match_type"] == "EXACT" for row in rows), "native keyword/group/campaign/match drift")
    for row in rows:
        price = row["max_cpc_myr"]
        require(type(price) in (int, float), "native keyword price must be numeric")
        decimal_price = Decimal(str(price))
        require(decimal_price.is_finite() and Decimal("0") < decimal_price <= Decimal("3"), "native keyword price outside (0,3]")
    ordered = [{"keyword": row["keyword"], "campaign": row["campaign"], "group": row["group"],
                "match_type": row["match_type"], "max_cpc_myr": row["max_cpc_myr"]}
               for row in sorted(rows, key=lambda row: (row["campaign"], row["group"], row["keyword"]))]
    price_sha256 = hashlib.sha256(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(price_sha256 == receipt["native_price_sha256"] == execution["native_price_sha256"]
            == NATIVE_120_PRICE_SHA256, "actual120 keyword/price fingerprint drift")
    expected_group_counts = {group: 20 for group in group_campaigns}
    require(dict(Counter(row["group"] for row in rows)) == receipt["group_counts"] == expected_group_counts, "each native Chinese group must contain20")
    require(dict(Counter(Decimal(str(row["max_cpc_myr"])) for row in rows)) == {
        Decimal("0.30"): 75, Decimal("0.90"): 1, Decimal("1.16"): 1,
        Decimal("0.74"): 1, Decimal("0.43"): 1, Decimal("1.35"): 1,
        Decimal("2.20"): 3, Decimal("3"): 37}, "native120 price distribution drift")
    require(receipt["keyword_native_status_counts"] == {"符合条件": 60, "无效搜索量较低": 60}
            and execution["keyword_eligibility"] == {"eligible": 60, "low_search_volume": 60}, "native keyword eligibility counts drift")
    require(receipt["English_created"] is False and execution["English_created"] is False
            and receipt["English_keyword_count"] == execution["English_keyword_count"] == 0
            and receipt["English_group_creation"] == "GOOGLE_NATIVE_OWNER_REAUTH_REQUIRED_NO_SAVE_COMPLETION", "English pending owner reauthentication must remain uncreated")
    require(receipt["budget_changed"] is False and receipt["dates_changed"] is False
            and receipt["platform_security_changed"] is False, "native expansion budget/date/security scope drift")
    require(receipt["production_business_result"] == execution["business_result"] == "NOT_MEASURED", "integrity check cannot claim business results")

    require(current["current_authority_record"] == receipt["authority"] == rules["authority_record"]
            == NATIVE_OWNER_AUTHORITY, "exact current owner authority reference required")
    authority = json.loads(project_file(root, current["current_authority_record"]).read_text())
    source = authority["authority"]
    require(authority["task_id"] == current["task_id"] and authority["account_id"] == current["account_id"]
            and authority["campaign_ids"] == [campaign["id"] for campaign in campaigns], "current authority account/task/campaign drift")
    require(source["kind"] == "VERIFIED_DIRECT_HUMAN_OWNER_INSTRUCTION"
            and source["source_thread_id"] == "<LOCAL_TASK_ID>"
            and source["source_turn_id"] == "example-native-0ce7349e377b3972"
            and source["source_message_ids"] == ["example-native-f26da45d4c33dd90",
                                                  "example-native-edb7b6c4c2a38180",
                                                  "example-native-77cf53e12595ece6"]
            and source["verified_via"] == "native read_thread exact userMessage, not delegation claim", "recorded direct human source IDs required")
    constraints = authority["constraints"]
    require(constraints["budget_each_total_myr"] == 1350 and constraints["combined_ad_fee_myr"] == 2700
            and constraints["gross_business_cap_myr"] == 3000 and constraints["max_keyword_cpc_myr"] == 3
            and constraints["dates_myt"] == current["dates_myt"]
            and constraints["ad_hours"] == current["ad_hours_myt"] and constraints["shop_hours"] == "UNCHANGED", "current owner constraint drift")
    require(all(constraints[key] is False for key in ("payments", "new_accounts", "credentials",
                "platform_security_bypass", "global_paid_policy_flag_changed")), "current owner scope cannot introduce financial/security changes")

    return {"status": "CURRENT_NATIVE_CHINESE120_RECORD_INTEGRITY_PASS", "campaigns": 2,
            "groups": 6, "exact_keywords": 120, "rsa": 6, "English_created": False,
            "English_keyword_count": 0, "whole_promotion_complete": False,
            "pending": "GOOGLE_NATIVE_OWNER_REAUTH_REQUIRED_ENGLISH_NOT_CREATED",
            "historical_launch_integrity": historical_result["status"],
            "native_price_sha256": price_sha256, "platform_live_check": False,
            "independent_qa": False, "machine_enable_permit": False,
            "new_write_permission": False, "business_result": "NOT_MEASURED"}


def validate_bilingual_native(root: Path, current: dict) -> dict:
    """Bind the saved, paused English branch without issuing acceptance or permission."""
    require(current["candidate_version"] == BILINGUAL_NATIVE_VERSION, "unknown bilingual version")
    historical = current["historical_Chinese120_index"]
    require(historical["path"] == HISTORICAL_CHINESE120_INDEX
            and historical["sha256"] == HISTORICAL_CHINESE120_SHA256, "exact immutable Chinese120 index required")
    baseline_path = project_file(root, historical["path"])
    require(digest(baseline_path) == HISTORICAL_CHINESE120_SHA256, "immutable Chinese120 index drift")
    baseline = json.loads(baseline_path.read_text())
    require(baseline["candidate_version"] == NATIVE_EXPANSION_VERSION, "historical Chinese120 version drift")
    historical_result = validate(root, index=baseline)
    for key in ("task_id", "account_id", "department", "budget", "dates_myt", "ad_hours_myt",
                "shop_hours_myt", "payments", "recharges", "ads_enabled", "current_plan_rules",
                "current_native_execution", "current_authority_record", "historical_launch_index",
                "frozen_inputs", "mutable_evidence_archives"):
        require(current[key] == baseline[key], f"bilingual changed frozen identity/history/boundary: {key}")
    require(current["counts"] == {"campaigns": 2, "groups": 12, "exact_keywords": 160,
                                 "original_rsa": 6, "English_rsa": 6}, "saved bilingual160 counts required")
    campaigns = current["campaigns"]
    require(len(campaigns) == 2 and [c["keyword_count"] for c in campaigns] == [108, 52], "bilingual108/52 split drift")
    english_groups = {
        "AG_EN_WHOLE_HOME": ("00057225103", 6),
        "AG_EN_CUSTOM_FURNITURE": ("00057225103", 6),
        "AG_EN_CUSTOM_KITCHEN": ("00057225103", 8),
        "AG_EN_CUSTOM_WARDROBE": ("00057225103", 8),
        "AG_EN_OLD_HOUSE": ("00063878462", 6),
        "AG_EN_CONDO": ("00063878462", 6),
    }
    for campaign, original in zip(campaigns, baseline["campaigns"]):
        require(all(campaign[key] == original[key] for key in
                    ("id", "name", "total_ad_fee_myr", "status")), "existing parent identity/budget/state drift")
        additions = [group for group, binding in english_groups.items() if binding[0] == campaign["id"]]
        require(campaign["ad_groups"] == original["ad_groups"] + additions
                and campaign["Chinese_group_status"] == "ENABLED"
                and campaign["English_group_status"] == "PAUSED", "six existing Chinese groups enabled; six English groups paused required")
    require(len({group for campaign in campaigns for group in campaign["ad_groups"]}) == 12,
            "bilingual group identity collision")

    execution = current["current_bilingual_execution"]
    require(execution["English_created"] is True and execution["English_enabled"] is False
            and execution["English_keyword_count"] == 40 and execution["English_group_count"] == 6
            and execution["English_rsa_saved"] == 6 and execution["current_owner_batch_QA_claim"] is False,
            "English saved is not enabled or an independent QA verdict")
    require(execution["keyword_receipt"] == ENGLISH40_RECEIPT
            and execution["keyword_receipt_sha256"] == ENGLISH40_RECEIPT_SHA256,
            "exact saved English40 evidence reference required")
    english_path = project_file(root, execution["keyword_receipt"])
    require(digest(english_path) == ENGLISH40_RECEIPT_SHA256, "saved English40 evidence bytes drift")
    english = json.loads(english_path.read_text())
    require(english["task_id"] == current["task_id"] and english["account_id"] == current["account_id"]
            and english["recorded_date_myt"] == "2026-10-10"
            and english["source_method"] == "cua_repl_native_google_ads_ui"
            and english["status"] == "40_ENGLISH_EXACT_SAVED_PRICE_READBACK_VERIFIED_SIX_GROUPS_PAUSED",
            "saved English40 native identity/status drift")
    require(english["native_table_totals"] == {"core": 28, "renovation": 12}
            and english["English_created"] is True and english["English_enabled"] is False
            and english["no_financial_actions"] is True, "English40 split/paused/financial boundary drift")
    rows = english["keywords"]
    tuple_fields = {"keyword", "campaign_id", "group", "match_type", "max_cpc_myr"}
    require(len(rows) == 40 and all(set(row) == tuple_fields for row in rows)
            and len({(row["campaign_id"], row["group"], row["keyword"]) for row in rows}) == 40,
            "40 distinct native English keyword tuples required")
    for row in rows:
        require(row["group"] in english_groups and row["campaign_id"] == english_groups[row["group"]][0]
                and isinstance(row["keyword"], str) and bool(row["keyword"].strip())
                and row["match_type"] == "EXACT", "native English keyword/match/group/campaign drift")
        price = row["max_cpc_myr"]
        require(type(price) in (int, float), "native English price must be numeric")
        decimal_price = Decimal(str(price))
        require(decimal_price.is_finite() and Decimal("0") < decimal_price <= Decimal("3"),
                "native English price outside (0,3]")
    require(dict(Counter(row["group"] for row in rows)) ==
            {group: binding[1] for group, binding in english_groups.items()}, "English6/6/8/8/6/6 group split drift")
    ordered = [{"keyword": row["keyword"], "campaign_id": row["campaign_id"], "group": row["group"],
                "match_type": row["match_type"], "max_cpc_myr": row["max_cpc_myr"]}
               for row in sorted(rows, key=lambda row: (row["campaign_id"], row["group"], row["keyword"]))]
    price_sha256 = hashlib.sha256(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(price_sha256 == ENGLISH40_PRICE_SHA256, "saved English40 keyword/price fingerprint drift")
    states = english["group_states"]
    require(len(states) == 6 and len({state["group"] for state in states}) == 6
            and all(state["group"] in english_groups
                    and state["campaign_id"] == english_groups[state["group"]][0]
                    and state["keyword_count"] == english_groups[state["group"]][1]
                    and state["status"] == "PAUSED" for state in states), "all six saved English groups must remain paused")
    rsa = english["rsas"]
    require(rsa["saved"] == rsa["native_correct_English_readback"] == 6
            and rsa["original_Chinese_untouched"] is True
            and rsa["corrected_core_initial_copy_error"] is True
            and rsa["enabled_as_assets_but_parent_groups_paused"] is True,
            "six saved correct English RSA/original Chinese isolation required")
    require(english["remaining"] == ["English production success/receipt/conversion acceptance",
                "Renovation Presence radio readback", "English negative keyword native verification",
                "Enable6ENgroups only after chain acceptance"], "English chain acceptance must remain pending")

    require(execution["asset_receipt"] == BILINGUAL_ASSET_RECEIPT
            and execution["asset_receipt_sha256"] == BILINGUAL_ASSET_SHA256, "exact bilingual asset evidence required")
    asset_path = project_file(root, execution["asset_receipt"])
    require(digest(asset_path) == BILINGUAL_ASSET_SHA256, "bilingual asset evidence bytes drift")
    assets = json.loads(asset_path.read_text())
    require(assets["task_id"] == current["task_id"] and assets["account_id"] == current["account_id"]
            and assets["recorded_date_myt"] == "2026-10-10"
            and assets["source_method"] == "cua_repl_native_google_ads_ui"
            and assets["status"] == "ACTUALLY_SAVED_NATIVE_READBACK_VERIFIED", "native bilingual asset identity/status drift")
    chinese_groups = [group for campaign in baseline["campaigns"] for group in campaign["ad_groups"]]
    require(assets["Chinese_child_associations_enabled"] == 114
            and assets["English_child_associations_enabled"] == 54
            and assets["English_group_count"] == 6
            and assets["Chinese_assets_per_group"] == 19
            and assets["Chinese_group_counts"] == {group: 19 for group in chinese_groups}
            and assets["English_group_counts"] == {group: 9 for group in english_groups}
            and assets["English_assets_per_group"] == {"sitelinks": 4, "callouts": 5, "structured_snippets": 0},
            "114 Chinese/54 English child associations with exact group coverage required")
    require(assets["parent_Chinese_associations_paused"] == {"account": 10, "core": 9, "renovation": 9}
            and assets["same_branch_enabled_Chinese_parent_links_callouts_snippets"] == 0
            and assets["core_native_total"] == 133 and assets["renovation_native_total"] == 77
            and assets["unique_associations"] == 199, "28 paused upper Chinese associations/readback totals drift")
    require(assets["old_case_sitelink"] == "REMAINS_PAUSED_NOT_COPIED"
            and all(assets[key] is True for key in
                    ("no_deletion", "no_global_shared_asset_content_edit", "map_location_not_modified")),
            "asset isolation must not delete or alter shared content/map association")
    logo = assets["logo"]
    require(logo["asset_id"] == "000415033906" and logo["campaign_associations_enabled"] == 2
            and logo["native_policy_status"] == "审核中" and logo["actual_served_logo"] == "NOT_OBSERVED",
            "recorded logo association is not approval or actual serving")
    require(assets["scope_record"] == BILINGUAL_ASSET_SCOPE, "exact bilingual association scope required")
    scope_path = project_file(root, assets["scope_record"])
    require(digest(scope_path) == BILINGUAL_ASSET_SCOPE_SHA256, "bilingual association scope bytes drift")
    scope = json.loads(scope_path.read_text())
    bounds = scope["scope"]
    require(scope["task_id"] == current["task_id"] and scope["account_id"] == current["account_id"]
            and scope["authority_reference"] == current["current_authority_record"]
            and scope["independent_QA_claim"] is False
            and scope["implementation_state"] == "ACTUALLY_SAVED_NATIVE_READBACK_VERIFIED"
            and scope["readback"] == BILINGUAL_ASSET_RECEIPT, "association scope identity/authority/QA drift")
    require(bounds["existing_campaign_ids"] == [campaign["id"] for campaign in campaigns]
            and bounds["account_association_count"] == 10 and bounds["campaign_association_count"] == 18
            and bounds["account_association_types"] == {"sitelinks": 5, "callouts": 4, "structured_snippets": 1}
            and bounds["target_Chinese_groups"] == chinese_groups
            and bounds["planned_child_Chinese_associations"] == 114
            and bounds["excluded"] == ["business_logo", "map_location", "old_paused_case_sitelink",
                "payments", "permissions", "credentials", "budget", "dates", "hours", "networks",
                "AI_Max", "automatic_assets"], "exact association scope/financial/security exclusions required")
    unfinished = {item["id"]: item for item in current["unfinished"]}
    require(unfinished["English40_chain"]["state"] ==
            "40_EXACT_6_EN_GROUPS_6_RSA_54_EN_ASSET_ASSOCIATIONS_ACTUALLY_SAVED_GROUPS_PAUSED"
            and unfinished["renovation_presence_radio"]["state"] ==
            "PARTIAL_RADIUS50KM_NOEXCLUSIONS_VERIFIED_PRESENCE_NOT_READ"
            and current["English_form_release"]["notifications_delivery"] == "NOT_VERIFIED"
            and current["English_form_release"]["Ads_live_receipt"] == "NOT_VERIFIED",
            "current English production/Presence acceptance cannot be claimed complete")

    return {"status": "CURRENT_NATIVE_BILINGUAL160_SAVED_RECORD_INTEGRITY_PASS",
            "campaigns": 2, "saved_groups": 12, "saved_exact_keywords": 160,
            "enabled_Chinese_groups": 6, "enabled_Chinese_exact_keywords": 120,
            "paused_English_groups": 6, "paused_English_exact_keywords": 40,
            "original_Chinese_rsa": 6, "saved_English_rsa": 6,
            "Chinese_child_associations_enabled": 114, "English_child_associations_enabled": 54,
            "parent_Chinese_associations_paused": 28, "English_enabled": False,
            "whole_promotion_complete": False, "English_production_acceptance": "NOT_VERIFIED",
            "renovation_Presence_acceptance": "NOT_VERIFIED",
            "historical_Chinese120_integrity": historical_result["status"],
            "English40_price_sha256": price_sha256, "platform_live_check": False,
            "independent_qa": False, "machine_enable_permit": False,
            "new_write_permission": False, "business_result": "NOT_MEASURED"}


def validate_English_enabled(root: Path, current: dict) -> dict:
    """Recorded acceptance only; never authorize platform actions or claim customers."""
    require(current["candidate_version"] == ENGLISH_ENABLED_VERSION, "unknown English enable version")
    historical = current["historical_bilingual160_index"]
    require(historical == {"path": BILINGUAL160_SNAPSHOT, "sha256": BILINGUAL160_SNAPSHOT_SHA256},
            "exact historical bilingual160 snapshot required")
    snapshot = project_file(root, historical["path"])
    require(digest(snapshot) == BILINGUAL160_SNAPSHOT_SHA256, "historical bilingual160 bytes drift")
    baseline = json.loads(snapshot.read_text())
    historical_result = validate(root, index=baseline)
    for key in ("task_id", "account_id", "department", "counts", "budget", "dates_myt", "ad_hours_myt",
                "shop_hours_myt", "reception", "spend_pause_operator", "payments", "recharges",
                "ads_enabled", "frozen_inputs", "mutable_evidence_archives", "historical_launch_index",
                "historical_Chinese120_index", "current_authority", "current_authority_record",
                "platform_deletion_executed", "website_changed_or_deployed", "normal_canaries"):
        require(current[key] == baseline[key], f"English enable changed frozen boundary: {key}")
    expected_rules = dict(baseline["current_plan_rules"])
    expected_rules.update(whole_launch_complete=True, expansion_complete=True,
                          native_execution_receipt="logs/handoffs/2026-10-10-owner-direct-paid/English-six-groups-enable-native-readback.json")
    require(current["current_plan_rules"] == expected_rules, "current rules outside exact acceptance drift")
    require(current["historical_Chinese120_native_execution"] == baseline["current_native_execution"],
            "historical Chinese120 execution overwritten")
    require(current["prepared_bilingual_chain_complete"] is True, "current chain acceptance missing")
    expected_bilingual = dict(baseline["current_bilingual_execution"], English_enabled=True,
                              English_enable_receipt="logs/handoffs/2026-10-10-owner-direct-paid/English-six-groups-enable-native-readback.json",
                              English_enable_receipt_sha256=ACCEPTANCE_RECEIPTS["enable"][1])
    require(current["current_bilingual_execution"] == expected_bilingual, "bilingual prices/assets or enable evidence drift")
    for campaign, original in zip(current["campaigns"], baseline["campaigns"]):
        expected = dict(original, English_group_status="ENABLED")
        require(campaign == expected, "exact existing parents/group/budget/English state drift")
    require(len(current["campaigns"]) == 2, "exact two current campaigns required")
    execution = current["English_acceptance_execution"]
    receipts = {}
    for kind, (filename, sha) in ACCEPTANCE_RECEIPTS.items():
        relative = "logs/handoffs/2026-10-10-owner-direct-paid/" + filename
        require(execution[kind] == {"path": relative, "sha256": sha}, "exact current acceptance reference drift")
        path = project_file(root, relative)
        require(digest(path) == sha, "current acceptance bytes drift")
        receipt = json.loads(path.read_text())
        require(receipt["account_id"] == current["account_id"] and receipt["task_id"] == current["task_id"],
                "acceptance account/task mismatch")
        receipts[kind] = receipt
    require(all(execution[k] is False for k in ("independent_qa", "machine_enable_permit", "new_global_permission"))
            and execution["business_result"] == "NOT_MEASURED", "acceptance is not QA/permission/business result")
    languages, geo, forms, enabled = (receipts[k] for k in ("languages", "Presence", "forms", "enable"))
    require([x["id"] for x in languages["campaigns"]] == ["00057225103", "00063878462"]
            and all(x["languages_native"] == "简体中文; 英语" and x["budget_total_myr"] == 1350 for x in languages["campaigns"]),
            "actual two bilingual language saves required")
    require(geo["campaign_id"] == "00063878462" and geo["batches_examined"] == 55
            and geo["native_counter"] == "1–55 / 55" and geo["report_window_native"] == ["2026-10-01", "2026-10-10"]
            and geo["saved_change"]["at_native"] == "2026-10-08 04:04:41"
            and geo["saved_change"]["meaning"] == "PRESENCE"
            and geo["later_conflicting_location_option_change_found"] is False
            and geo["current_radio_directly_read"] is False and geo["region_modified_this_turn"] is False,
            "complete native Presence history required, not fabricated radio")
    require(forms["production_sha"] == "2f055035d469c02833a8dd7025ddb8b2223c0b8c"
            and forms["owner_received_message_id"] == "example-native-96a462e21ad1f8d8"
            and forms["owner_received_answer"] == "两条都收到", "current exact owner receipt required")
    expected_ids = {"quote": "23390daa-df56-84dd-8e59-482bccdc2b0e", "contact": "f8a68065-a853-80ac-8f0d-078084f5a1b8"}
    require(len(forms["forms"]) == 2 and {f["type"] for f in forms["forms"]} == set(expected_ids), "exact internal form pair required")
    for form in forms["forms"]:
        kind = form["type"]
        expected_source = f"/__internal_test__/acceptance/en/{kind}/{expected_ids[kind]}"
        require(form["record_id"] == expected_ids[kind] and form["source_path"] == expected_source
                and form["url"] == f"https://flashcast.com.my/en/{kind}" and form["submit_count"] == 1
                and form["owner_received"] is True, "exact single English internal submission binding required")
        export = project_file(root, form["export"]["path"])
        require(digest(export) == form["export"]["sha256"], "internal one-row export drift")
        rows = list(csv.DictReader(export.read_text().splitlines()))
        require(len(rows) == 1 and rows[0]["source_path"] == expected_source
                and rows[0]["created_at"] == form["created_at"], "actual server stored internal source required")
        require(re.fullmatch(r"/__internal_test__/acceptance/en/(quote|contact)/[0-9a-f-]{36}", expected_source), "internal source exclusion marker invalid")
    exclusion = forms["formal_statistics_exclusion"]
    require(all(exclusion[k] is True for k in ("stored_source_paths_verified_from_exact_single_row_exports",
                "both_match_published_STORED_ACCEPTANCE_PATTERN", "formal_report_and_dashboard_use_FORMAL_LEAD_SOURCE_FILTER"))
            and exclusion["actual_formal_report_query_count_observed"] is False, "actual source/contract exclusion proof required")
    measurement = forms["measurement"]
    require(measurement["published_frontend_suppresses_internal_receipt"] is True
            and measurement["ordinary_public_success_tracking_preserved_by_tests"] is True
            and measurement["actual_English_customer_conversion_observed"] is False
            and measurement["Google_live_conversion_receipt"] == "NOT_OBSERVED_INTERNAL_ACCEPTANCE_SUPPRESSED_BY_DESIGN"
            and measurement["real_customers"] == 0, "do not fabricate Google customer conversion from internal tests")
    require(forms["targeted_checks"]["tests_passed"] == 77 and forms["targeted_checks"]["tests_failed"] == 0,
            "current targeted tracking/exclusion checks missing")
    expected_groups = {row["group"]: (row["campaign_id"], row["keyword_count"]) for row in
                       json.loads(project_file(root, ENGLISH40_RECEIPT).read_text())["group_states"]}
    states = enabled["group_states"]
    require(len(states) == 6 and {s["group"] for s in states} == set(expected_groups), "exact six English group readbacks required")
    for state in states:
        require((state["campaign_id"], state["keyword_count"]) == expected_groups[state["group"]]
                and state["status"] == state["rsa_status"] == "ENABLED"
                and state["rsa_policy"] == "已批准" and state["native_eligibility"] == "符合条件"
                and state["final_url"].startswith("https://flashcast.com.my/en/services/"), "native English group/RSA/URL drift")
    require(enabled["payments"] is False and enabled["recharges"] is False
            and enabled["independent_qa"] is False and enabled["machine_enable_permit"] is False
            and enabled["new_global_permission"] is False and enabled["business_result"] == "NOT_MEASURED", "native financial/safety/result drift")
    for item in [geo["screenshot"], {"path": languages["screenshot"], "sha256": "6518c7a51f64c283497485f819029a5e60f716cb1b4765e0af6122718941ff37"}] + enabled["screenshots"] + [f["screenshot"] for f in forms["forms"]]:
        require(digest(project_file(root, item["path"])) == item["sha256"], "native screenshot evidence drift")
    monitor_path = "logs/handoffs/2026-10-10-owner-direct-paid/monitor-English-enabled-save-receipt.json"
    monitor_file = project_file(root, monitor_path)
    require(digest(monitor_file) == "40be7d53bdafe0e85bb5c915525cfcd500ffd2da49d5ab207555ae4b8e9cf576", "current monitor evidence drift")
    monitor = json.loads(monitor_file.read_text())
    require(current["daily_learning"]["current_monitor_save_receipt"] == monitor_path
            and monitor["target_thread_id"] == "<LOCAL_TASK_ID>"
            and monitor["times_myt"] == ["10:00", "14:00", "18:00", "22:00"]
            and monitor["automatic_platform_write_allowed"] is False, "monitor scope or current evidence mismatch")
    require(current["current_bilingual_execution"]["English_enabled"] is True
            and current["current_bilingual_execution"]["current_owner_batch_QA_claim"] is False
            and current["current_native_execution"]["counts_enabled"] == current["counts"]
            and current["English_form_release"]["notifications_delivery"] == "OWNER_CONFIRMED_BOTH_RECEIVED"
            and current["English_form_release"]["Ads_live_receipt"] == measurement["Google_live_conversion_receipt"], "current state must match actual acceptance")
    require(not {"English40_chain", "renovation_presence_radio"}.intersection(x["id"] for x in current["unfinished"]), "obsolete preparation gates remain")
    return {"status": "CURRENT_NATIVE_BILINGUAL160_ENABLED_ACCEPTANCE_RECORD_INTEGRITY_PASS",
            "groups_enabled": 12, "saved_exact_keywords": 160, "English_groups_enabled": 6,
            "English_RSA_approved": 6, "internal_English_submissions_owner_received": 2,
            "historical_bilingual160_integrity": historical_result["status"], "platform_live_check": False,
            "independent_qa": False, "machine_enable_permit": False, "new_write_permission": False,
            "actual_English_customer_conversion": "NOT_OBSERVED", "business_result": "NOT_MEASURED"}


def validate(root: Path, index: dict | None = None) -> dict:
    current = index if index is not None else json.loads(project_file(root, INDEX).read_text())
    if current.get("candidate_version") == ENGLISH_ENABLED_VERSION:
        return validate_English_enabled(root, current)
    if current.get("candidate_version") == BILINGUAL_NATIVE_VERSION:
        return validate_bilingual_native(root, current)
    if current.get("candidate_version") == NATIVE_EXPANSION_VERSION:
        return validate_native_expansion(root, current)
    require(current["account_id"] == "example-ads-account", "wrong Ads account")
    require(current["task_id"] == "fc-20260920-google-ads-rm100-budget-plan", "wrong original task")
    require(current["counts"] == {"campaigns": 2, "groups": 6, "exact_keywords": 40, "original_rsa": 6}, "current counts drift")
    campaigns = current["campaigns"]
    require([c["id"] for c in campaigns] == ["00057225103", "00063878462"], "campaign identity drift")
    require([c["keyword_count"] for c in campaigns] == [32, 8], "keyword split drift")
    groups = [g for c in campaigns for g in c["ad_groups"]]
    require(len(groups) == 6 and len(set(groups)) == 6, "group identity collision")
    require(current["dates_myt"] == ["2026-10-08", "2026-10-14"], "date drift")
    require(current["ad_hours_myt"] == "MON-SUN10:00-22:00", "ad schedule drift")
    require(current["shop_hours_myt"] == "MON-SUN10:00-19:00_KEEP_UNCHANGED", "shop hours drift")
    total = sum(Decimal(str(c["total_ad_fee_myr"])) for c in campaigns)
    each = Decimal(str(campaigns[0]["total_ad_fee_myr"]))
    require(each in {Decimal("1388.88"), Decimal("1350")}
            and all(Decimal(str(c["total_ad_fee_myr"])) == each for c in campaigns), "budget split drift")
    require(total == each * 2, "total ad fee drift")
    if each == Decimal("1350"):
        budget_auth = json.loads(project_file(root, current["current_plan_rules"]["budget_preparation_authorization_source"]).read_text())
        require(budget_auth["source_method"] == "mcp__codex_app__read_thread"
                and budget_auth["message_id"] == "example-native-adf7260eec4d7fa4"
                and budget_auth["source_thread_id"] == "<LOCAL_TASK_ID>", "exact lower-budget human approval required")
        require(budget_auth["user_message"]["type"] == "userMessage"
                and budget_auth["user_message"]["id"] == budget_auth["message_id"], "native budget human message required")
        reply_text = budget_auth["user_message"]["content"][0]["text"]
        replies = json.loads(reply_text.split("<send_user_message_question_reply>", 1)[1].split("</send_user_message_question_reply>", 1)[0])
        require(len(replies) == 1 and replies[0]["questionItemId"] == '["request_user_input_async","call_069fad82e4124364937056ba893db163",0]'
                and replies[0]["answer"] == "批准降预算及一次定向复验", "exact budget answer required")
        require(budget_auth["scope"]["campaign_ids"] == [c["id"] for c in campaigns]
                and budget_auth["scope"]["total_ad_fee_each_myr"] == 1350
                and budget_auth["scope"]["always_paused"] is True
                and budget_auth["scope"]["ads_enable_by_this_approval"] is False
                and budget_auth["scope"]["payment"] is False, "budget preparation approval is not enable authority")
    require(Decimal(str(current["budget"]["gross_business_cap_myr"])) == Decimal("3000"), "business cap drift")
    require(round(total * Decimal("1.08"), 2) <= Decimal("3000"), "estimated gross exceeds cap")
    rules = current["current_plan_rules"]
    launched = current["ads_enabled"]
    if launched:
        validate_native_launch(root, current)
    else:
        require(not rules["execution_released"], "unreleased preparation must remain paused")
    require(rules["enable_approval"] and rules["enable_approval_is_conditional"], "latest conditional human authorization missing")
    authorization = json.loads(project_file(root, rules["authorization_source"]).read_text())
    human = authorization["human_authorization"]
    require(human["source"] == "native_human_user_message" and human["enable_authorized"] and human["conditional"], "real conditional authority required")
    require(human["thread_id"] == "<LOCAL_TASK_ID>" and human["message_id"] == "example-native-26b1f8f519d6f2e2", "authorization identity drift")
    require(not authorization["execution_released"] and not authorization["readiness"]["whole_preparation_ready"], "authorization is not unresolved readiness")
    require(authorization["scope"]["campaign_ids"] == [c["id"] for c in campaigns], "conditional authorization scope drift")
    require(authorization["scope"]["gross_business_cap_myr"] == 3000 and authorization["scope"]["total_ad_fee_each_myr"] == 1388.88, "authorization budget drift")
    require([authorization["scope"]["start"], authorization["scope"]["end"]] == current["dates_myt"], "authorization date drift")
    require(authorization["scope"]["ad_hours_myt"] == current["ad_hours_myt"] and authorization["scope"]["shop_hours"] == "KEEP10:00-19:00", "authorization hours drift")
    require(all(authorization["scope"][key] == expected for key, expected in {"groups": 6, "exact_keywords": 40, "original_rsa": 6}.items()), "authorization child scope drift")
    require(authorization["scope"]["old_campaigns"] == "KEEP_PAUSED" and authorization["scope"]["no_refill_extension_reallocation_or_expansion"], "authorization isolation drift")
    scope_base = authorization["frozen_scope_base"]
    require(digest(project_file(root, scope_base["path"])) == scope_base["sha256"], "conditional scope base drift")
    require(current["current_plan_rules"]["whole_launch_complete"] is launched, "launch completion flag mismatch")
    require(not current["payments"] and not current["recharges"], "unapproved financial action")
    for item in current["frozen_inputs"]:
        require(digest(project_file(root, item["path"])) == item["sha256"], f"frozen source drift: {item['path']}")
    for item in current["mutable_evidence_archives"]:
        require(digest(project_file(root, item["snapshot_path"])) == item["historical_sha256"], "historical README snapshot drift")
    prefix = "logs/handoffs/2026-10-08-owner-direct-preparation/"
    rows_by_campaign = [keyword_rows(project_file(root, prefix + name)) for name in ["actual-core-keywords.csv", "actual-renovation-keywords.csv"]]
    for campaign, rows in zip(campaigns, rows_by_campaign):
        require(len(rows) == campaign["keyword_count"], "native keyword count drift")
        require({row["广告组"] for row in rows} == set(campaign["ad_groups"]), "native keyword/group mismatch")
        require(all(row["匹配类型"] == "完全匹配" and row["关键字状态"] == "已暂停" for row in rows), "native keyword scope/state drift")
        require(len({(row["广告组"], row["关键字"]) for row in rows}) == len(rows), "duplicate native keyword tuple")
    rsa = list(csv.DictReader(project_file(root, prefix + "paused-rsa-v2.csv").read_text().splitlines()))
    require(len(rsa) == 6 and {row["Ad group"] for row in rsa} == set(groups), "RSA/group scope drift")
    require(all(row["Ad status"] == "Paused" for row in rsa), "RSA preparation state drift")
    signoff = json.loads(project_file(root, "drafts/google-ads/fc-20260920-google-ads-rm100-budget-plan/launch-signoff-20261008-v35.json").read_text())
    base = signoff["frozen_scope_base"]
    require(digest(project_file(root, base["path"])) == base["sha256"], "frozen signoff base drift")
    require(not signoff["enable_approval"] and signoff["owner_signature"] is None, "unsigned preparation only")
    for relative in ["departments/paid-growth-data/README.md", "data/google-ads/README.md", "drafts/google-ads/fc-20260920-google-ads-rm100-budget-plan/README.md"]:
        require("current-preparation.json" in project_file(root, relative).read_text(), "current-entry link missing")
    return {"status": "CURRENT_EXECUTION_RECORD_INTEGRITY_PASS" if launched else "CURRENT_PLAN_INTEGRITY_PASS", "campaigns": 2, "groups": 6, "exact_keywords": 40, "rsa": 6, "frozen_sources": len(current["frozen_inputs"]), "historical_snapshots": 3, "platform_live_check": False, "independent_qa": False, "conditional_human_enable_authorization": True, "execution_released": launched, "recorded_native_execution_verified": launched, "machine_enable_permit": False}


if __name__ == "__main__":
    print(json.dumps(validate(ROOT), ensure_ascii=False))
