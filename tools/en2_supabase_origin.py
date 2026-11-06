"""Read-only EN2 MCP transcript shape checker. It does not authenticate a file's origin."""
from pathlib import Path
import argparse
import datetime as dt
import json
import re
import workflow_control as w

TASK='fc-20261011-english-kitchen-actual-publication-goal-v1'
ACTION='save-kitchen-english-two-fields-v1'
VERSION='publishing-english-kitchen-en2-actual-publication-v1-20261011'
PROJECT='exampleproject000000'
RECORD='ce4156db-9034-42c8-ba29-b35724ea7d6d'
ROW_SQL="SELECT clock_timestamp()::text AS server_observed_at, row_to_json(s)::text AS raw_full_record FROM public.services AS s WHERE s.id::text='ce4156db-9034-42c8-ba29-b35724ea7d6d' AND s.slug='kitchen';"
COLUMNS='permit_id,task_id,action_id,operation,scope,candidate_version,record_id,slug,expected_updated_at,github_run_id,github_run_attempt,policy_decision_id,issued_at,expires_at,status,claimed_at,writing_at,completed_at,saved_id,saved_updated_at'
KEY_SQL=f"select {COLUMNS} from public.managed_cms_release_permits where record_id::text='{RECORD}' and (task_id='{TASK}' or action_id='{ACTION}' or candidate_version='{VERSION}') order by issued_at,permit_id;"
SAME_ROW_SQL=f"select {COLUMNS} from public.managed_cms_release_permits where record_id::text='{RECORD}' order by issued_at,permit_id;"


def need(ok, message):
    if not ok: raise w.WorkflowError('EN2 Supabase native: '+message)


def _sql(s):
    return ' '.join(s.split()) if isinstance(s,str) else ''


def _unique(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,'duplicate JSON keys')
        out[k]=v
    return out


