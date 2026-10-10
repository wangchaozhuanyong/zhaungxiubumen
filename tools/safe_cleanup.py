"""Frozen company-only cleanup plans; real execution needs exact independent adoption and grant.

Usage and task-end observations are explicit trusted inputs; age alone never admits a file.
Quarantine does not free space. Freed space comes from filesystem readback, not file sizes.
"""
from pathlib import Path
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
import workflow_control as w

PROTECTED = {'data','logs','reports','backups','accounts','assets','library','history','skills',
             'departments','playbooks','prompts','tools','.git','.worktrees','.codex-worktrees','.codex'}
MARKERS = ('receipt','approval','authorization','qa','rights','rollback','delivery','manifest',
           'handoff','ledger','binding','registry','wip','release','publish','license','licence')
ALLOWED = {'runtime/temporary','runtime/cache','drafts/intermediate','runtime/cleanup-quarantine'}



def company_root(root):
    value=Path(root).absolute()
    if value.is_symlink() or any(p.is_symlink() for p in value.parents):
        raise w.WorkflowError('symlink project boundary denied')
    if not value.is_dir():raise w.WorkflowError('existing exact project root required')
    return value.resolve()


def checked_path(root, rel):
    root=Path(root).absolute();p=Path(rel)
    if not isinstance(rel,str) or not rel or p.is_absolute() or any(x in {'.','..'} for x in p.parts):
        raise w.WorkflowError('cleanup requires an exact relative path')
    current=root
    if root.is_symlink():raise w.WorkflowError('symlink project root denied')
    for name in p.parts:
        current=current/name
        if current.is_symlink():raise w.WorkflowError('cleanup symlink or traversal denied')
    if root.resolve() not in current.resolve().parents:raise w.WorkflowError('outside company denied')
    if any(part.casefold() in PROTECTED for part in p.parts) or not any(rel.startswith(a+'/') for a in ALLOWED):
        raise w.WorkflowError('formal/project source or unknown location protected')
    if any(marker in rel.casefold() for marker in MARKERS):raise w.WorkflowError('formal evidence protected')
    return current


def fingerprint(path, parent_fd=None):
    fd=os.open(path.name if parent_fd is not None else path,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):raise w.WorkflowError('only ordinary files eligible')
        h=hashlib.sha256()
        while True:
            data=os.read(fd,1024*1024)
            if not data:break
            h.update(data)
        after=os.fstat(fd)
        if any(getattr(after,k)!=getattr(st,k) for k in ('st_ino','st_dev','st_size','st_mtime_ns','st_nlink')):
            raise w.WorkflowError('file changed during read')
        return {'sha256':h.hexdigest(),'size':st.st_size,'device':st.st_dev,'inode':st.st_ino,
                'mtime_ns':st.st_mtime_ns,'links':st.st_nlink,'allocated_bytes':st.st_blocks*512}
    finally:os.close(fd)


def directory_fd(root, relative):
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in Path(relative).parts:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=next_fd
        return fd
    except BaseException:os.close(fd);raise


def guarded_purge(root,path,expected,simulation,journal,results,free_before,reference_sha=None,reference_targets=None,usage_row=None):
    staging_rel='runtime/cleanup-quarantine/.executing/'+uuid.uuid4().hex+'/'+path.name
    staging=checked_path(root,staging_rel);staging.parent.mkdir(parents=True,mode=0o700,exist_ok=False)
    recovery=root/'data/maintenance/cleanup-recovery'/('purge-'+staging.parent.name+'.json')
    recovery_value={'status':'prepared','original_path':str(path.relative_to(root)),
                    'quarantine_path':'runtime/cleanup-quarantine/.recovery/'+staging.parent.name+'/'+path.name,
                    'staging_path':staging_rel,'fingerprint':expected,'recovery_kind':'purge_staging'}
    w.atomic_write_json(recovery,recovery_value)
    source_fd=directory_fd(root,path.parent.relative_to(root));dest_fd=directory_fd(root,staging.parent.relative_to(root))
    try:
        if (fingerprint(path,source_fd)!=expected or in_use(path,simulation)
                or (reference_sha is not None and reference_state(root,reference_targets)[0]!=reference_sha)):
            raise w.WorkflowError('file bytes/use changed immediately before staging')
        os.rename(path.name,staging.name,src_dir_fd=source_fd,dst_dir_fd=dest_fd)
        try:
            if (fingerprint(staging,dest_fd)!=expected or in_use(staging,simulation)
                    or (reference_sha is not None and reference_state(root,reference_targets)[0]!=reference_sha)):
                raise w.WorkflowError('staged file changed or is now active; preserve it')
        except BaseException:
            # Exclusive link restores a moved concurrent replacement only if the
            # original name is still vacant; it never overwrites new user content.
            try:
                os.link(staging.name,path.name,src_dir_fd=dest_fd,dst_dir_fd=source_fd,follow_symlinks=False)
                os.unlink(staging.name,dir_fd=dest_fd)
            except FileExistsError:pass
            raise
        w.atomic_write_json(journal,{'status':'staged_pending_readback','results':results,
            'staging_path':staging_rel,'original_path':str(path.relative_to(root)),
            'fingerprint':expected,'recovery_record':str(recovery.relative_to(root)),'free_bytes_before':free_before})
        if usage_row is not None:
            ended_task(root,usage_row,simulation)
            if usage_row.get('kind')=='rebuildable':rebuild_evidence(root,usage_row,expected)
        os.unlink(staging.name,dir_fd=dest_fd)
        recovery_value['status']='purged';w.atomic_write_json(recovery,recovery_value)
    finally:os.close(source_fd);os.close(dest_fd)



