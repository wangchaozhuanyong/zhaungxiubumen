"""Candidate only: verify a producer-bound two-parent Git source union.

Caller must authenticate the original source, producer, account, current goal,
source metadata and role before invoking; this does not admit a source or grant
permission. All file paths and commits come from those authenticated sources.
"""
from pathlib import Path
import hashlib
import re
import subprocess
import tempfile

from original_production_delivery import _additive_registration_hunk
from reviewed_web_release import _peer_resolution


def _merge_inputs(scratch, directory, inputs):
    import workflow_control as w
    from paid_three_page_bounded_cms import _replayable_git

    validation = w._VALIDATION_CONTEXT.get()
    # This deterministic merge consumes only the exact supplied blob bytes.
    # Recheck the merge under the existing request commit guard.
    replay = validation is not None

    def run(folder):
        files = [str(folder / label) for label in ('peer', 'ancestor', 'own')]
        for name, raw in zip(files, inputs):
            Path(name).write_bytes(raw)
        command = ['git', 'merge-file', '-p', '-L', 'PEER', '-L', 'BASE', '-L', 'OWN', *files]
        result = _replayable_git(command) if replay else subprocess.run(command, capture_output=True)
        return result.returncode, result.stdout

    if not replay:
        code, output = run(directory)
    else:
        key = ('material_causal_merge', str(scratch), tuple(hashlib.sha256(raw).digest() for raw in inputs))
        if key not in validation.git_object_inputs:
            def reread():
                with tempfile.TemporaryDirectory(dir=scratch) as folder:
                    return run(Path(folder))
            validation.git_object_inputs[key] = {'raw': run(directory), 'reread': reread}
        code, output = validation.git_object_inputs[key]['raw']
    return subprocess.CompletedProcess('git merge-file', code, output)


