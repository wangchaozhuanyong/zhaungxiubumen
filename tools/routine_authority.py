"""Bounded assistant decisions. Existing professional execution gates remain authoritative."""
from pathlib import Path
import datetime as dt
import json
import human_control
import workflow_control as w

ASSISTANTS = {'operations-assistant','operations-assistant-2','operations-assistant-3'}
SAFE_RELEASE = {'cms_write':'R1', 'site_publish':'R2'}


def default_lane(sender, kind='', parent_owner=None):
    if sender in {'qa','qa-technical'}:
        if parent_owner not in ASSISTANTS: raise w.WorkflowError('QA returns to exact original business owner')
        return parent_owner
    if sender in {'publishing','designated-website-developer','qa-technical'} or kind in {'technical','cms','code'}:
        return 'operations-assistant-2'
    if sender in {'paid-growth-data','visual-design-video'}:
        return 'operations-assistant-3'
    if sender in {'content-organic-website','seo-content-research','local-seo-maps','sales'}:
        return 'operations-assistant'
    raise w.WorkflowError('unclassified business requires HQ direction')


def validate_policy_delegate(root, pin, role, task_id, department, action_id, action_class,
                             scope, consume, owner, claim):
    import routine_grants, result_coordination as c
    grant = routine_grants.validate(root, pin, role)
    release = grant.get('release', {})
    if (consume or SAFE_RELEASE.get(action_class) != release.get('risk_level')
            or 'release_gate' not in grant.get('allowed_decisions', [])
            or any(release.get(k) != v for k,v in {'task_id':task_id,
                'permission_department':department,'action_id':action_id,
                'action_class':action_class,'scope':scope}.items())
            or not scope.startswith('flashcast.com.my:')):
        raise w.WorkflowError('delegate cannot consume permission or widen exact release tuple')
    pin_candidate = release.get('candidate')
    if not isinstance(pin_candidate,dict) or w.file_digest(root,pin_candidate.get('path',''))!=pin_candidate:
        raise w.WorkflowError('release candidate drift')
    readiness=release.get('readiness')
    if not isinstance(readiness,dict) or w.file_digest(root,readiness.get('path',''))!=readiness:
        raise w.WorkflowError('frozen independently reviewed release readiness required')
    ready=w.read_json(w.safe_path(root,readiness['path']))
    if any(ready.get(k)!=v for k,v in {'task_id':task_id,'action_id':action_id,'scope':scope,
            'action_class':action_class,'risk_level':release['risk_level'],'candidate':pin_candidate}.items()):
        raise w.WorkflowError('release readiness tuple/candidate differs')
    required={'facts','exact_diff','checks','backup','rollback','lawful_channel','current_version'}
    gates=ready.get('gates',{})
    if set(gates)!=required:raise w.WorkflowError('all existing release gates must be explicit')
    for name,row in gates.items():
        if not isinstance(row,dict) or row.get('status')!='pass' or not isinstance(row.get('evidence'),list) or not row['evidence']:
            raise w.WorkflowError('missing verified release gate '+name)
        for item in row['evidence']:
            if not isinstance(item,dict) or w.file_digest(root,item.get('path',''))!=item:
                raise w.WorkflowError('release gate evidence changed')
    receipts,invalid=w._validate_receipt_chain(root,task_id)
    reviews=[r for r in receipts if r.get('receipt_type')=='qa_verdict' and r.get('department')=='qa']
    qa=reviews[-1] if reviews else {}
    if (invalid or qa.get('verdict')!='pass' or qa.get('action_id')!=action_id or qa.get('scope')!=scope
            or w._latest_qa_release_route([qa])!=action_class
            or w._latest_verified_qa_risk_level(root,task_id,[qa])!=release['risk_level']):
        raise w.WorkflowError('exact latest independent publication QA required')
    boxes=[]
    for item in qa.get('evidence',[]):
        if str(item.get('path','')).startswith('logs/department-outbox/') and str(item.get('path','')).endswith('.json'):
            if w.file_digest(root,item['path'])!=item:raise w.WorkflowError('publication QA outbox changed')
            boxes.append(w.read_json(w.safe_path(root,item['path'])))
    if not any(box.get('release_readiness')==readiness and box.get('candidate_path')==pin_candidate['path']
            and box.get('candidate_sha256')==pin_candidate['sha256'] for box in boxes):
        raise w.WorkflowError('independent QA must bind exact candidate and all readiness evidence')

    identity=c.exact_identity(grant);c._validate_queued(root,identity)
    store=c.CoordinationStore(root)
    try:store._lease(identity,role,owner,claim)
    finally:store.close()
    return grant


