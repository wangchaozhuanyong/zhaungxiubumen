"""Read actual responsibility for a new directly authorized frontend release.

This source is restricted to completion evidence; it is not a dispatch, ACK,
production permit, completion proof or replacement for historical contracts.
"""
from pathlib import Path
import datetime as dt
import workflow_control as w
import department_autonomy as a

SCHEMA='direct-owner-frontend-completion-responsibility/v1'
EVENT='direct_owner_frontend_completion_responsibility'
def need(value, message):a.require(value,'frontend completion responsibility: '+message)

def validate(root,snapshot,item):
    import goal_delivery_runtime as g
    import professional_web_execution as web
    import professional_web_increment as inc
    root=Path(root).resolve();goal=snapshot['goal_delivery'];role=goal['primary_owner']
    need(set(item)=={'schema','task_id','goal_contract','WEB_completed_native','WEB_result','proofs'}
         and item['schema']==SCHEMA and item['task_id']==snapshot['task_id']
         and item['goal_contract']==snapshot['goal_contract'] and a.autonomous_goal(goal)
         and snapshot['current_state'] not in w.TERMINAL_STATES, 'exact open new autonomous goal')
    frozen=a.document(root,snapshot['goal_contract'])
    need(a.professional(root,role) and goal['producer_departments']==[role]
         and all(goal.get(k)==frozen.get(k) for k in ('primary_owner','producer_departments','authorized_scope',
                                                     'human_authorization','collaboration_scopes')),
         'unchanged original owner, producer, human and frozen scope')
    events=[e for e in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':snapshot['task_id']}) if e.get('task_id')==snapshot['task_id']]
    initialized=[e for e in events if e.get('details',{}).get('goal_contract')==snapshot['goal_contract']
                 and isinstance(e.get('details',{}).get('goal_delivery'),dict)]
    need(len(initialized)==1 and all(initialized[0]['details']['goal_delivery'].get(k)==goal.get(k)
         for k in ('primary_owner','producer_departments','authorized_scope','human_authorization','authorization_pin'))
         and not w.validate_workflow_events(root,snapshot['task_id'])
         and not w._validate_receipt_chain(root,snapshot['task_id'])[1], 'actual init binding and intact histories')
    sources=web.records(root,snapshot['task_id']);need(len(sources)==1 and sources[0].get('direct_owner_frontend_source')
         and sources[0]['owner']==role, 'one authentic direct human frontend source')
    base=sources[0]; successor=inc.sources(root,base);report=a.document(root,item['WEB_result'])
    matches=[x for x in successor if x.get('increment_source_mode')=='actual_CI_test_successor'
             and x.get('commit')==report.get('actual_candidate')]
    need(len(matches)==1 and report.get('schema')=='original-WEB-actual-frontend-Pages-public-acceptance-complete/v3'
         and report.get('task_id')==snapshot['task_id'] and report.get('scope')==base['scope']
         and report.get('business_owner')==role and report.get('executor')==base['role']
         and report.get('source_events')==[base['event_id'],matches[0]['increment_event_id']]
         and report.get('actual_candidate_parent')==base['commit'] and report.get('actual_tree')==matches[0]['tree']
         and report.get('cumulative_base')==base['base'] and report.get('status')=='CODE_RELEASED_AND_PUBLIC_ACCEPTANCE_COMPLETE',
         'actual original source and unique registered CI successor')
    native=g._native_document(root,item['WEB_completed_native']);binding=base['binding']
    need(all(native.get('thread',{}).get(k)==binding[v] for k,v in
             {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),'actual fixed WEB identity')
    turns=[t for t in native.get('turns',[]) if t.get('status')=='completed' and not t.get('error')]
    finals=[m for t in turns for m in t.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer'
            and str((root/item['WEB_result']['path']).resolve()) in m.get('text','')
            and report['actual_main'][:8] in m.get('text','') and report['PR']['url'] in m.get('text','')]
    need(len(finals)==1, 'actual completed WEB final names exact result, PR and deployed main')
    checks=report['exact_final_head_checks'];need({x['name'] for x in checks}==web.CHECKS and len(checks)==len(web.CHECKS)
         and all(x.get('head_sha')==matches[0]['commit'] and x.get('status')=='completed' and x.get('conclusion')=='success' and x.get('id') for x in checks)
         and report['PR'].get('merged') is True and report['PR']['number']==matches[0]['existing_pull_number']
         and report['Pages'].get('head_sha')==report['actual_main'] and report['Pages'].get('event')=='push'
         and report['Pages'].get('status')=='completed' and report['Pages'].get('conclusion')=='success'
         and report['public_version_and_acceptance'].get('checks',0)>0, 'real same-head official CI, merged PR, Pages and public readback')
    for pin in list(report['stage_results'].values())+[report['Pages']['evidence']]:web.code_pin(root,pin)
    reqs=a.requirement_rows(goal);proofs=item['proofs'];need(isinstance(proofs,dict) and set(proofs)=={x['requirement_id'] for x in reqs}, 'one existing actual proof for every original requirement')
    for req in reqs:
        proof=a.document(root,proofs[req['requirement_id']]);need(req['producer_department']==role and item['WEB_result'] in proof.get('actual_effects',[]), 'same owner and actual WEB result in each existing proof')
        a.validate_effect(root,snapshot,req,proofs[req['requirement_id']])
    return {'department':role,'task_id':snapshot['task_id'],'scope':base['scope'],'source_events':report['source_events'],
            'WEB_result':item['WEB_result'],'proofs':proofs,'not_a_dispatch_or_ACK':True,'permission_issued':False}

def record(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));proof=validate(root,snapshot,item)
        old=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task}) if e.get('task_id')==task and e.get('details',{}).get(EVENT)]
        if old:
            need(len(old)==1 and old[0]['details'][EVENT]==pin,'one immutable responsibility source')
            return {'result':'duplicate_ignored','source':pin,'event_id':old[0]['event_id'],'permission_issued':False}
        event=w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin,'external_permission_issued':False})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'responsibility':proof,'completion_proof_recorded':False,'permission_issued':False}

def registered(root,snapshot,role,proof_pin):
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':snapshot['task_id']}) if e.get('task_id')==snapshot['task_id'] and e.get('details',{}).get(EVENT)]
    if not rows:return False
    need(len(rows)==1 and rows[0]['details'].get('external_permission_issued') is False,'unique actual source event')
    source=a.document(root,rows[0]['details'][EVENT]);result=validate(root,snapshot,source)
    need(result['department']==role and proof_pin in result['proofs'].values(),'only exact owner and frozen actual proof')
    return True
