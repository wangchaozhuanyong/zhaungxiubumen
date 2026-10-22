"""Exact owner-direct native control delivery readers; no native tool calls.

An active HQ can deliver one whole verified configuration. Its frozen result
and original native message are separate pins, avoiding an outbox hash cycle.
No commentary, ACK or summary alone qualifies, and professional results keep
their original completed-final path. All mutations remain in existing services.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo
import workflow_control as w

KINDS = {"automation_create": "create", "automation_update": "update"}
MARKER = "RUNTIME_CONTROL_COMPLETE"
CARD = "Rendered automation card in the app."
CREATED = "Created automation in the app."
NOT_EXPOSED = "NOT_EXPOSED"


def require(value, message):
    if not value:
        raise w.WorkflowError("native control result: " + message)


def pin(root, value):
    require(isinstance(value, dict) and w.file_digest(root, value.get("path", "")) == value,
            "exact original project evidence pin required")
    return value


def document(root, value):
    return w.read_json(w.safe_path(root, pin(root, value)["path"]))


def matches(snapshot):
    goal = snapshot.get("goal_delivery", {})
    return (goal.get("source_mode") == "owner_direct" and goal.get("primary_owner") == "operations"
            and goal.get("producer_departments") == ["operations"] and isinstance(goal.get("native_routing_binding"), dict))


def context(root, snapshot):
    import goal_delivery_runtime as g
    require(matches(snapshot), "only a registered exact owner-direct OPS configuration task is eligible")
    task = w.validate_task_id(snapshot.get("task_id", ""))
    current = w.read_json(w.snapshot_path(root, task))
    require(current.get("task_id") == task and matches(current), "actual registered task required")
    restored = g.restore_goal(root, snapshot)
    require(restored.get("goal_delivery") == snapshot.get("goal_delivery")
            == current.get("goal_delivery"), "current control goal must equal its original committed source")
    snapshot = restored
    try:
        events = [_json(line) for line in (Path(root) / w.WORKFLOW_EVENTS).read_text().splitlines() if line.strip()]
    except OSError as exc:
        raise w.WorkflowError("native control result: original registered event source required") from exc
    previous = ""
    for event in events:
        require(event.get("previous_event_hash", "") == previous
                and event.get("event_hash") == w.sha256_value({k:v for k,v in event.items() if k != "event_hash"}),
                "original registration event chain changed")
        previous = event["event_hash"]
    require(any(event.get("task_id") == task and event.get("details", {}).get("goal_contract") == snapshot.get("goal_contract")
                for event in events), "actual original frozen goal registration required")
    goal = g.validate_goal(root, snapshot["goal_delivery"])
    contract = document(root, snapshot.get("goal_contract"))
    contract = contract.get("goal_delivery", contract)
    require(all(contract.get(k) == goal.get(k) for k in
                ("task_id", "primary_owner", "responsible_assistant", "acceptance_capability", "producer_departments",
                 "authorized_scope", "source_mode", "human_authorization", "native_routing_binding", "schedule_target_department"))
            and goal["acceptance_capability"] == "functional" and not goal["required_execution_actions"]
            and goal["responsible_assistant"] != "operations" and len(goal["authorized_scope"]) == 1,
            "original complete control goal and independent functional reviewer required")
    registry = w.department_registry(root)
    config = document(root, goal["native_routing_binding"])
    target, reviewer = goal.get("schedule_target_department"), goal["responsible_assistant"]
    require(target in registry and reviewer in registry
            and config.get("executor", {}).get("department") == "operations"
            and config.get("fixed_target", {}).get("department") == target
            and config.get("unique_acceptance", {}).get("department") == reviewer
            and config["unique_acceptance"].get("capability") == "functional"
            and config.get("routing_action_is_not_external_production_action") is True
            and set(config.get("policy_supported_action_classes", [])) == set(KINDS),
            "original frozen native control action/target/reviewer binding required")
    for role, key in (("operations", "executor"), (target, "fixed_target"), (reviewer, "unique_acceptance")):
        actual, original = registry[role].get("chat_binding", {}), config[key].get("binding_snapshot", {})
        require(w._chat_binding_healthy(actual, verification_ttl_hours=26)
                and actual.get("cwd") == str(Path(root).resolve())
                and all(actual.get(k) == original.get(k) for k in ("task_id", "project_id", "cwd", "title"))
                and actual.get("project_id") == registry["operations"]["chat_binding"].get("project_id"),
                "healthy original same-project fixed configuration bindings required")
    require(goal["human_authorization"]["source_thread_id"] == registry["operations"]["chat_binding"]["task_id"],
            "actual original owner human source required")
    pin(root, config.get("prompt"))
    schedule = config.get("requested_schedule", {})
    require(schedule.get("kind") == "heartbeat" and schedule.get("project_only") is True
            and schedule.get("targetThreadId") == registry[target]["chat_binding"]["task_id"]
            and schedule.get("timezone") == "Asia/Kuala_Lumpur"
            and schedule.get("weekday") == "Sunday" and schedule.get("local_time") == "20:00",
            "frozen original exact schedule required")
    return snapshot, goal, config, registry


def _json(raw):
    if isinstance(raw, dict):
        return raw
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate native JSON key")
            value[key] = item
        return value
    require(isinstance(raw, str), "original native JSON required")
    try:
        result = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError) as exc:
        raise w.WorkflowError("native control result: original structured JSON required") from exc
    require(isinstance(result, dict), "native structured object required")
    return result


def weekly_rule(raw):
    """The whole original indefinite Sunday 20:00 rule, not one next run."""
    require(isinstance(raw, str) and raw and raw == raw.strip(), "exact weekly RRULE required")
    value = raw[6:] if raw.startswith("RRULE:") else raw
    parts = {}
    for part in value.split(";"):
        pair = part.split("=")
        require(len(pair) == 2 and pair[0] not in parts, "duplicate or invalid RRULE field")
        parts[pair[0]] = pair[1]
    require(set(parts) in ({"FREQ", "BYDAY", "BYHOUR", "BYMINUTE"},
                          {"FREQ", "INTERVAL", "BYDAY", "BYHOUR", "BYMINUTE"})
            and parts.get("FREQ") == "WEEKLY" and parts.get("INTERVAL", "1") == "1"
            and parts.get("BYDAY") == "SU" and parts.get("BYHOUR") == "20"
            and parts.get("BYMINUTE") == "0",
            "only weekly interval one, Sunday 20:00; expanding/unknown RRULE semantics rejected")


def _json_value(raw):
    # Reuse the duplicate-key guard for arrays as well as objects.
    return _json('{"value":' + raw + '}')["value"]


def _exec_requests(code):
    """Recognize bounded original JS transports as data. Never eval/execute JS."""
    require(isinstance(code, str), "original exec input required")
    single = re.fullmatch(r"\s*text\(await tools\.mcp__codex_app__automation_update\((\{[\s\S]*\})\)\);?\s*", code)
    if single:
        return [_json(single.group(1))], "single"
    # This is the exact real HQ Promise.allSettled map/output form. Both ID
    # arrays must be identical; unknown appended JS/calls cannot be hidden.
    batch = re.fullmatch(
        r'\s*const rs=await Promise\.allSettled\((\[[^\n]*\])\.map\(id=>tools\.mcp__codex_app__automation_update\(\{mode:"view",id\}\)\)\);'
        r'const out=\[\];for\(let i=0;i<rs\.length;i\+\+\)\{const r=rs\[i\];if\(r\.status==="fulfilled"\)\{'
        r'store\("[A-Za-z0-9_]+"\+i,r\.value\);const v=r\.value\.structuredContent\?\?r\.value;'
        r'out\.push\(\{id:(\[[^\n]*\])\[i\],result:v\}\);\}else out\.push\(\{error:String\(r\.reason\)\}\);\}text\(out\);\s*', code)
    if batch:
        ids, repeated = _json_value(batch.group(1)), _json_value(batch.group(2))
        require(isinstance(ids, list) and ids == repeated and ids and len(ids) == len(set(ids))
                and all(isinstance(value, str) and value for value in ids), "exact unique original batch IDs required")
        return [{"mode": "view", "id": value} for value in ids], "batch_ids"
    # The equally bounded literal-argument batch retains each real settled
    # result. It is useful for create/update whose result is only a card.
    settled = re.fullmatch(
        r'\s*const rs=await Promise\.allSettled\((\[[\s\S]*\])\.map\(args=>tools\.mcp__codex_app__automation_update\(args\)\)\);text\(rs\);\s*', code)
    if settled:
        args = _json_value(settled.group(1))
        require(isinstance(args, list) and args and all(isinstance(value, dict) for value in args), "literal original batch arguments required")
        return args, "settled"
    require("automation_update" not in code, "unknown automation exec syntax or extra calls rejected")
    return [], "unrelated"


def _responses(result, args, shape):
    if shape == "single":
        return [result]
    require(isinstance(result, list) and len(result) == len(args), "complete original batch output required")
    values = []
    for request, response in zip(args, result):
        require(isinstance(response, dict), "original batch result object required")
        if shape == "batch_ids":
            require(set(response) == {"id", "result"} and response["id"] == request["id"], "exact ordered original batch result ID required")
            values.append(response["result"])
        else:
            require(set(response) == {"status", "value"} and response["status"] == "fulfilled", "rejected/partial batch cannot prove success")
            values.append(response["value"])
    return values


def _configuration(result):
    require(isinstance(result, dict) and result.get("isError", False) is False
            and result.get("success", True) is True, "native mutation/readback failure cannot be accepted")
    if "content" in result:
        require(set(result) <= {"content", "isError", "structuredContent", "_meta"}
                and isinstance(result["content"], list) and len(result["content"]) in {1, 2}
                and all(isinstance(block, dict) and block.get("type") == "text"
                        and isinstance(block.get("text"), str)
                        for block in result["content"]), "one complete native response required")
        if len(result["content"]) == 2:
            require("structuredContent" not in result and result["content"][0]["text"] == CREATED
                    and all(set(block) == {"type", "text"} for block in result["content"]),
                    "exact successful create text and one structured receipt required")
            receipt = _json(result["content"][1]["text"])
            require(set(receipt) == {"automationId", "mode", "status"}
                    and isinstance(receipt["automationId"], str)
                    and re.fullmatch(r"[a-z0-9][a-z0-9-]*", receipt["automationId"])
                    and receipt["mode"] == "create" and receipt["status"] == "ACTIVE",
                    "exact native create ID/mode/status receipt required")
            # This sparse receipt is not a configuration. native_call binds it
            # to the original mutation; effects still requires canonical/view.
            return receipt
        text = result["content"][0]["text"]
        if text == CARD:
            require("structuredContent" not in result, "ambiguous card and structured response rejected")
            return None
        result = _json(text)
        require(result.get("isError", False) is False and result.get("success", True) is True, "native structured response failed")
    configuration = result.get("automation", result)
    require(isinstance(configuration, dict), "actual native configuration response required")
    return configuration


def _session(root, frozen, fixed, thread_source):
    """Frozen exact UTF-8 session records plus actual fixed-thread projection."""
    import goal_delivery_runtime as g
    source = document(root, frozen)
    projection_source = document(root, thread_source)
    if projection_source.get("schema") == "actual_native_view_format_evidence/v1":
        # Preserve this actual frozen projection shape. Its missing results
        # prove only fixed thread/turn identity; raw records prove the calls.
        projection = projection_source.get("hq_native_read_thread_projection", {})
        require(projection.get("projection_only") is True
                and projection_source.get("native_configuration_mutation_performed") is False,
                "actual view projection is identity only")
        native = {"thread": projection.get("thread"), "turns": [projection.get("turn", {})]}
    else:
        native = g._collaboration_native(root, pin(root, thread_source))
    thread = native.get("thread", {})
    require(thread.get("id") == fixed["task_id"] and thread.get("cwd") == fixed["cwd"]
            and thread.get("title") == fixed["title"], "actual fixed OPS projection required for raw session source")
    require(source.get("source_thread_id") == fixed["task_id"]
            and isinstance(source.get("source_session"), str) and Path(source["source_session"]).is_absolute()
            and source["source_session"].endswith(".jsonl")
            and source.get("original_payload_values_not_normalized") is True
            and isinstance(source.get("original_records"), list) and source["original_records"], "exact original session export required")
    session_path = Path(source["source_session"])
    require(session_path.is_file() and session_path == session_path.resolve()
            and not any(parent.is_symlink() for parent in (session_path, *session_path.parents)), "canonical original native session file required")
    selected = {}
    for entry in source["original_records"]:
        number, text = entry.get("original_line_number"), entry.get("original_line_utf8")
        require(type(number) is int and number > 1 and number not in selected and isinstance(text, str), "unique selected original session lines required")
        selected[number] = text.encode("utf-8")
    # Other lines are skipped as opaque bytes and never decoded, emitted or
    # persisted. Only session_meta.id and these precise frozen lines are read.
    with session_path.open("rb") as handle:
        first = handle.readline()
        meta = _json(first.decode("utf-8"))
        require(meta.get("type") == "session_meta" and meta.get("payload", {}).get("id") == fixed["task_id"], "original session_meta thread identity differs")
        del first, meta
        found = 0
        for number in range(2, max(selected) + 1):
            raw_line = handle.readline()
            require(raw_line, "selected original session line missing")
            if number in selected:
                require(raw_line == selected[number], "selected actual source-session UTF-8 differs from frozen export")
                found += 1
            del raw_line
        require(found == len(selected), "all selected original session records required")
    turns = [turn for turn in native.get("turns", []) if turn.get("id") == source.get("source_turn_id")]
    require(len(turns) == 1 and not turns[0].get("error") and turns[0].get("status") in {"inProgress", "completed"},
            "actual original active/completed source turn required")
    if "startedAt" in turns[0]:
        require(type(turns[0]["startedAt"]) in {int, float} and turns[0]["startedAt"] > 0, "invalid exposed native turn start")
    items, times = [], []
    last_line = last_ordinal = 0
    last_time = turns[0].get("startedAt", 0)
    for entry in source["original_records"]:
        raw = entry.get("original_line_utf8")
        require(isinstance(raw, str) and hashlib.sha256(raw.encode("utf-8")).hexdigest() == entry.get("original_line_sha256")
                and _json(raw) == entry.get("original_record"), "original session UTF-8/hash/record mismatch")
        record = entry["original_record"]
        observed = w._parse_observed_at(record.get("timestamp"))
        require(type(entry.get("original_line_number")) is int and entry["original_line_number"] > last_line
                and type(record.get("ordinal")) is int and record["ordinal"] > last_ordinal
                and observed is not None and last_time <= observed.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp()
                and record.get("type") == "response_item", "original ordered session line/ordinal/time required")
        payload = record.get("payload", {})
        metadata = payload.get("internal_chat_message_metadata_passthrough", {})
        # The actual session's ISO timestamp is milliseconds, while its
        # server metadata retains finer precision (e.g. .537 vs .537170).
        # Respect only that represented timestamp interval, never a grace sec.
        fraction = re.search(r"\.(\d+)(?:Z|[+-]\d\d:\d\d)$", record["timestamp"])
        precision = 10 ** (-len(fraction[1])) if fraction else 1
        require(payload.get("id") and metadata.get("turn_id") == turns[0]["id"]
                and type(metadata.get("create_time")) in {int, float}
                and 0 < metadata["create_time"] < observed.timestamp() + precision
                and metadata["create_time"] <= dt.datetime.now(dt.timezone.utc).timestamp(), "original session turn/message identity required")
        if payload.get("type") == "custom_tool_call_output":
            require(record.get("metadata", {}).get("client_authored") is False, "native server output required")
        items.append(payload); times.append(max(observed.timestamp(), metadata["create_time"]))
        last_line, last_ordinal, last_time = entry["original_line_number"], record["ordinal"], observed.timestamp()
    if "original_call_id" in source:
        require(source["original_call_id"] and sum(item.get("type") == "custom_tool_call"
                and item.get("call_id") == source["original_call_id"] for item in items) == 1,
                "original export call identity differs")
    return items, times, turns[0]["id"]


def _session_output(payload):
    blocks = payload.get("output")
    require(isinstance(blocks, list) and len(blocks) == 2
            and all(isinstance(block, dict) and set(block) == {"type", "text"} and block["type"] == "input_text" for block in blocks)
            and re.fullmatch(r"Script completed\nWall time [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n", blocks[0]["text"]),
            "complete successful original exec input_text output required")
    return _json_value(blocks[1]["text"])


def native_call(root, frozen, fixed, mode, *, automation_id=None, thread_source=None):
    """Exact native call/output, including raw exec; a card is not config."""
    import goal_delivery_runtime as g
    frozen = pin(root, frozen)
    source = document(root, frozen)
    raw_session = "original_records" in source
    if raw_session:
        items, times, turn_id = _session(root, frozen, fixed, thread_source)
        turns = [{"id": turn_id, "items": items, "times": times}]
    else:
        native = g._collaboration_native(root, frozen)
        require(native.get("thread", {}).get("id") == fixed["task_id"]
                and native["thread"].get("cwd") == fixed["cwd"] and native["thread"].get("title") == fixed["title"],
                "actual original OPS native tool thread required")
        turns = native.get("turns", [])
    pairs = []
    mutations = 0
    for turn in turns:
        if not raw_session:
            require(not turn.get("error") and turn.get("status") in {"inProgress", "completed"},
                    "successful original native execution turn required")
        items = turn.get("items", [])
        for index, call in enumerate(items):
            if call.get("type") not in {"functionCall", "custom_tool_call"}:
                continue
            if raw_session and call.get("type") == "custom_tool_call" and call.get("name") == "exec":
                require(call.get("status") == "completed", "completed original exec call required")
                args_list, shape = _exec_requests(call.get("input"))
            elif call.get("type") == "functionCall" and call.get("name") in {"automation_update", "mcp__codex_app__automation_update"}:
                require(call.get("namespace") in {"codex_app", "mcp__codex_app"}, "original native tool namespace required")
                args_list, shape = [_json(call.get("arguments"))], "single"
            elif call.get("name") == "exec" and call.get("namespace") == "functions":
                args_list, shape = _exec_requests(call.get("arguments"))
            else:
                continue
            if not args_list:
                continue
            call_id = call.get("call_id") if raw_session else call.get("callId")
            require(call_id and sum((item.get("call_id") if raw_session else item.get("callId")) == call_id
                    for item in items if item.get("type") in {"functionCall", "custom_tool_call"}) == 1,
                    "unique original native call ID required")
            outputs = [item for item in items[index + 1:] if
                       (raw_session and item.get("type") == "custom_tool_call_output" and item.get("call_id") == call_id)
                       or (not raw_session and item.get("type") == "functionCallOutput" and item.get("callId") == call_id
                           and item.get("name") == call.get("name") and item.get("namespace") == call.get("namespace"))]
            require(len(outputs) == 1, "unique matching original native call output required")
            output_index = items.index(outputs[0])
            if raw_session:
                result = _session_output(outputs[0])
                started, output_time = turn["times"][index], turn["times"][output_index]
            else:
                output = outputs[0].get("output", {})
                require(output.get("truncated") is False and output.get("isError", False) is False,
                        "successful complete original native tool output required")
                result = _json_value(output.get("text"))
                started = output_time = turn.get("startedAt")
            require(type(started) in {int, float} and 0 < started <= dt.datetime.now(dt.timezone.utc).timestamp(),
                    "actual nonfuture native call time required")
            for args, response in zip(args_list, _responses(result, args_list, shape)):
                allowed = {"mode", "id"} if args.get("mode") == "view" else {"mode", "id", "name", "prompt", "rrule", "status", "kind", "targetThreadId"}
                require(set(args) <= allowed and args.get("mode") in {"view", "create", "update"}, "bounded native automation arguments required")
                if args["mode"] != "view":
                    mutations += 1
                    require(mutations <= 1 and (mode == "view" or args["mode"] == mode), "one original mutation only; unknown retry rejected")
                configuration = _configuration(response)
                create_receipt = (configuration if isinstance(response, dict)
                                  and isinstance(response.get("content"), list)
                                  and len(response["content"]) == 2 else None)
                if create_receipt is not None:
                    require(args["mode"] == create_receipt["mode"] == "create"
                            and args.get("status") == create_receipt["status"] == "ACTIVE",
                            "native create receipt must match the original mutation mode/status")
                    configuration = None
                if args.get("mode") != mode or (automation_id is not None and args.get("id") != automation_id):
                    continue
                pairs.append({"args": args, "configuration": configuration, "create_receipt": create_receipt, "started": started,
                              "output_time": output_time, "turn_id": turn.get("id"), "index": index, "items": items,
                              "item_times": turn.get("times"), "source_pin": frozen, "thread_source_pin": thread_source,
                              "output_index": output_index, "transport": "original_session_exec" if raw_session else "original_read_thread"})
    require(len(pairs) == 1, "one exact native call, no duplicate or ambiguous effect")
    return pairs[0]


def _toml_safe_fields(raw):
    """Python 3.9, native scalar whitelist only; never expose other TOML data."""
    keys = {"id", "name", "status", "kind", "rrule", "target_thread_id", "prompt", "timezone", "next_run_at", "created_at", "updated_at"}
    lines, values, index, section = raw.splitlines(keepends=True), {}, 0, False
    while index < len(lines):
        line = lines[index]; index += 1
        if line.lstrip().startswith(b"["):
            section = True
        match = re.match(rb"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line.rstrip(b"\r\n"))
        if not match or match[1].decode("ascii") not in keys:
            continue
        key = match[1].decode("ascii")
        require(not section and key not in values, "unique top-level native config whitelist fields required")
        value = match[2].decode("utf-8")
        if key in {"created_at", "updated_at"}:
            require(re.fullmatch(r"[0-9]+", value) and int(value) > 0, "native tool millisecond timestamp required")
            values[key] = int(value)
            continue
        triple = value[:3] if value.startswith(('"""', "'''")) else None
        if triple:
            content = value[3:]
            while triple not in content and index < len(lines):
                content += '\n' if not content.endswith('\n') else ''
                content += lines[index].decode("utf-8"); index += 1
            require(content.count(triple) == 1 and not content.split(triple, 1)[1].strip(), "bounded native multiline string required")
            content = content.split(triple, 1)[0]
            if content.startswith('\n'):
                content = content[1:]
            if triple == "'''":
                value = content
            else:
                require('\\\n' not in content and '"' not in content.replace('\\"', ''), "unsupported native TOML escape syntax")
                value = _json_value('"' + content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"')
        elif value.startswith("'") and value.endswith("'") and value.count("'") == 2:
            value = value[1:-1]
        else:
            require(value.startswith('"') and value.endswith('"'), "native whitelist string syntax required")
            value = _json_value(value)
        require(isinstance(value, str), "native config whitelist string required")
        values[key] = value
    return values


def local_configuration(root, frozen, target, viewed, *, mutation=None):
    """Re-read the exact native file; caller projection/hash alone is insufficient."""
    import goal_delivery_runtime as g
    source = document(root, frozen)
    require(source.get("schema") == "actual_native_automation_local_readback/v1" and source.get("read_only") is True,
            "explicit actual local native config source required")
    projection = source.get("nonsecret_exact_scalar_projection", {})
    require(set(projection) == {"id", "name", "status", "kind", "rrule", "target_thread_id"}
            and all(isinstance(value, str) and value for value in projection.values())
            and re.fullmatch(r"[a-z0-9][a-z0-9-]*", projection["id"]), "exact safe native scalar projection required")
    path = Path(source.get("source_path", ""))
    require(path.is_absolute() and path.is_file() and not any(parent.is_symlink() for parent in (path, *path.parents))
            and path == path.resolve() and path.parts[-3:] == ("automations", projection["id"], "automation.toml"),
            "canonical native automation TOML source required; no symlink or substitute")
    original_stat = path.stat()
    raw = path.read_bytes()
    stat = path.stat()
    require((original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns)
            == (stat.st_ino, stat.st_size, stat.st_mtime_ns) and len(raw) == stat.st_size,
            "native config changed during readonly observation")
    require(hashlib.sha256(raw).hexdigest() == source.get("source_sha256") and len(raw) == source.get("source_size"),
            "actual readonly native file bytes differ from frozen source")
    fields = _toml_safe_fields(raw)
    require(all(fields.get(key) == value for key, value in projection.items()) and isinstance(fields.get("prompt"), str),
            "actual native config must match every safe scalar and expose prompt bytes")
    prompt = fields["prompt"].encode("utf-8")
    require(prompt and source.get("prompt_utf8") == {"sha256": hashlib.sha256(prompt).hexdigest(), "size": len(prompt)}, "actual native prompt UTF-8 differs")
    observed = w._parse_observed_at(source.get("observed_at"))
    require(observed is not None and viewed <= observed.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp(), "ordered actual local native readback required")
    if mutation is not None:
        require(mutation["started"] <= stat.st_mtime <= observed.timestamp(), "old native config cannot prove this mutation; actual mtime must be after call and before observation")
        if "updated_at" in fields:
            require(int(mutation["started"] * 1000) <= fields["updated_at"] <= int(observed.timestamp() * 1000),
                    "actual native updated_at differs from this mutation")
    native = g._collaboration_native(root, pin(root, source.get("fixed_target_source")))
    thread = native.get("thread", {})
    require(thread.get("id") == target["task_id"] and thread.get("title") == target["title"] and thread.get("cwd") == target["cwd"]
            and thread.get("projectId", target["project_id"]) == target["project_id"], "actual same-project fixed target source required")
    timezone, next_run = fields.get("timezone", NOT_EXPOSED), fields.get("next_run_at", NOT_EXPOSED)
    require(("timezone" not in fields or timezone == "Asia/Kuala_Lumpur")
            and ("next_run_at" not in fields or w._parse_observed_at(next_run) is not None),
            "explicit invalid native time fields are not NOT_EXPOSED")
    require(source.get("native_timezone_field") == timezone and source.get("native_next_run_field") == next_run,
            "native exposed/unexposed time fields must be reported honestly")
    return {**projection, "prompt": fields["prompt"], "targetThreadId": projection["target_thread_id"],
            "projectId": target["project_id"], "cwd": target["cwd"], "timezone": timezone, "nextRunAt": next_run,
            "_created_at_ms": fields.get("created_at"), "_mtime_ns": stat.st_mtime_ns,
            "field_provenance": {"configuration": "actual_native_local_TOML", "projectId": "derived_from_registered_binding_and_actual_fixed_target",
                                 "cwd": "derived_from_registered_binding_and_actual_fixed_target", "timezone": timezone, "nextRunAt": next_run}}


def _card_create_source(root, action, executed, local, policy, args, *, snapshot=None, config=None):
    """A rendered create card needs a genuinely new ID, not matching old state."""
    require(executed["transport"] == "original_session_exec" and action.get("actual_local_no_match"),
            "card create dependency: current original-session local no-match source required")
    source = document(root, action["actual_local_no_match"])
    observed = w._parse_observed_at(source.get("observed_at_utc"))
    policy_at = w._parse_observed_at(policy.get("checked_at"))
    require(source.get("schema") == "actual_native_local_no_match/v1"
            and source.get("task_id") == action["task_id"] and source.get("action_id") == action["action_id"]
            and source.get("directory") == str(Path(document(root, action["local_native_configuration"])["source_path"]).parent.parent)
            and source.get("proposed_name") == args["name"] and source.get("proposed_prompt_sha256") == action["payload_sha256"]
            and source.get("fixed_target_thread_id") == action["target_thread_id"]
            and source.get("candidates") == [] and source.get("read_errors") == []
            and type(source.get("files_examined_for_name_prompt_target")) is int and source["files_examined_for_name_prompt_target"] >= 0
            and source.get("global_native_account_absence_claimed") is False and source.get("native_field_inference_from_cards") is False
            and source.get("match_decision") == "no_local_match_for_proposed_name_prompt_or_fixed_A3_target"
            and observed is not None and policy_at is not None and observed <= policy_at,
            "card create dependency: refreshed exact scoped local no-match required before same policy")
    matches = []
    for index, item in enumerate(executed["items"][:executed["index"]]):
        if item.get("type") != "custom_tool_call_output":
            continue
        calls = [call for call in executed["items"][:index] if call.get("type") == "custom_tool_call"
                 and call.get("name") == "exec" and call.get("call_id") == item.get("call_id")]
        if len(calls) != 1 or "tools.exec_command" not in calls[0].get("input", ""):
            continue
        try:
            value = _session_output(item)
        except w.WorkflowError:
            continue
        if value == source:
            call_index = executed["items"].index(calls[0])
            require(executed["item_times"][call_index] <= observed.timestamp()
                    <= executed["item_times"][index] <= policy_at.timestamp(),
                    "card create dependency: old/prepared no-match cannot replace current original observation before policy")
            matches.append(index)
    policy_indices = []
    for index, item in enumerate(executed["items"][:executed["index"]]):
        if item.get("type") == "custom_tool_call_output":
            try:
                value = _session_output(item)
                if value == policy or (snapshot is not None and _weekly_policy_output_matches(
                        root, snapshot, config, policy, executed, index, value)):
                    policy_indices.append(index)
            except w.WorkflowError:
                continue
    require(len(matches) == len(policy_indices) == 1 and matches[0] < policy_indices[0],
            "card create dependency: exact no-match JSON in original native output before original policy required")
    created = local.get("_created_at_ms")
    require(type(created) is int and int(executed["started"] * 1000) <= created <= int(executed["output_time"] * 1000),
            "card create dependency: actual tool created_at must bind new ID to mutation call/output")



# A source-specific observed persistence difference, not a whitespace rule.
_WEEKLY_PROMPT_SOURCE = {
    "task_id": "fc-20261010-weekly-safe-cleanup-native-enablement-v1",
    "scope": "project:flashcast:weekly-safe-cleanup-native-enablement:v1",
    "action_id": "hq-native-weekly-safe-cleanup-enable-v1",
    "policy_decision_id": "pol-b18670a21481f16f45c2",
    "automation_id": "flash-cast-20-00",
    "source_thread_id": "example-native-0d0689f4e3a4c895",
    "source_turn_id": "example-native-0262040e8f0ae4b4",
    "source_session": "<USER_HOME>/.codex/sessions/2026/10/06/rollout-2026-10-06T00-58-55-example-native-0d0689f4e3a4c895_example-native-9d841697a48914a9.jsonl",
    "prompt": {"path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/prepared/native-weekly-cleanup-prompt-prepared-v1.md",
               "sha256": "00a2a794e4a61d5bb04c062901a4139f2353b154facf86308b94d6246d8f9ac9", "size": 5006},
    "persisted_prompt": {"sha256": "e412600b2e421f80adfef2b26b515c0d683a3e55bec193eee2eec2eec04496b3", "size": 5005},
    "canonical": {"path": "<USER_HOME>/.codex/automations/flash-cast-20-00/automation.toml",
                  "sha256": "8390e44b78f41357e8caf2cda9628de59b9d30870ab5cb9e11f44c17844503d6", "size": 5336,
                  "stat_mtime_ns": 1791671511166072070},
    "decode": {"path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/native-prompt-TOML-scalar-independent-decode-difference-v1.json",
               "sha256": "a2bd60b0bb595e1fd954e908f58db13f2c83edeaf6ad688904228f4d8060f69b", "size": 3312},
    "original_lines": {
        69720: "6689a7efd1dc00f1464664c3b900ee2e12c4a635e63efd25ecdcf83d6fb0f5f1",
        69723: "4279303c081970a77344c733d9ff8ee3c4580472019050992c3b49a41ad97b20",
        69725: "11761df569a8075cdc6e357313f4b0517ee00d8499685d7be718253ed785d1bb",
        69728: "5bbd3cc09fc50a1d473310aea354b61f2bc1ee103fd4c605efb2c4642aa6d347",
        69730: "717b932f18a3b709422c3da8d61212a1b1302c865966c2cf0fa4563a64343733",
        69733: "f33b4289bc94f85662c06b49a38000a895b933b5a570601740c336dde1569f48",
        69735: "ea3eba19a2aeacedf0d1839902f60d441f632368f9099889f22def8db9ce660f",
        69738: "7c2f8332ed7264402556ab62a63591cce87dd7e45da88abcec19267b935d8995",
        69748: "4269ab1a45caf724b7e29ca11154f211fa0a223ce869002a144113fa84b9d0f0"},
}



def _weekly_policy_output_matches(root, snapshot, config, policy, executed, index, value):
    """Exact original CLI projection, with its real command/output and ledger.

    Full-row outputs keep their original equality path. This one historical
    public CLI projection does not expose action/scope; its byte-pinned call
    proves those arguments and the immutable task plus actual ledger agree.
    """
    if value == policy:
        return True
    known = _WEEKLY_PROMPT_SOURCE
    if not isinstance(value, dict) or value.get("decision_id") != known["policy_decision_id"]:
        return False
    snapshot, goal, actual_config, registry = context(root, snapshot)
    require(config == actual_config and snapshot["task_id"] == known["task_id"]
            and goal["authorized_scope"] == [known["scope"]]
            and goal["responsible_assistant"] == "operations-assistant-2"
            and goal["schedule_target_department"] == "operations-assistant-3",
            "CLI projection compatibility requires the exact original weekly goal")
    rows = [_json(line) for line in (Path(root) / w.POLICY_DECISIONS).read_text().splitlines() if line.strip()]
    current = [row for row in rows if row.get("decision_id") == known["policy_decision_id"]]
    expected = config["policy_inputs_only_after_native_exact_no_match"]
    require(len(current) == 1 and current[0] == policy and policy.get("status") == "allow"
            and policy.get("routing_status") == "routing_allowed"
            and all(policy.get(key) == item for key, item in expected.items())
            and policy.get("action_id") == known["action_id"] and policy.get("scope") == known["scope"],
            "actual unique original full policy ledger row and action identity required")
    actual = native_call(root, executed.get("source_pin"), registry["operations"]["chat_binding"], "create",
                         thread_source=executed.get("thread_source_pin"))
    require(actual == executed and actual["transport"] == "original_session_exec"
            and actual["turn_id"] == known["source_turn_id"] and type(index) is int
            and index == 3 < actual["index"], "actual original pre-mutation CLI policy output required")
    source = document(root, executed["source_pin"])
    require(source.get("source_thread_id") == known["source_thread_id"]
            and source.get("source_turn_id") == known["source_turn_id"]
            and source.get("source_session") == known["source_session"]
            and {entry.get("original_line_number"): entry.get("original_line_sha256")
                 for entry in source.get("original_records", [])} == known["original_lines"]
            and _session_output(actual["items"][index]) == value,
            "original CLI command/output UTF-8 hashes and exact public result required")
    public_keys = {"status", "task_id", "approval_id", "decision_id", "reason", "required_receipts", "routing_status",
                   "routing_quarantine_mode", "routing_health_probe_mode", "target_automation_status", "source_project_id",
                   "target_project_id", "target_department", "target_thread_id", "target_thread_title", "target_cwd",
                   "target_sidebar_section_id", "payload_sha256", "message_body_stored", "paid_promotion_enabled",
                   "department", "checked_at"}
    public = {key: policy.get(key) for key in public_keys}
    public.update(run_id="", artifacts=["data/action-policy.json", "logs/approvals/ledger.jsonl", "logs/policy-decisions.jsonl"])
    require(value == public, "the exact original CLI public projection must equal its full ledger fields")
    return True

def _weekly_persisted_prompt(root, snapshot, config, action, executed, verified, local):
    """Prove this original call's exact single-final-LF persistence observation.

    The normal context/call/canonical/view guards remain prerequisites. This
    repeats those provenance readers so a direct evidence maker cannot turn a
    caller-supplied pair of strings into an accepted historical observation.
    """
    expected = _WEEKLY_PROMPT_SOURCE
    snapshot, goal, actual_config, registry = context(root, snapshot)
    require(config == actual_config and snapshot["task_id"] == expected["task_id"]
            and goal["authorized_scope"] == [expected["scope"]]
            and goal["responsible_assistant"] == "operations-assistant-2"
            and goal["schedule_target_department"] == "operations-assistant-3"
            and config["prompt"] == expected["prompt"]
            and action.get("task_id") == expected["task_id"] and action.get("scope") == expected["scope"]
            and action.get("action_id") == expected["action_id"]
            and action.get("action_class") == "automation_create"
            and action.get("policy_decision_id") == expected["policy_decision_id"]
            and action.get("payload_sha256") == expected["prompt"]["sha256"],
            "single-final-LF compatibility is limited to the exact original weekly source")
    fixed = registry["operations"]["chat_binding"]
    actual_executed = native_call(root, action.get("actual_execution"), fixed, "create",
                                  thread_source=action.get("actual_native_thread"))
    actual_verified = native_call(root, action.get("actual_readback"), fixed, "view",
                                  automation_id=expected["automation_id"], thread_source=action.get("actual_native_thread"))
    require(executed == actual_executed and verified == actual_verified
            and executed["transport"] == verified["transport"] == "original_session_exec"
            and executed["turn_id"] == verified["turn_id"] == expected["source_turn_id"]
            and executed["output_index"] < verified["index"]
            and executed["items"][:executed["output_index"]+1] == verified["items"][:executed["output_index"]+1]
            and executed.get("create_receipt") == {"automationId": expected["automation_id"], "mode": "create", "status": "ACTIVE"},
            "single-final-LF compatibility requires the actual original two-text create and same-ID view")
    for frozen in (action["actual_execution"], action["actual_readback"]):
        source = document(root, frozen)
        require(source.get("source_thread_id") == expected["source_thread_id"]
                and source.get("source_turn_id") == expected["source_turn_id"]
                and source.get("source_session") == expected["source_session"]
                and {entry.get("original_line_number"): entry.get("original_line_sha256")
                     for entry in source.get("original_records", [])} == expected["original_lines"],
                "original fixed source lines must retain their exact UTF-8 hashes")
    target = registry[goal["schedule_target_department"]]["chat_binding"]
    actual_local = local_configuration(root, action.get("local_native_configuration"), target,
                                       verified["output_time"], mutation=executed)
    source = document(root, action["local_native_configuration"])
    canonical = expected["canonical"]
    require(local == actual_local and local["id"] == expected["automation_id"]
            and source.get("source_path") == canonical["path"]
            and source.get("source_sha256") == canonical["sha256"] and source.get("source_size") == canonical["size"]
            and source.get("prompt_utf8") == expected["persisted_prompt"]
            and local.get("_mtime_ns") == canonical["stat_mtime_ns"],
            "single-final-LF compatibility requires the unchanged actual canonical file")
    decode = document(root, expected["decode"])
    require(decode.get("schema") == "actual_native_prompt_scalar_decode_comparison/v1"
            and decode.get("task_id") == expected["task_id"] and decode.get("read_only") is True
            and decode.get("actual_canonical_source") == {"path": canonical["path"], "sha256": canonical["sha256"],
                                                         "size": canonical["size"], "stat_mtime_ns": canonical["stat_mtime_ns"]}
            and decode.get("exact_relations", {}).get("actual_create_argument_equals_frozen") is True
            and decode["exact_relations"].get("safe_reader_equals_trusted_scalar") is True
            and decode["exact_relations"].get("trusted_scalar_equals_frozen_without_one_final_LF") is True,
            "unchanged independent decode evidence for the actual canonical scalar required")
    original = w.safe_path(root, config["prompt"]["path"]).read_bytes()
    called = executed["args"].get("prompt", "").encode("utf-8")
    persisted = local["prompt"].encode("utf-8")
    require(called == original and len(original) == expected["prompt"]["size"]
            and hashlib.sha256(original).hexdigest() == expected["prompt"]["sha256"]
            and len(persisted) == expected["persisted_prompt"]["size"]
            and hashlib.sha256(persisted).hexdigest() == expected["persisted_prompt"]["sha256"]
            and original.endswith(b"\n") and not original.endswith(b"\n\n")
            and persisted == original[:-1], "only this exact one-final-LF byte difference is eligible")
    return True

def effects(root, snapshot, producer_pin):
    snapshot, goal, config, registry = context(root, snapshot)
    producer_pin = pin(root, producer_pin)
    box = document(root, producer_pin)
    w.validate_outbox(root, [producer_pin], "operations", snapshot["task_id"])
    proof = box.get("runtime_control", {})
    require(box.get("status") == "completed" and box.get("department") == box.get("sender_department") == "operations"
            and box.get("fixed_chat_task_id") == registry["operations"]["chat_binding"]["task_id"]
            and isinstance(box.get("candidate_version"), str) and bool(box["candidate_version"].strip())
            and box.get("scope") == goal["authorized_scope"][0]
            and proof.get("schema") == "actual_native_control_configuration/v1"
            and proof.get("goal_contract") == snapshot["goal_contract"]
            and proof.get("human_authorization") == goal["authorization_pin"]
            and proof.get("native_routing_binding") == goal["native_routing_binding"]
            and proof.get("delivery_kind") == "complete_native_configuration_result"
            and proof.get("remaining_configuration_actions") == [] and len(proof.get("actions", [])) == 1
            and all(box.get(k) is False for k in ("production_write_allowed", "external_permission_issued", "production_release_eligible")),
            "whole exact configuration result required; prepared/partial/summary is not delivery")
    action = proof["actions"][0]
    action_class = action.get("action_class")
    require(action_class in KINDS and action_class in w.ROUTING_ACTION_CLASSES
            and action_class not in w.EXTERNAL_ACTION_CLASSES, "existing exact routing action only; no new production permit")
    key = "policy_inputs_if_actual_matching_id" if action_class == "automation_update" else "policy_inputs_only_after_native_exact_no_match"
    expected = config.get(key, {})
    require(expected.get("task_id") == snapshot["task_id"] and expected.get("department") == "operations"
            and expected.get("action_class") == action_class and expected.get("scope") == box["scope"], "original frozen action policy identity required")
    for field in ("task_id", "action_id", "action_class", "scope", "payload_sha256", "target_thread_id", "target_department",
                  "source_project_id", "target_project_id", "target_cwd", "target_thread_title", "target_sidebar_section_id"):
        require(action.get(field) == expected.get(field), "exact original action/target/payload required: " + field)
    raw_rows = (Path(root) / w.POLICY_DECISIONS).read_text().splitlines()
    rows = [_json(raw) for raw in raw_rows if raw.strip()]
    policies = [row for row in rows if row.get("decision_id") == action.get("policy_decision_id")]
    require(len(policies) == 1, "one original actual action policy decision required")
    policy = policies[0]
    require(policy.get("status") == "allow" and policy.get("routing_status") == "routing_allowed"
            and all(policy.get(k) == action[k] for k in expected if k in action)
            and action["payload_sha256"] == config["prompt"]["sha256"], "actual exact allowed native routing policy required")
    local_pin = action.get("local_native_configuration")
    local_id = document(root, local_pin).get("nonsecret_exact_scalar_projection", {}).get("id") if local_pin else None
    executed = native_call(root, action.get("actual_execution"), registry["operations"]["chat_binding"], KINDS[action_class],
                           thread_source=action.get("actual_native_thread"))
    verified = native_call(root, action.get("actual_readback"), registry["operations"]["chat_binding"], "view",
                           automation_id=local_id, thread_source=action.get("actual_native_thread"))
    args, changed, started = executed["args"], executed["configuration"], executed["started"]
    view_args, readback, viewed = verified["args"], verified["configuration"], verified["output_time"]
    target = registry[goal["schedule_target_department"]]["chat_binding"]
    local = local_configuration(root, local_pin, target, viewed, mutation=executed) if local_pin else None
    create_card = changed is None and action_class == "automation_create"
    require((changed is not None and readback is not None) or local is not None,
            "automation card alone is not a complete configuration; exact local source required")
    if local is not None:
        for exposed in (changed, readback):
            if exposed is not None:
                require(all(exposed.get(key) == local.get(key) for key in ("id", "name", "prompt", "rrule", "status", "kind", "targetThreadId")),
                        "native returned fields disagree with actual local configuration")
        changed = local if changed is None else changed
        readback = local if readback is None else readback
    policy_at = w._parse_observed_at(policy.get("checked_at"))
    # HQ may already be active when policy is checked. A turn start is not a
    # call timestamp: bind the earlier original policy output and item order.
    ordered_policy = []
    for index, item in enumerate(executed["items"][:executed["index"]]):
        if item.get("type") == "functionCallOutput" and item.get("namespace") == "functions" and item.get("name") == "exec":
            output = item.get("output", {})
            if output.get("truncated") is False and output.get("isError", False) is False:
                try:
                    value = _json(output.get("text"))
                except w.WorkflowError:
                    continue
                if value == policy or _weekly_policy_output_matches(root, snapshot, config, policy, executed, index, value):
                    ordered_policy.append(item)
        elif item.get("type") == "custom_tool_call_output" and item.get("call_id"):
            prior = [call for call in executed["items"][:index] if call.get("type") == "custom_tool_call"
                     and call.get("name") == "exec" and call.get("call_id") == item["call_id"]]
            if len(prior) == 1:
                try:
                    value = _session_output(item)
                except w.WorkflowError:
                    continue
                if value == policy or _weekly_policy_output_matches(root, snapshot, config, policy, executed, index, value):
                    ordered_policy.append(item)
    require(len(ordered_policy) == 1 and executed["turn_id"] == verified["turn_id"]
            and executed["output_index"] < verified["index"]
            and executed["items"][:executed["output_index"]+1] == verified["items"][:executed["output_index"]+1],
            "original policy then one mutation then exact view call order required; no unknown retry")
    require(policy_at is not None and policy_at.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp() and started <= viewed
            and isinstance(args.get("prompt"), str)
            and args["prompt"].encode("utf-8") == w.safe_path(root, config["prompt"]["path"]).read_bytes()
            and args.get("kind") == "heartbeat" and args.get("targetThreadId") == expected["target_thread_id"]
            and args.get("status") == expected.get("target_automation_status") == "ACTIVE"
            and args.get("rrule") and args.get("name"), "actual original exact native mutation args and ordered readback required")
    require(executed["transport"] != "original_session_exec" or policy_at.timestamp() <= started,
            "original policy must precede raw native mutation time")
    if config.get("local_native_configuration_dedup"):
        frozen_query = document(root, config["local_native_configuration_dedup"])
        require(frozen_query.get("proposed_name") == args["name"]
                and frozen_query.get("proposed_prompt_sha256") == config["prompt"]["sha256"]
                and frozen_query.get("fixed_target_thread_id") == args["targetThreadId"], "actual mutation must preserve original frozen dedup name/prompt/target")
    if create_card:
        _card_create_source(root, action, executed, local, policy, args, snapshot=snapshot, config=config)
    if executed.get("create_receipt") is not None:
        require(local is not None and executed["create_receipt"]["automationId"] == local["id"],
                "actual returned create ID must equal canonical and exact view ID")
    identifier = changed.get("id")
    require(isinstance(identifier, str) and bool(identifier) and view_args == {"mode": "view", "id": identifier}
            and readback.get("id") == identifier and (action_class != "automation_update" or args.get("id") == identifier),
            "exact original native automation id and readback required")
    for key in ("name", "prompt", "rrule", "status", "kind", "targetThreadId"):
        equal = readback.get(key) == args.get(key)
        if not equal and key == "prompt" and local is not None:
            equal = _weekly_persisted_prompt(root, snapshot, config, action, executed, verified, local)
        require(equal, "actual native configuration differs: " + key)
    weekly_rule(args["rrule"])
    require(readback.get("projectId") == target["project_id"] and readback.get("cwd") == target["cwd"]
            and (readback.get("timezone") == config["requested_schedule"]["timezone"]
                 or (local is not None and readback.get("timezone") == NOT_EXPOSED)),
            "actual native target and exposed timezone required; derived fields need exact sources")
    if not (local is not None and readback.get("nextRunAt") == NOT_EXPOSED):
        next_run = w._parse_observed_at(readback.get("nextRunAt"))
        require(next_run is not None, "exposed native next run time must be valid")
        native_local = next_run.astimezone(ZoneInfo(config["requested_schedule"]["timezone"]))
        schedule = config["requested_schedule"]
        require(native_local.strftime("%A") == schedule["weekday"] and native_local.strftime("%H:%M") == schedule["local_time"]
                and native_local.second == 0 and native_local.microsecond == 0
                and next_run.timestamp() > viewed, "actual native schedule and future next run differ")
    return box, proof, viewed


def completion(root, request, fixed_id):
    import goal_delivery_runtime as g
    snapshot = w.read_json(w.snapshot_path(root, request["task_id"]))
    producer_pin = w.file_digest(root, request.get("outbox_path") or request.get("outbox", {}).get("path", ""))
    box, proof, viewed = effects(root, snapshot, producer_pin)
    _, goal, _, registry = context(root, snapshot)
    require(fixed_id == registry["operations"]["chat_binding"]["task_id"]
            and request.get("source_thread_id") == fixed_id, "original fixed OPS result source required")
    native = g._collaboration_native(root, pin(root, request.get("actual_native_completion")))
    reply_pin = pin(root, request.get("visible_reply"))
    raw = w.safe_path(root, reply_pin["path"]).read_bytes()
    turns = [turn for turn in native.get("turns", []) if turn.get("id") == request.get("source_turn_id")]
    require(native.get("thread", {}).get("id") == fixed_id
            and native["thread"].get("cwd") == str(Path(root).resolve())
            and native["thread"].get("title") == registry["operations"]["chat_binding"]["title"] and len(turns) == 1,
            "actual original whole-control delivery thread/turn required")
    messages = [item for item in turns[0].get("items", []) if item.get("type") == "agentMessage"
                and item.get("id") == request.get("source_message_id")
                and item.get("phase") in {"commentary", "final_answer"} and isinstance(item.get("text"), str)
                and item["text"].encode("utf-8") == raw]
    observed = w._parse_observed_at(request.get("reply_observed_at"))
    started = turns[0].get("startedAt")
    require(not turns[0].get("error") and turns[0].get("status") in {"inProgress", "completed"}
            and len(messages) == 1 and raw.strip() and request.get("source_reply_sha256") == reply_pin["sha256"]
            and observed is not None and type(started) in {int, float}
            and 0 < started <= observed.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp()
            and viewed <= observed.timestamp(), "original ordered complete-result UTF-8 required")
    text = messages[0]["text"]
    delivered = _json(text)
    expected = {"schema": "actual_native_control_complete/v1", "status": MARKER,
                "task_id": snapshot["task_id"], "candidate_version": box["candidate_version"],
                "outbox": producer_pin, "scope": box["scope"], "runtime_control": proof,
                "remaining_configuration_actions": [], "production_write_allowed": False,
                "external_permission_issued": False}
    require(delivered == expected,
            "whole configuration completion must bind task/version/final outbox SHA; bare commentary or ACK rejected")
    result = {"source_turn_id":turns[0]["id"],"source_message_id":messages[0]["id"],"source_thread_id":fixed_id,
            "source_reply_sha256":reply_pin["sha256"],"reply_observed_at":request["reply_observed_at"],
            "actual_native_completion":request["actual_native_completion"],"visible_reply":reply_pin,
            "runtime_control_complete":True,"professional_completed_final_rule_changed":False}
    local_pin = proof["actions"][0].get("local_native_configuration")
    if local_pin:
        local_source = document(root, local_pin)
        result["native_configuration_provenance"] = {
            "source": local_pin, "configuration_fields": "actual_native_local_TOML",
            "projectId": "derived_from_registered_binding_and_actual_fixed_target",
            "cwd": "derived_from_registered_binding_and_actual_fixed_target",
            "timezone": local_source["native_timezone_field"], "nextRunAt": local_source["native_next_run_field"],
            "schedule_context_timezone": "Asia/Kuala_Lumpur"}
    return result


def assigned_assistant(root, snapshot, role):
    """Reuse the exact original ordinary policy/send/ACK reader, without granting methods."""
    _, goal, _, _ = context(root, snapshot)
    from technical_review_backup import _qualified_responsibility
    require(role == goal["responsible_assistant"] and role != "operations"
            and _qualified_responsibility(root, role, goal, snapshot["task_id"]),
            "actual original independent assistant policy/send/ACK responsibility required")


def received_candidate(root, snapshot, plan, receipts=None, *, require_intake=False):
    context(root, snapshot)
    require(plan.get("producer_department") == "operations" and plan.get("action_class") == "runtime_control"
            and plan.get("scope") == snapshot["goal_delivery"]["authorized_scope"][0], "exact runtime-control review plan required")
    if receipts is None:
        from scoped_candidate_adoption import _receipts
        receipts = _receipts(root, snapshot["task_id"])
    boxes = [row for row in receipts if row.get("receipt_type") == "outbox_received" and row.get("department") == "operations"
             and plan.get("candidate") in row.get("evidence", [])]
    require(boxes, "actual frozen OPS result receipt required before review")
    candidates = []
    for frozen in boxes[-1].get("evidence", []):
        data = document(root, frozen)
        if data.get("schema") == "actual_native_control_delivery/v1":
            candidates.append(data)
    require(len(candidates) == 1 and candidates[0].get("outbox") == plan.get("candidate"),
            "one actual full configuration native delivery proof required")
    source = candidates[0]
    require(source.get("task_id") == snapshot["task_id"] and source.get("sender_department") == "operations",
            "delivery must preserve original task and OPS executor")
    if require_intake:
        from scoped_candidate_adoption import _committed
        assigned_assistant(root, snapshot, snapshot["goal_delivery"]["responsible_assistant"])
        rows = [row for row in w._result_handoff_rows(root, snapshot["task_id"])
                if row.get("sender_department") == "operations" and row.get("outbox") == plan["candidate"]]
        queues = [row for row in rows if row.get("event") == "notification_queued"]
        intakes = [row for row in rows if row.get("event") == "controller_received"]
        role = snapshot["goal_delivery"]["responsible_assistant"]
        require(len(queues) == len(intakes) == 1 and intakes[0].get("coordinator_role") == role
                and intakes[0].get("responsible_assistant") == role and intakes[0].get("intake_mode") == "queue"
                and type(intakes[0].get("coordination_fence")) is int
                and intakes[0].get("source_reply_sha256") == queues[0].get("source_reply_sha256")
                == source.get("source_reply_sha256"), "actual unique frozen queue and independent fenced intake required")
        _committed(root, intakes[0])
    return completion(root, source, w.department_registry(root)["operations"]["chat_binding"]["task_id"])


def independent_verdict(root, snapshot, plan, binding, box, receipt, reviewer_pin):
    """Actual native independent whole-scope verdict, with the existing ACK gates."""
    import goal_delivery_runtime as g
    _, goal, _, registry = context(root, snapshot)
    role = goal["responsible_assistant"]
    require(role != "operations" and role == receipt.get("department") == plan.get("reviewer_department"),
            "original sole functional assistant required; no producer review")
    sources = [document(root, frozen) for frozen in receipt.get("evidence", []) if frozen != reviewer_pin]
    sources = [source for source in sources if source.get("schema") == "actual_native_control_acceptance/v1"]
    require(len(sources) == 1, "one actual native independent full-control acceptance source required")
    source = sources[0]
    native = g._collaboration_native(root, pin(root, source.get("actual_native_completion")))
    reply = pin(root, source.get("visible_reply"))
    raw = w.safe_path(root, reply["path"]).read_bytes()
    fixed = registry[role]["chat_binding"]
    require(native.get("thread", {}).get("id") == fixed["task_id"]
            and native["thread"].get("cwd") == fixed["cwd"] and native["thread"].get("title") == fixed["title"],
            "actual independent fixed reviewer source required")
    turns = [turn for turn in native.get("turns", []) if turn.get("id") == source.get("source_turn_id")]
    require(len(turns) == 1 and not turns[0].get("error"), "original unique nonerror reviewer turn required")
    messages = [item for item in turns[0].get("items", []) if item.get("type") == "agentMessage"
                and item.get("id") == source.get("source_message_id") and item.get("phase") in {"commentary", "final_answer"}
                and isinstance(item.get("text"), str) and item["text"].encode("utf-8") == raw]
    observed = w._parse_observed_at(source.get("reply_observed_at"))
    verdict_at = w._parse_observed_at(receipt.get("created_at"))
    require(len(messages) == 1 and observed is not None and verdict_at is not None
            and type(turns[0].get("startedAt")) in {int, float}
            and 0 < turns[0]["startedAt"] <= observed.timestamp() <= verdict_at.timestamp(),
            "original ordered independent UTF-8 verdict required")
    expected = {"schema": "actual_native_control_verdict/v1", "task_id": snapshot["task_id"],
                "candidate_version": plan["candidate_version"], "producer_outbox": plan["candidate"],
                "reviewer_outbox": reviewer_pin, "review_plan": binding["pin"],
                "reviewer": role, "verdict": receipt["verdict"], "goal_acceptance": box["goal_acceptance"],
                "production_write_allowed": False, "external_permission_issued": False}
    require(_json(raw.decode("utf-8")) == expected, "actual native verdict must bind complete goal and exact final outboxes/plan")