def check_special_decision(root, request, grant):
    decision = request.get('decision')
    if decision in {'send_qa','rework'}:
        snapshot=w.read_json(w.snapshot_path(root,grant['task_id']))
        reviewer=w._final_qa_department(root,snapshot)
        if decision=='send_qa' and request.get('next_owner')!=reviewer:
            raise w.WorkflowError('routine QA dispatch requires the exact independent planned reviewer')
        if decision=='rework':
            producer=grant.get('sender_department')
            if producer in {'qa','qa-technical'}:
                import qa_review_plan
                plan=qa_review_plan.load_plan(root,snapshot)
                if plan:
                    producer=plan['producer_department']
                else:
                    choices={r.get('department') for r in snapshot.get('departments',[])
                             if r.get('department') not in ASSISTANTS|{'operations','qa','qa-technical','publishing'}}
                    producer=next(iter(choices)) if len(choices)==1 else None
            if not producer or request.get('next_owner')!=producer:
                raise w.WorkflowError('routine rework must return to the exact original professional owner')
    if decision == 'close_scope':
        scope = request.get('acceptance_scope')
        if not scope or scope != grant.get('scope') or scope not in grant.get('accepted_scopes', []):
            raise w.WorkflowError('assistant may only close the exact admitted acceptance scope')
        accepted=grant.get('accepted_candidate')
        if not isinstance(accepted,dict) or w.file_digest(root,accepted.get('path',''))!=accepted:
            raise w.WorkflowError('closure needs unchanged exact independently accepted candidate')
        snapshot=w.read_json(w.snapshot_path(root,grant['task_id']))
        reviewer=w._final_qa_department(root,snapshot)
        receipts,invalid=w._validate_receipt_chain(root,grant['task_id'])
        reviews=[r for r in receipts if r.get('receipt_type')=='qa_verdict' and r.get('department')==reviewer]
        qa=reviews[-1] if reviews else {}
        bound=False
        for item in qa.get('evidence',[]):
            if str(item.get('path','')).startswith('logs/department-outbox/') and str(item.get('path','')).endswith('.json'):
                if w.file_digest(root,item['path'])!=item:raise w.WorkflowError('accepted QA evidence changed')
                box=w.read_json(w.safe_path(root,item['path']))
                bound=bound or (box.get('candidate_path')==accepted['path'] and box.get('candidate_sha256')==accepted['sha256'])
        if invalid or qa.get('verdict')!='pass' or qa.get('scope')!=scope or not bound:
            raise w.WorkflowError('scope closure requires actual current independent QA of these exact bytes')
        if request.get('qa_status') != 'pass':
            raise w.WorkflowError('accurate independently accepted scope required')
        if grant.get('risk_level') not in {'R0','R1','R2'}:
            raise w.WorkflowError('unknown or R3 closure must escalate')
        if grant.get('risk_level') != 'R0' or str(scope).startswith('flashcast.com.my:'):
            if request.get('execution_status') != 'verified' or request.get('public_postcheck_status') != 'pass':
                raise w.WorkflowError('published scope closure needs actual execution and public postcheck')
            receipts,invalid=w._validate_receipt_chain(root,grant['task_id'])
            actual=[r for r in receipts if r.get('receipt_type')=='postcheck' and r.get('verdict')=='pass' and r.get('scope')==scope]
            if invalid or not actual:
                raise w.WorkflowError('published close needs exact native original-task postcheck, not asserted flags')
    if decision == 'release_gate':
        pin=request.get('proxy_release')
        if not isinstance(pin, dict) or w.file_digest(root,pin.get('path',''))!=pin:
            raise w.WorkflowError('exact admitted proxy AUTO_RELEASE required')
        data=w.read_json(w.safe_path(root,pin['path']))
        policy_rows=w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
        matches=[row for row in policy_rows if row.get('decision_id')==data.get('policy_decision_id')]
        if (len(matches)!=1 or matches[0].get('status')!='allow'
                or matches[0].get('delegate_grant')!=request.get('routine_grant')
                or matches[0].get('actor_role')!=grant['actor_role']
                or any(matches[0].get(k)!=v for k,v in {
                    'task_id':grant.get('release',{}).get('task_id'),
                    'action_id':grant.get('release',{}).get('action_id'),
                    'action_class':grant.get('release',{}).get('action_class'),
                    'scope':grant.get('scope'),
                    'department':grant.get('release',{}).get('permission_department')}.items())
                or matches[0].get('qa_risk_level')!=grant.get('release',{}).get('risk_level')
                or matches[0].get('approval_basis') not in {'standing_authorization','standing_site_auto_release'}
                or data.get('approval_id')!=matches[0].get('approval_id')
                or data.get('candidate')!=grant.get('release',{}).get('candidate')
                or w.file_digest(root,data.get('candidate',{}).get('path',''))!=data.get('candidate')
                or data.get('status')!='AUTO_RELEASE_ARRANGED' or data.get('actor_role')!=grant['actor_role']
                or data.get('grant')!=request.get('routine_grant')
                or data.get('original_result_sha256')!=request.get('result_sha256')
                or data.get('scope')!=grant.get('scope')
                or data.get('risk_level')!=grant.get('release',{}).get('risk_level')
                or data.get('permission_consumed') is not False or data.get('external_write_executed') is not False):
            raise w.WorkflowError('proxy release exact native decision/actor/candidate mismatch')