def verify_causal_merge(*, worktree, site_root, original_head, original_base,
                        current_base, head, tree, original_paths, files,
                        original_target_count, scratch, original_tree=None):
    import professional_web_execution as web
    import workflow_control as w
    original_wt = Path(worktree).resolve(strict=False)
    if not original_wt.is_relative_to(Path(site_root).resolve(strict=True)):
        raise ValueError('original fixed website worktree required')
    if original_wt.is_dir():
        wt = original_wt
    else:
        if not re.fullmatch(r'[0-9a-f]{40}', original_tree or ''):
            raise ValueError('original tree required for missing worktree custody')
        from professional_cms_channel import _immutable_en2_git_reader
        custody, missing = _immutable_en2_git_reader(original_wt, {'cwd': str(site_root)},
                                                      original_head, original_base, original_tree,
                                                      historical_material=True)
        if not missing:
            raise ValueError('exact missing original worktree custody required')
        wt = Path(custody['worktree']).resolve(strict=True)
    if any(not re.fullmatch(r'[0-9a-f]{40}', x or '') for x in
           (original_head, original_base, current_base, head, tree)):
        raise ValueError('exact real Git identities required')
    repository = {'worktree': str(wt), 'historical_material_custody': True}
    def git(*args):
        try:
            return web.git(repository, *args)
        except w.WorkflowError as error:
            raise ValueError('required original Git evidence unavailable') from error
    actual=git('show','-s','--format=%H %P %T',head).decode().strip().split()
    if actual != [head,original_head,current_base,tree] or git('merge-base',original_head,current_base).decode().strip()!=original_base:
        raise ValueError('exact original and peer parents and tree required')
    origin=set(original_paths)
    if not origin or len(origin)!=len(original_paths) or set(git('diff','--name-only',original_base,original_head).decode().splitlines())!=origin:
        raise ValueError('complete original contribution paths required')
    current=set(git('diff','--name-only',current_base,head).decode().splitlines())
    entries={x['repo_path']:x for x in files}
    if len(entries)!=len(files) or set(entries)!=current or not origin.issubset(current):
        raise ValueError('candidate exact path set and all original contributions required')
    extras=current-origin
    if not extras or any(not p.endswith('.test.ts') for p in extras):
        raise ValueError('only the necessary separately checked test deltas may be added')
    if type(original_target_count) is not int or original_target_count <= 0:
        raise ValueError('real original target count required')
    for path,entry in entries.items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('relative original Git path required')
        data=git('show',head+':'+path)
        row=git('ls-tree',head,'--',path).decode().split()
        if len(row)!=4 or row[:3]!=[entry['mode'],'blob',entry['blob']] or row[3]!=path or len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('exact candidate blob, mode and bytes required')
        if path in origin:
            original=git('ls-tree',original_head,'--',path).decode().split()
            if len(original)!=4 or original[0]!=row[0] or original[1]!='blob':
                raise ValueError('original file mode must survive')
    for path in extras:
        before=git('show',current_base+':'+path).decode();after=git('show',head+':'+path).decode()
        patt=r'toHaveLength\((\d+)\)'
        prior=list(re.finditer(patt,before)); matches=[]
        for m in prior:
            n=int(m.group(1)); expected=before[:m.start(1)]+str(n+original_target_count)+before[m.end(1):]
            if expected==after:matches.append(n)
        if len(matches)!=1:
            raise ValueError('one exact target-count correction, all other assertions unchanged')
    conflicts=[]
    with tempfile.TemporaryDirectory(dir=Path(scratch)) as tmp:
        for path in sorted(origin):
            def blob(commit):
                # A successful tree lookup can prove that an optional path
                # is absent. A failed object read cannot prove absence.
                if not git('ls-tree', commit, '--', path):
                    return b''
                return git('show', commit + ':' + path)
            inputs = tuple(blob(commit) for commit in (current_base, original_base, original_head))
            merged = _merge_inputs(Path(scratch), Path(tmp), inputs)
            actual=blob(head)
            if merged.returncode==0:
                if merged.stdout!=actual:raise ValueError('nonconflicting original and peer contributions must be identical: '+path)
                continue
            if merged.returncode<1 or merged.returncode>127:raise ValueError('Git merge reconstruction failed')
            patt=rb'^<<<<<<< PEER\n(.*?)^=======\n(.*?)^>>>>>>> OWN\n'
            blocks=list(re.finditer(patt,merged.stdout,re.M|re.S))
            if len(blocks)!=merged.returncode:raise ValueError('all actual conflict blocks required')
            # A valid two-parent merge may reorder single-line imports before
            # the first executable statement. Authenticate the exact union and
            # each parent's order before normalizing only that import area.
            if path.endswith('.mjs'):
                pattern=rb'^(?:(?:import [^\n]+;\n)|\n)+'
                samples=[blob(original_head),blob(current_base),merged.stdout,actual]
                heads=[re.match(pattern,b) for b in samples]
                if all(heads):
                    sequences=[[x for x in h.group().splitlines(keepends=True) if x.strip()] for h in heads]
                    own,peer,auto,combined=sequences
                    if (all(len(x)==len(set(x)) for x in sequences)
                            and set(combined)==set(own)|set(peer)==set(auto)
                            and [x for x in combined if x in own]==own
                            and [x for x in combined if x in peer]==peer):
                        actual=heads[2].group()+actual[heads[3].end():]
            cursor=0; actual_at=0
            for i,match in enumerate(blocks):
                prefix=merged.stdout[cursor:match.start()]
                if not actual.startswith(prefix,actual_at):raise ValueError('non-conflict prefix changed: '+path)
                actual_at+=len(prefix);nextpos=blocks[i+1].start() if i+1<len(blocks) else len(merged.stdout)
                suffix=merged.stdout[match.end():nextpos]
                if not suffix:raise ValueError('ambiguous adjacent conflict blocks refused')
                end=actual.find(suffix,actual_at)
                if end<0 or actual.find(suffix,end+1)>=0:raise ValueError('one unambiguous original non-conflict context required')
                combined=actual[actual_at:end].decode();left=match[1].decode();right=match[2].decode()
                lines=(left.splitlines(True),right.splitlines(True),combined.splitlines(True))
                if path.endswith(('.yml','.yaml')) and all(lines) and all(x.startswith(' ') for group in lines for x in group):
                    a,b,c=lines
                    if len(set(c))!=len(c) or set(c)!=set(a)|set(b) or [x for x in c if x in a]!=a or [x for x in c if x in b]!=b:
                        raise ValueError('only original ordered CI argument union permitted')
                else:
                    try:_peer_resolution(path,blob(original_base).decode(),left,right,combined)
                    except Exception:
                        _additive_registration_hunk(left,right,combined)
                conflicts.append((path,i));actual_at=end;cursor=match.end()
            suffix=merged.stdout[cursor:]
            if actual[actual_at:]!=suffix:raise ValueError('non-conflict suffix changed')
    return {'head':head,'paths':len(current),'original_paths':len(origin),'extra_tests':len(extras),'conflict_blocks':conflicts}

