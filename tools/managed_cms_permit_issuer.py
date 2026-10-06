#!/usr/bin/env python3
"""Issue one short-lived CMS permit only from fixed, verified release evidence.

This tool is an issuer, not a substitute for QA or operations. Its credential is
injected by a protected operator process, never stored in the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from uuid import uuid4

if __package__:
    from . import workflow_control as wc
else:
    import workflow_control as wc

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = Path("<WEBSITE_PROJECT_ROOT>")
REPOSITORY = "wangchaozhuanyong/zhuangxiuwangzhan"
SUPABASE_HOST = "rbsnyexjifounogswrjp.supabase.co"
KEYCHAIN_SERVICE = "com.flashcast.managed-cms-permit-issuer"
KEYCHAIN_ACCOUNT = "rbsnyexjifounogswrjp"
QA_THREAD_ID = "<LOCAL_TASK_ID>"
OPERATIONS_THREAD_ID = "<LOCAL_TASK_ID>"
if __package__:
    from .native_cms_issuer_integration import (load_native_issuer_targets, validate_native_issuer_candidate, native_release_qa_matches)
else:
    sys.path.insert(0, str(ROOT))
    from tools.native_cms_issuer_integration import (load_native_issuer_targets, validate_native_issuer_candidate, native_release_qa_matches)

if __package__:
    from .native_repair_faq_registration import load_repair_faq_registration, validate_repair_faq_candidate
else:
    from tools.native_repair_faq_registration import load_repair_faq_registration, validate_repair_faq_candidate

if __package__:
    from .native_wave234_body_registration import load_wave234_body_registration, validate_wave234_body_candidate
else:
    from tools.native_wave234_body_registration import load_wave234_body_registration, validate_wave234_body_candidate

if __package__:
    from .native_remaining186_blog_registration import load_remaining186_blog_registration, validate_remaining186_blog_candidate
else:
    from tools.native_remaining186_blog_registration import load_remaining186_blog_registration, validate_remaining186_blog_candidate
if __package__:
    from .native_shop_children_body_registration import load_shop_children_body_registration, validate_shop_children_body_candidate
else:
    from tools.native_shop_children_body_registration import load_shop_children_body_registration, validate_shop_children_body_candidate

if __package__:
    from .native_five_source_projection_registration import load_five_source_projection_registration, validate_five_source_projection_candidate
else:
    from tools.native_five_source_projection_registration import load_five_source_projection_registration, validate_five_source_projection_candidate


if __package__:
    from .native_publisher_exact_registration import load_publisher_exact_registration, validate_publisher_registration_candidate
else:
    from tools.native_publisher_exact_registration import load_publisher_exact_registration, validate_publisher_registration_candidate


TARGETS = {
    "builtin-whole-house-custom-v1": {
        "task_id": "fc-20260920-builtin-whole-house-custom-v1",
        "action_id": "publish-builtin-whole-house-custom-v1",
        "candidate_version": "builtin-whole-house-custom-v1",
        "record_id": "b401a610-a4dc-4a0b-a7e0-efcac6c81d71",
        "slug": "builtin",
        "scope": "flashcast.com.my:services/b401a610-a4dc-4a0b-a7e0-efcac6c81d71",
        "candidate": ("drafts/seo/fc-20260920-builtin-whole-house-custom-v1/builtin-service-cms-candidate-v1.json", "1c2e381e6393dc588d11df2e960641a3d37a5c0145d61dc3b95804129fa1dd45"),
        "rollback": ("backups/fc-20260920-builtin-whole-house-custom-v1/rollback-package.json", "1dcafc0f1a003835c519e15b3ff2b4f840898c1596396cbeb210f20f48e2feb6"),
    },
    "en-renovation-owner-cms-v2": {
        "task_id": "fc-20260920-en-renovation-owner-publish-v2",
        "action_id": "publish-en-renovation-owner-cms-v2",
        "candidate_version": "en-renovation-owner-cms-v2",
        "record_id": "0d947129-0595-43ef-baa1-0fd9d8b870e6",
        "slug": "renovation",
        "scope": "flashcast.com.my:/en/services/renovation:service:renovation:english-content-fields",
        "candidate": ("drafts/seo/fc-20260920-en-renovation-owner-publish-v2/cms-content-candidate.json", "85826741469e39663ab6bf42411eaccb4186dacc128c0b32f8846d6549510c50"),
        "rollback": ("drafts/seo/fc-20260920-en-renovation-owner-publish-v2/rollback-plan.json", "241768c4365a6ce4b8d5466184b5d66ab2ae38d313162b0dae28f9e12f842f5d"),
    },
    "pg002-shop-cms-v1": {
        "task_id": "fc-20260921-seo-pg002-shop-candidate-v1",
        "action_id": "publish-pg002-shop-cms-v1",
        "candidate_version": "pg002-shop-cms-v1",
        "record_id": "32f5374f-9919-41ea-80c7-00b5ac917532",
        "slug": "shop-renovation",
        "scope": "flashcast.com.my:services/32f5374f-9919-41ea-80c7-00b5ac917532",
        "candidate": ("drafts/seo/fc-20260921-seo-pg002-shop-candidate-v1/shop-service-cms-candidate-v1.json", "cfeecb6ae5bcb55c9c2bb2f0993aaf4de309906dd1e2ed6dd189e29e18e2c988"),
        "rollback": ("backups/fc-20260921-seo-pg002-shop-candidate-v1/rollback-package.json", "05a9e506f3ed1d517a36387543309befffd70d3dab4dcab8b4cd68cefa074a04"),
    },
    "kitchen-r1-cms-row-20260924-v1": {
        "task_id": "fc-20260924-seo-owner-implementation-v1",
        "action_id": "publish-kitchen-r1-cms-row-20260924-v1",
        "candidate_version": "kitchen-r1-cms-row-20260924-v1",
        "record_id": "ce4156db-9034-42c8-ba29-b35724ea7d6d",
        "slug": "kitchen",
        "scope": "flashcast.com.my:services/ce4156db-9034-42c8-ba29-b35724ea7d6d",
        "evidence_root": SITE_ROOT,
        "qa_candidate_only": True,
        "candidate": ("backups/kitchen-r1-cms-row-20260924-v1/candidate-row.json", "327ee90b39bb315f5847c3c68c83651f3ee3426e693901c948fe91d9376cd2ff"),
        "rollback": ("backups/kitchen-r1-cms-row-20260924-v1/rollback-record-template.json", "dbf2db39217fcfea2b440dc0ebb4db848144a1f41517189d16939d84b015e498"),
    },
    "design-r1-cms-row-20260924-v1": {
        "task_id": "fc-20260924-seo-owner-implementation-v1",
        "action_id": "publish-design-r1-cms-row-20260924-v1",
        "candidate_version": "design-r1-cms-row-20260924-v1",
        "record_id": "0af89b93-8938-4a98-ba65-6525fbbe92c1",
        "slug": "design",
        "scope": "flashcast.com.my:services/0af89b93-8938-4a98-ba65-6525fbbe92c1",
        "evidence_root": SITE_ROOT,
        "qa_candidate_only": True,
        "candidate": ("backups/design-r1-cms-row-20260924-v1/candidate-row.json", "d5f9666aead0c1048607479cdab86e9e22cc083b30f584d7ac60f7da2ab59c05"),
        "rollback": ("backups/design-r1-cms-row-20260924-v1/rollback-record-template.json", "5db30dddaa8ef5cb5e76695b0fe428ec2c1e67b8c5cbcf025d76bc41ffcd7c3a"),
    },
    "selangor-service-area-r1-v4": {
        "task_id": "fc-20260923-selangor-public-fact-risk-v1",
        "action_id": "publish-selangor-service-area-r1-v4",
        "candidate_version": "selangor-r1-cms-row-20260923-v4",
        "record_id": "e2e461b7-3bb8-4206-817a-7f830824b8ac",
        "slug": "selangor",
        "scope": "flashcast.com.my:selangor-service-area-fact-risk-v1",
        "evidence_root": SITE_ROOT,
        "qa_candidate_only": True,
        "candidate": ("backups/selangor-r1-cms-row-20260923-v4/candidate-row.json", "f992ca26072deb33f0f1b58b4f3895eeb5f7bec2734a4c4a30a61a8e1a264265"),
        "rollback": ("backups/selangor-r1-cms-row-20260923-v4/rollback-record-template.json", "5eab9ad20430493c1a3c86a4d61b7ceb67ac5f6b6b9394d11342ec9538bdb133"),
    },
    "org-017-bathroom-faq-parity-reconciliation-v4": {
        "task_id": "fc-20260924-org-017-bathroom-faq-rework-v3",
        "action_id": "org-017-bathroom-faq-parity-reconcile-v4",
        "candidate_version": "org-017-bathroom-faq-parity-reconciliation-v4",
        "record_id": "0f294e6d-2e2c-4f13-a93f-096728ccc6af",
        "slug": "bathroom",
        "scope": "flashcast.com.my:services/0f294e6d-2e2c-4f13-a93f-096728ccc6af:faqs_en,faqs_zh",
        "evidence_root": ROOT,
        "qa_candidate_only": True,
        "candidate": ("backups/fc-20260924-org-017-bathroom-faq-rework-v3/desired-row.json", "4856f083b50acce95d444e960c2243836b1f89eb9854807429edcf76e4c7a938"),
        "rollback": ("backups/fc-20260924-org-017-bathroom-faq-rework-v3/rollback-target.json", "732d8396cb6c65291fdc9f8a12ea0d85edef48ce9046729a92d3055d3a0e5be5"),
        "qa_request": ("backups/fc-20260924-org-017-bathroom-faq-rework-v3/publisher-dry-run-request.json", "874fb4d6be549bd226289a9d3265d37fff71151d55d9ad6547db9120d0384aaf"),
        "qa_outbox": ("logs/department-outbox/fc-20260924-org-017-bathroom-faq-rework-v3-qa-recheck-v4.json", "ccc75985ce1889a88b0f8504dc7ff6224b729d8e6c64c6a99bec8f92f7f2852a"),
    },
    "office-service-scope-r1-v1": {
        "task_id": "fc-20260925-organic-owner-implementation-wave2",
        "action_id": "update-office-renovation-service-bilingual-content-v1",
        "candidate_version": "office-service-scope-r1-v1",
        "record_id": "a87541ac-1cba-4f1a-972d-428dccdbcc0f",
        "slug": "office-renovation",
        "scope": "flashcast.com.my:services/a87541ac-1cba-4f1a-972d-428dccdbcc0f:content_en,content_zh",
        "qa_candidate_only": True,
        "candidate": ("drafts/seo/fc-20260925-organic-owner-implementation-wave2/office-renovation-service-cms-candidate-v1.json", "852b311118c6ea920ec56807a017cd68221edcf6e51b9a99cb966dc15258244e"),
        "rollback": ("reports/evidence/2026-09-25-office-protected-preflight-v1/office-row-readonly.json", "7857a4eea39bbd96d546cbf379af9d6ae9eaf3d481c4d719aa920f82800c9f70"),
        "qa_outbox": ("logs/department-outbox/fc-20260925-organic-owner-implementation-wave2-qa-office-service-scope-r1-v1.json", "a9325dc7f3766849b49f0a01b7e8927a68b23dd06e8d49a237740e44b7de892a"),
    },
    "blog-kitchen-cabinet-cost-r1-v1": {
        "task_id": "fc-20260925-organic-query-page-completion-v1",
        "action_id": "update-kitchen-cabinet-cost-existing-blog-v1",
        "candidate_version": "kitchen-cabinet-cost-r1-v1",
        "record_id": "3fa4ff63-1ee6-4b7c-8f32-792c948c8545",
        "slug": "kitchen-cabinet-price-malaysia",
        "scope": "flashcast.com.my:blog_posts/3fa4ff63-1ee6-4b7c-8f32-792c948c8545",
        "qa_candidate_only": True,
        "candidate": ("drafts/seo/fc-20260925-organic-query-page-completion-v1/kitchen-cabinet-price-cms-candidate-v1.json", "63be90190ad6423ae195ca8ece1b8fe1c4d1ed097d8945adb65cb06114719f99"),
        "rollback": ("backups/fc-20260925-organic-query-page-completion-v1/kitchen-cabinet-price-current-row.json", "7821ff2f84daf4ab01cf707ef2f75fe29c80efefe941f095c349dacef8c7c3e9"),
        "qa_outbox": ("logs/department-outbox/fc-20260925-organic-query-page-completion-v1-qa-v2.json", "7fb78a2a0c866dcc3f04bb9563808eab2a615d1824af7220e752e32047f0f208"),
    },
    "blog-renovation-quotation-links-r1-v1": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "update-renovation-quotation-existing-blog-links-v1",
        "candidate_version": "renovation-quotation-links-r1-v1",
        "record_id": "cf594080-7230-4d77-83ac-0be55dfb3b9d",
        "slug": "renovation-quotation-checklist-malaysia",
        "scope": "flashcast.com.my:blog_posts/cf594080-7230-4d77-83ac-0be55dfb3b9d",
        "qa_candidate_only": True,
        "candidate": ("drafts/seo/fc-20260925-existing-page-content-gap-v1/renovation-quotation-checklist-malaysia-candidate-v1.json", "c14c828db8294b54a8076bfa978b3d1c8cb663b8b040d7d377284b2b8948d98e"),
        "rollback": ("backups/fc-20260925-existing-page-content-gap-v1/renovation-quotation-checklist-malaysia/current-row.json", "05472cd1f81b495e1f6efbfea741a06440cbf414ce12a5ebff60bbd29853126c"),
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-renovation-quotation-v2.json", "3fe913fdf26bf84b2a5dc1dce7af46d3af561f7f8d5e2434a781b3cabda64ee8"),
    },
    "blog-office-checklist-links-r1-v1": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "update-office-checklist-existing-blog-links-v1",
        "candidate_version": "office-checklist-links-r1-v1",
        "record_id": "190d319c-b027-4730-ab34-df5010f4acc0",
        "slug": "office-renovation-checklist-malaysia",
        "scope": "flashcast.com.my:blog_posts/190d319c-b027-4730-ab34-df5010f4acc0",
        "qa_candidate_only": True,
        "candidate": ("drafts/seo/fc-20260925-existing-page-content-gap-v1/office-renovation-checklist-malaysia-candidate-v1.json", "c9f7edd884a5b4e3583538ccdcbbd29bc666487b8bae73e88c69e52b41a2bb8c"),
        "rollback": ("backups/fc-20260925-existing-page-content-gap-v1/office-renovation-checklist-malaysia/current-row.json", "e2a94385407078a28b7dd5f8f27c5df8cad5ba228d1433bbecf00401f9749001"),
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-office-checklist-v2.json", "4952cbaa6a40ed8b44a053758682209e816adf6b858db7d38425a55f87fced97"),
    },
    "kl-location-intent-r1-v2": {
        "task_id": "fc-20260926-kl-location-cms-r1-closure-v1",
        "action_id": "update-kl-location-bilingual-content-v1",
        "candidate_version": "kl-location-intent-r1-v2",
        "record_id": "4e2cd77f-ac25-4a16-87bc-03652c4121b1",
        "slug": "kuala-lumpur",
        "scope": "flashcast.com.my:service_areas/4e2cd77f-ac25-4a16-87bc-03652c4121b1:content_en,content_zh",
        "candidate_shape": "record_key",
        "changed_fields": ("content_en", "content_zh"),
        "qa_candidate_only": True,
        "candidate": ("drafts/seo/fc-20260926-seo-owner-existing-page-wave3/kuala-lumpur-location-cms-candidate-v2.json", "78494509fc42d7bd91b4524ed2da200cb45f2ca4ea7d2c600b4f3032796af601"),
        "rollback": ("backups/fc-20260926-kl-location-cms-r1-closure-v1/current-row-readonly.json", "e041a994f3c4fe156fce51ba15158af85d8a86d575223e82d131b7a6ab818813"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-kl-location-cms-r1-closure-v1-qa.json", "2d35485c8af563bceadb686250bd68d26e9f069942c283394974ba4734c0e726"),
    },
    "org026-builtin-media-r1-v5": {
        "task_id": "fc-20260926-org026-service-media-cms-content-r1-v2",
        "action_id": "org026-service-media-cms-fields-r1-v4",
        "candidate_version": "service-media-fields-r1-v5",
        "record_id": "b401a610-a4dc-4a0b-a7e0-efcac6c81d71",
        "slug": "builtin",
        "scope": "flashcast.com.my:services/b401a610-a4dc-4a0b-a7e0-efcac6c81d71:image_url,alt_en,alt_zh",
        "candidate_shape": "items",
        "changed_fields": ("image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org026-service-media-cms-content-r1-v2/service-media-fields-r1-v5.json", "3c643421acbfc8df06df7041f7e189da13b8513f4f5ea35c6f72c208ed0c9cce"),
        "rollback": ("backups/fc-20260926-org026-service-media-cms-content-r1-v2/current-service-rows-readonly.json", "27b61d4a4e9defa8eb83e80241936718918130d54a5c52b5aa87a29b332f1050"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-org026-service-media-cms-content-r1-v2-qa.json", "f1c272478700e35d89f7dc199af92af3a06d1171dd59bfa85a094430b9a8b524"),
    },
    "org026-warehouse-media-r1-v5": {
        "retired_for_new_permit": True,
        "task_id": "fc-20260926-org026-service-media-cms-content-r1-v2",
        "action_id": "org026-service-media-cms-fields-r1-v4",
        "candidate_version": "service-media-fields-r1-v5",
        "record_id": "1fab3adb-aa8c-4aab-9c30-8931152cdc91",
        "slug": "warehouse",
        "scope": "flashcast.com.my:services/1fab3adb-aa8c-4aab-9c30-8931152cdc91:image_url,alt_en,alt_zh",
        "candidate_shape": "items",
        "changed_fields": ("image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org026-service-media-cms-content-r1-v2/service-media-fields-r1-v5.json", "3c643421acbfc8df06df7041f7e189da13b8513f4f5ea35c6f72c208ed0c9cce"),
        "rollback": ("backups/fc-20260926-org026-service-media-cms-content-r1-v2/current-service-rows-readonly.json", "27b61d4a4e9defa8eb83e80241936718918130d54a5c52b5aa87a29b332f1050"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-org026-service-media-cms-content-r1-v2-qa.json", "f1c272478700e35d89f7dc199af92af3a06d1171dd59bfa85a094430b9a8b524"),
    },
    "org026-office-renovation-media-r1-v5": {
        "retired_for_new_permit": True,
        "task_id": "fc-20260926-org026-service-media-cms-content-r1-v2",
        "action_id": "org026-service-media-cms-fields-r1-v4",
        "candidate_version": "service-media-fields-r1-v5",
        "record_id": "a87541ac-1cba-4f1a-972d-428dccdbcc0f",
        "slug": "office-renovation",
        "scope": "flashcast.com.my:services/a87541ac-1cba-4f1a-972d-428dccdbcc0f:image_url,alt_en,alt_zh",
        "candidate_shape": "items",
        "changed_fields": ("image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org026-service-media-cms-content-r1-v2/service-media-fields-r1-v5.json", "3c643421acbfc8df06df7041f7e189da13b8513f4f5ea35c6f72c208ed0c9cce"),
        "rollback": ("backups/fc-20260926-org026-service-media-cms-content-r1-v2/current-service-rows-readonly.json", "27b61d4a4e9defa8eb83e80241936718918130d54a5c52b5aa87a29b332f1050"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-org026-service-media-cms-content-r1-v2-qa.json", "f1c272478700e35d89f7dc199af92af3a06d1171dd59bfa85a094430b9a8b524"),
    },
    "org026-warehouse-media-r1-v6": {
        "task_id": "fc-20260926-org026-service-media-cms-content-r1-v2",
        "action_id": "org026-warehouse-media-cms-fields-r1-v6",
        "candidate_version": "warehouse-media-fields-r1-v6",
        "record_id": "1fab3adb-aa8c-4aab-9c30-8931152cdc91",
        "slug": "warehouse",
        "scope": "flashcast.com.my:services/1fab3adb-aa8c-4aab-9c30-8931152cdc91:image_url,alt_en,alt_zh",
        "candidate_shape": "items",
        "changed_fields": ("image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org026-service-media-cms-content-r1-v2/warehouse-media-fields-r1-v6.json", "02a3b0ba02f0cd5677bf77d2faeb0cbcad5c2d9cd6bdb1ca58082905487bdd28"),
        "rollback": ("backups/fc-20260926-org026-service-media-cms-content-r1-v2/current-service-rows-readonly.json", "27b61d4a4e9defa8eb83e80241936718918130d54a5c52b5aa87a29b332f1050"),
        # Fixed QA's independently produced row-specific outbox, not the retired shared QA.
        "qa_outbox": ("logs/department-outbox/fc-20260926-org026-service-media-cms-content-r1-v2-qa-warehouse-media-fields-r1-v6.json", "012824f73a57a0c52d27b5ac970e18dab1093042dfd40f48577c93753c0ebd33"),
    },
    "org026-office-renovation-media-r1-v6": {
        "task_id": "fc-20260926-org026-service-media-cms-content-r1-v2",
        "action_id": "org026-office-renovation-media-cms-fields-r1-v6",
        "candidate_version": "office-renovation-media-fields-r1-v6",
        "record_id": "a87541ac-1cba-4f1a-972d-428dccdbcc0f",
        "slug": "office-renovation",
        "scope": "flashcast.com.my:services/a87541ac-1cba-4f1a-972d-428dccdbcc0f:image_url,alt_en,alt_zh",
        "candidate_shape": "items",
        "changed_fields": ("image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org026-service-media-cms-content-r1-v2/office-renovation-media-fields-r1-v6.json", "338390baf2783b84a66a9acbf4c046f6918a4ce15dbb6c8fd820564ea59109b1"),
        "rollback": ("backups/fc-20260926-org026-service-media-cms-content-r1-v2/current-service-rows-readonly.json", "27b61d4a4e9defa8eb83e80241936718918130d54a5c52b5aa87a29b332f1050"),
        # Fixed QA's independently produced row-specific outbox, not the retired shared QA.
        "qa_outbox": ("logs/department-outbox/fc-20260926-org026-service-media-cms-content-r1-v2-qa-office-renovation-media-fields-r1-v6.json", "4c98dae0aa152e66baa0733131450986c3db494c39ad32583fc6a9693d21def1"),
    },
    "blog-kitchen-cabinet-media-r1-v1": {
        "task_id": "fc-20260926-org027-org028-blog-media-implementation-v1",
        "action_id": "replace-kitchen-cabinet-price-malaysia-cover-alt-v1",
        "candidate_version": "kitchen-cabinet-price-malaysia-media-r1-v1",
        "record_id": "3fa4ff63-1ee6-4b7c-8f32-792c948c8545",
        "slug": "kitchen-cabinet-price-malaysia",
        "scope": "flashcast.com.my:blog_posts/3fa4ff63-1ee6-4b7c-8f32-792c948c8545:cover_image_url,alt_en,alt_zh",
        "candidate_shape": "cms_media_row",
        "changed_fields": ("cover_image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org027-org028-blog-media-implementation-v1/kitchen-cabinet-price-malaysia-media-r1-v1.json", "a392eb317b03dd8b49b883e38954bcdaae5db8ebddd7873b225e15057a7241d9"),
        "rollback": ("backups/fc-20260926-org027-org028-blog-media-implementation-v1/cms-readonly-baseline-v1/kitchen-cabinet-price-malaysia.json", "d802d229a974d919fd17f7fce3e85b416524b532493cea72eabdf10d2abc7e41"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-org027-org028-blog-media-implementation-v1-qa-kitchen-media-v2.json", "a7f5b4cfc33e3aafaa5163cfb11c02715424c3e095bf40640951a327ed29a045"),
        # Baseline is audit-only, never authorization to restore the old cover.
    },
    "blog-office-checklist-media-r1-v1": {
        "task_id": "fc-20260926-org027-org028-blog-media-implementation-v1",
        "action_id": "replace-office-renovation-checklist-malaysia-cover-alt-v1",
        "candidate_version": "office-renovation-checklist-malaysia-media-r1-v1",
        "record_id": "190d319c-b027-4730-ab34-df5010f4acc0",
        "slug": "office-renovation-checklist-malaysia",
        "scope": "flashcast.com.my:blog_posts/190d319c-b027-4730-ab34-df5010f4acc0:cover_image_url,alt_en,alt_zh",
        "candidate_shape": "cms_media_row",
        "changed_fields": ("cover_image_url", "alt_en", "alt_zh"),
        "qa_candidate_only": True,
        "rollback_allowed": False,
        "candidate": ("drafts/seo/fc-20260926-org027-org028-blog-media-implementation-v1/office-renovation-checklist-malaysia-media-r1-v1.json", "fed6adf1629329526d0679867356a3376ffff0d19fca815ddb8fffe73af196e9"),
        "rollback": ("backups/fc-20260926-org027-org028-blog-media-implementation-v1/cms-readonly-baseline-v1/office-renovation-checklist-malaysia.json", "536216045e04f297ca3d6def38e0ad9d65e866fe926418248794520e72b42c71"),
        "qa_outbox": ("logs/department-outbox/fc-20260926-org027-org028-blog-media-implementation-v1-qa-office-media-v2.json", "2883272a8debbfeb31ce655c33e38a3bb5ec4b2a2766fc19b4bda81209ce8f2d"),
    },
}

# ORG-020 exact field-patch targets. QA pins stay absent until the fixed QA
# produces actual per-action evidence; registration alone cannot issue permits.
ORG020_TARGETS = {
    "org020-shop-intent-body-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-shop-intent-body-v7",
        "candidate_version": "shop-intent-body-r1-v7",
        "record_id": "32f5374f-9919-41ea-80c7-00b5ac917532",
        "slug": "shop-renovation",
        "scope": "flashcast.com.my:services/32f5374f-9919-41ea-80c7-00b5ac917532:content_en,content_zh",
        "table": "services",
        "content_type": "service",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_zh",
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "image_url",
            "alt_zh",
            "alt_en",
            "suitable_for_zh",
            "suitable_for_en",
            "common_projects_zh",
            "common_projects_en",
            "process_steps_zh",
            "process_steps_en",
            "scope_items_zh",
            "scope_items_en",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "f9a3126d01293039128270db7d9456cc10ff52fc8606c046d0a06d406a405776",
        "desired_fields_sha256": "8aa01f3de2801376adc20e0f8a7a875a661ddcd26bc9a218cfde0cd5cdd314dc",
        "expected_updated_at": "2026-09-25T07:25:59.506056+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/shop-intent-body-candidate.json",
            "86b665e0e5dffbba0a37ecf79b2dfa83ac86b3ce0e222a59388c45998edbc36c"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/shop-intent-body-candidate.json",
            "86b665e0e5dffbba0a37ecf79b2dfa83ac86b3ce0e222a59388c45998edbc36c"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/shop-intent-body-current-row.json",
            "3c48a91e41c28350a0c3bf5e836b6389091890c6a79914ba0051ed4c9c912625"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-shop-intent-body-r1-v7-candidate-v2.json", "8816cc950ae00f3f608dbe8574a771cc79beb7ff3a683601a3062c14f68f5a12")
    },
    "org020-zh-renovation-study-room-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-zh-renovation-study-room-v7",
        "candidate_version": "zh-renovation-study-room-r1-v7",
        "record_id": "0d947129-0595-43ef-baa1-0fd9d8b870e6",
        "slug": "renovation",
        "scope": "flashcast.com.my:services/0d947129-0595-43ef-baa1-0fd9d8b870e6:content_zh",
        "table": "services",
        "content_type": "service",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_zh"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "image_url",
            "alt_zh",
            "alt_en",
            "suitable_for_zh",
            "suitable_for_en",
            "common_projects_zh",
            "common_projects_en",
            "process_steps_zh",
            "process_steps_en",
            "scope_items_zh",
            "scope_items_en",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "618c50c2f7828a95998fe54d712f0330392e50aa2a692354e3ff118c5aa1934c",
        "desired_fields_sha256": "077457370f423287765eccc3551b20c5daf8c7a65a3d850644d2eb1fd0f03145",
        "expected_updated_at": "2026-09-25T08:02:22.805442+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/zh-renovation-study-room-candidate.json",
            "94c1c0c5feb68aaf2da7cf99523bc0c53cca5e75d7e3df8ba869c5427af698b4"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/zh-renovation-study-room-candidate.json",
            "94c1c0c5feb68aaf2da7cf99523bc0c53cca5e75d7e3df8ba869c5427af698b4"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/zh-renovation-study-room-current-row.json",
            "1a60a51a6e5ea472ef48e725a1d68f1c35948cfdeb02fc086baef7e0a300fa05"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-zh-renovation-study-room-r1-v7-candidate-v2.json", "9c152c9c99bd4a6cb0142863ad78a5478aa7dcf6030b3585a41f0a857104ec19")
    },
    "org020-budget-timeline-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-budget-timeline-v7",
        "candidate_version": "budget-timeline-r1-v7",
        "record_id": "1fcb274f-dbb8-4330-ba53-869a7880378c",
        "slug": "malaysia-renovation-budget-guide",
        "scope": "flashcast.com.my:blog_posts/1fcb274f-dbb8-4330-ba53-869a7880378c:content_en,content_zh",
        "table": "blog_posts",
        "content_type": "blog",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en",
            "content_zh"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "category",
            "tags",
            "cover_image_url",
            "alt_zh",
            "alt_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "published_at",
            "sort_order"
        ],
        "baseline_fields_sha256": "1207d2b633cb852611f15401c180ae8072744bd00c93d2babaf4c19c6363ba51",
        "desired_fields_sha256": "17a50eb5d2ae1a2fcda29f4da6363d5559395b06a9c9df256959368fcc77f012",
        "expected_updated_at": "2026-09-07T15:08:55.233699+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/budget-timeline-candidate.json",
            "f6c1e9252d2e45586f3681e4254fb0241254e66ed2fa59968a58b87711e67123"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/budget-timeline-candidate.json",
            "f6c1e9252d2e45586f3681e4254fb0241254e66ed2fa59968a58b87711e67123"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/budget-timeline-current-row.json",
            "1f92459601be634057687d9c5dc16af94235323dad68e85fe3eaaf56bfb91cc3"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-budget-timeline-r1-v7-candidate-v2.json", "1df71e592ae0acf637ff6fbad8c847eb1457b9399dd3a8ecdb3c1b196d1a1fdb")
    },
    "org020-area-ampang-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-ampang-prune-v7",
        "candidate_version": "area-ampang-prune-r1-v7",
        "record_id": "9c36157c-bcca-4911-b45e-f0c880681058",
        "slug": "ampang",
        "scope": "flashcast.com.my:service_areas/9c36157c-bcca-4911-b45e-f0c880681058:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "752730724810690a8164e47e22feeb29265bb3fe3382799f785c3774b243157b",
        "desired_fields_sha256": "c4c1439209ddef732c4fbfda0f64299c6b10ad636e3bde0277027f4ed63cb376",
        "expected_updated_at": "2026-08-22T08:46:01.228463+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-ampang-prune-candidate.json",
            "eb3502f27901de289ee55f99b5253298f988816f75f77df28ec55c79306c4370"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-ampang-prune-candidate.json",
            "eb3502f27901de289ee55f99b5253298f988816f75f77df28ec55c79306c4370"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-ampang-prune-current-row.json",
            "4ba79a86c04eea8fbd449facfd77eff0dc6220002a2fd4fe819f92ad380f7a1b"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-ampang-prune-r1-v7-candidate-v2.json", "0bda1861bedc5dd613f53b7c73ff28fc65b17aa27887f9268a1e560a2c5590ba")
    },
    "org020-area-ara-damansara-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-ara-damansara-prune-v7",
        "candidate_version": "area-ara-damansara-prune-r1-v7",
        "record_id": "a47b04a1-99ad-46df-9976-5a63135adf1f",
        "slug": "ara-damansara",
        "scope": "flashcast.com.my:service_areas/a47b04a1-99ad-46df-9976-5a63135adf1f:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "78e7bfd0fb7d56054f04c9a58d55d4d92c374a799a6a537a81695110c9bd9e3d",
        "desired_fields_sha256": "7ac2e7854ac2780bdc8bec8251e34a6743b77b6ef53fb2134383a596b00def62",
        "expected_updated_at": "2026-06-02T08:05:17.249751+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-ara-damansara-prune-candidate.json",
            "1f0fcce32663b5bba1aa7384f3cd8046e4083979a32b217fc0fb4be6ad9c9b90"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-ara-damansara-prune-candidate.json",
            "1f0fcce32663b5bba1aa7384f3cd8046e4083979a32b217fc0fb4be6ad9c9b90"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-ara-damansara-prune-current-row.json",
            "a43deca88ac5594ff183d50dbd90277653b6ff8e456c7919ce65dde3abbe49d6"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-ara-damansara-prune-r1-v7-candidate-v2.json", "5bcb4efd6cbf7736f290f60d8aed617279891bb8e4a8de3c8a0a0aab0b06fcde")
    },
    "org020-area-bangsar-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-bangsar-prune-v7",
        "candidate_version": "area-bangsar-prune-r1-v7",
        "record_id": "199e291e-2a95-4899-be5e-d78aea868ea7",
        "slug": "bangsar",
        "scope": "flashcast.com.my:service_areas/199e291e-2a95-4899-be5e-d78aea868ea7:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "25116eba79e48a1ba34613ddc52afb49f0f6163d92d26153cb07b6dec1239b57",
        "desired_fields_sha256": "236789294cfedf77abfc8a47effcef6926b9df25ac0bcced0bc6aab1299c7cf4",
        "expected_updated_at": "2026-08-22T08:45:49.406599+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-bangsar-prune-candidate.json",
            "33e3472c473e98c5cb8a96a847941a557ca1fe68e90033d58497cd9a7a4773e0"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-bangsar-prune-candidate.json",
            "33e3472c473e98c5cb8a96a847941a557ca1fe68e90033d58497cd9a7a4773e0"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-bangsar-prune-current-row.json",
            "90893ae65f11ae812d7ef102cfee536e44fab5e678031ca90bfe1977607fdbb4"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-bangsar-prune-r1-v7-candidate-v2.json", "2fef76c8212ac955fd2c8351545c0aa7a54d53dc995320600760c3d1159c6ebc")
    },
    "org020-area-bukit-jalil-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-bukit-jalil-prune-v7",
        "candidate_version": "area-bukit-jalil-prune-r1-v7",
        "record_id": "53665859-85f5-4176-a8e8-e70571f4e8fa",
        "slug": "bukit-jalil",
        "scope": "flashcast.com.my:service_areas/53665859-85f5-4176-a8e8-e70571f4e8fa:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "140e644e298908ad8b30a8fe286b254244f5ec6daa6cd9872ca1b7fe97d15f16",
        "desired_fields_sha256": "d939a86b8bb2a3e054c86610a07d1e0c997d66f25798e5d6614396a25a8b2bb1",
        "expected_updated_at": "2026-06-02T08:05:13.486508+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-bukit-jalil-prune-candidate.json",
            "d1b0fc8fdd06c45b672f0a6c0784a8d99156bb0e700947705b68cf63b9786dd8"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-bukit-jalil-prune-candidate.json",
            "d1b0fc8fdd06c45b672f0a6c0784a8d99156bb0e700947705b68cf63b9786dd8"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-bukit-jalil-prune-current-row.json",
            "38d54778f122d23046c2ca62d46faee4d46395190d6ca2d580818d630bf497dc"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-bukit-jalil-prune-r1-v7-candidate-v2.json", "e3c99f06fe4c1a5a7d006c91e6cd2b6a55ed6b9bc71bb42f667d7b5b4c98ec8a")
    },
    "org020-area-cheras-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-cheras-prune-v7",
        "candidate_version": "area-cheras-prune-r1-v7",
        "record_id": "2153b108-6057-4efd-b22c-d0ffed2ce44b",
        "slug": "cheras",
        "scope": "flashcast.com.my:service_areas/2153b108-6057-4efd-b22c-d0ffed2ce44b:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "32b00246c9f3dfbfedea0b347787e5f934d655b77f9989fc5f3e1627b8433fcb",
        "desired_fields_sha256": "1c04e69dabffd66267ff5820e2dc842aef4554219ac1920c3be26281c65dfe52",
        "expected_updated_at": "2026-08-22T08:45:39.396+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-cheras-prune-candidate.json",
            "15dc683c7a75fe3a0a66c17a97565f136436a8a494c212a3871d7d0e5a3cc721"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-cheras-prune-candidate.json",
            "15dc683c7a75fe3a0a66c17a97565f136436a8a494c212a3871d7d0e5a3cc721"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-cheras-prune-current-row.json",
            "335b1ddd6143d8300ae35f9a7d0be3d5bc37705a95f5bbee6b117f88f16820d4"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-cheras-prune-r1-v7-candidate-v2.json", "507c3b64581fb878be463cbe3c4ecec357f305363c34be35c690ca9b6999fed7")
    },
    "org020-area-cyberjaya-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-cyberjaya-prune-v7",
        "candidate_version": "area-cyberjaya-prune-r1-v7",
        "record_id": "2f7a98cf-26c2-4404-aead-86e9841e9d0b",
        "slug": "cyberjaya",
        "scope": "flashcast.com.my:service_areas/2f7a98cf-26c2-4404-aead-86e9841e9d0b:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "88aab2d174a407118ad497ab9b185f4c95813ec50c332ac2eb3f4c775e947e18",
        "desired_fields_sha256": "50f43f2a47b1d6c41712f25e97a2dddc3f34bcebdfdb0ad64fdcfbbd33d96018",
        "expected_updated_at": "2026-08-22T08:46:24.088266+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-cyberjaya-prune-candidate.json",
            "063c1d34637aa4ad9bd1b6c03197d91b63bbf81402abaa70196d6c4659f5b43a"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-cyberjaya-prune-candidate.json",
            "063c1d34637aa4ad9bd1b6c03197d91b63bbf81402abaa70196d6c4659f5b43a"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-cyberjaya-prune-current-row.json",
            "61436670fc2356dd47d96a8332de16e09b6f43308bdc28ae89751f72b8f58c6a"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-cyberjaya-prune-r1-v7-candidate-v2.json", "e1e3fc4d59cc304604ef1441e9123be0fab525263dedc1ba1047f7b21be4c075")
    },
    "org020-area-damansara-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-damansara-prune-v7",
        "candidate_version": "area-damansara-prune-r1-v7",
        "record_id": "14357d69-61b5-4057-a877-8a413e830b62",
        "slug": "damansara",
        "scope": "flashcast.com.my:service_areas/14357d69-61b5-4057-a877-8a413e830b62:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "461a208fb368b01ac11f299e62e365cdd3987494f8ff4a5568e7e8eca3393938",
        "desired_fields_sha256": "1d7be7df144a68c2333c570a40097e87783910f8e23228b5af2834e4a9b24384",
        "expected_updated_at": "2026-08-22T08:45:58.122724+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-damansara-prune-candidate.json",
            "e3924bb2009f342e42899418639924d80968bedc5ee66afe0015fe58cbe6c17a"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-damansara-prune-candidate.json",
            "e3924bb2009f342e42899418639924d80968bedc5ee66afe0015fe58cbe6c17a"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-damansara-prune-current-row.json",
            "6762f2a89012a92c5f4264ed8bc6c1b9d1908215fb1d837d92aa091efec59b2c"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-damansara-prune-r1-v7-candidate-v2.json", "d1ac6b7fb4158c1b0d930241ae2fdacdfb1d2c3b9323fe88a4a8bdf76c75b4ca")
    },
    "org020-area-kepong-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-kepong-prune-v7",
        "candidate_version": "area-kepong-prune-r1-v7",
        "record_id": "c30df350-2c5d-45eb-938d-919cca97b9a3",
        "slug": "kepong",
        "scope": "flashcast.com.my:service_areas/c30df350-2c5d-45eb-938d-919cca97b9a3:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "4126043133ae4b3477f26ddb3adc6e6a7dc4b69662cbdaf25cd03404350c86cc",
        "desired_fields_sha256": "b4e1d6d808023ae73b03a281bc554c990fe374be25b3b57775dfd6c79df34476",
        "expected_updated_at": "2026-08-22T08:46:04.051118+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-kepong-prune-candidate.json",
            "278c9518b5c4665dbdadb8ce407398bdd00e66450b491d2e34e58ef4d5d9ddd8"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-kepong-prune-candidate.json",
            "278c9518b5c4665dbdadb8ce407398bdd00e66450b491d2e34e58ef4d5d9ddd8"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-kepong-prune-current-row.json",
            "c14c6e470dc242e3950859e1bf4bbe74dcfabfd11becbc98dac784e305653dd9"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-kepong-prune-r1-v7-candidate-v2.json", "6720a07d34d51fa8e5548f5adc17ad4d3a555868e599019425e6e0b4772c1f15")
    },
    "org020-area-kota-damansara-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-kota-damansara-prune-v7",
        "candidate_version": "area-kota-damansara-prune-r1-v7",
        "record_id": "a1822d67-a918-4208-a9d8-2ddb8e199837",
        "slug": "kota-damansara",
        "scope": "flashcast.com.my:service_areas/a1822d67-a918-4208-a9d8-2ddb8e199837:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "d10d59aa809e50e57ab1b5d2ceb704c72c2c5a483367fa9adb5ad340d3d44703",
        "desired_fields_sha256": "5be3e945b5db1e08314040b4e2e124a63e9bbc08f9c280a41901618a2a3ec20c",
        "expected_updated_at": "2026-06-02T08:05:12.47671+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-kota-damansara-prune-candidate.json",
            "198c3b637087a15dd2a15eeb73bf2224dd96806bf46f25c9bbb0efea5ee8e8a0"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-kota-damansara-prune-candidate.json",
            "198c3b637087a15dd2a15eeb73bf2224dd96806bf46f25c9bbb0efea5ee8e8a0"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-kota-damansara-prune-current-row.json",
            "e5e92817564fa004ae52f9447b5376e5bc510fb5edd0cb9c621812796da5c40f"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-kota-damansara-prune-r1-v7-candidate-v2.json", "a47b445b1a174c07fd2e02880ddfa68a66d4f7a6f3dbeb280dd6c71acf403be1")
    },
    "org020-area-mont-kiara-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-mont-kiara-prune-v7",
        "candidate_version": "area-mont-kiara-prune-r1-v7",
        "record_id": "7829a30b-0c34-4972-b088-28b06784f039",
        "slug": "mont-kiara",
        "scope": "flashcast.com.my:service_areas/7829a30b-0c34-4972-b088-28b06784f039:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "fe0d74b095d0e4de5ca29df70091def3781338d492af7bb530da8797437ac7b3",
        "desired_fields_sha256": "e81f171925eb4ee6daaffccd6c0fc93be3c7fd41a9015c469500edd15ad4bf9c",
        "expected_updated_at": "2026-08-22T08:44:54.880713+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-mont-kiara-prune-candidate.json",
            "e76104c2893b84c39d3b8947e7e1db3f1dcbec2acb967ab583aaa1865d7e5619"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-mont-kiara-prune-candidate.json",
            "e76104c2893b84c39d3b8947e7e1db3f1dcbec2acb967ab583aaa1865d7e5619"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-mont-kiara-prune-current-row.json",
            "fc6c7f59851ca8cd18eec1c9d6e304cb9668621b5be5f973cd3ade78fc007046"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-mont-kiara-prune-r1-v7-candidate-v2.json", "d8eb6cb7773b5537cded7df6f88ede1a38f12e386f3588b57d3a0d34fc7095ef")
    },
    "org020-area-petaling-jaya-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-petaling-jaya-prune-v7",
        "candidate_version": "area-petaling-jaya-prune-r1-v7",
        "record_id": "0211fd88-54c7-4e5a-bdcc-5452601c779f",
        "slug": "petaling-jaya",
        "scope": "flashcast.com.my:service_areas/0211fd88-54c7-4e5a-bdcc-5452601c779f:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "eb83ecefc6a79e8e00090982f7816defaa8982292e379c91830003b890beae2c",
        "desired_fields_sha256": "0f8dc70dbec1daae11e9ed80d2d188cb5061ff8d3dfa35583db851d3a6b03a20",
        "expected_updated_at": "2026-08-22T08:45:28.095037+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-petaling-jaya-prune-candidate.json",
            "3e272f77445389b4e609129207ac2ee979e54e72e3ec52b0955267bb92214b5b"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-petaling-jaya-prune-candidate.json",
            "3e272f77445389b4e609129207ac2ee979e54e72e3ec52b0955267bb92214b5b"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-petaling-jaya-prune-current-row.json",
            "c02b98d5c217b36f3f17b19be2f3492536c307153690431975dd6452c02d03a9"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-petaling-jaya-prune-r1-v7-candidate-v2.json", "1a09163c3134a172b4f75738939970d86c905acbb0e622ef61ff12ca6f0275de")
    },
    "org020-area-puchong-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-puchong-prune-v7",
        "candidate_version": "area-puchong-prune-r1-v7",
        "record_id": "c4586bbc-4f42-4ab9-8ca9-ac8d7015b229",
        "slug": "puchong",
        "scope": "flashcast.com.my:service_areas/c4586bbc-4f42-4ab9-8ca9-ac8d7015b229:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "31fee888ec9c2574e33ee96159fe1004fc12720578b4a5f17d35eae7ba02645b",
        "desired_fields_sha256": "4ad51fee10ea3f6b36ac71fa9c66d438a8c9a3b1084b274167db65f0cea9f2d5",
        "expected_updated_at": "2026-08-22T08:45:35.520904+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-puchong-prune-candidate.json",
            "5994be38bd0f7de6e26ee1a57ed5286ee5f472eaa4486c5b1161008d6c0f9db3"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-puchong-prune-candidate.json",
            "5994be38bd0f7de6e26ee1a57ed5286ee5f472eaa4486c5b1161008d6c0f9db3"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-puchong-prune-current-row.json",
            "0a22d62ac7794b51950b421d08cf3fa51d20d630f658eface3847750b4dfa137"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-puchong-prune-r1-v7-candidate-v2.json", "4a938262ef81c9c0eb8d46c1b0efdab199c6722c03d98dcd39eecf642bce9a89")
    },
    "org020-area-selangor-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-selangor-prune-v7",
        "candidate_version": "area-selangor-prune-r1-v7",
        "record_id": "e2e461b7-3bb8-4206-817a-7f830824b8ac",
        "slug": "selangor",
        "scope": "flashcast.com.my:service_areas/e2e461b7-3bb8-4206-817a-7f830824b8ac:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "6d69c4e08e2a10cb5cd0b2bd745f21f191a18e3da8acbaa7d29ea59a33585517",
        "desired_fields_sha256": "e92bd6eee6513f9a32b9bd8b4993fc738e0b8173e45cf3eb92e3553cd9beab6c",
        "expected_updated_at": "2026-09-25T15:58:19.761673+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-selangor-prune-candidate.json",
            "300f77876b904a68f4fcffaa74ee7c25922e17f95c9e9a9853e02fffe0d1b8e2"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-selangor-prune-candidate.json",
            "300f77876b904a68f4fcffaa74ee7c25922e17f95c9e9a9853e02fffe0d1b8e2"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-selangor-prune-current-row.json",
            "4ef96b8d0d0311208570ce4469e42674fd4bffa160c33c73d0a7d2b59a542b5e"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-selangor-prune-r1-v7-candidate-v2.json", "1897b9a472102d7d58bb8f1e4cc92d3cc0e3d6177f6c0725c2bb7bfb03fb094a")
    },
    "org020-area-setapak-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-setapak-prune-v7",
        "candidate_version": "area-setapak-prune-r1-v7",
        "record_id": "5fa21a11-4f43-4aca-8635-80f010e3ee51",
        "slug": "setapak",
        "scope": "flashcast.com.my:service_areas/5fa21a11-4f43-4aca-8635-80f010e3ee51:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "3f189b9db99fa91a93973c85706b1bd4b729e2edc72ea72458d213dbcb661f4b",
        "desired_fields_sha256": "5484ad6e2436c08b0beb414c5d42b5b79ce05a60356f4b5ed3588a370d77f7cd",
        "expected_updated_at": "2026-08-22T08:46:18.327823+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-setapak-prune-candidate.json",
            "22c034b7be42f1107933ed0d331fa9d2f0a56b2a2ecbe26d928b355136dfee14"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-setapak-prune-candidate.json",
            "22c034b7be42f1107933ed0d331fa9d2f0a56b2a2ecbe26d928b355136dfee14"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-setapak-prune-current-row.json",
            "d4ab759e21c1b5c83a2e1b433ffe976a6344d5e4225f46f53b94fe2f025fe29b"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-setapak-prune-r1-v7-candidate-v2.json", "18dad61d0ff439365689c2c43fa42456381e7013ca7e9bec70b4867eaffe9cd1")
    },
    "org020-area-setia-alam-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-setia-alam-prune-v7",
        "candidate_version": "area-setia-alam-prune-r1-v7",
        "record_id": "5fcb39f0-979e-41a5-b627-be817b00cca7",
        "slug": "setia-alam",
        "scope": "flashcast.com.my:service_areas/5fcb39f0-979e-41a5-b627-be817b00cca7:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "ff96f44c4782852663de933efc5752c75fe72974aac6dea43dd47f9b06de5714",
        "desired_fields_sha256": "4501eaf6b8141a329c329173a5072d904401128ab1551ebf8e32f3dae26f7e44",
        "expected_updated_at": "2026-06-02T08:05:11.544684+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-setia-alam-prune-candidate.json",
            "89676a1d2ab5bf6c31fa25ed9a03a1c9bfd5e70e5d5689d22c213abc1f0c4dbb"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-setia-alam-prune-candidate.json",
            "89676a1d2ab5bf6c31fa25ed9a03a1c9bfd5e70e5d5689d22c213abc1f0c4dbb"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-setia-alam-prune-current-row.json",
            "75eec6bf8513df125c14b8540b4478b313ffe8aeb8397c28b6c1ef64501761f0"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-setia-alam-prune-r1-v7-candidate-v2.json", "b68e4205c605009f736c6feddeb5059b6b6195417e20566604e75490bc6d57cd")
    },
    "org020-area-shah-alam-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-shah-alam-prune-v7",
        "candidate_version": "area-shah-alam-prune-r1-v7",
        "record_id": "d0db92f6-37e7-45f6-bd46-522fbd7dde54",
        "slug": "shah-alam",
        "scope": "flashcast.com.my:service_areas/d0db92f6-37e7-45f6-bd46-522fbd7dde54:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "a3a601633e0ab0e128abe4b00d8d74225c517614e98127bb2e0853bfaaebf372",
        "desired_fields_sha256": "afd8d512053d7d3c51cb202ab0cac326d2a46e629b3700a953bbdcfa5436b90b",
        "expected_updated_at": "2026-08-22T08:45:52.426264+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-shah-alam-prune-candidate.json",
            "dc7f20a710ba76a70e9a07ff74b07ba282e9018639d8e583b2feffcb2eddcc78"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-shah-alam-prune-candidate.json",
            "dc7f20a710ba76a70e9a07ff74b07ba282e9018639d8e583b2feffcb2eddcc78"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-shah-alam-prune-current-row.json",
            "3941840ddc40048a3bb9df98bd2c796e6c36588a694e3afa6586444cbdd54f55"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-shah-alam-prune-r1-v7-candidate-v2.json", "a779afae926d9f9fcf8866833e11427d637d9a98bf7fdd2c1cd0494d1c4a26c3")
    },
    "org020-area-sri-petaling-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-sri-petaling-prune-v7",
        "candidate_version": "area-sri-petaling-prune-r1-v7",
        "record_id": "c9355ba6-16fc-4054-a00b-8ba6b9ae1b2b",
        "slug": "sri-petaling",
        "scope": "flashcast.com.my:service_areas/c9355ba6-16fc-4054-a00b-8ba6b9ae1b2b:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "6fbb7add3c2064019818173e574d9a9def3d8042198e9f4bdc5fece410449d44",
        "desired_fields_sha256": "12353874171dafe5e2387f6137a51a730f773cc4e24232c2a908afb4fb4173ed",
        "expected_updated_at": "2026-08-22T08:46:15.313911+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-sri-petaling-prune-candidate.json",
            "4165712b25b40f0de05e19d807ea1dd2504d7ec804fda7f4192336d90f212fa4"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-sri-petaling-prune-candidate.json",
            "4165712b25b40f0de05e19d807ea1dd2504d7ec804fda7f4192336d90f212fa4"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-sri-petaling-prune-current-row.json",
            "49d38572aa8ebc0bde3a18d602b3585e2aeefd959741dd49b223690d7993b5f4"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-sri-petaling-prune-r1-v7-candidate-v2.json", "406fe6f68d430a8e1b0b93d7cae8fac08d490d6260da8c87b1021dd1f331675b")
    },
    "org020-area-subang-jaya-prune-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-area-subang-jaya-prune-v7",
        "candidate_version": "area-subang-jaya-prune-r1-v7",
        "record_id": "5ad0e8bf-04c6-43e1-9596-7fb6f6112543",
        "slug": "subang-jaya",
        "scope": "flashcast.com.my:service_areas/5ad0e8bf-04c6-43e1-9596-7fb6f6112543:content_en",
        "table": "service_areas",
        "content_type": "service_area",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "area_name",
            "property_types",
            "common_needs",
            "construction_notes_zh",
            "construction_notes_en",
            "projects",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "a564cd23c282aa2242dcf51ffa31d0b0d8ff9c0e972463990fd6ec21657d6424",
        "desired_fields_sha256": "ddc2d6f41f5f653287d79b5b583ff828f4f746082d89e5027d992dab9dd4d544",
        "expected_updated_at": "2026-08-22T08:45:32.28099+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-subang-jaya-prune-candidate.json",
            "766df86f2ea1bad5eb039187d1d8fdeff3edf9b18bdfaa301749a71c3a91a449"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/area-subang-jaya-prune-candidate.json",
            "766df86f2ea1bad5eb039187d1d8fdeff3edf9b18bdfaa301749a71c3a91a449"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/area-subang-jaya-prune-current-row.json",
            "043cc818550b1869ec09b5b59cb4cf88cc906babe2f934ff8c398de0d769f361"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-area-subang-jaya-prune-r1-v7-candidate-v2.json", "f9359f5fc27e9947349c62768630016ff2d7e111540528c771914101a53381a8")
    },
    "org020-general-quote-30km-answer-r1-v8": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-general-quote-30km-v7-answer-execution-v8",
        "candidate_version": "general-quote-30km-answer-execution-r1-v8",
        "record_id": "baa8e461-1269-47a7-a82f-c81487c1c657",
        "slug": "faq-baa8e461-1269-47a7-a82f-c81487c1c657",
        "scope": "flashcast.com.my:faqs/baa8e461-1269-47a7-a82f-c81487c1c657:answer_en,answer_zh",
        "table": "faqs",
        "content_type": "faq",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "answer_zh",
            "answer_en"
        ],
        "baseline_projection_fields": [
            "id",
            "page_key",
            "question_zh",
            "question_en",
            "answer_zh",
            "answer_en",
            "status",
            "sort_order",
            "updated_at"
        ],
        "baseline_fields_sha256": "94bcaa30663b1a0ea2d7b068f38886361b0138f32f2b70a6e12a11f40d29501c",
        "desired_fields_sha256": "9f07adf698d8bc4d23bb32d213eb977dc2ba8f0d71989d7f8372ab9a338806a1",
        "expected_updated_at": "2026-05-29T12:52:02.57532+00:00",
        "candidate": [
            "drafts/seo/fc-20260926-org020-v7-publisher-capability-v1/general-quote-30km-answer-execution-r1-v8.json",
            "f83eae7fdf0477d0f946ba34bae59594d1667e77cda66ab9f0e1ca471322f3b3"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/general-quote-30km-candidate.json",
            "41bd09cebd20f33185c007f34676188db20652f281ce5e82cdf870b7c196ec15"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/general-quote-30km-current-row.json",
            "dcce1c69dbea98decebb770a569177ade6bd79b343b8e80c209f14a910e75ec2"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-general-quote-30km-answer-r1-v8-candidate-v2.json", "c0f7fe86d8732f0cc44c0a8c569d6f622b9e612f2aa7794e38bfbe5d08c638ba")
    },
    "org020-home-quote-30km-answer-r1-v8": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-home-quote-30km-v7-answer-execution-v8",
        "candidate_version": "home-quote-30km-answer-execution-r1-v8",
        "record_id": "4cd35122-16d3-4f0d-a60c-49c8e0d996f8",
        "slug": "faq-4cd35122-16d3-4f0d-a60c-49c8e0d996f8",
        "scope": "flashcast.com.my:faqs/4cd35122-16d3-4f0d-a60c-49c8e0d996f8:answer_en,answer_zh",
        "table": "faqs",
        "content_type": "faq",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "answer_zh",
            "answer_en"
        ],
        "baseline_projection_fields": [
            "id",
            "page_key",
            "question_zh",
            "question_en",
            "answer_zh",
            "answer_en",
            "status",
            "sort_order",
            "updated_at"
        ],
        "baseline_fields_sha256": "cb2db9898ce946612a0acff470dbfca7bb1e7427bce01a17c71f8c489ea31d5f",
        "desired_fields_sha256": "c004dd71c236dc4c380cb9316a3de37984514f64d52e64496efa19b4fb88d201",
        "expected_updated_at": "2026-08-21T15:49:56.800849+00:00",
        "candidate": [
            "drafts/seo/fc-20260926-org020-v7-publisher-capability-v1/home-quote-30km-answer-execution-r1-v8.json",
            "6c25c4fc765f1636b667a2956972c08ec70fbfcb41779513fea5435f5d7d282a"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/home-quote-30km-candidate.json",
            "80032c7ccd11feb76d193304fd975c165d0df6970cd340036ec54d806454439e"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/home-quote-30km-current-row.json",
            "1d25d525a3ce7e6b6c44dac7ca18941e986bfad467c2798d2b7bff371236ceba"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-home-quote-30km-answer-r1-v8-candidate-v2.json", "3c4c166522e4f207aa86c104814015a9ea7f1b91a9267235ce2c8c48c7df8dec")
    },
    "org020-home-one-year-warranty-answer-r1-v8": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-home-one-year-warranty-v7-answer-execution-v8",
        "candidate_version": "home-one-year-warranty-answer-execution-r1-v8",
        "record_id": "c2fad758-eff4-4feb-a9fb-87e6cb5bf77e",
        "slug": "faq-c2fad758-eff4-4feb-a9fb-87e6cb5bf77e",
        "scope": "flashcast.com.my:faqs/c2fad758-eff4-4feb-a9fb-87e6cb5bf77e:answer_en,answer_zh",
        "table": "faqs",
        "content_type": "faq",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "answer_zh",
            "answer_en"
        ],
        "baseline_projection_fields": [
            "id",
            "page_key",
            "question_zh",
            "question_en",
            "answer_zh",
            "answer_en",
            "status",
            "sort_order",
            "updated_at"
        ],
        "baseline_fields_sha256": "ca110819313f79322c675024879678fc8fb1b8570d91125f2cfeab71e9fe465a",
        "desired_fields_sha256": "a9943008b1eb62c339ca35b19c65dcd13d18e9dc6d9afc8c5eb8c3bc7a0e1b9c",
        "expected_updated_at": "2026-08-21T15:49:57.402821+00:00",
        "candidate": [
            "drafts/seo/fc-20260926-org020-v7-publisher-capability-v1/home-one-year-warranty-answer-execution-r1-v8.json",
            "ecf5b94786abf6253a1de709afd707411116a44f64b6188c19add037c7cafbb7"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/home-one-year-warranty-candidate.json",
            "97ac2e9f61af21ccb339b213fae7dcca03cc942117da46eda97ed4b7f23eb654"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/home-one-year-warranty-current-row.json",
            "450f3d655d4208d63f6fc0c3e4712d55e8ea1d5080b35e1b85bb5036cf9578e2"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-home-one-year-warranty-answer-r1-v8-candidate-v2.json", "7d02b25d3f142921fc30e7fac2710d85ba1ae2bec5c2911a6f64b03249df81aa")
    },
    "org020-locations-hub-availability-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-locations-hub-availability-v7",
        "candidate_version": "locations-hub-availability-r1-v7",
        "record_id": "2a2ce510-780f-4ce0-8750-0be8f3753944",
        "slug": "locations",
        "scope": "flashcast.com.my:site_pages/2a2ce510-780f-4ce0-8750-0be8f3753944:description_en,description_zh",
        "table": "site_pages",
        "content_type": "site_page",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "description_zh",
            "description_en"
        ],
        "baseline_projection_fields": [
            "id",
            "page_key",
            "path",
            "title_zh",
            "title_en",
            "subtitle_zh",
            "subtitle_en",
            "description_zh",
            "description_en",
            "content_zh",
            "content_en",
            "cta_title_zh",
            "cta_title_en",
            "cta_description_zh",
            "cta_description_en",
            "image_url",
            "alt_zh",
            "alt_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "seo_keywords_zh",
            "seo_keywords_en",
            "items_zh",
            "items_en",
            "status",
            "sort_order",
            "updated_at"
        ],
        "baseline_fields_sha256": "41b098748f7c6b0b2e9f0ad607d68224c8ec00867ce359193f0db774a69d6cdb",
        "desired_fields_sha256": "a7fe847e8ef13d245a1142e6c5f3ab10dd7c850cef5799d716fbb51f05c519b3",
        "expected_updated_at": "2026-08-21T20:03:25.119179+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/locations-hub-availability-candidate.json",
            "2f1424d029e6b15c20d9623ac1f6911f998f590f3a37c82965c1e757e245e17e"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/locations-hub-availability-candidate.json",
            "2f1424d029e6b15c20d9623ac1f6911f998f590f3a37c82965c1e757e245e17e"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/locations-hub-availability-current-row.json",
            "81b71b67b2677e2375c090c71842e025eb2f9cf8e5d1c60c149d631437532af1"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-locations-hub-availability-r1-v7-candidate-v2.json", "879a6bcdfdb1f131a5a3ab11d24dcff4568f4b5c188dbd920bdc883fc7d09f0b")
    },
    "org020-coating-fact-safe-body-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-coating-fact-safe-body-v7",
        "candidate_version": "coating-fact-safe-body-r1-v7",
        "record_id": "d862312d-d5f3-4bb7-9bf0-137ed71c87be",
        "slug": "artistic-coating",
        "scope": "flashcast.com.my:services/d862312d-d5f3-4bb7-9bf0-137ed71c87be:alt_en,alt_zh,content_en,content_zh,excerpt_en,excerpt_zh,process_steps_en,process_steps_zh,scope_items_en,scope_items_zh,seo_description_en,seo_description_zh,seo_title_en,seo_title_zh,title_en,title_zh",
        "table": "services",
        "content_type": "service",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_zh",
            "content_en",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "alt_zh",
            "alt_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "scope_items_zh",
            "scope_items_en",
            "process_steps_zh",
            "process_steps_en"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "image_url",
            "alt_zh",
            "alt_en",
            "suitable_for_zh",
            "suitable_for_en",
            "common_projects_zh",
            "common_projects_en",
            "process_steps_zh",
            "process_steps_en",
            "scope_items_zh",
            "scope_items_en",
            "faqs_zh",
            "faqs_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "sort_order"
        ],
        "baseline_fields_sha256": "0ea082a23256203346441716285fd06521de278d583b84090c9e3c339c3fc219",
        "desired_fields_sha256": "59e14663f5bef76a32ed23f5f05f10eee4efc79216598447e42c7d6a500853c4",
        "expected_updated_at": "2026-06-02T08:04:52.946145+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/coating-fact-safe-body-candidate.json",
            "31cf327c300937e7f3721412f3f50a0234f35c83b5d5f6cbe089f62002c1d46f"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/coating-fact-safe-body-candidate.json",
            "31cf327c300937e7f3721412f3f50a0234f35c83b5d5f6cbe089f62002c1d46f"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/coating-fact-safe-body-current-row.json",
            "f5ae51670807b4a0cbdbeb967dac64cf2780891777dfb63a556f44d260b79aba"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-coating-fact-safe-body-r1-v7-candidate-v2.json", "22a93faac10357f7e8b11f69c392a2d52bedba460d281dd2c769364ca5d9be66")
    },
    "org020-condo-current-sources-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-condo-current-sources-v7",
        "candidate_version": "condo-current-sources-r1-v7",
        "record_id": "701c2406-ba5b-4bbc-8d47-f985047d5c81",
        "slug": "condo-renovation-management-approval-malaysia",
        "scope": "flashcast.com.my:blog_posts/701c2406-ba5b-4bbc-8d47-f985047d5c81:content_en,content_zh",
        "table": "blog_posts",
        "content_type": "blog",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en",
            "content_zh"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "category",
            "tags",
            "cover_image_url",
            "alt_zh",
            "alt_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "published_at",
            "sort_order"
        ],
        "baseline_fields_sha256": "33543229cebb5085fdd17d8c27a74c083b0ab1cedc7edb0f5b627d16275f63e1",
        "desired_fields_sha256": "258a1d3f30917b2848c4792bea16c399ab6f1b6959738d3acb9abb58a6335e4b",
        "expected_updated_at": "2026-08-22T12:22:48.46177+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/condo-current-sources-candidate.json",
            "cf83e6b6c2956792f2eac842583326b69baed62910db3b714d03722d984c314b"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/condo-current-sources-candidate.json",
            "cf83e6b6c2956792f2eac842583326b69baed62910db3b714d03722d984c314b"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/condo-current-sources-current-row.json",
            "11e3b499f22616b5c0bdb0abcf89e13c6bef5916ff9108622049e56b4d0cfcbf"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-condo-current-sources-r1-v7-candidate-v2.json", "0129235747a3d60faa688bb5bcc85c144908cf83816b5c4a757d89a7e1a32506")
    },
    "org020-dbkl-current-sources-r1-v7": {
        "task_id": "fc-20260925-existing-page-content-gap-v1",
        "action_id": "org020-dbkl-current-sources-v7",
        "candidate_version": "dbkl-current-sources-r1-v7",
        "record_id": "a58f337f-f070-4d28-a28e-bc6add7c42fd",
        "slug": "renovation-permit-dbkl-guide",
        "scope": "flashcast.com.my:blog_posts/a58f337f-f070-4d28-a28e-bc6add7c42fd:content_en,content_zh",
        "table": "blog_posts",
        "content_type": "blog",
        "qa_candidate_only": True,
        "candidate_shape": "org020_field_patch",
        "rollback_allowed": False,
        "changed_fields": [
            "content_en",
            "content_zh"
        ],
        "baseline_projection_fields": [
            "id",
            "slug",
            "status",
            "updated_at",
            "title_zh",
            "title_en",
            "excerpt_zh",
            "excerpt_en",
            "content_zh",
            "content_en",
            "category",
            "tags",
            "cover_image_url",
            "alt_zh",
            "alt_en",
            "seo_title_zh",
            "seo_title_en",
            "seo_description_zh",
            "seo_description_en",
            "published_at",
            "sort_order"
        ],
        "baseline_fields_sha256": "4768610336b18ae78dc5e5db9a25b876dac20caa68ee13bd8fcb25d314e05802",
        "desired_fields_sha256": "1a3c934809c65760d00e98507b73c56beadfb9053254f7c4fc58752d9e75c350",
        "expected_updated_at": "2026-08-22T12:23:01.800158+00:00",
        "candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/dbkl-current-sources-candidate.json",
            "e1e36404c51e7a25e6117109f6aa7ea2a393a46bc5d4b61fe48ff96d2bef151f"
        ],
        "source_frozen_candidate": [
            "drafts/seo/fc-20260925-existing-page-content-gap-v1/v7/dbkl-current-sources-candidate.json",
            "e1e36404c51e7a25e6117109f6aa7ea2a393a46bc5d4b61fe48ff96d2bef151f"
        ],
        "rollback": [
            "backups/fc-20260925-existing-page-content-gap-v1/v7/dbkl-current-sources-current-row.json",
            "52c91c6f839177c504965e92b4837f6c13a367f6985e5ea13b2979e4f9826443"
        ],
        "qa_outbox": ("logs/department-outbox/fc-20260925-existing-page-content-gap-v1-qa-org020-dbkl-current-sources-r1-v7-candidate-v2.json", "f835f17bfe3b7abf397de18b61e171ffd6e5f26d41f3f90020bf085bb1fa0868")
    }
}
TARGETS.update(ORG020_TARGETS)

NATIVE_TARGETS = load_native_issuer_targets(ROOT)
if set(TARGETS) & set(NATIVE_TARGETS):
    raise ValueError("Native target conflicts with a historical issuer identity")
TARGETS.update(NATIVE_TARGETS)

REPAIR_FAQ_TARGETS = load_repair_faq_registration(ROOT)
if set(TARGETS) & set(REPAIR_FAQ_TARGETS):
    raise ValueError("Repair FAQ registration collides with an existing target")
TARGETS.update(REPAIR_FAQ_TARGETS)

WAVE234_BODY_TARGETS = load_wave234_body_registration(ROOT)
if set(TARGETS) & set(WAVE234_BODY_TARGETS):
    raise ValueError("Wave234 body registration collides with an existing target")
TARGETS.update(WAVE234_BODY_TARGETS)

REMAINING186_BLOG_TARGETS = load_remaining186_blog_registration(ROOT)
if set(TARGETS) & set(REMAINING186_BLOG_TARGETS):
    raise ValueError("Remaining186 Blog registration collides with an existing target")
TARGETS.update(REMAINING186_BLOG_TARGETS)

SHOP_CHILDREN_BODY_TARGETS = load_shop_children_body_registration(ROOT)
if set(TARGETS) & set(SHOP_CHILDREN_BODY_TARGETS):
    raise ValueError("Shop/children registration collides with an existing target")
TARGETS.update(SHOP_CHILDREN_BODY_TARGETS)

FIVE_PROJECTION_TARGETS = load_five_source_projection_registration(ROOT)
if set(TARGETS) & set(FIVE_PROJECTION_TARGETS):
    raise ValueError("Five-source projection registration collides with an existing target")
TARGETS.update(FIVE_PROJECTION_TARGETS)

PUBLISHER_EXACT_TARGETS = load_publisher_exact_registration(ROOT)
if set(TARGETS) & set(PUBLISHER_EXACT_TARGETS):
    raise ValueError('Publisher tuple collides with a historical target')
TARGETS.update(PUBLISHER_EXACT_TARGETS)

BLOG_TARGETS = frozenset({
    "blog-kitchen-cabinet-cost-r1-v1",
    "blog-renovation-quotation-links-r1-v1",
    "blog-office-checklist-links-r1-v1",
})
BLOG_MEDIA_TARGETS = frozenset({
    "blog-kitchen-cabinet-media-r1-v1",
    "blog-office-checklist-media-r1-v1",
})
PARENT_RUN_TARGETS = BLOG_TARGETS | BLOG_MEDIA_TARGETS | {"kl-location-intent-r1-v2"} | set(NATIVE_TARGETS) | set(WAVE234_BODY_TARGETS)


class PermitEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PermitEvidenceError(message)


def load_protected_issuer_secret() -> str:
    """Read the issuer credential without putting it in arguments or logs.

    A protected operator may inject the environment variable. On the local Mac,
    the exact Supabase project's dedicated login-Keychain item is a fallback.
    Neither path creates, rotates, or prints a credential.
    """
    secret = os.environ.get("MANAGED_CMS_PERMIT_ISSUER_SECRET", "")
    if secret:
        require(len(secret) >= 32, "Protected issuer secret is too short")
        return secret
    require(sys.platform == "darwin", "Protected issuer secret is not configured")
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT,
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise PermitEvidenceError("Protected Keychain lookup timed out") from error
    require(result.returncode == 0, "Protected issuer secret is not configured in Keychain")
    secret = result.stdout.rstrip("\n")
    require(len(secret) >= 32, "Protected Keychain issuer secret is too short")
    return secret


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Evidence timestamp must have a timezone")
    return parsed.astimezone(timezone.utc)


def exact_file(root: Path, item: tuple[str, str]) -> Path:
    path, digest = item
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()) and resolved.is_file(), f"Evidence file missing: {path}")
    require(sha256_file(resolved) == digest, f"Evidence file changed: {path}")
    return resolved


def rollback_parent_binding(target_name: str, operation: str,
                            parent_permit_id: str | None, parent_run_id: int | None) -> dict:
    if operation != "rollback":
        require(not parent_permit_id and parent_run_id is None,
                "Publish cannot reuse a rollback parent")
        return {"parentPermitId": None}
    require(bool(parent_permit_id) and parent_run_id is not None and parent_run_id > 0,
            "Rollback requires the completed parent permit and run")
    binding = {"parentPermitId": parent_permit_id}
    if target_name in PARENT_RUN_TARGETS:
        binding["parentRunId"] = parent_run_id
    return binding


def validate_completed_parent_status(status: dict, target: dict,
                                     parent_permit_id: str, parent_run_id: int) -> None:
    """Fail closed against the protected permit status before bound rollback."""
    require(status.get("permitId") == parent_permit_id
            and status.get("status") == "completed"
            and status.get("operation") == "publish"
            and status.get("taskId") == target["task_id"]
            and status.get("actionId") == target["action_id"]
            and status.get("candidateVersion") == target["candidate_version"]
            and status.get("githubRunId") == parent_run_id
            and status.get("savedId") == target["record_id"]
            and bool(status.get("savedUpdatedAt")),
            "Rollback parent permit is not the completed exact publish run")


def validate_candidate_binding(candidate: dict, target: dict) -> None:
    """Bind newly added targets to one approved row and its exact field set."""
    shape = target.get("candidate_shape")
    if shape == 'native_publisher_registration':
        try:
            validate_publisher_registration_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_five_projection_registration":
        try:
            validate_five_source_projection_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_shop_children_body_registration":
        try:
            validate_shop_children_body_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_wave234_body_registration":
        try:
            validate_wave234_body_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_remaining186_blog_registration":
        try:
            validate_remaining186_blog_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_repair_faq_registration":
        try:
            validate_repair_faq_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_bilingual_body":
        try:
            validate_native_issuer_candidate(ROOT, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if not shape:
        return
    if shape == "org020_field_patch":
        source = json.loads(exact_file(ROOT, target["source_frozen_candidate"]).read_text())
        baseline = json.loads(exact_file(ROOT, target["rollback"]).read_text())
        fields = set(target["changed_fields"])
        projection = target["baseline_projection_fields"]
        require(source.get("task_id") == target["task_id"]
                and source.get("record_id") == target["record_id"] == baseline.get("id")
                and source.get("table") == target["table"]
                and source.get("scope") == target["scope"]
                and source.get("action_class") == "cms_content_candidate"
                and source.get("production_write_executed") is False
                and set(source.get("changed_fields", [])) == fields
                and set(source.get("desired_fields", {})) == fields
                and source.get("baseline_projection_fields") == projection
                and source.get("expected_updated_at") == baseline.get("updated_at") == target["expected_updated_at"]
                and source.get("baseline_fields_sha256") == target["baseline_fields_sha256"]
                and wc.sha256_value({key: baseline.get(key) for key in projection}) == target["baseline_fields_sha256"]
                and source.get("desired_fields_sha256") == target["desired_fields_sha256"]
                and wc.sha256_value(source.get("desired_fields")) == target["desired_fields_sha256"],
                "Pinned ORG-020 frozen source, row, fields, hashes or CAS differs")
        require(candidate.get("task_id") == target["task_id"]
                and candidate.get("action_id") == target["action_id"]
                and candidate.get("candidate_version") == target["candidate_version"]
                and candidate.get("record_id") == target["record_id"]
                and candidate.get("scope") == target["scope"]
                and candidate.get("action_class") == "cms_content_candidate"
                and candidate.get("production_write_executed") is False
                and set(candidate.get("changed_fields", [])) == fields
                and candidate.get("baseline_fields_sha256") == target["baseline_fields_sha256"]
                and candidate.get("desired_fields_sha256") == target["desired_fields_sha256"],
                "Pinned ORG-020 execution candidate identity or field digest differs")
        if target["table"] == "faqs":
            require(source.get("request") is None
                    and candidate.get("source_frozen_candidate_path") == target["source_frozen_candidate"][0]
                    and candidate.get("source_frozen_candidate_sha256") == target["source_frozen_candidate"][1]
                    and candidate.get("original_candidate_version") == source.get("candidate_version")
                    and candidate.get("original_action_id") == source.get("action_id")
                    and candidate.get("content_unchanged_from_frozen_v7") is True
                    and target["slug"] == f"faq-{target['record_id']}"
                    and fields == {"answer_en", "answer_zh"},
                    "FAQ execution adapter is not the frozen answer-only source")
        else:
            require(candidate.get("table") == target["table"]
                    and candidate.get("desired_fields") == source.get("desired_fields")
                    and candidate.get("action_id") == source.get("action_id")
                    and candidate.get("candidate_version") == source.get("candidate_version"),
                    "ORG-020 non-FAQ candidate differs from the frozen source")
        request = candidate.get("request") or {}
        record = request.get("record") or {}
        require(request.get("mode") == "dry-run"
                and request.get("contentType") == target["content_type"]
                and request.get("nextStatus") == baseline.get("status") == "published"
                and request.get("expectedUpdatedAt") == target["expected_updated_at"]
                and record.get("id") == target["record_id"]
                and record.get("updated_at") == target["expected_updated_at"]
                and record.get("status") == baseline.get("status")
                and set(record).issubset(set(baseline) | fields)
                and {key for key in record if record[key] != baseline.get(key)} == fields
                and all(record.get(key) == source["desired_fields"][key] for key in fields)
                and all(key in record for key in projection),
                "ORG-020 request differs from exact dry-run, unchanged baseline or field-only patch")
        if target["table"] == "faqs":
            managed = request.get("managedCandidate") or {}
            require(managed.get("taskId") == target["task_id"]
                    and managed.get("actionId") == target["action_id"]
                    and managed.get("candidateVersion") == target["candidate_version"]
                    and managed.get("scope") == target["scope"]
                    and managed.get("operation") == "publish",
                    "FAQ execution request managed tuple differs")
        elif target["table"] == "site_pages":
            require(record.get("page_key") == target["slug"],
                    "ORG-020 site page stable key differs")
        else:
            require(record.get("slug") == target["slug"],
                    "ORG-020 native slug differs")
        return
    if shape == "cms_media_row":
        fields = set(target["changed_fields"])
        require(candidate.get("task_id") == target["task_id"]
                and candidate.get("action_id") == target["action_id"]
                and candidate.get("candidate_version") == target["candidate_version"]
                and candidate.get("cms_row_id") == target["record_id"]
                and candidate.get("slug") == target["slug"]
                and candidate.get("scope") == target["scope"]
                and candidate.get("candidate_type") == "cms_content_candidate"
                and candidate.get("external_write_executed") is False
                and candidate.get("cms_saved_id") is None
                and candidate.get("body_and_links_unchanged") is True
                and set(candidate.get("allowed_fields", [])) == fields
                and set(candidate.get("field_diff", {})) == fields
                and set(candidate.get("desired_fields", {})) == fields
                and all(candidate["field_diff"][key].get("after") == candidate["desired_fields"][key]
                        for key in fields),
                "Pinned Blog media candidate identity, fields or unpublished status differs")
        return
    require(candidate.get("task_id") == target["task_id"]
            and candidate.get("action_id") == target["action_id"]
            and candidate.get("candidate_version") == target["candidate_version"]
            and candidate.get("published") is False,
            "Pinned candidate identity or unpublished status differs")
    expected_fields = set(target["changed_fields"])
    if shape == "record_key":
        key = candidate.get("record_key", {})
        require(key.get("id") == target["record_id"] and key.get("slug") == target["slug"]
                and candidate.get("scope") == target["scope"]
                and set(candidate.get("modified_fields", [])) == expected_fields
                and set(candidate.get("field_diff", {})) == expected_fields,
                "Pinned single-row candidate differs from exact target")
    elif shape == "items":
        require(set(candidate.get("modified_fields", [])) == expected_fields,
                "Pinned multi-row candidate has extra fields")
        items = candidate.get("items", [])
        matched = [item for item in items if item.get("cms_row_id") == target["record_id"]]
        require(len(matched) == 1 and matched[0].get("slug") == target["slug"]
                and matched[0].get("scope") == target["scope"]
                and set(matched[0].get("allowed_fields", [])) == expected_fields
                and set(matched[0].get("field_diff", {})) == expected_fields,
                "Pinned multi-row candidate differs from exact target")
    else:
        raise PermitEvidenceError("Unknown pinned candidate shape")


def structured_qa_outbox_matches(row: dict, target: dict) -> bool:
    """Require a per-target QA PASS inside a pinned V2.6 outbox."""
    if (target.get("candidate_shape") == "native_bilingual_body"
            and not native_release_qa_matches(row, target)):
        return False
    owner_review = (
        target.get("candidate_shape") == "cms_media_row"
        and row.get("gate_status") == "PASS_FOR_OWNER_REVIEW"
        and row.get("risk_level") == "R3"
        and row.get("approval_required") is True
    )
    if not (row.get("department") == "qa" and row.get("task_id") == target["task_id"]
            and row.get("status") == "completed"
            and (row.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
                 and row.get("risk_level") != "R3" or owner_review)
            and row.get("verdict", row.get("qa_verdict")) == "pass"
            and row.get("action_id") == target["action_id"]
            and row.get("candidate_version") == target["candidate_version"]
            and row.get("candidate_sha256") == target["candidate"][1]
            and not any(str(item.get("priority", "")).upper() in {"P0", "P1"}
                        for item in row.get("blockers", []) if isinstance(item, dict))):
        return False
    if target["candidate_shape"] in {"record_key", "cms_media_row", "org020_field_patch", "native_bilingual_body"}:
        return row.get("scope") == target["scope"]
    return any(
        item.get("slug") == target["slug"]
        and item.get("record_id") == target["record_id"]
        and item.get("scope") == target["scope"]
        and item.get("action_id") == target["action_id"]
        and item.get("candidate_version") == target["candidate_version"]
        and item.get("candidate_sha256") == target["candidate"][1]
        and item.get("action_class") == "cms_content_candidate"
        and item.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
        and item.get("qa_verdict") == "pass"
        for item in row.get("qa_subactions", []) if isinstance(item, dict)
    )


def validate_qa(root: Path, target: dict, operation: str, *, allow_blocked_retry: bool = False) -> dict:
    task_id = target["task_id"]
    expected_action = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    expected_version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    pinned_qa_path = exact_file(root, target["qa_outbox"]) if target.get("qa_outbox") else None
    if target.get("candidate_shape"):
        candidate = json.loads(exact_file(root, target["candidate"]).read_text())
        validate_candidate_binding(candidate, target)
    if target.get("qa_request"):
        evidence_root = target.get("evidence_root", root)
        candidate = json.loads(exact_file(evidence_root, target["candidate"]).read_text())
        rollback = json.loads(exact_file(evidence_root, target["rollback"]).read_text())
        request = json.loads(exact_file(evidence_root, target["qa_request"]).read_text())
        require(request.get("mode") == "dry-run" and request.get("contentType") == "service"
                and request.get("record") == candidate
                and request.get("expectedUpdatedAt") == rollback.get("updated_at")
                and candidate.get("id") == rollback.get("id") == target["record_id"]
                and candidate.get("slug") == rollback.get("slug") == target["slug"]
                and {key for key in candidate if candidate[key] != rollback.get(key)} == {"faqs_en", "faqs_zh"},
                "Pinned QA request, candidate, or rollback row differs from the two-field V4 scope")
    registry_path = root / "data/department-registry.json"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        fixed = [row for row in registry.get("departments", []) if row.get("id") == "qa"]
        binding = fixed[0].get("chat_binding", {}) if len(fixed) == 1 else {}
        require(binding.get("task_id") == QA_THREAD_ID
                and binding.get("status") == "bound_and_visible"
                and binding.get("dispatch_eligible") is True
                and binding.get("reply_health") == "healthy_visible_reply_verified",
                "Fixed QA registry identity changed; refresh the exact binding")
        verified_at = timestamp(str(binding.get("last_verified_at", "")))
        now = datetime.now(timezone.utc)
        require(now - timedelta(hours=26) <= verified_at <= now,
                "Fixed QA health proof is stale; refresh before issuing a permit")
    snapshot = json.loads((root / "data/workflows" / f"{task_id}.json").read_text())
    # A sibling action can close a shared task. Exact action QA, pinned evidence,
    # policy, CAS and one-use permit checks below still apply to every target.
    normal_states = {"qa_passed", "waiting_owner_approval", "owner_approved", "execution_completed", "verified", "closed"}
    blocked_retry = (allow_blocked_retry and snapshot.get("current_state") == "blocked"
                     and snapshot.get("blockers") == ["execution_result_blocked"]
                     and snapshot.get("resume_from") == "owner_approved")
    require(snapshot.get("current_state") in normal_states or blocked_retry,
            "Original workflow has no current QA PASS")
    receipts, invalid = wc._validate_receipt_chain(root, task_id)
    require(not invalid, f"Workflow receipt chain invalid: {invalid[:2]}")
    qa_rows = [row for row in receipts if row.get("receipt_type") == "qa_verdict" and row.get("department") == "qa"
               and row.get("chat_task_id") == QA_THREAD_ID
               and row.get("task_id") == task_id and row.get("scope") == target["scope"]
               and row.get("action_class") == "cms_content_candidate"
               and row.get("action_id") == expected_action]
    require(bool(qa_rows), "Fixed QA receipt is not an exact release PASS")
    qa = qa_rows[-1]
    require(qa.get("verdict") == "pass", "Latest fixed QA receipt is not an exact release PASS")
    outboxes = []
    for evidence in qa.get("evidence", []):
        path = str(evidence.get("path", ""))
        if path.startswith("logs/department-outbox/") and path.endswith(".json"):
            outboxes.append((path, json.loads((root / path).read_text())))
    if pinned_qa_path is not None:
        # Older QA workflows registered their exact outbox in an earlier
        # outbox_received receipt, while qa_verdict cited the shared report.
        # The receipt chain and pinned file digest must both match; never infer
        # a PASS merely from a loose file on disk.
        qa_index = next(index for index, row in enumerate(receipts)
                        if row.get("receipt_id") == qa.get("receipt_id"))
        for receipt in receipts[:qa_index]:
            if (receipt.get("receipt_type") != "outbox_received"
                    or receipt.get("department") != "qa"
                    or receipt.get("chat_task_id") != QA_THREAD_ID
                    or receipt.get("task_id") != task_id):
                continue
            for evidence in receipt.get("evidence", []):
                path = str(evidence.get("path", ""))
                if (path == target["qa_outbox"][0]
                        and evidence.get("sha256") == target["qa_outbox"][1]):
                    outboxes.append((path, json.loads(pinned_qa_path.read_text())))
    if target.get("candidate_shape") and operation == "publish":
        require(pinned_qa_path is not None and any(
            (root / path).resolve() == pinned_qa_path
            and structured_qa_outbox_matches(row, target)
            for path, row in outboxes),
            "Pinned structured QA PASS does not bind the exact candidate, row, fields, and scope")
        return qa
    require(any(row.get("department") == "qa" and row.get("task_id") == task_id
                and row.get("status") == "completed" and row.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
                and row.get("verdict", row.get("qa_verdict")) == "pass"
                and (row.get("scope") or row.get("release_boundary", {}).get("scope")) == target["scope"]
                and (not target.get("qa_candidate_only") and row.get("candidate_version") == expected_version
                     and row.get("release_boundary", {}).get("publish_authorized") is True
                     or target.get("qa_candidate_only") and row.get("action_id") == expected_action
                     and (row.get("candidate_version") == expected_version
                          or operation == "publish" and row.get("candidate_version") is None)
                     and ((pinned_qa_path is not None and (root / path).resolve() == pinned_qa_path)
                          or (row.get("candidate", {}).get("row_id") == target["record_id"]
                              and row.get("candidate", {}).get("slug") == target["slug"]
                              and (operation == "rollback" or
                                   (row.get("candidate", {}).get("candidate_row_sha256")
                                    or row.get("candidate", {}).get("candidate_row", {}).get("sha256")) == target["candidate"][1]))))
                and not any(str(item.get("priority", "")).upper() in {"P0", "P1"}
                            for item in row.get("blockers", []) if isinstance(item, dict))
                for path, row in outboxes), "QA PASS evidence does not bind the exact candidate and scope")
    return qa


def validate_operations(decision: dict, target: dict, operation: str, payload_sha256: str, qa_receipt_id: str, now: datetime) -> dict:
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    require(decision.get("department") == "operations" and decision.get("operations_chat_task_id") == OPERATIONS_THREAD_ID
            and decision.get("decision") == "AUTO_RELEASE"
            and decision.get("operation") == operation and decision.get("task_id") == target["task_id"]
            and decision.get("action_id") == action_id and decision.get("action_class") == "cms_write"
            and decision.get("scope") == target["scope"] and decision.get("candidate_version") == version
            and decision.get("record_id") == target["record_id"]
            and decision.get("payload_sha256") == payload_sha256
            and decision.get("qa_receipt_id") == qa_receipt_id
            and isinstance(decision.get("decision_id"), str) and decision["decision_id"],
            "Operations AUTO_RELEASE is missing or does not match the exact action")
    decided_at = timestamp(str(decision.get("decided_at", "")))
    require(now - timedelta(hours=24) <= decided_at <= now, "Operations decision is stale or future-dated")
    return decision


def validate_policy(row: dict, target: dict, operation: str, payload_sha256: str, operations: dict, now: datetime) -> dict:
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    require(row.get("status") == "allow" and row.get("department") == target.get("execution_owner", "content-organic-website")
            and row.get("task_id") == target["task_id"] and row.get("action_id") == action_id
            and row.get("action_class") == "cms_write" and row.get("scope") == target["scope"]
            and row.get("payload_sha256") == payload_sha256
            and row.get("approval_status") == "consumed"
            and isinstance(row.get("decision_id"), str) and row["decision_id"],
            "Policy decision is not exact, allowed, and consumed")
    checked_at = timestamp(str(row.get("checked_at", "")))
    require(timestamp(operations["decided_at"]) <= checked_at <= now
            and now - timedelta(minutes=30) <= checked_at, "Policy allow is stale or predates operations")
    return row


def validate_retry_state(root: Path, target: dict, operation: str, policy: dict) -> None:
    """Bind a blocked execution to its one permitted policy retry before issuing."""
    snapshot = json.loads((root / "data/workflows" / f"{target['task_id']}.json").read_text())
    if snapshot.get("current_state") != "blocked":
        require(policy.get("approval_basis") != "blocked_execution_retry",
                "Retry policy requires the original blocked workflow")
        return
    require(snapshot.get("blockers") == ["execution_result_blocked"]
            and snapshot.get("resume_from") == "owner_approved"
            and policy.get("approval_basis") == "blocked_execution_retry",
            "Blocked workflow requires an exact execution retry policy")
    receipts, invalid = wc._validate_receipt_chain(root, target["task_id"])
    require(not invalid, f"Workflow receipt chain invalid: {invalid[:2]}")
    executions = [row for row in receipts if row.get("receipt_type") == "execution_result"]
    require(bool(executions), "Blocked workflow has no execution receipt")
    latest = executions[-1]
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    expected = {"receipt_type": "execution_result", "verdict": "blocked",
                "department": target.get("execution_owner", "content-organic-website"), "task_id": target["task_id"],
                "action_id": action_id, "action_class": "cms_write", "scope": target["scope"],
                "approval_id": policy.get("approval_id")}
    require(all(latest.get(key) == value for key, value in expected.items())
            and policy.get("retry_source_receipt_id") == latest.get("receipt_id"),
            "Retry policy does not bind the latest exact blocked execution")


def gh_json(*args: str) -> dict:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def artifact_for_run(run_id: int, target_name: str, folder: Path) -> tuple[dict, dict, dict, Path]:
    run = gh_json("api", f"repos/{REPOSITORY}/actions/runs/{run_id}")
    require(run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
            and run.get("conclusion") == "success" and run.get("name") == "Approved website content publish"
            and run.get("path") == ".github/workflows/content-publish-approved.yml"
            and run.get("id") == run_id and len(str(run.get("head_sha", ""))) == 40,
            "Dry-run workflow identity or conclusion is invalid")
    subprocess.run(["gh", "run", "download", str(run_id), "-R", REPOSITORY,
                    "-n", f"approved-content-publish-{run_id}", "-D", str(folder)], check=True, capture_output=True)
    target_dir = folder / target_name
    receipt = json.loads((target_dir / "locked-dry-run-receipt.json").read_text())
    digest = json.loads((target_dir / "managed-payload-digest.json").read_text())
    probe = json.loads((target_dir / "managed-identity-probe.json").read_text())
    backup = json.loads((target_dir / "rollback-payload-digest.json").read_text()) if (target_dir / "rollback-payload-digest.json").is_file() else {}
    require(receipt.get("http_status") == 200 and receipt.get("dry_run") is True
            and receipt.get("performed_write") is False and receipt.get("external_writes") == 0
            and receipt.get("row_unchanged_after_dry_run") is True,
            "Protected dry-run did not prove zero writes and exact row readback")
    identity = probe.get("identity", {})
    require(probe.get("ok") is True and probe.get("dry_run") is True and probe.get("performed_write") is False
            and identity.get("runId") == run_id and identity.get("runAttempt") == run.get("run_attempt")
            and identity.get("repositoryId") == 1248188229
            and identity.get("workflowRef") == f"{REPOSITORY}/.github/workflows/content-publish-approved.yml@refs/heads/main"
            and identity.get("actorId") == run.get("actor", {}).get("id")
            and len(str(identity.get("workflowSha", ""))) == 40,
            "Server-verified OIDC identity probe does not match the dry-run run")
    return run, receipt, digest, target_dir / "backup.json"


def endpoint_request(control: dict, secret: str, base_url: str) -> dict:
    parsed = urlparse(base_url)
    require(parsed.scheme == "https" and parsed.netloc == SUPABASE_HOST and parsed.path in {"", "/"}, "Wrong Supabase project")
    request = Request(f"{base_url.rstrip('/')}/functions/v1/content-publish",
                      data=json.dumps(control, separators=(",", ":")).encode(), method="POST",
                      headers={"Content-Type": "application/json", "x-managed-permit-issuer-secret": secret})
    with urlopen(request, timeout=20) as response:
        body = json.load(response)
    require(body.get("ok") is True, "Permit issuer endpoint did not confirm success")
    return body


def validate_new_permit_target(target: dict) -> None:
    """Keep historical evidence readable without reissuing a colliding action."""
    if target.get('candidate_shape') == 'native_publisher_registration':
        raise PermitEvidenceError('Publisher registration cannot issue a permit; protected preview and exact production QA remain required')
    if target.get("candidate_shape") == "native_five_projection_registration":
        raise PermitEvidenceError("Five-source registration has no separately reviewed production capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_shop_children_body_registration":
        raise PermitEvidenceError("Shop/children registration has no separately deployed native capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_wave234_body_registration":
        raise PermitEvidenceError("Wave234 body registration has no separately reviewed production capability or protected preview; no new permit")
    if target.get("candidate_shape") == "native_remaining186_blog_registration":
        raise PermitEvidenceError("Remaining186 Blog registration has no deployed native capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_repair_faq_registration":
        raise PermitEvidenceError("Repair FAQ registration has no deployed native capability or exact protected preview; no new permit")
    require(not target.get("retired_for_new_permit", False),
            "Target action identity is retired; use its independently reviewed row-specific successor")
    if target.get("candidate_shape") == "native_bilingual_body":
        require(target.get("native_registration_only") is False
                and target.get("release_ready") is True,
                "Native registration has no actual release readiness; exact QA and protected preview required")
    if target.get("candidate_shape") in {"org020_field_patch", "native_bilingual_body"}:
        pin = target.get("qa_outbox")
        require(bool(pin) and len(pin) == 2 and len(str(pin[1])) == 64,
                "ORG-020 target has no pinned actual fixed QA outbox")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--operation", choices=["publish", "rollback"], required=True)
    parser.add_argument("--dry-run-run-id", type=int, required=True)
    parser.add_argument("--operations-decision", required=True)
    parser.add_argument("--policy-decision-id", required=True)
    parser.add_argument("--github-actor-id", type=int, required=True)
    parser.add_argument("--parent-permit-id")
    parser.add_argument("--parent-run-id", type=int)
    parser.add_argument("--issue-and-dispatch", action="store_true")
    args = parser.parse_args()
    target = TARGETS[args.target]
    if args.issue_and_dispatch:
        validate_new_permit_target(target)
    require(args.operation != "rollback" or target.get("rollback_allowed", True),
            "Rollback to the prior public media is not rights-safe")
    parent_binding = rollback_parent_binding(args.target, args.operation,
                                             args.parent_permit_id, args.parent_run_id)
    now = datetime.now(timezone.utc)
    evidence_root = target.get("evidence_root", ROOT)
    exact_file(evidence_root, target["candidate"])
    exact_file(evidence_root, target["rollback"])
    qa = validate_qa(ROOT, target, args.operation, allow_blocked_retry=True)
    require(args.github_actor_id > 0, "GitHub actor ID must be positive")

    artifact_root = ROOT / "logs/permit-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="managed-cms-", dir=artifact_root) as temporary:
        folder = Path(temporary)
        run, receipt, digest, backup_path = artifact_for_run(args.dry_run_run_id, args.target, folder)
        require(run.get("actor", {}).get("id") == args.github_actor_id, "Dry-run GitHub actor does not match the intended publisher")
        require(now - timedelta(minutes=30) <= timestamp(run["updated_at"]) <= now,
                "Protected dry-run is stale or future-dated")
        expected_action = target["action_id"] if args.operation == "publish" else f"rollback-{target['candidate_version']}"
        require(receipt.get("task_id") == target["task_id"] and receipt.get("candidate_version") == target["candidate_version"]
                and receipt.get("action_id") == expected_action and receipt.get("operation") == args.operation
                and receipt.get("scope") == target["scope"],
                "Dry-run receipt target differs from the locked candidate")
        require(digest.get("task_id") == target["task_id"] and digest.get("operation") == args.operation
                and len(str(digest.get("payload_sha256", ""))) == 64,
                "Payload digest evidence missing")
        payload_sha256 = digest["payload_sha256"]
        rollback_digest = json.loads((backup_path.parent / "rollback-payload-digest.json").read_text()) if args.operation == "publish" else None
        if args.operation == "publish":
            require(rollback_digest.get("task_id") == target["task_id"] and len(str(rollback_digest.get("payload_sha256", ""))) == 64,
                    "Prior version rollback digest missing")
            require(json.loads(backup_path.read_text()).get("record", {}).get("id") == target["record_id"],
                    "Parent backup does not contain the target record")
        else:
            require(json.loads(backup_path.read_text()).get("record", {}).get("id") == target["record_id"],
                    "Rollback readback does not contain the target record")

        decision_path = (ROOT / args.operations_decision).resolve()
        require(decision_path.is_relative_to(ROOT) and decision_path.is_file(), "Operations decision file is missing")
        operations = validate_operations(json.loads(decision_path.read_text()), target, args.operation,
                                         payload_sha256, qa["receipt_id"], now)
        policies = [json.loads(line) for line in (ROOT / "logs/policy-decisions.jsonl").read_text().splitlines() if line.strip()]
        matches = [row for row in policies if row.get("decision_id") == args.policy_decision_id]
        require(len(matches) == 1, "Exact policy decision ID is missing or ambiguous")
        policy = validate_policy(matches[0], target, args.operation, payload_sha256, operations, now)
        validate_retry_state(ROOT, target, args.operation, policy)
        require(timestamp(qa["created_at"]) <= timestamp(operations["decided_at"]),
                "Operations decision predates QA PASS")

        evidence = {"candidate": target["candidate"][1], "rollback": target["rollback"][1],
                    "qa_receipt_hash": qa["receipt_hash"], "operations_file_sha256": sha256_file(decision_path),
                    "policy_decision_id": policy["decision_id"], "dry_run_id": args.dry_run_run_id,
                    "dry_run_receipt_sha256": sha256_file(backup_path.parent / "locked-dry-run-receipt.json"),
                    "payload_sha256": payload_sha256}
        evidence_sha256 = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        action_id = target["action_id"] if args.operation == "publish" else f"rollback-{target['candidate_version']}"
        candidate_version = target["candidate_version"] if args.operation == "publish" else f"{target['candidate_version']}-rollback-v1"
        request = {"controlAction": "issue", "permitId": str(uuid4()), "taskId": target["task_id"],
                   "actionId": action_id, "actionClass": "cms_write", "operation": args.operation,
                   "scope": target["scope"], "candidateVersion": candidate_version,
                   "recordId": target["record_id"], "slug": target["slug"],
                   "expectedUpdatedAt": digest["expected_updated_at"], "payloadSha256": payload_sha256,
                   "rollbackPayloadSha256": rollback_digest["payload_sha256"] if rollback_digest else None,
                   **parent_binding,
                   "githubActorId": args.github_actor_id,
                   "githubWorkflowSha": json.loads((backup_path.parent / "managed-identity-probe.json").read_text())["identity"]["workflowSha"],
                   "qaReceiptId": qa["receipt_id"], "operationsDecisionId": operations["decision_id"],
                   "policyDecisionId": policy["decision_id"], "issuerEvidenceSha256": evidence_sha256,
                   "expiresAt": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}
        if not args.issue_and_dispatch:
            print(json.dumps({"status": "LOCAL_EVIDENCE_VALIDATED", "target": args.target,
                              "operation": args.operation, "dry_run_run_id": args.dry_run_run_id,
                              "evidence_sha256": evidence_sha256, "production_write": False}))
            return
        current_main = gh_json("api", f"repos/{REPOSITORY}/commits/main")
        require(current_main.get("sha") == run["head_sha"],
                "Main changed after the protected dry-run; obtain fresh QA and dry-run evidence")
        secret = load_protected_issuer_secret()
        base_url = os.environ.get("SUPABASE_URL", "")
        if args.operation == "rollback" and args.target in PARENT_RUN_TARGETS:
            parent_status = endpoint_request({"controlAction": "status", "permitId": args.parent_permit_id},
                                             secret, base_url)
            validate_completed_parent_status(parent_status, target, args.parent_permit_id, args.parent_run_id)
        issued = endpoint_request(request, secret, base_url)
        require(issued.get("status") == "issued" and issued.get("permitId") == request["permitId"],
                "Permit issue receipt mismatch; inspect status before retry")
        fields = ["-f", "mode=publish", "-f", f"target={args.target}",
                  "-f", f"managed_operation={args.operation}",
                  "-f", f"managed_permit_id={request['permitId']}"]
        if args.operation == "rollback":
            fields += ["-f", f"parent_run_id={args.parent_run_id}"]
        subprocess.run(["gh", "workflow", "run", "content-publish-approved.yml", "-R", REPOSITORY,
                        "--ref", "main", *fields], check=True, capture_output=True)
        print(json.dumps({"status": "DISPATCHED", "target": args.target, "operation": args.operation,
                          "permit_id_sha256": hashlib.sha256(request["permitId"].encode()).hexdigest(),
                          "evidence_sha256": evidence_sha256, "production_write": "pending-run-result"}))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit("BLOCKED_MANAGED_CMS_PERMIT: External GitHub command failed; inspect permit status before retry")
    except (PermitEvidenceError, OSError, ValueError, KeyError) as error:
        raise SystemExit(f"BLOCKED_MANAGED_CMS_PERMIT: {error}")