def proxy_auto_release(root, grant_pin, role, request):
    """Arrange an exact standing-authorized R1/R2 execution; never publish or consume permit."""
    import routine_grants, result_coordination as c
    identity=c.exact_identity(request)
    with human_control.action_gate(root,identity['task_id']),c.coordination_lock(root):
        grant=routine_grants.validate(root,grant_pin,role)
        if any(request.get(k)!=grant.get(k) for k in (*c.IDENTITY_FIELDS,'scope')):
            raise w.WorkflowError('proxy release differs from granted original result/scope')
        release=request.get('release')
        if not isinstance(release,dict) or release!=grant.get('release'):
            raise w.WorkflowError('frozen exact release tuple required')
        action_class=release.get('action_class');risk=release.get('risk_level')
        expected_executor='publishing' if action_class=='cms_write' else 'designated-website-developer'
        if (SAFE_RELEASE.get(action_class)!=risk or release.get('executor')!=expected_executor
                or 'release_gate' not in grant['allowed_decisions']
                or not str(release.get('scope','')).startswith('flashcast.com.my:')
                or release.get('scope')!=grant['scope'] or release.get('task_id')!=grant['task_id']):
            raise w.WorkflowError('R3/Ads/Maps/fees/accounts or wrong professional executor must escalate')
        candidate=release.get('candidate')
        if not isinstance(candidate,dict) or w.file_digest(root,candidate.get('path',''))!=candidate:
            raise w.WorkflowError('unknown or changed release candidate')
        # CMS executor remains publishing. Code policy is evaluated for the
        # registered specialist permission holder; actual code execution stays
        # on the exact designated developer bridge, never on an assistant.
        permission_department=release.get('permission_department')
        if permission_department not in ({'publishing'} if action_class=='cms_write' else {'content-organic-website'}):
            raise w.WorkflowError('cannot impersonate policy issuer or execution permission holder')
        c._validate_queued(root,identity)
        store=c.CoordinationStore(root)
        try:
            store._lease(identity,role,request.get('coordinator_owner'),request.get('coordination_claim'))
            effect=c._sha(['proxy_auto_release',release['task_id'],release['action_id'],release['scope']])
            payload={'grant':grant_pin,'actor_role':role,'release':release,'original_result':identity}
            store._begin()
            old=store.conn.execute('SELECT * FROM reservations WHERE effect_key=?',(effect,)).fetchone()
            if old:
                if json.loads(old['payload_json'])!=payload:raise w.WorkflowError('proxy effect version changed')
                if old['status']!='committed':raise w.WorkflowError('uncertain proxy effect requires native policy readback; no reissue')
                store.conn.commit();return json.loads(old['native_record_json'])
            store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)",(c._key(identity),effect,c._canonical(payload)))
            store._audit(identity,'proxy_release_reserved',{'effect':effect,'actor_role':role});store.conn.commit()
            # Existing engine checks current independent QA/risk/facts/channel/
            # backup/rollback/sparse publisher admission/standing authorization.
            decision,_=w.policy_check(root,task_id=release['task_id'],department=permission_department,
                action_id=release['action_id'],action_class=action_class,scope=release['scope'],
                consume_approval=False,delegate_actor_role=role,delegate_grant=grant_pin,
                delegate_coordinator_owner=request.get('coordinator_owner'),
                delegate_coordination_claim=request.get('coordination_claim'))
            if (decision.get('status')!='allow' or decision.get('approval_basis') not in {'standing_authorization','standing_site_auto_release'}
                    or decision.get('qa_risk_level')!=risk):
                raise w.WorkflowError('existing release gates deny or do not prove exact R1/R2 standing authority')
            value={'status':'AUTO_RELEASE_ARRANGED','actor_role':role,'actor_thread_id':grant['actor_thread_id'],
                   'grant':grant_pin,'task_id':identity['task_id'],'scope':release['scope'],'risk_level':risk,
                   'original_result_sha256':identity['result_sha256'],'candidate':candidate,
                   'policy_decision_id':decision['decision_id'],'approval_id':decision.get('approval_id'),
                   'executor':expected_executor,'permission_consumed':False,'external_write_executed':False,
                   'created_at':w.utc_timestamp(),'actor_metadata_is_authentication':False}
            path='logs/routine-release/'+c._key(identity)+'-'+effect+'.json'
            w.atomic_write_json(w.safe_path(root,path),value);value['proof']=w.file_digest(root,path)
            store._begin();store.conn.execute("UPDATE reservations SET status='committed',native_record_json=? WHERE result_key=? AND effect_key=?",
                (c._canonical(value),c._key(identity),effect));store._audit(identity,'proxy_release_native_readback',{'decision_id':decision['decision_id']});store.conn.commit()
            return value
        finally:
            if store.conn.in_transaction:store.conn.rollback()
            store.close()