def guarded_quarantine(root,path,item,simulation,now,plan):
    expected=item['fingerprint']
    tag=hashlib.sha256((item['path']+expected['sha256']).encode()).hexdigest()
    target=checked_path(root,'runtime/cleanup-quarantine/'+tag+'/'+path.name)
    staging=checked_path(root,'runtime/cleanup-quarantine/.executing/'+tag+'/'+path.name)
    record=root/'data/maintenance/cleanup-recovery'/(tag+'.json')
    if target.exists() or staging.exists() or record.exists():
        raise w.WorkflowError('quarantine identity already exists; read back/restore instead of moving again')
    target.parent.mkdir(parents=True,exist_ok=True);staging.parent.mkdir(parents=True,exist_ok=True)
    value={'status':'prepared','original_path':item['path'],'quarantine_path':str(target.relative_to(root)),
           'staging_path':str(staging.relative_to(root)),'fingerprint':expected,'quarantined_at':now.isoformat(),
           'task_id':item['usage']['task_id'],'production_mutation':not simulation}
    w.atomic_write_json(record,value)
    source_fd=directory_fd(root,path.parent.relative_to(root));stage_fd=directory_fd(root,staging.parent.relative_to(root))
    target_fd=directory_fd(root,target.parent.relative_to(root))
    try:
        if fingerprint(path,source_fd)!=expected or in_use(path,simulation):
            raise w.WorkflowError('quarantine path/use/content drift')
        ended_task(root,item['usage'],simulation)
        os.rename(path.name,staging.name,src_dir_fd=source_fd,dst_dir_fd=stage_fd)
        try:
            if (fingerprint(staging,stage_fd)!=expected or in_use(staging,simulation)
                    or reference_state(root,plan['reference_targets'])[0]!=plan['reference_sha256']):
                raise w.WorkflowError('quarantine staging drift; preserve source')
            ended_task(root,item['usage'],simulation)
            os.link(staging.name,target.name,src_dir_fd=stage_fd,dst_dir_fd=target_fd,follow_symlinks=False)
            os.unlink(staging.name,dir_fd=stage_fd)
        except BaseException:
            try:
                os.link(staging.name,path.name,src_dir_fd=stage_fd,dst_dir_fd=source_fd,follow_symlinks=False)
                os.unlink(staging.name,dir_fd=stage_fd)
            except (FileExistsError,FileNotFoundError):pass
            raise
        value['status']='quarantined';w.atomic_write_json(record,value)
        return target,record
    finally:os.close(source_fd);os.close(stage_fd);os.close(target_fd)


def _restore_reference_guard(root, paths, expected_sha=None):
    """Use the existing reference parser afresh before moving any recovery name."""
    targets=[str(path.relative_to(root)) for path in paths]
    try:
        current_sha,refs=reference_state(root,targets)
    except (w.WorkflowError,OSError,ValueError,UnicodeError) as exc:
        raise w.WorkflowError('restore reference state unknown; preserve current files') from exc
    if any(rel in text or str(root/rel) in text for rel in targets for text in refs):
        raise w.WorkflowError('restore valid current reference exists; preserve current files')
    if expected_sha is not None and current_sha!=expected_sha:
        raise w.WorkflowError('restore references changed before move CAS; preserve current files')
    return current_sha