SCHEMA = 'current-owner-original-custody-causal-merge-successor/v1'


def validate(root, base, item):
    import json
    import workflow_control as w
    import department_autonomy as a
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from original_production_delivery import _source_pin
    from reviewed_web_release import need, same
    root=Path(root).resolve()
    keys={'schema','task_id','scope','original_source_registration','producer_native','report','frozen','gap'}
    need(set(item)==keys and item['schema']==SCHEMA and base.get('current_owner_reviewed_release')
         and isinstance(base.get('source_custody_registration'), dict) and item['task_id']==base['task']
         and item['scope']==base['scope'] and same(root,item['original_source_registration'],base['registration']),
         'one exact original owner reviewed custody and authorized scope required')
    report=a.document(root,item['report']);frozen=a.document(root,item['frozen']);gap=a.document(root,item['gap'])
    native=g._native_document(root,item['producer_native']);binding=base['binding']
    need(all(native.get('thread',{}).get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),
         'real original WEB native fixed identity required')
    turns=[t for t in native.get('turns',[]) if t.get('status')=='completed' and not t.get('error')]
    finals=[m for t in turns for m in t.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer'
            and str((root/item['report']['path']).resolve()) in m.get('text','')]
    need(len(turns)==len(finals)==1,'one actual completed WEB turn pointing at exact report required')
    authorized=a.document(root,base['registration'])
    need(report.get('schema')=='WEB-original-two-materials-current-owner-actual-result/v1'
         and report.get('task_id')==item['task_id'] and report.get('owner')==base['owner']
         and report.get('WEB_executor')==base['role']
         and report.get('in_reply_to_action_id')==base['exact_owner_action']['action_id']
         and report.get('existing_owner_source_registered') is True
         and report.get('human_authorization')==authorized['human']['sha256']
         and report.get('HQ_decision')==authorized['HQ_decision']['sha256']
         and report.get('reviewed_package')==authorized['reviewed_package']['sha256'],
         'same genuine WEB result and exact original owner message required')
    need(gap.get('schema')=='WEB-exact-immutable-custody-and-causal-source-gap-input/v1'
         and gap.get('task_id')==item['task_id'] and gap.get('not_registered_or_adopted') is True
         and gap.get('existing_registered_owner_source')==item['original_source_registration']['sha256']
         and gap.get('existing_registered_event')==base.get('event_id'),
         'same original source event and real previously unregistered gap required')
    ref=report['normal_gate']['specific_dependency']
    need(ref.get('sha256')==item['gap']['sha256'] and ref.get('size')==item['gap']['size']
         and Path(ref['path']).resolve()==(root/item['gap']['path']).resolve(),
         'completed original report must bind exact new gap source')
    need(frozen.get('schema')=='frozen-original-WEB-result-pins/v1' and frozen.get('task_id')==item['task_id']
         and frozen.get('count')==len(frozen.get('pins',[])) and len({p['path'] for p in frozen['pins']})==len(frozen['pins']),
         'actual distinct original producer evidence pins required')
    for pin in frozen['pins']:
        path=Path(pin['path'])
        if path.is_absolute() and not path.resolve().is_relative_to(root): web._external_bytes(pin,binding)
        else:
            actual=w.file_digest(root,pin['path'])
            need(all(actual[k]==pin[k] for k in ('sha256','size'))
                 and (root/actual['path']).resolve()==path.resolve(), 'unchanged local original producer evidence')
    meta=json.loads(_source_pin(root,gap['current_causal_source'],binding))
    code=report['code']; original=meta['files']['immutable-original593']; files=meta['files']['immutable-current539']
    need(meta.get('task_id')==item['task_id'] and meta.get('original_head')==base['commit']
         and meta.get('current_head')==code['head'] and meta.get('current_base')==code['base']
         and meta.get('current_tree')==code['tree'] and meta.get('actual_parents')==code['parents']
         and code['parents']==[base['commit'],code['base']] and code['worktree']==base['worktree']
         and code['branch']==base['branch'] and set(meta['current_paths'])==set(code['changed_paths'])
         and set(x['repo_path'] for x in original)==set(base['paths'])
         and len(base['original_PUB_tuples'])==len(base['registered_protected_body_targets'])==2,
         'same real source lineage and both independent original material targets required')
    result=verify_causal_merge(worktree=base['worktree'],site_root=binding['cwd'],original_head=base['commit'],
        original_base=base['base'],original_tree=base['tree'],current_base=code['base'],head=code['head'],tree=code['tree'],
        original_paths=list(base['paths']),files=files,original_target_count=len(base['original_PUB_tuples']),
        scratch=root/'logs/professional-CMS-channel-source-checks')
    need(result['paths']==len(code['changed_paths']) and result['original_paths']==len(base['paths']),
         'full actual causal contribution scope required')
    for key,left,right in [('forward',code['base'],code['head']),('inverse_source_only',code['head'],code['base'])]:
        need(web._patch_effect(web._patch_delta(_source_pin(root,meta[key],binding)))==
             web._patch_effect(web._patch_delta(web.git({**base,'historical_material_custody':True},
                 'diff','--no-ext-diff','--binary','--full-index',left,right))),
             'exact real original WEB forward and source-only inverse patches required')
    paths={row['repo_path']:row['sha256'] for row in files}
    component={'head':code['head'],'base':code['base'],'paths':paths}
    return {**base,'commit':code['head'],'base':code['base'],'tree':code['tree'],'paths':paths,
            'git_parent':code['parents'][0],'git_parents':code['parents'],'ordinary_increment':True,
            'reviewed_peer_successor':item,'original_peer_overlap_source':item,
            'increment_actor_id':base['actor_id'],'increment_allowed_operations':sorted(web.OPS),
            'increment_source_mode':'current_reviewed_causal_custody_successor','source_components':[component],
            'increment_forward_patch':meta['forward'],'increment_inverse_patch':meta['inverse_source_only']}