def release_after_ack(root, grant_pin, role, request):
    import routine_grants, result_coordination as c
    with human_control.action_gate(root):
        grant=routine_grants.validate(root,grant_pin,role);route=grant.get('routing',{})
        rows,invalid=w._validate_receipt_chain(root,route.get('task_id',''))
        sends=[(i,row) for i,row in enumerate(rows) if row.get('receipt_type')=='dispatch_sent'
               and row.get('action_id')==route.get('action_id') and row.get('scope')==route.get('scope')
               and row.get('actor_role')==role]
        if invalid or not sends:raise w.WorkflowError('actual exact assistant dispatch required before release')
        i,sent=sends[-1]
        ack=next((row for row in rows[i+1:] if row.get('receipt_type')=='chat_ack'
            and row.get('chat_task_id')==route.get('target_thread_id') and row.get('ack_nonempty') is True),None)
        if ack is None:raise w.WorkflowError('actual fixed department ACK required before release')
        note_path=w.safe_path(root,'logs/routine-continuations/'+c._key(c.exact_identity(grant))+'.json')
        if note_path.exists():
            previous=w.read_json(note_path)
            if previous.get('ack_receipt_id')==ack['receipt_id'] and previous.get('coordinator_role')==role:
                return previous
        store=c.CoordinationStore(root)
        try:
            released=store.release(c.exact_identity(grant),role,request.get('coordinator_owner'),request.get('coordination_claim'),'actual dispatch accepted; release exclusive coordination')
        finally:store.close()
        value={'original_task_id':grant['task_id'],'linked_task_id':route['task_id'],'coordinator_role':role,
               'next_owner':route['target_department'],'phase':'department_executing','ack_receipt_id':ack['receipt_id'],
               'holds_headquarters_open':False,'claim_released':True,'created_at':w.utc_timestamp()}
        w.atomic_write_json(w.safe_path(root,'logs/routine-continuations/'+c._key(c.exact_identity(grant))+'.json'),value)
        return value