def _restore_quarantine(root,record_pin,*,simulation=False):
    """Exact recovery CAS with exclusive destination, preserving concurrent WIP."""
    root=company_root(root)
    if simulation:
        marker=root/'.cleanup-simulation.json';source=Path(__file__).resolve().parents[1]
        boundary=source.parent/'test-runtime' if source.name=='candidate' else source/'test-runtime'
        if boundary.resolve() not in root.parents or w.read_json(marker)!={'self_owned_fixture_root':str(root)}:
            raise w.WorkflowError('restore simulation requires the exact self-owned fixture')
    rel=record_pin.get('path','') if isinstance(record_pin,dict) else ''
    if not rel.startswith('data/maintenance/cleanup-recovery/'):
        raise w.WorkflowError('only exact cleanup recovery records may restore')
    record=pinned_document(root,record_pin,'quarantine recovery')
    original=checked_path(root,record.get('original_path',''))
    quarantine=checked_path(root,record.get('quarantine_path',''))
    staging=checked_path(root,record.get('staging_path',''))
    expected=record.get('fingerprint')
    if record.get('status')=='restored':
        if original.exists() and fingerprint(original)==expected and not quarantine.exists() and not staging.exists():
            return {'status':'duplicate_ignored','restored_path':record['original_path'],'production_mutation':False,
                    'current_effect':{'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                        'observation_scope':'fresh_read_only_current_effect',
                        'original_currently_exists':True,'quarantine_currently_exists':False,
                        'staging_currently_exists':False,'original_matches_recovery_fingerprint':True,
                        'reexecution_authorized':False}}
        raise w.WorkflowError('restored record readback drift; preserve current files')
    if record.get('status') not in {'quarantined','prepared'} or original.exists():
        raise w.WorkflowError('restore conflict or unknown recovery state; preserve concurrent source')
    present=[p for p in (quarantine,staging) if p.exists()]
    if len(present)!=1 or fingerprint(present[0])!=expected or in_use(present[0],simulation):
        raise w.WorkflowError('exact single preserved quarantine/staging file required')
    paths=[original,quarantine,staging]
    reference_sha=_restore_reference_guard(root,paths)
    source=present[0];original.parent.mkdir(parents=True,exist_ok=True)
    source_fd=directory_fd(root,source.parent.relative_to(root));dest_fd=directory_fd(root,original.parent.relative_to(root))
    try:
        if w.file_digest(root,rel)!=record_pin or fingerprint(source,source_fd)!=expected:
            raise w.WorkflowError('recovery changed before restore CAS')
        holding=checked_path(root,'runtime/cleanup-quarantine/.executing/restore-'+uuid.uuid4().hex+'/'+source.name)
        holding.parent.mkdir(parents=True,exist_ok=False)
        paths.append(holding)
        _restore_reference_guard(root,paths,reference_sha)
        if w.file_digest(root,rel)!=record_pin:
            raise w.WorkflowError('recovery record changed before restore preparation')
        original_record=dict(record)
        record.update(status='prepared',staging_path=str(holding.relative_to(root)))
        w.atomic_write_json(w.safe_path(root,rel),record)
        prepared_pin=w.file_digest(root,rel)
        holding_fd=directory_fd(root,holding.parent.relative_to(root))
        try:
            try:
                if w.file_digest(root,rel)!=prepared_pin or fingerprint(source,source_fd)!=expected or in_use(source,simulation):
                    raise w.WorkflowError('recovery source/record/use changed before restore CAS')
                _restore_reference_guard(root,paths,reference_sha)
            except BaseException:
                if w.file_digest(root,rel)==prepared_pin and not holding.exists():
                    w.atomic_write_json(w.safe_path(root,rel),original_record)
                raise
            os.rename(source.name,holding.name,src_dir_fd=source_fd,dst_dir_fd=holding_fd)
            try:
                if fingerprint(holding,holding_fd)!=expected or in_use(holding,simulation):
                    raise w.WorkflowError('restore source replaced or active; preserve new bytes')
                _restore_reference_guard(root,paths,reference_sha)
                os.link(holding.name,original.name,src_dir_fd=holding_fd,dst_dir_fd=dest_fd,follow_symlinks=False)
                _restore_reference_guard(root,paths,reference_sha)
                os.unlink(holding.name,dir_fd=holding_fd)
            except BaseException:
                try:
                    # A newly referenced/unknown holding file stays tracked by
                    # the prepared recovery record; moving it again could break
                    # a live reference. An exclusive link never overwrites WIP.
                    _restore_reference_guard(root,paths,reference_sha)
                    os.link(holding.name,source.name,src_dir_fd=holding_fd,dst_dir_fd=source_fd,follow_symlinks=False)
                    os.unlink(holding.name,dir_fd=holding_fd)
                    if w.file_digest(root,rel)==prepared_pin:
                        w.atomic_write_json(w.safe_path(root,rel),original_record)
                except (w.WorkflowError,FileExistsError):pass
                raise
        finally:os.close(holding_fd)
        if fingerprint(original,dest_fd)!=expected:raise w.WorkflowError('restored source readback changed; preserve it')
        record.update(status='restored',restored_at=dt.datetime.now(dt.timezone.utc).isoformat())
        w.atomic_write_json(w.safe_path(root,rel),record)
        return {'status':'restored','restored_path':record['original_path'],'production_mutation':not simulation}
    finally:os.close(source_fd);os.close(dest_fd)



def _js_literals(text):
    """Decode static JS/TS strings without evaluating code.

    Comments are skipped; interpolated templates, broken literals and legacy
    octal escapes cannot prove unused state and therefore refuse cleanup.
    """
    values=[];tokens=[];i=0;size=len(text)
    simple={'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f','v':'\v','0':'\0'}
    while i<size:
        if text.startswith('//',i):
            end=text.find('\n',i+2);i=size if end<0 else end+1;continue
        if text.startswith('/*',i):
            end=text.find('*/',i+2)
            if end<0:raise w.WorkflowError('unresolved JS comment makes use state unknown')
            i=end+2;continue
        if text[i]=='/':
            # A regex/division token requires more than static string decoding.
            # Refuse rather than misread regex contents as a comment and lose
            # the quoted reference that follows it.
            raise w.WorkflowError('unsupported JS slash expression makes use state unknown')
        quote=text[i]
        if quote not in "\"'`":
            tokens.append(quote);i+=1;continue
        i+=1;value=[];closed=False
        while i<size:
            char=text[i];i+=1
            if char==quote:closed=True;break
            if quote=='`' and char=='$' and i<size and text[i]=='{':
                raise w.WorkflowError('dynamic JS template makes use state unknown')
            if char!='\\':
                if char in '\r\n' and quote!='`':raise w.WorkflowError('unresolved JS string makes use state unknown')
                value.append(char);continue
            if i>=size:raise w.WorkflowError('incomplete JS escape makes use state unknown')
            escape=text[i];i+=1
            if escape in '\r\n':
                if escape=='\r' and i<size and text[i]=='\n':i+=1
                continue
            if escape in {'u','x'}:
                width=4 if escape=='u' else 2
                braced=escape=='u' and i<size and text[i]=='{'
                if braced:
                    end=text.find('}',i+1)
                    if end<0:raise w.WorkflowError('incomplete JS Unicode escape')
                    raw=text[i+1:end];i=end+1
                    if not 1<=len(raw)<=6:raise w.WorkflowError('invalid JS Unicode escape')
                else:raw=text[i:i+width];i+=width
                if not raw or any(c not in '0123456789abcdefABCDEF' for c in raw) or (not braced and len(raw)!=width):
                    raise w.WorkflowError('invalid JS Unicode escape')
                number=int(raw,16)
                if number>0x10ffff:raise w.WorkflowError('invalid JS Unicode code point')
                value.append(chr(number));continue
            if escape.isdigit() and (escape!='0' or i<size and text[i].isdigit()):
                raise w.WorkflowError('legacy JS octal escape makes use state unknown')
            value.append(simple.get(escape,escape))
        if not closed:raise w.WorkflowError('unclosed JS string makes use state unknown')
        values.append(''.join(value));tokens.append(' STRING_LITERAL ')
    # This lexer cannot prove arbitrary application expressions have no path.
    # Accept only declarations consisting of literal/primitive atoms; calls,
    # property/index access, operators and other executable forms stay unknown.
    import re
    primitive=r'(?:STRING_LITERAL|true|false|null|[0-9]+(?:\.[0-9]+)?)'
    declaration=rf'(?:(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*)?{primitive}\s*;?'
    remainder=''.join(tokens).strip()
    while remainder:
        match=re.match(declaration,remainder)
        if match is None:
            raise w.WorkflowError('computed or unsupported JS expression makes use state unknown')
        remainder=remainder[match.end():].strip()
    return values


