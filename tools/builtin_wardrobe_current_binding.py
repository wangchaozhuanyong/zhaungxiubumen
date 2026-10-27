"""Original W registration-only successor. This module never issues a permit."""
import json
from pathlib import Path

import workflow_control as w

SCHEMA = "builtin-wardrobe-current-publisher-binding/v1"
PREFLIGHT = "builtin-wardrobe-current-publisher-preflight/v1"
EVENT = "builtin_wardrobe_current_publisher_binding"
TASK = "fc-20261014-builtin-wardrobe-layout-cms-publication-v1"
REPAIR = "fc-20261024-original-flow-recovery-execution-stage-v1"


def require(value, message):
    if not value:
        raise w.WorkflowError(message)


def document(root, pin):
    require(isinstance(pin, dict) and w.file_digest(root, pin.get("path", "")) == pin,
            "Exact original W source bytes required")
    value = json.loads(w.safe_path(root, pin["path"]).read_text())
    require(isinstance(value, dict), "Original W source must be an object")
    return value


def context(root, source):
    """Authenticate the original owner work order and already received PUB result."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    import managed_cms_permit_issuer as issuer
    from paid_three_page_bounded_cms import _current_original_publisher_metadata

    root = Path(root).resolve()
    require(root == issuer.ROOT.resolve() and source.get("schema") == SCHEMA
            and set(source) == {"schema", "task_id", "source_action_id", "request", "candidate"}
            and source.get("task_id") == TASK and a.current_mode(root),
            "Exact original W registration-only source required")
    old = issuer.BUILTIN_WARDROBE_TARGET
    original = json.loads(issuer.exact_file(root, old["candidate"]).read_text())
    # Reuse every original human/contract/native/payload guard. Do not rewrite it.
    issuer.validate_builtin_wardrobe_one_field_candidate(root, original, old)
    request = document(root, source["request"])
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    frozen = json.loads(issuer.exact_file(root, issuer.BUILTIN_WARDROBE_GOAL).read_text())
    goal = snapshot["goal_delivery"]
    require(snapshot.get("goal_contract") == w.file_digest(root, issuer.BUILTIN_WARDROBE_GOAL[0])
            and all(goal.get(k) == frozen.get(k) for k in (
                "primary_owner", "producer_departments", "authorized_scope", "required_execution_actions", "human_authorization"))
            and not w.validate_workflow_events(root, TASK) and not w._validate_receipt_chain(root, TASK)[1],
            "Unchanged active original W owner, contract and intact committed history required")
    require(request.get("schema") == "paid-original-W-current-binding-integration-request/v1"
            and request.get("task_id") == TASK and request.get("scope") == old["scope"]
            and request.get("owner") == "paid-growth-data" and request.get("target_department") == "system-development"
            and request.get("goal_contract") == snapshot["goal_contract"]
            and request.get("original_human_authorization") == w.file_digest(root, frozen["human_authorization"]["evidence_path"])
            and request.get("original_target_name") == issuer.BUILTIN_WARDROBE_NAME
            and request.get("original_CMS_action_id") == old["action_id"]
            and request.get("original_candidate_version") == old["candidate_version"]
            and request.get("changed_fields") == old["changed_fields"]
            and request.get("record_type") == old["table"] and request.get("record_id") == old["record_id"]
            and request.get("slug") == old["slug"] and request.get("current_binding_not_execution_CAS") is True
            and request.get("no_new_fee_account_permissions_or_Save") is True,
            "Original owner registration request cannot change tuple, payload, authority or execution scope")
    states = g._collaboration_wait_states(root, snapshot, only_action_id=source["source_action_id"])
    require(len(states) == 1 and states[0].get("received") is True
            and states[0].get("proof_state") in {"RECEIVED", "PROVEN"},
            "Actual original owner-to-SYS work order receipt required")
    order = states[0]["approved_action"]
    body = w.safe_path(root, order["payload"]["path"]).read_text()
    require(w.file_digest(root, order["payload"]["path"]) == order["payload"]
            and all(order.get(k) == v for k, v in {
                "task_id": TASK, "scope": old["scope"], "action_class": "thread_message",
                "sender_department": "paid-growth-data", "target_department": "system-development"}.items())
            and source["request"]["path"] in body and source["request"]["sha256"] in body,
            "Real owner message must bind this exact request, not a caller label")
    report = document(root, request["PUB_actual_completed_result"])
    received = g._collaboration_wait_states(root, snapshot, only_action_id=report.get("received_action_id"))
    require(len(received) == 1 and received[0].get("proof_state") == "PROVEN"
            and received[0].get("status") == "result_received"
            and received[0].get("result") == request["PUB_actual_completed_result"]
            and received[0]["approved_action"].get("sender_department") == "paid-growth-data"
            and received[0]["approved_action"].get("target_department") == "publishing"
            and received[0]["approved_action"].get("scope") == old["scope"],
            "Original Paid owner must actually receive this one complete PUB result")
    current = _current_original_publisher_metadata(root, old["execution_thread_id"])
    fixed = w.department_registry(root)["publishing"]["chat_binding"]
    required = request["current_binding_required"]
    require(required.get("actual_PUB_fixed_thread") == fixed["task_id"] == current["execution_thread_id"]
            == received[0]["threadId"] and required.get("actual_PUB_fixed_title") == fixed["title"]
            and required.get("actual_PUB_project") == fixed["project_id"]
            and required.get("actual_PUB_cwd") == fixed["cwd"] and Path(fixed["cwd"]).resolve() == root,
            "Verified current same-role original PUB binding required")
    require(report.get("schema") == "PUB-original-W-single-paragraph-current-effect-and-exact-remainder/v1"
            and report.get("task_id") == TASK and report.get("scope") == old["scope"]
            and report.get("department") == "publishing" and report.get("original_business_owner") == "paid-growth-data"
            and all(report.get(k) == 0 for k in ("actual_original_W_permit_or_Saved_records", "active_or_unknown_permits_same_record",
                "actual_new_Save", "actual_new_preview", "actual_new_policy", "actual_new_permit"))
            and report.get("public_original_paragraph_present") is False
            and report.get("current_authenticated_and_public_body_match") is True
            and report.get("workflow_CLI_and_Edge_W_target_present") is True,
            "Actual zero-W-effect/current target evidence required; unknown effects cannot be renewed")
    original_patch = document(root, request["original_candidate"])
    binding = json.loads(issuer.exact_file(root, issuer.BUILTIN_WARDROBE_BINDING).read_text())
    require(request["original_candidate"] == report["original_candidate"]
            == binding["source"]["write-only-content-zh.json"]
            and original_patch == {"content_zh": original["content_zh"]}
            and w.sha256_value(original_patch) == old["payload_sha256"], "Original one-paragraph write-only bytes must remain exact")
    before = document(root, request["current_full41_source"])
    native = document(root, report["full_authenticated_row"])
    require(request["current_full41_source"] == report["complete_before_backup"]
            and native.get("rows") == [{"record": before}], "Exact authenticated current full row and physical backup required")
    stable = sorted(set(before) - {"content_zh", "updated_at", "version"})
    ms = sorted(k for k in before if k.endswith("_ms"))
    require(len(before) == 41 and len(stable) == 38 and len(ms) == 11
            and sorted(required.get("stable_non_target_fields", [])) == stable
            and sorted(required.get("MS_fields", [])) == ms
            and required.get("stable_count") == 38 and required.get("MS_count") == 11
            and required.get("authenticated_fields_count") == 41
            and sorted(required.get("server_only", [])) == ["updated_at", "version"]
            and required.get("server_fields_not_sent") is True
            and before.get("id") == old["record_id"] and before.get("slug") == old["slug"]
            and before.get("status") == "published"
            and before.get("updated_at") == required.get("source_observed_rawCAS") == report.get("current_rawCAS")
            and before.get("version") == required.get("source_version") == report.get("server_version")
            and type(before.get("version")) is int and w._parse_observed_at(before["updated_at"]),
            "Current full41, all38 protected fields, MS11 and raw server CAS must agree")
    paragraph = request.get("only_original_missing_paragraph")
    desired = original_patch["content_zh"]
    old_before = json.loads(issuer.exact_file(root, old["rollback"]).read_text())
    require(isinstance(paragraph, str) and paragraph and paragraph not in before["content_zh"]
            and desired.count(paragraph) == 1 and paragraph not in old_before["content_zh"]
            and any(desired.replace(x, "", 1) == before["content_zh"] for x in (
                paragraph, paragraph + "\n", paragraph + "\n\n", "\n" + paragraph, "\n\n" + paragraph)),
            "Only the originally authorized missing paragraph may differ; preserve current local3/body")
    after = document(root, source["candidate"])
    require(after == {**before, **original_patch}, "Current candidate must preserve all40 nonwrite fields byte-for-byte")
    for pin in request["proofs"].values():
        require(w.file_digest(root, pin["path"]) == pin, "Original current target/selfcheck/effect proof changed")
    require(request["proofs"]["current_workflow"] == report["workflow"]
            and request["proofs"]["current_CLI"] == report["CLI"]
            and request["proofs"]["current_Edge_W"] == report["actual_Edge_W_source"]
            and request["proofs"]["PUB_selfcheck"] == report["self_check"]
            and request["proofs"]["safe_original_effect_lookup"] == report["all_policy_and_original_key_effect_lookup"],
            "One real current PUB source bundle required")
    effects = document(root, report["all_policy_and_original_key_effect_lookup"])
    require(isinstance(effects.get("rows"), list) and len(effects["rows"]) == report["other_task_completed_permits_same_record"]
            and all(x.get("record_id") == old["record_id"] and x.get("slug") == old["slug"]
                    and x.get("task_id") != TASK and x.get("status") == "completed" for x in effects["rows"]),
            "Original-key absence and no active/unknown same-row permit evidence required")
    observed, result_at, requested = [w._parse_observed_at(v) for v in
                                    (native.get("observed_at"), report.get("actual_at"), request.get("actual_created_at"))]
    require(observed and result_at and requested and observed <= result_at <= requested,
            "Real current source/result/owner instruction chronology required")
    target = {**old, **current, "expected_updated_at": before["updated_at"], "observed_version": before["version"],
              "candidate": (source["candidate"]["path"], source["candidate"]["sha256"]),
              "rollback": (request["current_full41_source"]["path"], request["current_full41_source"]["sha256"]),
              "baseline_projection_fields": sorted(before), "baseline_fields_sha256": w.sha256_value(before),
              "desired_fields_sha256": old["payload_sha256"],
              "rollback_fields_sha256": w.sha256_value({"content_zh": before["content_zh"]}),
              "retained_projection_fields": stable, "retained_fields_sha256": w.sha256_value({k: before[k] for k in stable}),
              "requires_parent_run": True, "source_binding_fingerprint": w.sha256_value(source)}
    return target


def registered(root):
    """No current catalog replacement without an authenticated append-only event."""
    rows = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if EVENT in e.get("details", {})]
    if not rows:
        return None
    require(len(rows) == 1 and rows[0].get("task_id") == REPAIR and not w.validate_workflow_events(root, REPAIR),
            "One intact original SYS current-W registration event required")
    # A completed original task retains its immutable source/event, but has no
    # active catalog successor and must never validate a new execution from it.
    if w.read_json(w.snapshot_path(root, TASK)).get("current_state") in w.TERMINAL_STATES:
        return None
    pin = rows[0]["details"][EVENT]
    value = context(root, document(root, pin))
    return {**value, "current_binding_source": pin, "current_binding_event_id": rows[0]["event_id"]}


def record(root, task_id, path):
    import department_autonomy as a
    import goal_delivery_runtime as g
    require(task_id == TASK, "Original W registration task required")
    with w.workflow_lock(root):
        pin = w.file_digest(root, path)
        target = context(root, document(root, pin))
        original = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
        require(original.get("current_state") not in w.TERMINAL_STATES,
                "Active original W registration required; history cannot issue a new source")
        repair = g.restore_goal(root, w.read_json(w.snapshot_path(root, REPAIR)))
        require(a.participant(root, repair, "system-development")["primary_owner"] == "system-development",
                "Original SYS repair responsibility required")
        a.original_assignment_ready(root, repair, "system-development")
        old = registered(root)
        if old:
            require(old["current_binding_source"] == pin, "Preserve existing current-W source; explicit successor required")
            return {"result": "duplicate_ignored", "source": pin, "event_id": old["current_binding_event_id"], "external_permission_issued": False}
        event = w.append_workflow_event(root, REPAIR, repair["current_state"],
                                        {EVENT: pin, "external_permission_issued": False})
    return {"result": "recorded", "source": pin, "event_id": event["event_id"], "target": target,
            "external_permission_issued": False, "production_READY": False, "CMS_Save": 0}


def validate_candidate(root, candidate, target):
    current = registered(root)
    require(current is not None and target == current
            and candidate == document(root, document(root, current["current_binding_source"])["candidate"]),
            "Exact registered current-W target/candidate required")


def validate_preflight(root, item, target):
    """A new PUB selfcheck does not overwrite or consume its historical preflight."""
    require(item.get("schema") == PREFLIGHT and item.get("current_binding_source") == target["current_binding_source"]
            and all(item.get(k) == v for k, v in {"task_id": TASK, "action_id": target["action_id"],
                "action_class": "cms_write", "scope": target["scope"], "department": "publishing",
                "candidate_version": target["candidate_version"], "payload_sha256": target["payload_sha256"]}.items())
            and item.get("risk_level") in {"R1", "R2"}, "Exact current-W PUB selfcheck/source tuple required")
    facts, check, backup, rollback = [document(root, item.get(k)) for k in ("facts", "self_check", "backup", "rollback")]
    request = document(root, document(root, target["current_binding_source"])["request"])
    before = document(root, request["current_full41_source"])
    observed = w._parse_observed_at(facts.get("observed_at"))
    require(backup == before and check.get("status") == "PASS"
            and all(check.get(k) == item[k] for k in ("action_id", "action_class", "scope", "department"))
            and check.get("candidate") == w.file_digest(root, target["candidate"][0])
            and check.get("payload_sha256") == target["payload_sha256"]
            and check.get("expected_updated_at") == before["updated_at"]
            and check.get("record_id") == target["record_id"] and check.get("changed_fields") == ["content_zh"]
            and check.get("executor_department") == "publishing" and check.get("production_write_allowed") is False
            and facts.get("current_binding_source") == target["current_binding_source"]
            and document(root, facts.get("current_full_record")) == before
            and observed and w._parse_observed_at(request.get("actual_created_at")) <= observed
            and rollback.get("rollback_allowed") is False and rollback.get("production_write_allowed") is False,
            "Real current full41 backup/selfcheck/facts and original no-inverse-permit boundary required")
    effects = document(root, facts.get("safe_original_key_effects"))
    require(isinstance(effects.get("rows"), list) and all(
        x.get("record_id") == target["record_id"] and x.get("slug") == target["slug"]
        and x.get("task_id") != TASK and x.get("status") == "completed" for x in effects["rows"]),
        "Fresh original-key effects required; completed W or active/unknown same-row effects cannot be replayed")
    return item


def preflight(root, snapshot):
    target = registered(root)
    require(target is not None and snapshot.get("task_id") == TASK, "Registered current-W source required")
    rows = []
    for event in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        details = event.get("details", {})
        if event.get("task_id") == TASK and details.get("current_W_binding_source") == target["current_binding_source"]:
            rows.append(document(root, details.get("production_preflight_registered")))
    require(len(rows) == 1, "One new actual PUB full41 preflight for current W source required; old Oct10 selfcheck cannot execute")
    return validate_preflight(root, rows[0], target)


def record_preflight(root, task_id, path):
    import goal_delivery_runtime as g
    require(task_id == TASK, "Original W preflight task required")
    with w.workflow_lock(root):
        target = registered(root)
        require(target is not None, "Current-W registration required before its new PUB preflight")
        pin = w.file_digest(root, path)
        item = validate_preflight(root, document(root, pin), target)
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
        require(snapshot.get("current_state") not in w.TERMINAL_STATES, "Active original W goal required")
        rows = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get("task_id") == TASK
                and e.get("details", {}).get("current_W_binding_source") == target["current_binding_source"]]
        if rows:
            require(len(rows) == 1 and rows[0]["details"]["production_preflight_registered"] == pin,
                    "One frozen current-W preflight; preserve prior sources")
            return {"result": "duplicate_ignored", "external_permission_issued": False}
        event = w.append_workflow_event(root, TASK, snapshot["current_state"], {
            "production_preflight_registered": pin, "current_W_binding_source": target["current_binding_source"],
            "external_permission_issued": False})
    return {"result": "recorded", "event_id": event["event_id"], "external_permission_issued": False}


WEB_SCHEMA = 'builtin-wardrobe-original-WEB-source-registration/v1'


def web_context(root, snapshot, source):
    """The original W's received WEB source; no new task or platform grant."""
    import datetime as dt
    import hashlib
    import department_autonomy as a
    import goal_delivery_runtime as g
    import professional_web_execution as web
    import managed_cms_permit_issuer as issuer

    root = Path(root).resolve()
    require(source.get('schema') == WEB_SCHEMA and source.get('task_id') == snapshot.get('task_id') == TASK
            and set(source) == {'schema', 'task_id', 'owner_input', 'WEB_completed_native', 'WEB_source_command',
                                'account_source', 'account_native', 'account_command', 'source_backup', 'rollback_runbook'},
            'Exact original W WEB source schema required')
    current = registered(root)
    require(current is not None, 'Actual current original PUB full41 source required')
    request = document(root, source['owner_input'])
    goal = g.restore_goal(root, snapshot)['goal_delivery']
    frozen = document(root, snapshot['goal_contract'])
    require(request.get('task_id') == TASK and request.get('scope') == current['scope']
            and request.get('business_owner') == goal.get('primary_owner') == 'paid-growth-data'
            and request.get('original_goal_contract') == snapshot['goal_contract']
            and request.get('original_human_authorization') == w.file_digest(root, frozen['human_authorization']['evidence_path'])
            and request.get('original_WEB_role') == 'designated-development'
            and all(goal.get(k) == frozen.get(k) for k in ('primary_owner', 'producer_departments', 'authorized_scope',
                                                         'human_authorization', 'required_execution_actions')),
            'Unchanged original W owner, scope, contract and human authority required')
    role = request['original_WEB_role']; binding = g._collaboration_binding(root, snapshot, role)
    require(binding and role not in w.department_registry(root)
            and {'sender_department': goal['primary_owner'], 'target_department': role, 'scope': current['scope']} in goal['collaboration_scopes']
            and all(request.get(k) == binding[v] for k, v in (
                ('actual_original_WEB_fixed_chat', 'thread_id'), ('actual_original_WEB_project_id', 'project_id'),
                ('actual_original_WEB_cwd', 'cwd'))), 'Real declared original external WEB binding, never an internal role')
    report_pin = request['WEB_original_result_exact_copy']; report = document(root, report_pin)
    proposed = document(root, request['prepared_source_original_exact_copy_NOT_REGISTERED'])
    states = g._collaboration_wait_states(root, snapshot, only_action_id=report.get('received_action_id'))
    require(len(states) == 1 and states[0].get('status') == 'result_received' and states[0].get('proof_state') == 'PROVEN'
            and states[0].get('received') is True and states[0].get('result') == report_pin
            and states[0].get('threadId') == binding['thread_id']
            and all(states[0]['approved_action'].get(k) == v for k, v in (
                ('task_id', TASK), ('scope', current['scope']), ('sender_department', goal['primary_owner']), ('target_department', role)))
            and states[0].get('native_result') == source['WEB_completed_native'],
            'Actual exact original WEB complete-result callback required')
    native = g._native_document(root, source['WEB_completed_native'])
    require(all(native.get('thread', {}).get(k) == binding[v] for k, v in
                (('id', 'thread_id'), ('title', 'title'), ('cwd', 'cwd'))), 'Actual fixed WEB native identity required')
    calls = [(t, c) for t in native.get('turns', []) for c in t.get('items', []) if c.get('id') == source['WEB_source_command']]
    require(len(calls) == 1, 'One real original source-output command required')
    turn, command = calls[0]; raw = w._completion_execution_output(command).decode('utf-8')
    decoder = json.JSONDecoder(); output, end = decoder.raw_decode(raw.lstrip())
    tail = raw.lstrip()[end:].strip()
    require(tail == 'FLASHCAST_DELIVERY_READY task_id=' + TASK + ' sender_department=' + role
            + ' candidate_version=' + report['candidate_version'] + ' result_sha256=' + report_pin['sha256'],
            'Exact single original result/READY output; conflicting or incomplete output rejected')
    final = [m for m in turn.get('items', []) if m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer']
    made = w._parse_observed_at(report.get('created_at'))
    require(turn.get('status') == 'completed' and not turn.get('error') and len(final) == 1
            and command.get('type') == 'commandExecution' and command.get('status') == 'completed' and command.get('exitCode') == 0
            and Path(command.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve())
            and made is not None and turn['startedAt'] <= made.timestamp() <= turn['completedAt'] <= dt.datetime.now(dt.timezone.utc).timestamp()
            and output.get('report', {}).get('sha256') == report_pin['sha256']
            and output['report'].get('size') == report_pin['size']
            and web._external_bytes(output['report'], binding) == w.safe_path(root, report_pin['path']).read_bytes()
            and output['report']['path'] in final[0].get('text', ''),
            'Successful completed original WEB output/final must bind the exact immutable report')
    require(report.get('task_id') == TASK and report.get('scope') == current['scope']
            and report.get('sender_department') == role and report.get('business_owner') == goal['primary_owner']
            and report.get('CMS_executor') == 'publishing'
            and proposed.get('task_id') == TASK and proposed.get('scope') == current['scope']
            and proposed.get('original_owner') == goal['primary_owner'] and proposed.get('channel_executor') == role
            and all(proposed.get('original_human_authorization', {}).get(k) == request['original_human_authorization'][k] for k in ('sha256', 'size'))
            and Path(proposed['original_human_authorization']['path']).resolve() == w.safe_path(root, request['original_human_authorization']['path']).resolve()
            and proposed.get('adopted_PUB_source_event') == current['current_binding_event_id']
            and proposed.get('source_registration_performed') is False
            and proposed.get('production_authority_created_by_this_input') is False,
            'Original producer proposal remains a nonexecuting source, not permission')
    meta = request['code_candidate']
    require(meta == report.get('local_git_candidate') and all(proposed.get('code_candidate', {}).get(k) == meta[k]
            for k in ('head', 'base', 'parent', 'tree', 'branch', 'worktree', 'files', 'forward', 'inverse')),
            'One authentic selected code candidate and proposal required')
    require(Path(meta['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve()), 'Original website worktree required')
    gitctx = {'worktree': meta['worktree']}; head = meta['head']; base = meta['base']
    paths = {f['path']: f['sha256'] for f in meta['file_blobs']}
    expected_paths = {'supabase/functions/_shared/builtin-wardrobe-targets.ts', 'scripts/managed-cms-targets-builtin-wardrobe-v1.mjs',
                      'supabase/functions/content-publish/service.ts', 'src/lib/contentPublishBuiltinWardrobe.test.ts'}
    require(len(paths) == len(meta['file_blobs']) == 4 and set(meta['files']) == set(paths) == expected_paths
            and meta['base'] == meta['parent']
            and web.git(gitctx, 'show', '-s', '--format=%H %P %T', head).decode().strip() == ' '.join([head, meta['parent'], meta['tree']])
            and set(web.git(gitctx, 'diff', '--name-only', base, head).decode().splitlines()) == set(paths),
            'Actual four-path Git head/parent/tree, no unrelated source')
    blobs = {}
    for f in meta['file_blobs']:
        data = web.git(gitctx, 'show', head + ':' + f['path']); blobs[f['path']] = data
        require(hashlib.sha256(data).hexdigest() == f['sha256'] and len(data) == f['size']
                and web.git(gitctx, 'rev-parse', head + ':' + f['path']).decode().strip() == f['blob'], 'Exact original source blob/hash/size')
    delta = web._patch_effect(web._delta({**gitctx, 'paths': paths}, base, head))
    require(web._patch_effect(web._patch_delta(web._external_bytes(meta['forward'], binding))) == delta
            and web._patch_effect(web._patch_delta(web._external_bytes(meta['inverse'], binding))) == {p: (added, removed) for p, (removed, added) in delta.items()},
            'Exact source forward/inverse effects; not a production rollback grant')
    # Both target objects are JSON inside existing TS/JS, not caller-built aliases.
    runtime = decoder.raw_decode(blobs['supabase/functions/_shared/builtin-wardrobe-targets.ts'].decode().split('= [', 1)[1].lstrip())[0]
    cli = decoder.raw_decode(blobs['scripts/managed-cms-targets-builtin-wardrobe-v1.mjs'].decode().split('const binding = ', 1)[1])[0]
    require(runtime == proposed['protection_only_runtime_selector'] == report['prepared_exact_parameters']['exact_runtime_selector']
            and proposed['protection_only_CLI_binding'] == report['prepared_exact_parameters']['exact_CLI_binding']
            and set(cli) - set(proposed['protection_only_CLI_binding']) == {'sourceCandidatePath', 'sourceCandidateSha256', 'sourceProvenanceSha256', 'publicPaths'}
            and all(cli[k] == v for k, v in proposed['protection_only_CLI_binding'].items()),
            'Both immutable original code binding objects must agree')
    five = {'expectedUpdatedAt', 'baselineProjectionFields', 'baselineFieldsSha256', 'retainedProjectionFields', 'retainedFieldsSha256'}
    for path, value, marker in [('supabase/functions/_shared/builtin-wardrobe-targets.ts', runtime, '= ['),
                                ('scripts/managed-cms-targets-builtin-wardrobe-v1.mjs', cli, 'const binding = ')]:
        old = decoder.raw_decode(web.git(gitctx, 'show', base + ':' + path).decode().split(marker, 1)[1].lstrip())[0]
        require(set(old) == set(value) and {k for k in old if old[k] != value[k]} == five,
                'Exactly five protection values may change; original tuple/payload/rollback stay frozen')
        require(all(value.get(k) == v for k, v in {'taskId': TASK, 'actionId': current['action_id'], 'candidateVersion': current['candidate_version'],
                    'scope': current['scope'], 'table': current['table'], 'changedFields': current['changed_fields'],
                    'expectedUpdatedAt': current['expected_updated_at'], 'baselineProjectionFields': current['baseline_projection_fields'],
                    'baselineFieldsSha256': current['baseline_fields_sha256'], 'retainedProjectionFields': current['retained_projection_fields'],
                    'retainedFieldsSha256': current['retained_fields_sha256'], 'desiredFieldsSha256': current['payload_sha256'],
                    'rollbackFieldsSha256': current['rollback_fields_sha256'], 'rollbackAllowed': False, 'requiresParentRun': True}.items()),
                'Original W exact tuple and registered full41/MS11 protection required')
    # Validate all original producer evidence bytes; reuse its 137 checks, never reinterpret them as permission.
    evidence = json.loads(web._external_bytes(report['evidence_manifest'], binding))
    for pin in web._pins(evidence):
        if Path(pin['path']).is_absolute() and not Path(pin['path']).resolve().is_relative_to(root): web._external_bytes(pin, binding)
        else:
            actual = w.file_digest(root, pin['path'])
            require(all(actual[k] == pin[k] for k in ('sha256', 'size')), 'Original immutable producer evidence changed')
    account = document(root, source['account_source']); account_native = g._native_document(root, source['account_native'])
    account_calls = [(t, c) for t in account_native.get('turns', []) for c in t.get('items', []) if c.get('id') == source['account_command']]
    require(len(account_calls) == 1 and account_native.get('thread', {}).get('id') == binding['thread_id'], 'Genuine original external account read required')
    at, ac = account_calls[0]; outputs = []
    for line in w._completion_execution_output(ac).decode().splitlines():
        try: value = json.loads(line)
        except ValueError: continue
        if isinstance(value, dict): outputs.append(value)
    name = account.get('full_name'); actor = account.get('authenticated_actor', {})
    require(at.get('status') == 'completed' and not at.get('error') and ac.get('status') == 'completed' and ac.get('exitCode') == 0
            and Path(ac.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve()) and outputs == [account]
            and name == 'wangchaozhuanyong/zhuangxiuwangzhan' and type(account.get('id')) is int
            and type(actor.get('id')) is int and actor['id'] > 0 and actor.get('login') == name.split('/')[0]
            and web.git(gitctx, 'config', '--get', 'remote.origin.url').decode().strip() in
                {'user-3de132cd98be@example.invalid:' + name + '.git', 'https://github.com/' + name, 'https://github.com/' + name + '.git'},
            'Actual existing repository/actor identity only, no other-task permission')
    components = [{'head': head, 'base': base, 'parent': meta['parent'], 'tree': meta['tree'], 'worktree': meta['worktree'],
                   'paths': paths, 'forward': meta['forward'], 'inverse': meta['inverse']}]
    backup = document(root, source['source_backup']); recovery = document(root, source['rollback_runbook'])
    require(backup == {'task_id': TASK, 'source_components': components, 'actual_platform_backup_or_restore_proven': False}
            and recovery == {'task_id': TASK, 'goal_contract': snapshot['goal_contract'], 'source_components': components,
                             'unknown_effect_replay_allowed': False, 'CMS_inverse_allowed': False,
                             'source_inverse_is_not_production_rollback': True, 'execution_requires_actual_platform_backup': True},
            'Exact source-only recovery recipe; runtime backup remains an actual execution prerequisite')
    require(not w.validate_workflow_events(root, TASK) and not w._validate_receipt_chain(root, TASK)[1]
            and snapshot.get('current_state') not in w.TERMINAL_STATES, 'Intact active original W history')
    project_ref = issuer.SUPABASE_HOST.split('.')[0]
    return {'root': str(root), 'task': TASK, 'scope': current['scope'], 'owner': goal['primary_owner'], 'role': role,
            'binding': binding, 'decision': source['owner_input'], 'authorization': request['original_human_authorization'],
            'contract': snapshot['goal_contract'], 'worktree': meta['worktree'], 'site': binding['cwd'], 'branch': meta['branch'],
            'commit': head, 'base': base, 'tree': meta['tree'], 'paths': paths, 'source_components': components,
            'backup': source['source_backup'], 'rollback': source['rollback_runbook'], 'repository': name,
            'repository_id': account['id'], 'actor_id': actor['id'], 'original_production_channel': True,
            'original_W_channel': True, 'prefix': TASK + '-web', 'edge_scope': 'company.example:edge:' + project_ref + ':content-publish',
            'pages_scope': 'company.example:pages:production', 'project_ref': project_ref}