def recover_proxy_release(root, grant_pin, role, request):
    """Read back one recorded native policy decision after an interrupted proxy; never reissue."""
    import routine_grants, result_coordination as c
    with human_control.action_gate(root), c.coordination_lock(root):
        grant=routine_grants.validate(root,grant_pin,role)
        release=grant.get('release',{});identity=c.exact_identity(grant)
        validate_policy_delegate(root,grant_pin,role,release.get('task_id'),release.get('permission_department'),
            release.get('action_id'),release.get('action_class'),release.get('scope'),False,
            request.get('coordinator_owner'),request.get('coordination_claim'))
        effect=c._sha(['proxy_auto_release',release['task_id'],release['action_id'],release['scope']])
        payload={'grant':grant_pin,'actor_role':role,'release':release,'original_result':identity}
        store=c.CoordinationStore(root)
        try:
            old=store.conn.execute('SELECT * FROM reservations WHERE effect_key=?',(effect,)).fetchone()
            if old is None or json.loads(old['payload_json'])!=payload:
                raise w.WorkflowError('no exact proxy reservation for recovery')
            if old['status']=='committed':return json.loads(old['native_record_json'])
            rows=[r for r in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if r.get('delegate_grant')==grant_pin
                and r.get('actor_role')==role and r.get('task_id')==release['task_id']
                and r.get('action_id')==release['action_id'] and r.get('scope')==release['scope']]
            if len(rows)!=1:raise w.WorkflowError('native proxy readback absent or ambiguous; keep uncertain')
            decision=rows[0]
            if (decision.get('status')!='allow' or decision.get('approval_basis') not in {'standing_authorization','standing_site_auto_release'}
                    or decision.get('qa_risk_level')!=release['risk_level']):
                raise w.WorkflowError('native policy denied; no AUTO_RELEASE proof')
            value={'status':'AUTO_RELEASE_ARRANGED','actor_role':role,'actor_thread_id':grant['actor_thread_id'],
                'grant':grant_pin,'task_id':identity['task_id'],'scope':release['scope'],'risk_level':release['risk_level'],
                'original_result_sha256':identity['result_sha256'],'candidate':release['candidate'],
                'policy_decision_id':decision['decision_id'],'approval_id':decision.get('approval_id'),
                'executor':release['executor'],'permission_consumed':False,'external_write_executed':False,
                'created_at':w.utc_timestamp(),'recovered_from_native_policy_readback':True,
                'actor_metadata_is_authentication':False}
            path='logs/routine-release/'+c._key(identity)+'-'+effect+'.json'
            w.atomic_write_json(w.safe_path(root,path),value);value['proof']=w.file_digest(root,path)
            store._begin();store.conn.execute("UPDATE reservations SET status='committed',native_record_json=? WHERE effect_key=?",
                (c._canonical(value),effect));store._audit(identity,'proxy_recovered',{'decision_id':decision['decision_id']});store.conn.commit()
            return value
        finally:
            if store.conn.in_transaction:store.conn.rollback()
            store.close()


def release_claim_for_ack(root, task_id, receipt):
    rows,invalid=w._validate_receipt_chain(root,task_id)
    if invalid:raise w.WorkflowError('ACK chain invalid')
    sends=[r for r in rows if r.get('receipt_type')=='dispatch_sent'
           and r.get('department')==receipt.get('department') and r.get('routine_grant')]
    if not sends:return None
    sent=sends[-1];pin=sent['routine_grant'];grant=w.read_json(w.safe_path(root,pin['path']))
    attempt=w.read_json(w.safe_path(root,grant['native_attempt_receipt_path']))
    return release_after_ack(root,pin,sent['actor_role'],{
        'coordinator_owner':attempt.get('coordinator_owner'),'coordination_claim':attempt.get('coordination_claim')})