def _reference_text(path, data, root):
    text=data.decode('utf-8',errors='strict')
    # Resolve literal paths relative to either the project or the referring
    # file. Never evaluate application code. Bare target basenames are a
    # conservative reference when a dynamic expression cannot be resolved.
    literals=[]
    if path.suffix.casefold() in {'.js','.mjs','.cjs','.jsx','.ts','.tsx'}:
        js_values=_js_literals(text)
        literals += js_values+[''.join(js_values)]
    if path.suffix.casefold() in {'.json','.jsonl'}:
        def collect(value):
            if isinstance(value,str):literals.append(value)
            elif isinstance(value,dict):
                for k,v in value.items():collect(k);collect(v)
            elif isinstance(value,list):
                for v in value:collect(v)
        try:
            if path.suffix.casefold()=='.json':collect(json.loads(text))
            else:
                for line in text.splitlines():
                    if line.strip():collect(json.loads(line))
        except ValueError:raise w.WorkflowError('unparseable reference JSON makes use state unknown')
    if path.suffix.casefold()=='.py':
        try:
            tree=ast.parse(text)
        except SyntaxError:
            raise w.WorkflowError('unparseable reference code makes use state unknown')
        def path_literal(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
            if isinstance(node,ast.Name) and node.id in {'root','ROOT'}:return str(root)
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Div,ast.Add)):
                left,right=path_literal(node.left),path_literal(node.right)
                if left is not None and right is not None:return left+'/'+right if isinstance(node.op,ast.Div) else left+right
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'Path','str'} and len(node.args)==1:
                return path_literal(node.args[0])
            return None
        for node in ast.walk(tree):
            value=path_literal(node)
            if value is not None and len(value)<4096:literals.append(value)
    # Text paths also cover TOML/JSON/JS/shell/template entry points.
    import re
    literals+=re.findall(r'[^\s\"\'<>]+',text)
    for token in re.findall(r'"(?:[^"\\]|\\.)*"',text):
        try:value=ast.literal_eval(token)
        except (ValueError,SyntaxError):continue
        if isinstance(value,str):literals.append(value)
    resolved=[]
    for value in literals:
        if '\n' in value or '\x00' in value:continue
        candidate=Path(value)
        for origin in (root,path.parent):
            absolute=(candidate if candidate.is_absolute() else origin/candidate).resolve(strict=False)
            if absolute.is_relative_to(root):resolved.append(str(absolute))
    return text+'\n'+'\n'.join(resolved)


def reference_state(root, targets=None):
    """Hash current reference-bearing files and their membership, never print their contents."""
    root=Path(root);records=[];refs=[]
    suffixes={'.json','.jsonl','.md','.toml','.txt','.yaml','.yml','.py','.pyi','.js','.mjs','.cjs','.ts','.tsx','.jsx','.sh','.ini','.cfg','.conf','.html','.css','.vue','.svelte','.xml'}
    folders=['data','logs','reports','backups','history','skills','departments','playbooks','prompts','.codex','.github','tools','scripts','ci','examples','drafts','runtime']
    paths=[]
    for base in folders:
        folder=root/base
        if folder.is_symlink():raise w.WorkflowError('reference root symlink makes use state unknown')
        if not folder.exists():continue
        for directory,dirs,files in os.walk(folder,followlinks=False):
            if any((Path(directory)/d).is_symlink() for d in dirs):
                raise w.WorkflowError('reference symlink makes use state unknown')
            for name in sorted(files):
                path=Path(directory)/name
                if path.is_symlink():raise w.WorkflowError('reference symlink makes use state unknown')
                rel=str(path.relative_to(root))
                if rel in (targets or []) and any(rel.startswith(a+'/') for a in ALLOWED):continue
                if rel=='data/maintenance/cleanup-usage.json' or rel.startswith(('data/maintenance/cleanup-plans/','data/maintenance/cleanup-journals/','data/maintenance/cleanup-observations/','data/maintenance/cleanup-recovery/')):continue
                if path.suffix.casefold() in suffixes or path.name.startswith('.env'):paths.append(path)
    paths += [p for p in root.iterdir() if p.is_file() and (p.suffix.casefold() in suffixes or p.name.startswith('.env'))]
    needles=([str(t) for t in targets]+[str(root/t) for t in targets]+[Path(t).name for t in targets]) if targets else []
    for path in sorted(set(paths)):
        if path.is_symlink():raise w.WorkflowError('reference symlink denied')
        if path.name.startswith('.env'):raise w.WorkflowError('secret-bearing reference source is protected; use state unknown')
        before=fingerprint(path)
        data=path.read_bytes()
        if fingerprint(path)!=before or hashlib.sha256(data).hexdigest()!=before['sha256']:
            raise w.WorkflowError('reference changed during observation')
        text=_reference_text(path,data,root)
        if any(n in text for n in needles):text+='\n'+'\n'.join(str(root/t) for t in (targets or []) if Path(t).name in text)
        records.append([str(path.relative_to(root)),before['sha256']]);refs.append(text)
    records.sort()
    return hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),refs


