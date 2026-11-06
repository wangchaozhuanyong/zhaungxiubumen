"""Read-only candidate for exact terminal R3 binding retirement.

No CLI, platform adapter, credential handling, policy authorization, or write
path is provided here. Normal authorization and independently verified native
terminal evidence are prerequisites for any future integration.
"""
from copy import deepcopy


class RetirementRefused(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise RetirementRefused(reason)


def check_terminal_snapshot(binding, expected_actor_id, repository, actor, run, environment, main):
    """Pure shape checks only; authentic native GET and issuer are separate gates."""
    require(isinstance(binding,dict) and isinstance(repository,dict) and isinstance(actor,dict)
            and isinstance(run,dict) and isinstance(environment,dict) and isinstance(main,dict), 'complete real snapshot required')
    full=binding.get('repository');rid=binding.get('repositoryId');head=binding.get('expectedSha')
    require(repository.get('full_name')==full and repository.get('id')==rid
            and actor.get('id')==expected_actor_id and actor.get('login')==str(full).split('/')[0], 'same original repository and actor')
    require(str(run.get('id'))==str(binding.get('runId')) and run.get('run_attempt')==binding.get('runAttempt')==1
            and run.get('event')=='workflow_dispatch' and run.get('head_sha')==head
            and run.get('head_branch')=='main' and run.get('repository',{}).get('id')==rid
            and run.get('repository',{}).get('full_name')==full and run.get('actor',{}).get('id')==expected_actor_id
            and binding.get('workflowRef')==str(full)+'/'+str(run.get('path'))+'@refs/heads/main', 'same exact original workflow/run/main/actor')
    require(run.get('status')=='completed' and run.get('conclusion') in {'success','failure','cancelled','timed_out','action_required','neutral','skipped','stale'}, 'actual terminal run required')
    require(main.get('object',{}).get('sha')==head, 'actual current main must still match the original binding')
    protection=environment.get('deployment_branch_policy',{})
    require(environment.get('name')==binding.get('environment')=='production-supabase'
            and protection.get('protected_branches') is True and protection.get('custom_branch_policies') is False
            and any(x.get('type')=='required_reviewers' and x.get('reviewers') for x in environment.get('protection_rules',[]) if isinstance(x,dict)),
            'original environment protections required')
    return {'state':'TERMINAL_SNAPSHOT_SHAPE_ONLY_NOT_AUTHORIZATION','run_id':str(run['id']),
            'conclusion':run['conclusion'],'current_main':head,'write':False}


def exact_retirement_plan(levels, binding):
    """Select one fully equal own row, preserving every other JSON row.

    The caller must authenticate the issuer and terminal state separately.
    This pure planner never establishes authority or past write effects.
    """
    require(isinstance(levels,dict) and set(levels)=={'repository','environment'}, 'both actual variable levels required')
    require(isinstance(binding,dict) and isinstance(binding.get('approvalId'),str)
            and binding['approvalId'] and str(binding.get('runId','')).isdigit(), 'exact issued reference and run required')
    before=deepcopy(levels); candidates=[]
    for level in ('repository','environment'):
        row=levels[level]
        require(isinstance(row,dict) and set(row)=={'path','exists','entries','updated_at','raw_sha256'}
                and isinstance(row['path'],str) and type(row['exists']) is bool
                and isinstance(row['entries'],list), 'complete authentic level snapshot required')
        require(row['exists'] or (row['entries']==[] and row['updated_at'] is None and row['raw_sha256'] is None),
                'absent level must not invent value or timestamp')
        if row['exists']:
            require(isinstance(row['updated_at'],str) and row['updated_at'] and isinstance(row['raw_sha256'],str)
                    and len(row['raw_sha256'])==64 and all(c in '0123456789abcdef' for c in row['raw_sha256']),
                    'actual raw value hash and timestamp required')
        for i,item in enumerate(row['entries']):
            require(isinstance(item,dict), 'unclassifiable row: preserve and refuse')
            ref=item.get('approvalId');run=item.get('runId')
            require(ref is not None or run is not None, 'unidentifiable row: preserve and refuse')
            same_ref=ref==binding['approvalId'];same_run=run is not None and str(run)==str(binding['runId'])
            if same_ref or same_run:
                require(same_ref and same_run and item==binding, 'same reference or run differs: preserve and refuse')
                candidates.append((level,i))
    require(len(candidates)<=1, 'duplicate own row or ambiguous levels: preserve and refuse')
    if not candidates:
        return {'state':'NO_OWN_ROW_CURRENTLY_OBSERVED_NOT_A_PAST_WRITE_PROOF','before':before,'write':False}
    level,index=candidates[0]; effective='environment' if levels['environment']['exists'] else 'repository'
    require(level==effective, 'own row only on shadowed level: preserve and refuse')
    after=deepcopy(levels[level]['entries']); removed=after.pop(index)
    require(removed==binding and after==levels[level]['entries'][:index]+levels[level]['entries'][index+1:], 'only exact own row removed')
    return {'state':'EXACT_OWN_ROW_PLAN_ONLY','before':before,'effective_level':level,
            'after_entries':after,'removed':deepcopy(binding),'write':False,
            'server_cas_available':False,'external_edit_race_not_atomic':True}