def partition_queue(root, queue):
    """Derive HQ versus admitted-assistant work from actual frozen grants, never row assertions."""
    import routine_grants, result_coordination as c
    cfg=w.load_policy(root).get('department_system_upgrade',{})
    pins=cfg.get('result_grants',{})
    answer=dict(queue);admitted=[]
    for name,count,hq in [('results','pending_count','headquarters_pending_count'),
                          ('followthrough_results','followthrough_pending_count','headquarters_followthrough_pending_count')]:
        rows=queue.get(name,[])
        if not isinstance(rows,list):raise w.WorkflowError('queue result array required')
        remaining=int(queue.get(count,0));derived=[]
        for index,row in enumerate(rows):
            item=dict(row) if isinstance(row,dict) else {'row_index':index,'coordination_status':'blocked_invalid_queue_row'}
            try:
                if not isinstance(row,dict):raise w.WorkflowError('exact queue row object required')
                identity=c.exact_identity(row);pin=pins.get(c._key(identity))
                if not isinstance(pin,dict):raise w.WorkflowError('no exact admitted result grant')
                data=w.read_json(w.safe_path(root,pin.get('path','')));role=data.get('actor_role')
                grant=routine_grants.validate(root,pin,role)
                if (any(grant.get(k)!=v for k,v in identity.items()) or grant.get('risk_level') not in {'R0','R1','R2'}
                        or 'controller_decision' not in grant.get('allowed_events',[]) or not grant.get('allowed_decisions')):
                    raise w.WorkflowError('result grant does not admit bounded decisions')
                c._validate_queued(root,identity)
                item.update(coordinator_role=role,routine_grant=pin,routine_grant_validated=True,
                            requires_headquarters_decision=False)
                remaining-=1;admitted.append(item)
            except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError):
                item.update(requires_headquarters_decision=True,routine_grant_validated=False)
            derived.append(item)
        answer[name]=derived;answer[hq]=max(0,remaining)
    answer['assistant_ready_results']=admitted
    answer['ordinary_inflight_is_stop_blocker']=False
    return answer


def classify_ready_tasks(root, rows):
    import routine_grants, result_coordination as c
    cfg=w.load_policy(root).get('department_system_upgrade',{})
    if not isinstance(rows,list):raise w.WorkflowError('ready task array required')
    result=[]
    for index,row in enumerate(rows):
        item=dict(row) if isinstance(row,dict) else {'row_index':index,'coordination_status':'blocked_invalid_ready_row'}
        try:
            if not isinstance(row,dict):raise w.WorkflowError('exact ready task object required')
            pin=cfg.get('routing_grants',{}).get(str(row.get('task_id'))+':'+str(row.get('action_id')))
            data=w.read_json(w.safe_path(root,pin['path']));role=data.get('actor_role')
            grant=routine_grants.validate(root,pin,role);route=grant.get('routing',{})
            if (route.get('task_id')!=row.get('task_id') or route.get('action_id')!=row.get('action_id')
                    or w.file_digest(root,str(row.get('packet_path','')))['sha256']!=route.get('payload_sha256')):
                raise w.WorkflowError('exact prepared packet/route grant required')
            c._validate_queued(root,c.exact_identity(grant))
            item.update(coordinator_role=role,routine_grant_validated=True,requires_headquarters_decision=False)
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError):
            item.update(routine_grant_validated=False,requires_headquarters_decision=True)
        result.append(item)
    return result


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['proxy-release','recover-proxy','release-after-ack'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--input',required=True)
    a=p.parse_args();d=w.read_json(w.safe_path(a.root,a.input))
    method={'proxy-release':proxy_auto_release,'recover-proxy':recover_proxy_release,'release-after-ack':release_after_ack}[a.command]
    print(json.dumps(method(a.root,d['grant'],d['actor_role'],d['request']),ensure_ascii=False))

if __name__=='__main__':main()