def in_use(path, simulation):
    if simulation:
        return False  # Only the explicit self-owned fixture, never a production assumption.
    try:
        r=subprocess.run(['lsof','-t','--',str(path)],capture_output=True,text=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):raise w.WorkflowError('open-file use is unknown')
    if r.returncode not in (0,1) or r.stderr.strip():raise w.WorkflowError('open-file use is unknown')
    return bool(r.stdout.strip())



def pinned_document(root, pin, purpose):
    if not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin:
        raise w.WorkflowError(purpose+' exact evidence pin required')
    return w.read_json(w.safe_path(root,pin['path']))


def continuous_nonuse(root,row,now,minimum_days):
    value=pinned_document(root,row.get('nonuse_evidence'),'continuous nonuse')
    start=w._parse_observed_at(value.get('coverage_start'))
    end=w._parse_observed_at(value.get('coverage_end'))
    if (value.get('path')!=row['path'] or value.get('task_id')!=row['task_id']
            or value.get('source')!='existing_usage_history' or value.get('continuous') is not True
            or value.get('no_use_observed') is not True or start is None or end is None
            or not 0 <= (now-end).total_seconds() <= 300
            or (end-start).total_seconds()<minimum_days*86400):
        raise w.WorkflowError('continuous unused coverage missing; last-used/mtime alone is insufficient')
    return value


def rebuild_evidence(root,row,pin):
    value=pinned_document(root,row.get('rebuild_evidence'),'rebuild and recovery')
    inputs=value.get('source_pins')
    if (value.get('task_id')!=row['task_id'] or value.get('path')!=row['path']
            or not isinstance(value.get('command'),str) or not value['command'].strip()
            or value.get('rebuild_verified') is not True or value.get('recovery_verified') is not True
            or value.get('rights_preserved') is not True or not isinstance(inputs,list) or not inputs
            or any(w.file_digest(root,x.get('path',''))!=x for x in inputs if isinstance(x,dict))
            or any(not isinstance(x,dict) for x in inputs)
            or not isinstance(value.get('output_sha256'),str) or value['output_sha256']!=pin['sha256']):
        raise w.WorkflowError('exact source/rebuild/recovery/rights evidence required')
    return value


def ended_task(root,row,simulation):
    ended=pinned_document(root,row.get('task_end'),'ended task')
    if ended.get('task_id')!=row.get('task_id') or ended.get('status') not in {'completed','cancelled'}:
        raise w.WorkflowError('task not ended')
    if not simulation:
        native,invalid=w._validate_receipt_chain(root,row.get('task_id',''))
        decisions=[r for r in w._result_handoff_rows(root,row['task_id']) if r.get('event')=='controller_decision']
        state=w.read_json(w.snapshot_path(root,row['task_id'])).get('current_state')
        if (invalid or not native or not decisions or decisions[-1].get('decision')!='close_scope'
                or state not in {'closed','cancelled'} or w.validate_workflow_events(root,row['task_id'])):
            raise w.WorkflowError('native ended-task proof missing; metadata alone cannot admit cleanup')


