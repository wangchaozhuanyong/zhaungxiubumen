"""Exact current owner-approved brand source; registration never issues a permit.

The existing per-action WEB preflight, native facts, CI, time, single-use and
effect checks remain the execution boundary. This codec does not edit contracts.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import department_autonomy as a
import workflow_control as w

SCHEMA = 'owner-reviewed-brand-WEB-source/v1'
TASK = 'fc-20261021-brand-main-name-preservation-and-dual-query-v1'
SCOPE = 'project:flashcast:brand-main-name-preservation-dual-query:20261021:v1'
OWNER = 'content-organic-website'
ROLE = 'designated-development'
HEAD = 'eeadbbb2c4e53113c28aefe995b87cc2b07e7508'
BASE = 'fba60220461d896a0c264a5a793d8c73cb688768'
TREE = '2af7fd3f8c13cf385171310967da1151aa981430'
ROOT_PACKAGE = 'logs/handoffs/2026-10-31-brand-design-owner-approved-execution-v1'
NATIVE_DIR = ROOT_PACKAGE + '/operations/local-source-repair/'
SITE_REPORT = '<WEBSITE_PROJECT_ROOT>/reports/brand-design-alias-consistency-20261031-v1/'
# These pins identify actual first-party observations and exact reviewed bytes,
# not a caller/role allowlist or a general authority renewal.
PINS = {}
PATHS = {
    'functions/_middleware.ts', 'src/components/scheme-a/SchemeAHome.tsx',
    'src/components/scheme-a/SchemeAHome.test.tsx', 'src/lib/middlewareChineseBrand.integration.test.ts',
}

def need(value, message):
    a.require(value, 'reviewed brand WEB source: ' + message)

def pin(root, name):
    path, sha, size = PINS[name]
    absolute = Path(path) if Path(path).is_absolute() else Path(root) / path
    raw = w.validation_bytes(absolute)
    need(not absolute.is_symlink() and hashlib.sha256(raw).hexdigest() == sha
         and (size is None or len(raw) == size), 'unchanged actual ' + name + ' bytes')
    return {'path': path, 'sha256': sha, 'size': len(raw)}

def read(root, frozen, binding):
    from professional_web_execution import _external_bytes
    if Path(frozen['path']).is_absolute():
        return _external_bytes(frozen, binding)
    need(w.file_digest(root, frozen['path']) == frozen, 'exact same-project source pin')
    return w.validation_bytes(w.safe_path(root, frozen['path']))

def identity(page, binding, external=False):
    key = 'thread_id' if external else 'task_id'
    need(all(page.get('thread', {}).get(k) == binding[v] for k, v in
             {'id': key, 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items()),
         'actual original fixed native identity')

def turn(page, turn_id, complete=True):
    rows = [t for t in page.get('turns', []) if t.get('id') == turn_id]
    need(len(rows) == 1 and not rows[0].get('error') and
         (rows[0].get('status') == 'completed' if complete else
          rows[0].get('status') in {'inProgress', 'completed'}), 'one actual original native turn')
    return rows[0]

def command(t, command_id):
    rows = [x for x in t.get('items', []) if x.get('id') == command_id]
    need(len(rows) == 1, 'one actual native command')
    c = rows[0]
    need(c.get('type') == 'commandExecution' and c.get('status') == 'completed'
         and c.get('exitCode') == 0 and c.get('output', {}).get('truncated') is False,
         'complete successful native command output')
    return c, w._completion_execution_output(c)

def validate(root, snapshot, item):
    import goal_delivery_runtime as g
    import professional_web_execution as web
    a.authority(root)
    need(set(item) == {'schema', 'task_id', 'scope', 'goal_contract', 'sources'}
         and item.get('schema') == SCHEMA and item.get('task_id') == snapshot.get('task_id') == TASK
         and item.get('scope') == SCOPE and item.get('goal_contract') == snapshot.get('goal_contract'),
         'exact existing task/scope/contract, never another task')
    frozen = a.document(root, snapshot['goal_contract']); goal = snapshot['goal_delivery']
    need(snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused'}
         and goal.get('primary_owner') == OWNER and SCOPE in goal.get('authorized_scope', [])
         and all(goal.get(k) == frozen.get(k) for k in
                 ('parent_task_id', 'primary_owner', 'producer_departments', 'authorized_scope', 'human_authorization', 'collaboration_scopes')),
         'unchanged open original owner/producers/authorization and collaboration')
    need(goal.get('authorization_pin') == w.file_digest(root, frozen['human_authorization']['evidence_path']),
         'unchanged original historical human evidence')
    binding = g._collaboration_binding(root, snapshot, ROLE)
    need(binding and binding.get('project_id') != a.PROJECT and ROLE not in goal['producer_departments']
         and {'sender_department': OWNER, 'target_department': ROLE, 'scope': SCOPE} in frozen['collaboration_scopes']
         and binding.get('runtime_goal_authorization_required') is True
         and binding.get('generic_cross_project_access_allowed') is False, 'original declared external executor only')
    expected = {name: pin(root, name) for name in PINS}
    need(item['sources'] == expected, 'all actual immutable reviewed inputs; no substituted observations')
    pages = {name: g._native_document(root, expected[name]) for name in ('owner_native', 'WEB_native', 'C1_native')}
    registry = w.department_registry(root); hq = registry['operations']['chat_binding']
    identity(pages['owner_native'], hq); identity(pages['WEB_native'], binding, True)
    identity(pages['C1_native'], registry[OWNER]['chat_binding'])
    ht = turn(pages['owner_native'], 'example-native-997c8c9b9904efd2', False)
    wt = turn(pages['WEB_native'], 'example-native-5bc59e4d4926ee84')
    ct = turn(pages['C1_native'], 'example-native-51a1e68d44452178')
    humans = [m for m in ht['items'] if m.get('type') == 'userMessage'
              and m.get('id') == 'example-native-7db7fa862927fe84']
    instruction = json.loads(read(root, expected['owner_instruction'], binding))
    need(len(humans) == 1, 'one actual owner message')
    full_human = ''.join(c.get('text', '') for c in humans[0]['content'] if c.get('type') == 'text')
    # Preserve the complete native message. The saved plan deliberately omits
    # only the app-labelled ambient browser context preceding My request.
    ambient, separator, actual_request = full_human.partition('## My request:\n')
    need(separator and ambient.strip().startswith('<in-app-browser-context source="ambient-ui-state">')
         and ambient.strip().endswith('</in-app-browser-context>')
         and instruction['actual_user_plan_text'] == actual_request
         and instruction['actual_user_plan_text'].startswith('PLEASE IMPLEMENT THIS PLAN:')
         and all(x in instruction['actual_user_plan_text'] for x in ('闪铸设计', '原网站开发', '发布', '独立验收')),
         'actual full current human plan, not an assistant quotation or old permission')
    need(ht['startedAt'] <= wt['startedAt'] <= wt['completedAt'] <= ct['completedAt'],
         'actual human, WEB production of candidate and independent review chronology')
    echoes = []
    for message in wt['items']:
        if message.get('type') != 'functionCallOutput': continue
        try: xml = ET.fromstring(message.get('output', {}).get('text', ''))
        except ET.ParseError: continue
        body = xml.findtext('input') or ''
        if xml.tag == 'codex_delegation' and xml.findtext('source_thread_id') == hq['task_id'] and all(
                x in body for x in (TASK, expected['owner_instruction']['sha256'])):
            echoes.append(message)
    need(len(echoes) == 1, 'actual original HQ-to-WEB receipt of this human plan')
    _, raw = command(wt, 'exec-329bd37f-5bea-4225-9038-ebb86aa0ffcb')
    need(json.loads(raw)['candidate_manifest'] == expected['candidate'], 'actual WEB emitted candidate manifest')
    _, raw = command(wt, 'exec-e475e090-2212-4d2b-908c-e1535b877422')
    need(json.loads(raw)['result'] == expected['WEB_result'], 'actual WEB emitted complete result')
    _, raw = command(ct, 'exec-034e12f4-f040-4df9-a28c-cb001d53b48d')
    need(expected['C1_review']['sha256'].encode() in raw
         and b'PASS_LOCAL_SCOPED_BRAND_ASSOCIATION_ONLY' in read(root, expected['C1_review'], binding),
         'actual independent C1 emitted scoped review')
    tested, raw = command(ct, 'exec-b0250b97-c922-4160-a538-cf6ecf75c21f')
    need('vitest' in tested['command'] and b'34 passed' in raw, 'actual independent candidate tests')
    meta = json.loads(read(root, expected['candidate'], binding))
    need(meta['task_id'] == TASK and meta['department'] == ROLE and meta['head'] == HEAD
         and meta['parent'] == meta['base'] == BASE and meta['tree'] == TREE, 'exact reviewed Git lineage')
    worktree = Path(meta['worktree']).resolve()
    need(worktree.is_relative_to(Path(binding['cwd']).resolve()) and worktree.parent.name == '.worktrees',
         'original isolated website worktree')
    ctx = {'root': str(Path(root).resolve()), 'task': TASK, 'scope': SCOPE, 'owner': OWNER, 'role': ROLE,
           'binding': binding, 'contract': snapshot['goal_contract'], 'decision': expected['owner_instruction'],
           'authorization': expected['owner_instruction'], 'worktree': str(worktree),
           'site': str(worktree.parent.parent), 'branch': meta['branch'], 'commit': HEAD, 'base': BASE,
           'tree': TREE, 'paths': {f['path']: f['sha256'] for f in meta['files']},
           'code_only_release': True, 'reviewed_brand_code': True, 'allowed_operations': web.CODE_OPS,
           'repository': 'example-owner/example-website', 'repository_id': 1248188229,
           'actor_id': 276684684, 'prefix': TASK + '-owner-reviewed-brand',
           'pages_scope': 'company.example:pages:production',
           'backup': expected['candidate'], 'rollback': expected['candidate']}
    need(set(ctx['paths']) == PATHS and len(meta['files']) == len(PATHS)
         and set(web.git(ctx, 'diff', '--name-only', BASE, HEAD).decode().splitlines()) == PATHS
         and web.git(ctx, 'show', '-s', '--format=%H %P %T', HEAD).decode().strip() == ' '.join([HEAD, BASE, TREE]),
         'complete exact four-path candidate and actual Git objects')
    need(web.git(ctx, 'config', '--get', 'remote.origin.url').decode().strip() in
         {'https://github.com/' + ctx['repository'] + '.git', 'https://github.com/' + ctx['repository'],
          'user-3de132cd98be@example.invalid:' + ctx['repository'] + '.git'}, 'original repository only')
    for f in meta['files']:
        raw = web.git(ctx, 'show', HEAD + ':' + f['path'])
        need(len(raw) == f['size'] and hashlib.sha256(raw).hexdigest() == f['sha256']
             and web.git(ctx, 'ls-tree', HEAD, '--', f['path']).decode().strip() == f['git_tree_entry'],
             'exact actual Git mode/blob/size/SHA')
    for cmd, expected_value in [('exec-4327fbe9-80ba-4561-8057-14a4d8b20a29', {'id': ctx['actor_id'], 'login': 'example-owner'}),
                                ('exec-82dc29a5-61cc-4ebe-b55a-6751334117dc', {'id': ctx['repository_id'], 'full_name': ctx['repository']})]:
        _, raw = command(wt, cmd); need(json.loads(raw) == expected_value, 'actual original repo/actor observation')
    effects = web._patch_effect(web._delta(ctx, BASE, HEAD))
    need(web._patch_effect(web._patch_delta(web._external_bytes(meta['forward'], binding))) == effects
         and web._patch_effect(web._patch_delta(web._external_bytes(meta['inverse'], binding))) ==
         {p: (added, removed) for p, (removed, added) in effects.items()}, 'actual own forward/inverse effects')
    web._external_bytes(meta['source_build_archive'], binding)
    need(not w.validate_workflow_events(root, TASK), 'intact append-only original workflow')
    return ctx

def readonly_return(root, snapshot, request):
    """The original C1 already read/reviewed this exact candidate via HQ.

    Return only that knowledge; never queue a duplicate WEB business message.
    Other external messages still require their own registered transport source.
    """
    if (snapshot.get('task_id') != TASK or request.get('sender_department') != ROLE
            or request.get('action_class') != 'thread_message'):
        return None
    import professional_web_execution as web
    sources = web.records(root, TASK)
    rows = [x for x in sources if x.get('reviewed_brand_code')]
    if not rows: return None
    need(len(rows) == 1, 'one unambiguous current reviewed brand source')
    ctx = rows[0]; original = a.document(root, pin(root, 'return_request'))
    keys = ('task_id', 'scope', 'sender_department', 'target_department', 'action_id', 'action_class',
            'source_project_id', 'target_project_id', 'target_thread_id', 'target_thread_title',
            'target_cwd', 'target_sidebar_section_id', 'payload', 'payload_sha256',
            'assignment_record_required', 'delivery_mode')
    need(set(request) <= set(original) | {'authorization_changes'}
         and all(request.get(k) == original.get(k) for k in keys)
         and not any(request.get(k) for k in ('approval_id', 'consume_approval', 'execution_request', 'authorization_changes')),
         'only exact already-reviewed return; no new assignment, recipient or platform permission')
    need(w.file_digest(root, request['payload']['path']) == request['payload']
         and request['payload_sha256'] == request['payload']['sha256'], 'unchanged exact return bytes')
    return {**a.authority(root), 'source': request['payload'], 'report': pin(root, 'candidate'), 'scope': SCOPE,
            'sender_department': ROLE, 'target_department': OWNER, 'readonly_collaboration_return': True,
            'actual_owner_knowledge_proven': True, 'formal_result_received_proven': False,
            'business_producer_added': False, 'external_permission_issued': False,
            'source_registration': ctx['registration'], 'knowledge_basis': pin(root, 'C1_review')}