def clean_disjoint_successor(ctx, state):
    """Derive only a byte-identical own delta on a genuinely disjoint later base.

    The caller has already authenticated the immutable original producer source.
    This adds no source record, approval, execution or CMS permission.
    """
    import professional_web_execution as web
    from reviewed_web_release import need
    head=state.get('candidate_commit'); base=state.get('candidate_base')
    need(ctx.get('increment_source_mode')=='current_reviewed_causal_custody_successor'
         and ctx.get('increment_registration') and ctx.get('reviewed_peer_successor')
         and all(re.fullmatch('[0-9a-f]{40}',str(x or '')) for x in (head,base))
         and state.get('source_mode','forward')=='forward'
         and state.get('candidate_parent')==ctx['commit']
         and state.get('candidate_parents')==[ctx['commit'],base]
         and state.get('branch')==ctx['branch'] and state.get('worktree')==ctx['worktree'],
         'actual clean successor of the exact adopted custody source required')
    info=web.git(ctx,'show','-s','--format=%H %P %T',head).decode().strip().split()
    need(info==[head,ctx['commit'],base,state.get('candidate_tree')]
         and web.git(ctx,'rev-parse','HEAD').decode().strip()==head
         and web.git(ctx,'branch','--show-current').decode().strip()==ctx['branch']
         and web.git(ctx,'merge-base',ctx['base'],base).decode().strip()==ctx['base']
         and base!=ctx['base'], 'actual tree, ordered parents, current branch and later base required')
    def changed(left,right):
        raw=web.git(ctx,'diff','--name-only','-z',left,right)
        return set(raw.decode('utf-8').split('\0')[:-1]) if raw else set()
    own=set(ctx['paths']); peer=changed(ctx['base'],base)
    need(bool(own) and bool(peer) and not (own & peer)
         and changed(ctx['base'],ctx['commit'])==own
         and changed(base,head)==own and changed(ctx['commit'],head)==peer,
         'exact complete own delta and disjoint peer paths required')
    for path in own:
        old=web.git(ctx,'ls-tree',ctx['commit'],'--',path)
        new=web.git(ctx,'ls-tree',head,'--',path)
        need(old==new and old.split()[:2] in ([b'100644',b'blob'],[b'100755',b'blob']),
             'all original own blobs and modes must remain identical')
    oldpatch=web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',ctx['base'],ctx['commit'])
    newpatch=web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',base,head)
    need(oldpatch==newpatch, 'exact original full binary patch required')
    return head,base