def scan(root, usage, *, now=None, simulation=False):
    root=company_root(root);now=now or dt.datetime.now(dt.timezone.utc)
    if usage.get('trusted_use_observations') is not True or not isinstance(usage.get('files'),list):
        raise w.WorkflowError('explicit actual use observations required; mtime is insufficient')
    if any(not isinstance(row,dict) for row in usage['files']):
        raise w.WorkflowError('cleanup usage rows must be objects')
    reference_targets=[row.get('path','') for row in usage['files'] if row.get('path')]
    reference_targets += [row['formally_referenced_keeper'] for row in usage['files'] if row.get('formally_referenced_keeper')]
    try:
        reference_sha,refs=reference_state(root,reference_targets)
    except w.WorkflowError as exc:
        # Unknown reference parsing or aliases protect every target; a dry-run
        # reports UNPROVEN and returns no eligible grant, without live mutation.
        return {'schema_version':1,'project_root':str(root),'created_at':now.isoformat(),
                'reference_sha256':None,'reference_targets':reference_targets,'reference_state':'UNPROVEN',
                'items':[],'skipped':[{'path':row.get('path',''),'reason':str(exc)} for row in usage['files']],
                'simulation_only':simulation,'deletion_executed':False,'business_goal_closed':False}
    items=[];skips=[];seen=set()
    duplicates={rel for rel in reference_targets if reference_targets.count(rel)>1}
    for row in usage['files']:
        rel=row.get('path','')
        try:
            if rel in duplicates or rel in seen:raise w.WorkflowError('duplicate usage path is not an exact observation')
            seen.add(rel);path=checked_path(root,rel);pin=fingerprint(path)
            used=w._parse_observed_at(row.get('last_used_at'));observed=w._parse_observed_at(row.get('observed_at'))
            ended_task(root,row,simulation)
            if (used is None or observed is None or not 0 <= (now-observed).total_seconds() <= 300
                    or row.get('actively_used') is not False or in_use(path,simulation)):
                raise w.WorkflowError('actively used, stale or unknown use')
            if any(rel in text or str(path) in text for text in refs):raise w.WorkflowError('valid reference exists')
            effective_used=max(used,dt.datetime.fromtimestamp(path.stat().st_mtime,dt.timezone.utc)) if not simulation else used
            days=(now-effective_used).total_seconds()/86400;kind=row.get('kind')
            if kind=='rebuildable' and days>=7:
                continuous_nonuse(root,row,now,7);rebuild_evidence(root,row,pin);action='purge'
            elif kind=='obsolete_intermediate' and days>=30:
                continuous_nonuse(root,row,now,30);action='quarantine'
            elif kind=='quarantined_intermediate' and days>=30:
                q=w._parse_observed_at(row.get('quarantined_at'))
                if q is None or (now-q).total_seconds()<30*86400:raise w.WorkflowError('quarantine under 30 days')
                continuous_nonuse(root,row,now,30)
                recovery=pinned_document(root,row.get('quarantine_record'),'quarantine recovery')
                if (recovery.get('status')!='quarantined' or recovery.get('quarantine_path')!=rel
                        or recovery.get('quarantined_at')!=row.get('quarantined_at')
                        or recovery.get('fingerprint')!=pin):
                    raise w.WorkflowError('exact quarantine recovery record required')
                action='purge'
            elif kind=='duplicate' and row.get('formally_referenced_keeper'):
                keeper_rel=Path(row['formally_referenced_keeper'])
                if keeper_rel.is_absolute() or '..' in keeper_rel.parts:raise w.WorkflowError('unsafe keeper')
                keeper=root/keeper_rel
                current=root
                for part in keeper_rel.parts:
                    current=current/part
                    if current.is_symlink():raise w.WorkflowError('keeper symlink denied')
                if keeper==path or fingerprint(keeper)['sha256']!=pin['sha256']:
                    raise w.WorkflowError('duplicate keeper missing or bytes differ')
                if not any(str(keeper.relative_to(root)) in text or str(keeper) in text for text in refs):
                    raise w.WorkflowError('keeper is not formally referenced')
                if days<30:raise w.WorkflowError('duplicate intermediate under 30 days')
                continuous_nonuse(root,row,now,30);action='quarantine'
            else:raise w.WorkflowError('age, reconstruction or quarantine gate not met')
            items.append({'path':rel,'fingerprint':pin,'action':action,'usage':row})
        except (w.WorkflowError,OSError,ValueError,UnicodeError) as e:skips.append({'path':rel,'reason':str(e)})
    return {'schema_version':1,'project_root':str(root),'created_at':now.isoformat(),
            'reference_sha256':reference_sha,'reference_targets':reference_targets,'items':items,'skipped':skips,'simulation_only':simulation,
            'deletion_executed':False,'business_goal_closed':False}


def simulate_execute(root, plan, usage, *, now=None):
    root=company_root(root);marker=root/'.cleanup-simulation.json'
    source=Path(__file__).resolve().parents[1]
    allowed_runtime=source.parent/'test-runtime' if source.name=='candidate' else source/'test-runtime'
    # Immutable candidate boundary: no switch or --owner-approved bypass for a real workspace.
    if (allowed_runtime.resolve() not in root.parents or not marker.is_file() or marker.is_symlink()
            or w.read_json(marker)!={'self_owned_fixture_root':str(root)}):
        raise w.WorkflowError('candidate execution is restricted to its exact self-owned simulation')
    return _execute_files(root,plan,usage,now=now,simulation=True)