def _provider_result(item):
    """Require response embedded in the same native MCP call, never a second file."""
    raw=item.get('result',item.get('output'))
    need(raw is not None,'DATA_MISSING: first-party read_thread omitted MCP result')
    if isinstance(raw,dict) and set(raw)=={'text','truncated'}:
        need(raw['truncated'] is False and isinstance(raw['text'],str),'DATA_MISSING: truncated MCP result')
        raw=json.loads(raw['text'],object_pairs_hook=_unique)
    need(isinstance(raw,dict) and not (set(raw)-{'content','isError','structuredContent','truncated','_meta'})
         and raw.get('isError',False) is False and not raw.get('error')
         and raw.get('truncated',False) is False and raw.get('structuredContent') is None,
         'successful complete actual MCP response with null structuredContent required')
    content=raw.get('content')
    need(isinstance(content,list) and len(content)==1 and isinstance(content[0],dict)
         and set(content[0])=={'type','text'} and content[0].get('type')=='text' and isinstance(content[0].get('text'),str),
         'one complete MCP text result required')
    body=json.loads(content[0]['text'],object_pairs_hook=_unique)
    text=body.get('result') if isinstance(body,dict) else None
    need(isinstance(text,str),'original Supabase result wrapper required')
    ends=list(re.finditer(r'</untrusted-data-([0-9a-f-]+)>',text))
    need(len(ends)==1,'one matching complete untrusted-data payload required')
    end=ends[0];opening='<untrusted-data-'+end.group(1)+'>'
    start=text.rfind(opening,0,end.start())
    need(start>=0,'matching original untrusted-data opener required')
    rows=json.loads(text[start+len(opening):end.start()].strip(),object_pairs_hook=_unique,
                    parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    need(isinstance(rows,list),'provider rows must be a list')
    return rows


def _call(turn, call_id, sql):
    matches=[v for v in turn.get('items',[]) if v.get('id')==call_id]
    need(len(matches)==1,'DATA_MISSING: one original MCP call required')
    call=matches[0];args=call.get('arguments')
    need(call.get('type')=='mcpToolCall' and call.get('server')=='codex_apps'
         and call.get('tool')=='supabase.execute_sql' and call.get('status')=='completed'
         and not call.get('error') and isinstance(args,dict) and set(args)=={'project_id','query'}
         and args['project_id']==PROJECT and _sql(args['query'])==_sql(sql),
         'exact completed first-party PUB project/query call required')
    return _provider_result(call)


def inspect_native(root, native_pin, row_call, key_call, same_row_call):
    """Validate structure of pinned native snapshot, never independently attest it.

    Exported files are caller-controlled, so even a perfect shape is not proof
    that read_thread returned those bytes. No network/SQL or write is done.
    """
    import department_autonomy as a
    import goal_delivery_runtime as g
    from professional_cms_issuer import targets
    root=Path(root).resolve();native=g._native_document(root,native_pin)
    fixed=w.department_registry(root)['publishing']['chat_binding'];thread=native.get('thread',{})
    need(fixed.get('project_id')==a.PROJECT and Path(fixed.get('cwd','')).resolve()==root
         and all(thread.get(k)==fixed[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),
         'actual original PUB fixed thread/project/directory required')
    need(len({row_call,key_call,same_row_call})==3 and all(isinstance(x,str) and x for x in (row_call,key_call,same_row_call)),
         'three distinct actual MCP calls required')
    turns=[t for t in native.get('turns',[]) if all(any(i.get('id')==cid for i in t.get('items',[])) for cid in (row_call,key_call,same_row_call))]
    need(len(turns)==1 and turns[0].get('status')=='completed' and not turns[0].get('error'),
         'DATA_MISSING: one completed same-PUB turn with all three calls required')
    turn=turns[0]
    ordered=[v.get('id') for v in turn.get('items',[])]
    need(ordered.index(row_call)<ordered.index(key_call)<ordered.index(same_row_call),
         'actual row, original-key and complete same-row calls must be ordered')
    # Authenticate the tuple source, but source custody is never permission.
    source=targets(root,task_id=TASK).get('english-kitchen-en2-exact-v1')
    need(isinstance(source,dict) and source.get('source_event_id')=='698ae455-16d7-4ad1-8744-ebfc8fd763e1'
         and source.get('actual_action_allowed') is False, 'original source-only target required')
    target=source['physical_target']
    rows=_call(turn,row_call,ROW_SQL);keys=_call(turn,key_call,KEY_SQL);same=_call(turn,same_row_call,SAME_ROW_SQL)
    need(len(rows)==1 and isinstance(rows[0],dict) and isinstance(rows[0].get('raw_full_record'),str),
         'one actual complete row and server clock required')
    row=json.loads(rows[0]['raw_full_record'],object_pairs_hook=_unique)
    need(isinstance(row,dict) and len(row)==41 and set(row)==set(target['baselineProjectionFields'])
         and row.get('id')==RECORD and row.get('slug')=='kitchen' and type(row.get('version')) is int
         and isinstance(row.get('updated_at'),str) and w.sha256_value(row)==target['baselineFieldsSha256']
         and w.sha256_value({k:row[k] for k in target['retainedProjectionFields']})==target['retainedFieldsSha256'],
         'original full41/protect37/MS11 target and raw CAS required')
    need(all(isinstance(x,dict) and x.get('record_id')==RECORD for x in keys+same),
         'exact original record effects only')
    expected=[x for x in same if x.get('task_id')==TASK or x.get('action_id')==ACTION or x.get('candidate_version')==VERSION]
    need(keys==expected,'key and independently complete same-row result must agree')
    need(not keys and all(x.get('status')=='completed' for x in same),
         'original-key prior effect or same-row unknown/in-flight blocks replay')
    observed=w._parse_observed_at(rows[0].get('server_observed_at'));now=dt.datetime.now(dt.timezone.utc)
    start,end=turn.get('startedAt'),turn.get('completedAt')
    need(observed is not None and type(start) in {int,float} and type(end) in {int,float}
         and start<=observed.timestamp()<=end<=now.timestamp(), 'actual observed server clock within completed PUB turn required')
    age=(now-observed).total_seconds()
    return {'result':'MCP_CALLS_STRUCTURALLY_MATCHED_NOT_INDEPENDENTLY_ATTESTED',
            'source_event_id':source['source_event_id'],'task_id':TASK,'record_id':RECORD,
            'server_observed_at':rows[0]['server_observed_at'],'raw_updated_at':row['updated_at'],
            'version':row['version'],'full_fields':41,'key_rows':len(keys),'same_row_count':len(same),
            'fresh_within_300_seconds':0<=age<=300,'provider_origin':'NOT_VERIFIED',
            'actual_action_allowed':False,'permit_issued':False,'preflight_registered':False}


def _official_call(turn, call_id, sql, *, live_upper_ms=None):
    matches=[x for x in turn.get('items',[]) if x.get('id')==call_id]
    need(len(matches)==1, 'DATA_MISSING: one exact original provider call required')
    call=matches[0]
    rows=_call(turn,call_id,sql)
    start,end=call.get('startedAtMs'),call.get('completedAtMs')
    tstart,tend=turn.get('startedAt'),turn.get('completedAt')
    upper = tend*1000+999 if type(tend) in {int,float} else live_upper_ms
    need(type(start) is int and type(end) is int and start<=end
         and type(tstart) in {int,float} and type(upper) in {int,float}
         and tstart*1000<=start<=end<=upper,
         'original provider call milliseconds must lie in the authenticated turn')
    return call,rows


def _compare_export(root, path, call):
    import department_autonomy as a
    pin=w.file_digest(root,path);export=a.document(root,pin)
    need(export.get('status')=='fulfilled' and isinstance(export.get('value'),dict),
         'exact successful saved original provider export required')
    raw=export['value'];live=call['result']
    need(raw.get('isError',False) is False and raw.get('structuredContent') is None
         and raw.get('content')==live.get('content'),
         'saved result content differs from actual live first-party provider call')
    return pin


def read_actual(root, turn_id, row_call, key_call, same_row_call=None, *, row_export=None, key_export=None,
                live_publisher=False, include_row=False):
    """Use existing official read-only RPC, never a caller-supplied transcript.

    This reads recorded native history only; it does not issue SQL or a permit.
    Null projectId is preserved as null and does not verify current execution identity.
    """
    import department_autonomy as a
    import department_event_dispatcher as dispatcher
    from professional_cms_issuer import targets
    root=Path(root).resolve();fixed=w.department_registry(root)['publishing']['chat_binding']
    need(fixed.get('project_id')==a.PROJECT and Path(fixed.get('cwd','')).resolve()==root,
         'original registered PUB project and directory required')
    need(all(isinstance(x,str) and x for x in (turn_id,row_call,key_call))
         and row_call!=key_call and (same_row_call is None or same_row_call not in {row_call,key_call}),
         'original turn and distinct provider call IDs required')
    rpc=dispatcher.RPC([dispatcher.native_queue_capability(root),'app-server','--listen','stdio://'])
    try:
        thread=rpc.call('thread/read',{'threadId':fixed['task_id'],'includeTurns':False})['thread']
        page=rpc.call('thread/turns/list',{'threadId':fixed['task_id'],'limit':3,
                      'sortDirection':'desc','itemsView':'full'})
    finally:
        rpc.close()
    need(thread.get('id')==fixed['task_id'] and thread.get('name')==fixed['title']
         and thread.get('cwd')==fixed['cwd'] and 'projectId' in thread
         and thread['projectId'] in (None,a.PROJECT), 'actual readonly PUB thread identity required')
    turns=[t for t in page.get('data',[]) if t.get('id')==turn_id]
    need(len(turns)==1 and not turns[0].get('error'),'one actual original PUB turn required')
    turn=turns[0]
    live_upper_ms=None
    if turn.get('status')!='completed':
        from en2_preview_web_identity import _desktop_live_turn
        live_upper_ms=dt.datetime.now(dt.timezone.utc).timestamp()*1000
        need(live_publisher is True and isinstance(same_row_call,str)
             and turn is page['data'][0] and turn.get('status') in {'interrupted','inProgress'}
             and _desktop_live_turn(turn,{**fixed,'thread_id':fixed['task_id']},same_row_call,live_upper_ms,compact=True),
             'one actual original completed PUB turn or current desktop proof after all three queries required')
    row_native,rows=_official_call(turn,row_call,ROW_SQL,live_upper_ms=live_upper_ms)
    key_native,keys=_official_call(turn,key_call,KEY_SQL,live_upper_ms=live_upper_ms)
    need(row_native['completedAtMs']<=key_native['startedAtMs'], 'actual original row precedes key lookup')
    source=targets(root,task_id=TASK).get('english-kitchen-en2-exact-v1')
    need(isinstance(source,dict) and source.get('source_event_id')=='698ae455-16d7-4ad1-8744-ebfc8fd763e1'
         and source.get('actual_action_allowed') is False,'original authenticated source-only target required')
    target=source['physical_target']
    need(len(rows)==1 and isinstance(rows[0],dict) and isinstance(rows[0].get('raw_full_record'),str),
         'one exact server row and clock required')
    row=json.loads(rows[0]['raw_full_record'],object_pairs_hook=_unique)
    need(isinstance(row,dict) and len(row)==41 and set(row)==set(target['baselineProjectionFields'])
         and row.get('id')==RECORD and row.get('slug')=='kitchen' and type(row.get('version')) is int
         and isinstance(row.get('updated_at'),str) and w.sha256_value(row)==target['baselineFieldsSha256']
         and w.sha256_value({k:row[k] for k in target['retainedProjectionFields']})==target['retainedFieldsSha256'],
         'original full41/protect37/MS11 and raw server CAS required')
    observed=w._parse_observed_at(rows[0].get('server_observed_at'));now=dt.datetime.now(dt.timezone.utc)
    need(observed is not None and row_native['startedAtMs']<=observed.timestamp()*1000<=row_native['completedAtMs']
         and key_native['completedAtMs']<=now.timestamp()*1000, 'real server clock and actual provider-call timing required')
    need(all(isinstance(x,dict) and x.get('record_id')==RECORD and
         (x.get('task_id')==TASK or x.get('action_id')==ACTION or x.get('candidate_version')==VERSION) for x in keys),
         'only original-key effects may be returned by original-key query')
    same=None;effect='UNKNOWN_SAME_ROW_NOT_QUERIED'
    if same_row_call is not None:
        same_native,same=_official_call(turn,same_row_call,SAME_ROW_SQL,live_upper_ms=live_upper_ms)
        need(key_native['completedAtMs']<=same_native['startedAtMs'],'same-row query must follow original key')
        need(all(isinstance(x,dict) and x.get('record_id')==RECORD for x in same),'same-row records required')
        expected=[x for x in same if x.get('task_id')==TASK or x.get('action_id')==ACTION or x.get('candidate_version')==VERSION]
        need(keys==expected,'original key and complete same-row query must agree')
        effect='BLOCKED_PRIOR_OR_UNKNOWN' if keys or any(x.get('status')!='completed' for x in same) else 'NO_BLOCKING_ROW_OBSERVED'
    output={'result':'ACTUAL_OFFICIAL_MCP_HISTORY_READ','row_call_origin':'VERIFIED_OFFICIAL_RPC',
      'original_key_call_origin':'VERIFIED_OFFICIAL_RPC','same_row_call_origin':'VERIFIED_OFFICIAL_RPC' if same is not None else 'DATA_MISSING',
      'task_id':TASK,'turn_id':turn_id,'record_id':RECORD,'row_call':row_call,'key_call':key_call,
      'server_observed_at':rows[0]['server_observed_at'],'raw_updated_at':row['updated_at'],'version':row['version'],
      'full_fields':41,'original_key_count':len(keys),'same_row_count':len(same) if same is not None else None,
      'same_row_effect':effect,'same_row_completed_at_ms':same_native['completedAtMs'] if same is not None else None,
      'row_sha256':w.sha256_value(row),'fresh_within_300_seconds':0<=(now-observed).total_seconds()<=300,
      'thread_project_id_actual':thread['projectId'],'current_project_membership':'NOT_PROVEN_BY_THIS_RPC' if thread['projectId'] is None else 'MATCHED',
      'preflight_origin':'NOT_VERIFIED','actual_action_allowed':False,'permit_issued':False,'preflight_registered':False}
    if row_export:output['row_export_match']=_compare_export(root,row_export,row_native)
    if key_export:output['key_export_match']=_compare_export(root,key_export,key_native)
    if include_row:output['verified_full_row']=row
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='read original full native history through official short-lived read-only RPC')
    parser.add_argument('--native',help='local pinned transcript; structural validation only')
    parser.add_argument('--turn-id');parser.add_argument('--row-call',required=True);parser.add_argument('--key-call',required=True)
    parser.add_argument('--same-row-call');parser.add_argument('--row-export');parser.add_argument('--key-export')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    with w.request_validation_context():
        if args.live:
            if not args.turn_id or args.native:parser.error('--live requires --turn-id and no --native')
            result=read_actual(root,args.turn_id,args.row_call,args.key_call,args.same_row_call,
                               row_export=args.row_export,key_export=args.key_export)
        else:
            if not args.native or not args.same_row_call:parser.error('local transcript requires --native and --same-row-call')
            result=inspect_native(root,w.file_digest(root,args.native),args.row_call,args.key_call,args.same_row_call)
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