_REBASE_REGISTRATIONS = {
    'scripts/publish-content-trust-fixes.mjs': ('Object.entries({', '...lockedTwoOriginalMaterialBodyCandidates'),
    'supabase/functions/_shared/managed-targets.ts': ('export { ORG020_V7_TARGETS', 'TWO_ORIGINAL_MATERIAL_BODY_TARGETS'),
    'supabase/functions/content-publish/service.ts': ('import { MANAGED_AREAS,', 'TWO_ORIGINAL_MATERIAL_BODY_TARGETS'),
}
_REBASE_COUNT_TESTS = {
    'src/lib/contentPublishNativeBody.test.ts',
    'src/lib/contentPublishOwnerPublisherThree.test.ts',
    'src/lib/contentPublishUnifiedContent.test.ts',
}


def _rebased_patch_effect(path, effect, *, current):
    """Recognize the exact prior contribution adapted to a newer registry."""
    from reviewed_web_release import need
    if path not in _REBASE_REGISTRATIONS and path not in _REBASE_COUNT_TESTS:
        return effect
    removed, added = effect
    marker, token = _REBASE_REGISTRATIONS.get(path, ('expect(historicalTargets).toHaveLength(', None))
    pairs = [[(i, line) for i, line in enumerate(lines) if marker in line] for lines in (removed, added)]
    need(all(len(pair) == 1 for pair in pairs), 'one exact rebased registry edit per original path')
    (left_index, left), (right_index, right) = [pair[0] for pair in pairs]
    if token is not None:
        need(token not in left and right.count(token) == 1
             and right.replace(', ' + token, '', 1) == left,
             'only the original two-material registration may be inserted')
    else:
        pattern = r'(.*expect\(historicalTargets\)\.toHaveLength\()(\d+)(\);)(.*)'
        before, after = (re.fullmatch(pattern, line) for line in (left, right))
        need(before and after and before[1] == after[1] and before[3] == after[3]
             and int(after[2]) == int(before[2]) + 2 and (not current or before[4] == after[4]),
             'the registry test may increase its existing count by exactly two')
    return (removed[:left_index] + removed[left_index + 1:],
            added[:right_index] + added[right_index + 1:])