def _execute_files(root,plan,usage,*,now=None,simulation=False):
    now=now or dt.datetime.now(dt.timezone.utc)
    if plan.get('project_root')!=str(root):raise w.WorkflowError('plan project differs')
    free_before=shutil.disk_usage(root).free;results=[]
    journal=root/'data/maintenance/cleanup-journals'/(('simulation-' if simulation else 'cleanup-')+hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()+'.json')
    if journal.exists():
        old=w.read_json(journal)
        if old.get('status')=='complete':
            return {'status':'duplicate_ignored','results':old.get('results',[]),'journal':str(journal.relative_to(root)),
                    'results_observation':'immutable_historical_completed_journal',
                    'current_effect':readback_journal(root,str(journal.relative_to(root))),
                    'production_deletion_executed':False,'production_mutation':False,
                    'attributable_freed_bytes':'NOT_MEASURED'}
        raise w.WorkflowError('execution journal already exists; read back interruption before any re-execution')
    refreshed=scan(root,usage,now=now,simulation=simulation)
    if refreshed['reference_sha256']!=plan['reference_sha256'] or refreshed['items']!=plan['items']:
        raise w.WorkflowError('references, usage or bytes changed; freeze a new plan')
    w.atomic_write_json(journal,{'status':'executing','plan_sha256':hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest(),'results':results,'free_bytes_before':free_before})
    for item in plan['items']:
        path=checked_path(root,item['path'])
        ended_task(root,item['usage'],simulation)
        continuous_nonuse(root,item['usage'],now,7 if item['usage']['kind']=='rebuildable' else 30)
        if reference_state(root,plan.get("reference_targets"))[0]!=plan['reference_sha256'] or fingerprint(path)!=item['fingerprint'] or in_use(path,simulation):
            raise w.WorkflowError('pre-execution path/reference/content drift')
        if item['action']=='quarantine':
            target,record=guarded_quarantine(root,path,item,simulation,now,plan)
            status='quarantined_not_freed'
        else:
            guarded_purge(root,path,item['fingerprint'],simulation,journal,results,free_before,
                          plan['reference_sha256'],plan.get('reference_targets'),item['usage'])
            status='purged_self_owned_fixture' if simulation else 'purged_admitted_rebuildable_or_quarantined_file'
        results.append({'path':item['path'],'status':status,'source_absent_readback':not path.exists(),
                        'quarantine_path':str(target.relative_to(root)) if item['action']=='quarantine' else None,
                        'quarantined_at':now.isoformat() if item['action']=='quarantine' else None,
                        'quarantine_record':str(record.relative_to(root)) if item['action']=='quarantine' else None,
                        'expected_allocated_bytes':item['fingerprint']['allocated_bytes']})
        w.atomic_write_json(journal,{'status':'executing','results':results,'free_bytes_before':free_before})
    free_after=shutil.disk_usage(root).free
    w.atomic_write_json(journal,{'status':'complete','results':results,'free_bytes_before':free_before,'free_bytes_after':free_after,'attributable_freed_bytes':'NOT_MEASURED'})
    return {'status':'simulation_complete' if simulation else 'admitted_cleanup_complete','results':results,'free_bytes_before':free_before,
        'free_bytes_after':free_after,'observed_free_bytes_delta':free_after-free_before,
        'attributable_freed_bytes':'NOT_MEASURED','journal':str(journal.relative_to(root)),
        'production_deletion_executed':not simulation and any(x['status'].startswith('purged_') for x in results),
        'production_mutation':not simulation and bool(results)}


def _admission(root,plan_pin,grant_pin,request,operation):
    """Existing exact grant keys, current independent goal review, no QA1/QA2 chain."""
    import goal_delivery_runtime as g,qa_review_plan as q
    cfg=w.load_policy(root).get('department_system_upgrade',{})
    if (cfg.get('cleanup_admitted') is not True or w.file_digest(root,plan_pin.get('path',''))!=plan_pin
            or cfg.get('cleanup_grants',{}).get(plan_pin['sha256'])!=grant_pin):
        raise w.WorkflowError('independent adoption plus frozen exact cleanup grant required')
    grant=pinned_document(root,grant_pin,'cleanup grant')
    task_id=w.validate_task_id(grant.get('task_id',''))
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task_id)))
    goal=snapshot.get('goal_delivery',{})
    actor='operations-assistant-3'
    if (not g.enabled(root,snapshot) or grant.get('cleanup_plan')!=plan_pin
            or grant.get('scope')!='company_cleanup:'+plan_pin['sha256']
            or grant['scope'] not in goal.get('authorized_scope',[]) or grant.get('risk_level')!='R0'
            or grant.get('actor_role')!=actor or actor not in goal.get('producer_departments',[])
            or grant.get('responsible_assistant')!=goal.get('responsible_assistant')
            or grant.get('authority')!=goal.get('authorization_pin')
            or operation not in grant.get('allowed_operations',[])):
        raise w.WorkflowError('current exact original cleanup goal and authority required')
    if w.file_digest(root,goal['authorization_pin']['path'])!=goal['authorization_pin']:
        raise w.WorkflowError('cleanup human authorization changed')
    rows,invalid=w._validate_receipt_chain(root,task_id)
    reviewer=q.reviewer_department(root,snapshot)
    qa=[r for r in rows if r.get('receipt_type')=='qa_verdict' and r.get('department')==reviewer]
    if invalid or not qa or qa[-1].get('verdict')!='pass' or reviewer in goal['producer_departments']:
        raise w.WorkflowError('exact independently accepted cleanup plan required')
    q.validate_verdict(root,snapshot,rows,qa[-1])
    review=q.load_plan(root,snapshot)
    if not review or review.get('candidate')!=plan_pin:
        raise w.WorkflowError('cleanup plan differs from independently reviewed candidate')
    adoption=grant.get('tool_adoption',{})
    proof=w._verify_operations_rework_completion(root,adoption,adoption.get('task_id',''))
    applied=w.read_json(w.safe_path(root,proof['control_applied_proof']['path']))
    runtime=w.file_digest(root,'tools/safe_cleanup.py')
    if runtime not in applied.get('applied_files',[]) or Path(__file__).resolve()!=w.safe_path(root,runtime['path']).resolve():
        raise w.WorkflowError('exact adopted cleanup runtime required; candidate is not executable authority')
    plan=pinned_document(root,plan_pin,'cleanup plan')
    if plan.get('project_root')!=str(root) or plan.get('simulation_only') is not False:
        raise w.WorkflowError('production cleanup requires real company-only observations')
    if (operation=='execute' and any(x.get('action')=='purge' for x in plan.get('items',[]))
            and grant.get('irreversible_delete_confirmed') is not True):
        raise w.WorkflowError('separate exact irreversible deletion confirmation required')
    return grant,plan


