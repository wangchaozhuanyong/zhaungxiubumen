"""Read actual WEB thread/inventory history. Evidence only; no policy or dispatch."""
from pathlib import Path
import datetime as dt,json
import workflow_control as w
import department_autonomy as a
TASK='fc-20261011-english-kitchen-actual-publication-goal-v1'
ROLE='designated-development'

def _desktop_live_turn(turn, binding, anchor_id, now_ms, *, compact=False):
    """Authenticate a recent self-read saved by the original desktop tool."""
    items = turn.get('items', [])
    anchors = [i for i, item in enumerate(items) if item.get('id') == anchor_id]
    if (len(anchors) != 1 or turn.get('completedAt') is not None
            or type(turn.get('startedAt')) not in (int, float)):
        return False
    after = items[anchors[0] + 1:]
    reads = [item for item in after
             if item.get('type') == 'mcpToolCall' and item.get('server') == 'codex_app'
             and item.get('tool') == 'read_thread'
             and isinstance(item.get('arguments'), dict)
             and item['arguments'].get('threadId') == binding['thread_id']
             and (not compact or item['arguments'].get('includeOutputs') is False)]
    if not reads:
        return False
    read = reads[-1]
    start, end = read.get('startedAtMs'), read.get('completedAtMs')
    anchor_time = items[anchors[0]].get('completedAtMs')
    args = read['arguments']
    if (read.get('status') != 'completed' or read.get('error')
            or args.get('hostId') != binding['host_id'] or args.get('turnLimit') != 1 or args.get('cursor')
            or type(anchor_time) is not int or type(start) is not int or type(end) is not int
            or not turn['startedAt'] * 1000 <= anchor_time <= start <= end <= now_ms <= end + 120000):
        return False
    result = read.get('result')
    if not isinstance(result, dict) or result.get('isError', False) is not False or result.get('structuredContent') is not None:
        return False
    content = result.get('content')
    if (not isinstance(content, list) or len(content) != 1
            or not isinstance(content[0], dict) or content[0].get('type') != 'text'):
        return False
    try:
        page = json.loads(content[0]['text'])
        thread, turns = page['thread'], page['turns']
        return (thread['id'] == binding['thread_id'] and thread['hostId'] == binding['host_id']
                and thread['title'] == binding['title'] and thread['cwd'] == binding['cwd']
                and thread['kind'] == 'codex' and thread['status']['type'] == 'active'
                and thread.get('projectId') in (None, binding['project_id'])
                and len(turns) == 1 and turns[0]['id'] == turn['id']
                and turns[0]['status'] == 'inProgress' and not turns[0].get('error')
                and turns[0].get('completedAt') is None and turns[0]['startedAt'] == turn['startedAt'])
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def read_native_turn(root, binding, turn_id, anchor_id):
    import department_event_dispatcher as d
    rpc = d.RPC([d.native_queue_capability(Path(root)), 'app-server', '--listen', 'stdio://'])
    try:
        thread = rpc.call('thread/read', {'threadId': binding['thread_id'], 'includeTurns': False})['thread']
        page = rpc.call('thread/turns/list', {'threadId': binding['thread_id'], 'limit': 3,
                        'sortDirection': 'desc', 'itemsView': 'full'})
    finally:
        rpc.close()
    a.require(thread.get('id') == binding['thread_id'] and thread.get('name') == binding['title']
              and Path(thread.get('cwd', '')).resolve() == Path(binding['cwd']).resolve()
              and thread.get('projectId') in (None, binding['project_id']),
              'EN2 preview: current original WEB thread identity differs')
    turns = page.get('data', [])
    matches = [turn for turn in turns if turn.get('id') == turn_id]
    a.require(len(matches) == 1 and not matches[0].get('error'), 'EN2 preview: one actual WEB turn required')
    turn = matches[0]
    if turn.get('status') in ('completed', 'inProgress'):
        return turn
    now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
    # A history-only server can project a still-open turn as interrupted.
    # Require the latest exact turn and a desktop observation after the anchor.
    a.require(turn is turns[0] and turn.get('status') == 'interrupted'
              and _desktop_live_turn(turn, binding, anchor_id, now_ms),
              'EN2 preview: fresh same-turn desktop read_thread after the required call')
    return turn


def attest(root,turn_id,call_id):
    import professional_web_execution as web
    root=Path(root).resolve();sources=web.records(root,TASK)
    a.require(len(sources)==1 and sources[0].get('current_owner_reviewed_release') is True and sources[0].get('role')==ROLE,'EN2 preview: one authenticated current original WEB source required')
    return _attest_reviewed_source(root,sources[0],turn_id,call_id)


def _attest_reviewed_source(root,ctx,turn_id,call_id):
    b=ctx['binding']
    a.require(ctx.get('registration',{}).get('sha256')=='f52a048ab07e02f2e90984b5a40a31b0f52faf3f9f7164ddacb578f58871ecb3'
              and ctx.get('task')==TASK and ctx.get('repository')=='example-owner/example-website'
              and b.get('thread_id')=='<LOCAL_THREAD_ID>'
              and b.get('project_id')=='<LOCAL_PROJECT_ID>'
              and b.get('cwd')=='<WEBSITE_PROJECT_ROOT>' and b.get('host_id')=='local',
              'EN2 preview: exact original source and fixed WEB project required')
    a.require(isinstance(turn_id,str) and turn_id and isinstance(call_id,str) and call_id,'EN2 preview: actual WEB inventory call IDs required')
    turn=read_native_turn(root,b,turn_id,call_id)
    matches=[x for x in turn.get('items',[]) if x.get('id')==call_id];a.require(len(matches)==1,'EN2 preview: actual original WEB inventory call required');call=matches[0]
    a.require(call.get('type')=='mcpToolCall' and call.get('server')=='codex_app' and call.get('tool')=='list_threads' and call.get('status')=='completed' and not call.get('error') and type(call.get('startedAtMs')) is int and type(call.get('completedAtMs')) is int and call['startedAtMs']<=call['completedAtMs'],'EN2 preview: completed first-party inventory call required')
    now=dt.datetime.now(dt.timezone.utc).timestamp()*1000;a.require(0<=now-call['completedAtMs']<=300000 and type(turn.get('startedAt')) in (int,float) and call['startedAtMs']>=turn['startedAt']*1000,'EN2 preview: fresh same-turn native inventory required')
    result=call.get('result');a.require(isinstance(result,dict) and result.get('isError',False) is False and result.get('structuredContent') is None,'EN2 preview: complete native inventory result required')
    content=result.get('content');a.require(isinstance(content,list) and len(content)==1 and content[0].get('type')=='text' and isinstance(content[0].get('text'),str),'EN2 preview: native inventory text required')
    inventory=json.loads(content[0]['text']);items=inventory.get('threads',[])+inventory.get('pinnedThreads',[]);hits=[x for x in items if x.get('id')==b['thread_id']]
    a.require(len(hits)==1 and all(hits[0].get(k)==b[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd','projectId':'project_id','hostId':'host_id'}.items()) and hits[0].get('kind')=='codex','EN2 preview: actual camelCase inventory must bind same WEB project')
    return {'state':'WEB_IDENTITY_ATTESTED_ONLY','thread_id':b['thread_id'],'project_id':b['project_id'],'turn_id':turn_id,'inventory_call_id':call_id,'inventory_completed_at_ms':call['completedAtMs'],'source_registration':ctx['registration'],'permission_issued':False,'dispatch_allowed':False}
