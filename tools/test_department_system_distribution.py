from pathlib import Path
import importlib.util
import json
import hashlib
import tempfile
import unittest

import setup_department_system as setup
import export_department_system as exporter


class DistributionTests(unittest.TestCase):
    def preparation_example(self):
        return ('from pathlib import Path\nfrom typing import Any\n'
                'AUTH_TURN_ID = "private-turn-fixture"\n'
                'AUTH_MESSAGE_ID = "private-message-fixture"\n'
                'AUTH_TEXT = "private-owner-fixture"\n'
                'AUTH_TEXT_SHA256 = "private-digest-fixture"\n'
                'def _require(condition, reason):\n'
                '    if not condition: raise ValueError(reason)\n'
                'def _frozen_request(root: Path, policy: dict[str, Any]) -> dict[str, Any]:\n'
                '    return policy\n')

    def test_owner_evidence_is_synthetic_and_example_cannot_authorize(self):
        result = exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", self.preparation_example())
        self.assertNotIn("private-", result)
        namespace = {}
        exec(result, namespace)
        self.assertEqual(namespace["AUTH_TEXT_SHA256"], hashlib.sha256(namespace["AUTH_TEXT"].encode()).hexdigest())
        with self.assertRaisesRegex(ValueError, "public_template_has_no_native_authorization"):
            namespace["_frozen_request"](Path("."), {"routing_policy": {"status": "approved_single_use"}})
        self.assertEqual(exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", result), result)

    def test_unknown_owner_evidence_or_changed_entrypoint_blocks_export(self):
        for source in (self.preparation_example() + 'AUTH_NEW_FIELD = "private-new-fixture"\n',
                       self.preparation_example().replace("def _frozen_request", "def renamed_request")):
            with self.assertRaises(ValueError):
                exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", source)

    def test_owner_transform_does_not_change_live_or_unrelated_module(self):
        source = self.preparation_example()
        self.assertEqual(exporter.public_source_text("tools/unrelated.py", source), source)
        exporter.public_source_text("tools/owner_delegated_publishing_preparation.py", source)
        self.assertIn("private-owner-fixture", source)

    def test_followthrough_examples_remove_real_record_ids_and_source_pins(self):
        source = 'TARGET_IDS = ["private-record-fixture"]\nSOURCE_PINS = {"v17": ("private-pin-fixture", "private-other-pin")}\n'
        result = exporter.public_source_text("tools/owner_delegated_publisher_followthrough.py", source)
        self.assertNotIn("private-", result)
        namespace = {}
        exec(result, namespace)
        self.assertEqual(len(namespace["TARGET_IDS"]), 3)
        self.assertEqual(set(namespace["SOURCE_PINS"]), {"v17", "v18", "v20"})

    def fixture(self, root):
        examples = root / "examples"
        examples.mkdir()
        for name in ("department-registry", "department-routing-rules", "task-contract", "action-policy", "delegation-policy"):
            value = {"departments": [{"id": "operations-assistant", "professional_skill": "departments/operations-assistant/SKILL.md", "chat_binding": {"status": "unbound", "dispatch_eligible": False}}]} if name == "department-registry" else {}
            (examples / (name + ".example.json")).write_text(json.dumps(value))
        for name in ("company-context", "service-area", "services-and-pricing", "customer-personas", "brand-guidelines", "case-studies", "faq"):
            (examples / (name + ".md")).write_text("待确认")

    def test_setup_does_not_activate_chats_or_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = setup.setup(root)
            self.assertEqual(result["external_permissions_issued"], 0)
            self.assertEqual(result["chats_created"], 0)
            binding = json.loads((root / "data/department-registry.json").read_text())["departments"][0]["chat_binding"]
            self.assertFalse(binding["dispatch_eligible"])

    def test_repeat_setup_preserves_local_bindings_and_company_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            setup.setup(root)
            path = root / "data/department-registry.json"
            path.write_text('{"departments": [], "local_history": "keep"}')
            company = root / "company-context.md"
            company.write_text("本机已确认资料")
            result = setup.setup(root)
            self.assertEqual(result["created"], [])
            self.assertIn("local_history", path.read_text())
            self.assertEqual(company.read_text(), "本机已确认资料")

    def test_missing_examples_fail_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def test_incomplete_examples_fail_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / "examples/faq.md").unlink()
            with self.assertRaises(FileNotFoundError):
                setup.setup(root)
            self.assertFalse((root / "data").exists())

    def test_new_registered_role_is_exported_sanitized_and_initialized(self):
        import copy,shutil
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'new-role-project'
            shutil.copytree(source,root,ignore=shutil.ignore_patterns('history','releases','__pycache__'))
            # Fixture copies stay writable even when the candidate is sealed read-only.
            for path in root.rglob('*'):
                path.chmod(0o700 if path.is_dir() else 0o600)
            root.chmod(0o700)
            registry=json.loads((root/'data/department-registry.json').read_text())
            role=copy.deepcopy(registry['departments'][-1]);role.update(id='new-specialist',name='新专业部门',
                professional_skill='departments/new-specialist/SKILL.md',role_config='.codex/agents/new-specialist.toml',
                department_readme='departments/new-specialist/README.md')
            role['chat_binding'].update(task_id='private-native-new-role',project_id='private-new-project',cwd=str(root))
            registry['departments'].append(role);(root/'data/department-registry.json').write_text(json.dumps(registry))
            folder=root/'departments/new-specialist';folder.mkdir()
            (folder/'SKILL.md').write_text('新专业职责；固定绑定private-native-new-role仅在本机。')
            (folder/'README.md').write_text('依注册表初始化与回报。')
            (root/role['role_config']).write_text('name = "新专业部门"\n')
            result=exporter.prepare(root,root/'releases/new-role')
            self.assertEqual(result['roles'],len(registry['departments']))
            release=root/'releases/new-role'
            public=json.loads((release/'examples/department-registry.example.json').read_text())
            self.assertIn('new-specialist',[r['id'] for r in public['departments']])
            self.assertNotIn('private-native-new-role',(release/'departments/new-specialist/SKILL.md').read_text())
            setup.setup(release)
            learning=json.loads((release/'data/learning/department-learning-registry.json').read_text())
            self.assertIn('new-specialist',[r['id'] for r in learning['departments']])
            self.assertEqual(setup.setup(release)['chats_created'],0)
            second=release/'releases/new-role-again'
            repeated=exporter.prepare(release,second)
            self.assertEqual(repeated['roles'],len(registry['departments']))
            second_manifest=json.loads((second/'release-manifest.json').read_text())
            self.assertEqual(second_manifest['privacy_gate']['status'],'PASS')
            self.assertEqual(second_manifest['version'],'2026.10.09.16')
            self.assertNotIn('private-native-new-role',(second/'departments/new-specialist/SKILL.md').read_text())

    def handover_fixture(self, root):
        import original_task_publisher_handover as handover
        (root/'data').mkdir()
        (root/'data/action-policy.json').write_text('{"schema_version":1}')
        return handover

    def test_public_handover_ordinary_interfaces_keep_original_neutral_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handover=self.handover_fixture(root)
            snapshot={'task_id':'ordinary-synthetic-task'};receipts=[]
            self.assertIsNone(handover.binding(root,snapshot['task_id'],receipts))
            self.assertEqual(handover.dispatch_precheck(root,snapshot,'qa','synthetic-qa','a','s'),[])
            self.assertFalse(handover.validate_new_receipt(root,snapshot,receipts,{}))
            unchanged=handover.legacy_context(root,snapshot,receipts)
            self.assertIs(unchanged[0],snapshot);self.assertIs(unchanged[1],receipts)
            self.assertIsNone(handover.replay(root,snapshot))
            self.assertIsNone(handover.progress(root,snapshot['task_id'],'a','s'))
            self.assertFalse(handover.recoverable_dispatch(root,snapshot,receipts,{}))
            self.assertIsNone(handover.retry_projection(root,snapshot['task_id'],'a','s','r','p'))
            self.assertIsNone(handover.shadow_projection(root,snapshot['task_id']))

    def test_public_handover_actual_ordinary_workflow_consumers_work(self):
        from test_workflow_control import WorkflowControlTests
        import workflow_control as workflow
        fixture=WorkflowControlTests()
        fixture.setUp()
        try:
            self.assertEqual(workflow.validate_workflow_events(fixture.root,fixture.task_id),[])
            decision=fixture.routing_decision('content-organic-website')
            self.assertEqual(decision['status'],'allow')
            fixture.receipt('dispatch_sent','content-organic-website','synthetic-dispatch')
            receipts,invalid=workflow._validate_receipt_chain(fixture.root,fixture.task_id)
            self.assertFalse(invalid)
            snapshot=workflow.read_json(workflow.snapshot_path(fixture.root,fixture.task_id))
            state=workflow._derive_state(fixture.root,snapshot,receipts)
            self.assertIn('state',state)
            projected,_=workflow.shadow_replay(fixture.root,fixture.task_id)
            self.assertEqual(projected['task_id'],fixture.task_id)
        finally:
            fixture.tearDown()

    def test_public_handover_policy_event_special_task_and_execution_stay_denied(self):
        import workflow_control as workflow
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handover=self.handover_fixture(root)
            calls=(lambda:handover.binding(root,'ordinary-synthetic-task'),
                   lambda:handover.dispatch_precheck(root,{'task_id':'ordinary-synthetic-task'},'qa','synthetic','a','s'),
                   lambda:handover.validate_new_receipt(root,{'task_id':'ordinary-synthetic-task'},[],{}))
            policy=root/'data/action-policy.json'
            policy.write_text(json.dumps({handover.POLICY_KEY:{'status':'reviewed_exact_execution_only_handover'}}))
            for call in calls:
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):call()
            policy.write_text('{"schema_version":1}')
            events=root/workflow.WORKFLOW_EVENTS;events.parent.mkdir(parents=True,exist_ok=True)
            events.write_text(json.dumps({'task_id':'ordinary-synthetic-task','details':{'publisher_execution_handover':True}})+'\n')
            for call in calls:
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):call()
            events.write_text('')
            with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                handover.binding(root,handover.TASK)
            self.assertTrue(handover.TASK.startswith('synthetic-deny-only-'))
            synthetic_private_task='synthetic-private-task-for-deny-digest'
            with patch.object(handover,'_TASK_DENY_SHA256',hashlib.sha256(synthetic_private_task.encode()).hexdigest()):
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                    handover.binding(root,synthetic_private_task)
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                    handover.dispatch_precheck(root,{'task_id':synthetic_private_task},'qa','synthetic','a','s')
                events.write_text(json.dumps({'task_id':synthetic_private_task,'details':{}})+'\n')
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                    handover.binding(root,'ordinary-synthetic-task')
            events.write_text('')
            for name in ('validate_request','validate_event','control_qa','apply','main'):
                with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                    getattr(handover,name)(root,{})

    def test_private_template_unknown_attributes_follow_import_protocol(self):
        import types
        import workflow_control as workflow
        import original_task_publisher_handover as handover
        self.assertFalse(hasattr(handover,'__path__'))
        with self.assertRaises(AttributeError):getattr(handover,'unknown_attribute')
        source='def private_execution():\n    return True\n'
        namespace={}
        exec(exporter.public_source_text('tools/native_example.py',source),namespace)
        module=types.ModuleType('synthetic_private_template');module.__dict__.update(namespace)
        self.assertFalse(hasattr(module,'__path__'))
        with self.assertRaises(AttributeError):getattr(module,'unknown_attribute')
        with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
            module.private_execution()
        facade=exporter.public_source_text('tools/original_task_publisher_handover.py',source)
        self.assertEqual(exporter.public_source_text('tools/original_task_publisher_handover.py',facade),facade)
        actual=Path(handover.__file__).read_text()
        self.assertEqual(exporter.public_source_text('tools/original_task_publisher_handover.py',actual),actual)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.handover_fixture(root);generated={};exec(facade,generated)
            self.assertIsNone(generated['binding'](root,'ordinary-synthetic-task'))
            with self.assertRaisesRegex(workflow.WorkflowError,'public_template_has_no_native_authorization'):
                generated['private_execution']()

    def test_only_complete_guarded_generated_AUTH_profile_is_public(self):
        source=exporter.public_source_text('tools/owner_delegated_publishing_preparation.py',self.preparation_example())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tools').mkdir();public=root/'public';public.mkdir()
            path=root/'tools/owner_delegated_publishing_preparation.py'
            path.write_text(source);(public/path.name).write_text(source)
            self.assertEqual(exporter.private_literals(root),set())
            self.assertEqual(exporter.validate_public_tree(root,public)['status'],'PASS')
            self.assertEqual(exporter.public_source_text('tools/owner_delegated_publishing_preparation.py',source),source)

    def test_AUTH_mutation_missing_guard_and_real_secret_shape_are_not_exempt(self):
        source=exporter.public_source_text('tools/owner_delegated_publishing_preparation.py',self.preparation_example())
        mutations={
            'turn':source.replace('example-turn-not-native','changed-turn-fixture'),
            'text':source.replace('Synthetic example only; not a native authorization.','Changed private owner fixture.'),
            'digest':source.replace(exporter.synthetic_auth_values()['AUTH_TEXT_SHA256'],'0'*64),
            'flag':source.replace('PUBLIC_TEMPLATE_ONLY = True','PUBLIC_TEMPLATE_ONLY = False'),
            'guard':source.replace('    _require(not PUBLIC_TEMPLATE_ONLY, "public_template_has_no_native_authorization")\n',''),
            'guard_helper':source.replace('if not condition: raise ValueError(reason)','return None'),
            'extra':source+'AUTH_EXTRA = "private-extra-fixture"\n',
            'reassignment':source+'PUBLIC_TEMPLATE_ONLY = True\n',
            'secret_shape':source.replace('example-turn-not-native','ghp_'+'z'*36),
        }
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tools').mkdir();public=root/'public';public.mkdir()
            path=root/'tools/owner_delegated_publishing_preparation.py'
            for name,changed in mutations.items():
                with self.subTest(mutation=name):
                    path.write_text(changed);(public/path.name).write_text(changed)
                    self.assertTrue(exporter.private_literals(root))
                    with self.assertRaisesRegex(ValueError,'Public privacy gate denied'):
                        exporter.validate_public_tree(root,public)

    def release_root(self):
        import os
        explicit = os.environ.get("FLASHCAST_TEST_RELEASE")
        if explicit:
            result = Path(explicit)
            if not result.is_absolute() or not (result / "release-manifest.json").is_file():
                raise ValueError("Actual assembled local source release required")
            return result
        project = Path(__file__).resolve().parents[1]
        return project if (project / "release-manifest.json").is_file() else project / "releases/zhaungxiubumen"

    def test_export_refuses_outside_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            with self.assertRaises(ValueError):
                exporter.prepare(root, Path(directory) / "other-project")

    def test_export_contains_no_runtime_account_or_history_files(self):
        # Test the actual release assembled for this project, if present.
        release = self.release_root()
        manifest = release / "release-manifest.json"
        if not manifest.exists():
            self.skipTest("source release not assembled in this workspace")
        data = json.loads(manifest.read_text())
        self.assertFalse(data["live_bindings_exported"])
        self.assertFalse(data["external_permissions_exported"])
        for row in data["files"]:
            self.assertNotIn(Path(row["path"]).parts[0], {"data", "logs", "reports", "accounts", "backups", "history"})
            self.assertNotIn("learning", Path(row["path"]).parts)
            self.assertNotIn(str(Path.home()), (release / row["path"]).read_text())

    def test_release_source_hashes_match_actual_bundle(self):
        release = self.release_root()
        if not (release / "release-manifest.json").is_file():
            self.skipTest("source release not assembled in this workspace")
        manifest = json.loads((release / "release-manifest.json").read_text())
        for row in manifest["files"]:
            self.assertEqual(hashlib.sha256((release / row["path"]).read_bytes()).hexdigest(), row["release_sha256"], row["path"])

    def test_public_templates_have_no_live_binding_or_grant(self):
        release = self.release_root()
        if not (release / "release-manifest.json").is_file():
            self.skipTest("source release not assembled in this workspace")
        registry = json.loads((release / "examples/department-registry.example.json").read_text())
        for role in registry["departments"]:
            self.assertTrue((release / role["role_config"]).is_file(), role["id"])
            self.assertTrue((release / role["professional_skill"]).is_file(), role["id"])
            binding = role["chat_binding"]
            self.assertEqual(binding["status"], "unbound")
            self.assertFalse(binding["dispatch_eligible"])
            for name in ("task_id", "project_id", "cwd", "title", "sidebar_section_id"):
                self.assertEqual(binding[name], "")
        policy = json.loads((release / "examples/action-policy.example.json").read_text())
        self.assertEqual(policy["standing_authorizations"], [])
        self.assertNotIn("owner_delegated_publishing_preparation", policy["routing_policy"])
        self.assertNotIn("owner_delegated_publisher_followthrough", policy["routing_policy"])
        self.assertFalse(policy["autonomous_site_release_policy"]["enabled"])
        for rule in policy["action_classes"].values():
            if isinstance(rule, dict) and "exact_requests" in rule:
                self.assertEqual(rule["exact_requests"], [])
        helper = release / "tools/owner_delegated_publishing_preparation.py"
        if helper.is_file():
            spec = importlib.util.spec_from_file_location("public_owner_preparation", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(module.PUBLIC_TEMPLATE_ONLY)
            self.assertEqual(module.AUTH_TURN_ID, "example-turn-not-native")
            self.assertEqual(module.AUTH_MESSAGE_ID, "example-message-not-native")
            with self.assertRaisesRegex(ValueError, "public_template_has_no_native_authorization"):
                module._frozen_request(release, {})


if __name__ == "__main__":
    unittest.main()