def execute_admitted_cleanup(root, plan_pin, usage, grant_pin, request):
    """Future adopted consumer. This candidate neither issues nor invokes real grants."""
    import result_coordination as c
    root=company_root(root)
    with c.coordination_lock(root),w.workflow_lock(root):
        grant,plan=_admission(root,plan_pin,grant_pin,request,'execute')
        identity=c.exact_identity(grant);c._validate_queued(root,identity)
        store=c.CoordinationStore(root)
        try:
            # The plan producer executes after independent acceptance; do not use
            # a reviewer lease to make its producer self-review or steal a claim.
            store._lease(identity,grant['responsible_assistant'],request.get('coordinator_owner'),request.get('coordination_claim'))
            result=_execute_files(root,plan,usage,simulation=False)
            if result['status']!='duplicate_ignored':
                store._begin();store._audit(identity,'exact_cleanup_executed',{
                    'plan':plan_pin,'actor_role':'operations-assistant-3','result':result});store.conn.commit()
            return result
        finally:
            if store.conn.in_transaction:store.conn.rollback()
            store.close()



def simulate_restore(root,record_pin):
    return _restore_quarantine(root,record_pin,simulation=True)


def restore_admitted_cleanup(root,plan_pin,grant_pin,request):
    import result_coordination as c
    root=company_root(root)
    with c.coordination_lock(root),w.workflow_lock(root):
        grant,plan=_admission(root,plan_pin,grant_pin,request,'restore')
        recovery=request.get('quarantine_record')
        if recovery not in grant.get('recovery_records',[]):
            raise w.WorkflowError('restore record outside exact admitted recovery scope')
        identity=c.exact_identity(grant);c._validate_queued(root,identity)
        store=c.CoordinationStore(root)
        try:
            store._lease(identity,grant['responsible_assistant'],request.get('coordinator_owner'),request.get('coordination_claim'))
            result=_restore_quarantine(root,recovery)
            store._begin();store._audit(identity,'exact_cleanup_restored',{
                'record':recovery,'actor_role':'operations-assistant-3','result':result});store.conn.commit()
            return result
        finally:
            if store.conn.in_transaction:store.conn.rollback()
            store.close()


def readback_journal(root, path):
    """Interruption readback only; a journal never authorizes re-execution."""
    root=company_root(root);value=w.read_json(w.safe_path(root,path));rows=[]
    for item in value.get('results',[]):
        source=checked_path(root,item['path'])
        exists=source.exists()
        rows.append({**item,'historical_source_absent_readback':item.get('source_absent_readback'),
                     'source_absent_readback':not exists,'source_currently_exists':exists})
    staged=value.get('staging_path')
    staging=checked_path(root,staged) if staged else None
    return {'status':value.get('status','unknown'),'items':rows,
            'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'observation_scope':'fresh_read_only_current_effect',
            'staged_file_preserved':bool(staging and staging.exists()),
            'staged_fingerprint':fingerprint(staging) if staging and staging.is_file() and not staging.is_symlink() else None,
            'recovery_record':w.file_digest(root,value['recovery_record']) if value.get('recovery_record') else None,
            'reexecution_authorized':False,
            'next_action':'verify exact native effects and freeze remaining scope; never replay the old journal'}


def command(root,args):
    """Minimal flashcast_ops handler. No legacy mtime maintenance dispatch."""
    root=company_root(root)
    if args.mode=='readback':
        if not args.readback:raise w.WorkflowError('readback requires exact journal path')
        return readback_journal(root,args.readback),[]
    if args.mode in {'execute','restore'}:
        if not all([args.plan,args.grant,args.request]):raise w.WorkflowError('exact plan/grant/claim request required')
        request=w.read_json(w.safe_path(root,args.request))
        plan=w.file_digest(root,args.plan);grant=w.file_digest(root,args.grant)
        if args.mode=='restore':return restore_admitted_cleanup(root,plan,grant,request),[]
        if not args.usage:raise w.WorkflowError('execution requires fresh exact usage observations')
        return execute_admitted_cleanup(root,plan,w.read_json(w.safe_path(root,args.usage)),grant,request),[]
    if not args.usage or not args.output:raise w.WorkflowError('scan requires exact usage and project-owned output')
    output=w.safe_path(root,args.output)
    if not str(output.relative_to(root)).startswith('data/maintenance/cleanup-plans/'):
        raise w.WorkflowError('frozen plans must remain in data/maintenance/cleanup-plans/')
    result=scan(root,w.read_json(w.safe_path(root,args.usage)))
    if output.exists():
        if w.read_json(output)!=result:raise w.WorkflowError('existing frozen cleanup plan cannot be overwritten')
    else:w.atomic_write_json(output,result)
    return {'items':len(result['items']),'skipped':len(result['skipped']),'execution':'not_requested','plan':w.file_digest(root,args.output)},[output]


def configure_parser(parser):
    parser.add_argument('--mode',choices=['scan','execute','readback','restore'],default='scan')
    for name in ('usage','output','plan','grant','request','readback'):parser.add_argument('--'+name)
    parser.set_defaults(handler=command)
    return parser


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    configure_parser(p)
    a=p.parse_args()
    result,_=command(a.root,a)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