def reviewed_rebase(root, parent, state):
    """Bind a received original WEB rebase to its exact unchanged own delta."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from paid_three_page_bounded_cms import MATERIAL_PUBLICATION_TASK
    from reviewed_web_release import need

    source = a.document(root, state['material_reviewed_rebase_source'])
    need(set(source) == {'report', 'producer_native'} and parent['task'] == MATERIAL_PUBLICATION_TASK
         and parent.get('increment_source_mode') == 'current_reviewed_causal_custody_successor',
         'only the original reviewed material rebase may use this selector')
    report = a.document(root, source['report'])
    native = g._native_document(root, source['producer_native'])
    binding = parent['binding']
    need(all(native.get('thread', {}).get(k) == binding[v] for k, v in
             {'id':'thread_id', 'title':'title', 'cwd':'cwd', 'hostId':'host_id'}.items()),
         'actual original WEB rebase producer identity required')
    report_path = str((Path(root) / source['report']['path']).resolve())
    turns = native.get('turns', [])
    finals = [item for turn in turns for item in turn.get('items', [])
              if item.get('type') == 'agentMessage' and item.get('phase') == 'final_answer'
              and report_path in item.get('text', '')]
    need(len(turns) == len(finals) == 1 and turns[0].get('status') == 'completed' and not turns[0].get('error')
         and report.get('schema') == 'WEB-materials-current-causal-successor-source-input/v1'
         and report.get('task_id') == parent['task'] and report.get('scope') == parent['scope']
         and report.get('owner') == parent['owner'] and report.get('actual_executor') == parent['role']
         and report.get('parent_source_event') == parent['increment_event_id']
         and report.get('business_source') == parent['registration'],
         'completed original WEB report must bind the exact adopted material predecessor')

    facts = report['git']
    keys = ('candidate_commit', 'candidate_base', 'candidate_parent', 'candidate_parents',
            'candidate_tree', 'branch', 'worktree')
    head, base = (facts[key] for key in keys[:2])
    tree = facts['candidate_tree']
    worktree = Path(facts['worktree']).resolve(strict=True)
    site = Path(binding['cwd']).resolve(strict=True)
    need(state.get('source_mode') == 'forward'
         and all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (head, base, tree))
         and facts['candidate_parent'] == parent['commit'] and facts['candidate_parents'] == [parent['commit'], base]
         and facts['repository'] == parent['repository'] and facts['actor']['id'] == parent['actor_id']
         and worktree.is_relative_to(site) and worktree.parent.name == '.worktrees',
         'same exact forward rebase identities, two parents and isolated original repository required')
    ctx = {**parent, 'worktree': str(worktree), 'branch': facts['branch']}
    history = {**ctx, 'historical_material_custody': True}
    git = lambda *args: web.git(history, *args)
    need(git('show', '-s', '--format=%H %P %T', head).decode().split() == [head, parent['commit'], base, tree]
         and git('merge-base', parent['commit'], base).decode().strip() == parent['base'],
         'actual rebase tree, parents and original integration base required')
    paths = report['own_paths']
    need(set(paths) == set(parent['paths']), 'same exact complete original material paths required')
    def delta(left, right):
        return web._patch_effect(web._patch_delta(git('diff', '--no-ext-diff', '--binary', '--full-index', left, right)))
    previous, proposed = delta(parent['base'], parent['commit']), delta(base, head)
    need(set(previous) == set(proposed) == set(paths), 'no extra or missing rebased path allowed')
    for path, pin in paths.items():
        raw = git('show', head + ':' + path)
        row = git('ls-tree', head, '--', path).decode().split()
        old = git('ls-tree', parent['commit'], '--', path).decode().split()
        need(row == [pin['mode'], 'blob', pin['blob'], path] and old[:2] == row[:2]
             and len(raw) == pin['size'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and _rebased_patch_effect(path, previous[path], current=False)
             == _rebased_patch_effect(path, proposed[path], current=True),
             'original material contribution and file mode must survive the rebase: ' + path)
    exact = {**ctx, 'commit': head, 'base': base, 'tree': tree, 'git_parent': parent['commit'],
            'git_parents': [parent['commit'], base], 'paths': {path: pin['sha256'] for path, pin in paths.items()},
            'increment_registration': state['material_reviewed_rebase_source'],
            'increment_forward_patch': report['forward'], 'increment_inverse_patch': report['inverse_source_only']}
    if state.get('candidate_commit') == head:
        need(all(state.get(key) == facts[key] for key in keys), 'exact authenticated material rebase identity required')
        return exact
    return _advance_reviewed_rebase(exact, state, site)


def _advance_reviewed_rebase(reviewed, state, site):
    """Allow the same reviewed patch on a later base with disjoint changes."""
    import professional_web_execution as web
    from reviewed_web_release import need

    head, base, tree = (state.get(key) for key in ('candidate_commit', 'candidate_base', 'candidate_tree'))
    predecessor = reviewed['git_parent']
    worktree = Path(state['worktree']).resolve(strict=True)
    branch = state.get('branch')
    need(all(re.fullmatch(r'[0-9a-f]{40}', str(value)) for value in (head, base, tree))
         and base != reviewed['base'] and state.get('candidate_parent') == predecessor
         and state.get('candidate_parents') == [predecessor, base]
         and worktree.is_relative_to(site) and worktree.parent.name == '.worktrees'
         and isinstance(branch, str) and branch,
         'exact later material base and original two-parent source required')
    ctx = {**reviewed, 'worktree': str(worktree), 'branch': branch}
    git = lambda *args: web.git(ctx, *args)
    need(git('rev-parse', '--path-format=absolute', '--git-common-dir')
         == web.git(reviewed, 'rev-parse', '--path-format=absolute', '--git-common-dir')
         and git('show', '-s', '--format=%H %P %T', head).decode().split() == [head, predecessor, base, tree]
         and git('merge-base', reviewed['base'], base).decode().strip() == reviewed['base'],
         'actual same repository, later base and exact Git tree required')
    own = set(reviewed['paths'])
    peer = set(git('diff', '--name-only', reviewed['base'], base).decode().splitlines())
    need(peer and own.isdisjoint(peer) and set(git('diff', '--name-only', base, head).decode().splitlines()) == own
         and git('diff', '--no-ext-diff', '--binary', '--full-index', base, head)
         == git('diff', '--no-ext-diff', '--binary', '--full-index', reviewed['base'], reviewed['commit']),
         'later main changes must be disjoint and the complete reviewed patch must stay byte-identical')
    return {**ctx, 'commit': head, 'base': base, 'tree': tree, 'git_parents': [predecessor, base]}


_MATERIAL_REGISTRY_REPAIR = 'c29b09e4cdc4a6a514d9afcda70a0c29b62afe2e'
_MATERIAL_REGISTRY_REPORT = {
    'path': 'logs/handoffs/2026-10-29-two-materials-current-owner-WEB-continuation-v1/designated-development/'
            'actual-currentc5f5a1-20261106.4VNdI2f4/ACTUAL-OWNER-ADDITIONAL-1F92-RECHECK._dntkgoc/'
            'WEB-ACTUAL-PR312-CI-AND-EXACT-TWO-ASSERTION-SUCCESSOR.json',
    'sha256': '887a532e02f9ed0635fec4bbd92b83ad5d8e162978f91dcd5ebddbd3549bd998',
    'size': 5379,
}


def material_registry_test_state(root, base, state):
    """Resolve the shipped parent through its original executed push policy."""
    if state.get('candidate_commit') != _MATERIAL_REGISTRY_REPAIR:
        return None
    import department_autonomy as a
    import workflow_control as w
    from paid_three_page_bounded_cms import MATERIAL_PUBLICATION_TASK
    from reviewed_web_release import need

    report = a.document(root, _MATERIAL_REGISTRY_REPORT)
    execution = a.document(root, report['push'])
    rows = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={'decision_id': report['push_policy']})
    need(len(rows) == 1, 'one original executed material push policy required')
    policy = rows[0]
    request = a.document(root, policy['exact_request'])
    parent = request['state']
    need(base['task'] == report['task_id'] == request['task_id'] == MATERIAL_PUBLICATION_TASK
         and report['owner'] == base['owner'] and report['actual_executor'] == base['role']
         and policy.get('status') == 'allow' and policy.get('department') == base['role']
         and request['operation'] == 'git_push' and request.get('exact_original_production_source') == base['registration']
         and execution['decision_id'] == policy['decision_id'] and execution['action_id'] == request['action_id']
         and execution['result'] == 'pushed_and_read_back'
         and execution['remote_head'] == parent['candidate_commit'] == report['PR']['head']
         and report['PR']['number'] == 312 and report['PR']['state'] == 'open'
         and parent['material_reviewed_rebase_source'] == state['material_reviewed_rebase_source'],
         'exact original published branch predecessor and reviewed material source required')
    return parent


def material_registry_test_successor(root, reviewed, state):
    """Admit only the two original WEB registry expectation repairs for PR 312."""
    import department_autonomy as a
    import professional_web_execution as web
    from reviewed_web_release import need

    report = a.document(root, _MATERIAL_REGISTRY_REPORT)
    parent = reviewed['commit']
    local = report['local_CI_successor']
    head = local['candidate_commit']
    tree = local['candidate_tree']
    worktree = reviewed['worktree']
    git = lambda *args: web.git(reviewed, *args)
    need(head == state.get('candidate_commit') == _MATERIAL_REGISTRY_REPAIR
         and state.get('candidate_parent') == parent and state.get('candidate_parents') == [parent]
         and state.get('candidate_base') == local['candidate_base'] == reviewed['base']
         and state.get('candidate_tree') == tree and state.get('source_mode') == 'forward'
         and state.get('branch') == reviewed['branch'] and state.get('worktree') == worktree
         and git('show', '-s', '--format=%H %P %T', head).decode().split() == [head, parent, tree],
         'exact linear original material test successor and original execution worktree required')
    edits = report['changed_files']
    expected = {'src/lib/contentPublishPaidFourCurrent.test.ts', 'src/lib/managedContentPublishWorkflow.test.ts'}
    need(set(edits) == expected and expected.isdisjoint(reviewed['paths'])
         and set(git('diff', '--name-only', parent, head).decode().splitlines()) == expected,
         'only two exact registry expectation test paths may differ')
    paths = dict(reviewed['paths'])
    for path, pair in edits.items():
        for commit, phase in ((parent, 'before'), (head, 'after')):
            raw = git('show', commit + ':' + path)
            pin = pair[phase]
            need(git('ls-tree', commit, '--', path).decode().split() == ['100644', 'blob', pin['blob'], path]
                 and len(raw) == pin['size'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
                 'actual original WEB reviewed assertion blobs required')
        paths[path] = pair['after']['sha256']
    return {**reviewed, 'commit': head, 'tree': tree, 'git_parent': parent, 'git_parents': [parent],
            'paths': paths, 'existing_pull_number': 312, 'material_registry_test_successor': True}
