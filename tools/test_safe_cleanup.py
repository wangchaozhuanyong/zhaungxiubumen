import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import safe_cleanup as cleanup
import test_runtime_paths
import workflow_control as w


class SafeCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=test_runtime_paths.root())
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.now=dt.datetime.now(dt.timezone.utc)
        (self.root/'.cleanup-simulation.json').write_text(json.dumps({'self_owned_fixture_root':str(self.root)}))
        (self.root/'data').mkdir();self.write('data/task-end.json',{'task_id':'ended-task','status':'completed'})

    def write(self,rel,value):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value) if not isinstance(value,str) else value);return p

    def usage(self,rel='runtime/cache/build.bin',days=8,kind='rebuildable',**changes):
        row={'path':rel,'task_id':'ended-task','task_end':w.file_digest(self.root,'data/task-end.json'),
            'last_used_at':(self.now-dt.timedelta(days=days)).isoformat(),'observed_at':self.now.isoformat(),
            'actively_used':False,'kind':kind,'rebuild_recipe':'synthetic rebuild'}
        row.update(changes);return {'trusted_use_observations':True,'files':[row]}

    def scan(self,usage):return cleanup.scan(self.root,usage,now=self.now,simulation=True)

    def test_rebuildable_ended_unused_file_has_actual_simulated_readback(self):
        p=self.write('runtime/cache/build.bin','rebuildable temporary')
        usage=self.usage();plan=self.scan(usage)
        self.assertEqual(len(plan['items']),1)
        result=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertFalse(p.exists());self.assertTrue(result['results'][0]['source_absent_readback'])
        self.assertFalse(result['production_deletion_executed'])
        self.assertEqual(result['attributable_freed_bytes'],'NOT_MEASURED')

    def test_age_alone_active_and_under_seven_days_are_skipped(self):
        self.write('runtime/cache/build.bin','temporary')
        for usage in [self.usage(days=6),self.usage(actively_used=True),self.usage(rebuild_recipe='')]:
            self.assertEqual(self.scan(usage)['items'],[])
        with self.assertRaises(w.WorkflowError):cleanup.scan(self.root,{'files':[]})

    def test_formal_evidence_and_project_source_are_protected(self):
        for rel in ['reports/old.md','data/end.json','runtime/cache/approval.json','runtime/cache/nested/.git/index','AGENTS.md']:
            self.write(rel,'formal')
            try:self.assertEqual(self.scan(self.usage(rel,days=100))['items'],[])
            except w.WorkflowError:pass  # Unknown/malformed reference state also fails closed.
            self.assertTrue((self.root/rel).exists())

    def test_symlink_parent_leaf_and_path_traversal_are_denied(self):
        outside=self.write('reports/protected.md','formal')
        parent=self.root/'runtime/cache';parent.mkdir(parents=True)
        (parent/'link.bin').symlink_to(outside)
        for rel in ['runtime/cache/link.bin','../outside','/tmp/outside']:
            self.assertEqual(self.scan(self.usage(rel,days=100))['items'],[])
        (self.root/'runtime/temporary').symlink_to(self.root/'reports')
        self.assertEqual(self.scan(self.usage('runtime/temporary/protected.md',days=100))['items'],[])

    def test_existing_reference_or_new_reference_after_freeze_prevents_cleanup(self):
        p=self.write('runtime/cache/build.bin','tmp');usage=self.usage();plan=self.scan(usage)
        self.write('reports/current.json',{'using':'runtime/cache/build.bin'})
        self.assertEqual(self.scan(usage)['items'],[])
        with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertTrue(p.exists())

    def test_file_change_after_freeze_is_preserved(self):
        p=self.write('runtime/cache/build.bin','old');usage=self.usage();plan=self.scan(usage)
        p.write_text('new task has replaced this file')
        with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertIn('new task',p.read_text())

    def test_intermediate_quarantine_is_not_freed_and_needs_thirty_more_days(self):
        p=self.write('drafts/intermediate/old.bin','obsolete');usage=self.usage(str(p.relative_to(self.root)),31,'obsolete_intermediate')
        plan=self.scan(usage);self.assertEqual(plan['items'][0]['action'],'quarantine')
        result=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertEqual(result['results'][0]['status'],'quarantined_not_freed')
        q=next((self.root/'runtime/cleanup-quarantine').rglob('old.bin'))
        newer=self.usage(str(q.relative_to(self.root)),61,'quarantined_intermediate',quarantined_at=(self.now-dt.timedelta(days=29)).isoformat())
        self.assertEqual(self.scan(newer)['items'],[])

    def test_duplicate_keeps_formal_reference_and_missing_keeper_is_denied(self):
        keep=self.write('reports/current.txt','same');self.write('runtime/temporary/duplicate.bin','same')
        self.write('reports/index.json',{'formal_delivery':'reports/current.txt'})
        usage=self.usage('runtime/temporary/duplicate.bin',31,'duplicate',formally_referenced_keeper='reports/current.txt')
        plan=self.scan(usage);self.assertEqual(len(plan['items']),1)
        cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertTrue(keep.exists());self.assertEqual(keep.read_text(),'same')
        self.write('runtime/temporary/duplicate.bin','different')
        self.assertEqual(self.scan(usage)['items'],[])

    def test_hardlink_readback_does_not_claim_expected_size_as_freed(self):
        keep=self.write('runtime/temporary/kept.bin','same inode')
        target=self.root/'runtime/cache/build.bin';target.parent.mkdir();os.link(keep,target)
        usage=self.usage();result=cleanup.simulate_execute(self.root,self.scan(usage),usage,now=self.now)
        self.assertTrue(keep.exists());self.assertEqual(result['attributable_freed_bytes'],'NOT_MEASURED')

    def test_real_workspace_execution_is_disabled_even_with_a_prepared_plan(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage();plan=self.scan(usage)
        (self.root/'.cleanup-simulation.json').unlink()
        with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)

    def test_concurrent_replacement_at_atomic_move_is_restored_and_not_deleted(self):
        p=self.write('runtime/cache/build.bin','old build');usage=self.usage();plan=self.scan(usage)
        original=os.rename
        def replace_during_move(src,dst,*args,**kwargs):
            if src=='build.bin' and kwargs.get('src_dir_fd') is not None:
                fd=kwargs['src_dir_fd'];os.unlink(src,dir_fd=fd)
                output=os.open(src,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd)
                os.write(output,b'new concurrent user content');os.close(output)
            return original(src,dst,*args,**kwargs)
        with mock.patch.object(cleanup.os,'rename',side_effect=replace_during_move):
            with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertEqual(p.read_text(),'new concurrent user content')

    def test_interruption_after_staging_preserves_file_and_forbids_replay(self):
        self.write('runtime/cache/build.bin','rebuildable');usage=self.usage();plan=self.scan(usage)
        original=w.atomic_write_json
        def crash(path,value):
            original(path,value)
            if value.get('status')=='staged_pending_readback':raise OSError('simulated process stop')
        with mock.patch.object(w,'atomic_write_json',side_effect=crash):
            with self.assertRaises(OSError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        journal=next((self.root/'data/maintenance/cleanup-journals').glob('*.json'))
        readback=cleanup.readback_journal(self.root,str(journal.relative_to(self.root)))
        self.assertTrue(readback['staged_file_preserved']);self.assertFalse(readback['reexecution_authorized'])
        with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)

    def test_unadmitted_cleanup_grant_cannot_execute_the_real_consumer(self):
        self.write('data/action-policy.json',{'department_system_upgrade':{'cleanup_admitted':False}})
        self.write('data/human-control-state.json',{'schema_version':1,'paused':False,'revision':1,'project_root':str(self.root)})
        self.write('runtime/cache/build.bin','keep')
        with self.assertRaises(w.WorkflowError):cleanup.execute_admitted_cleanup(self.root,{},self.usage(),{}, {})
        self.assertTrue((self.root/'runtime/cache/build.bin').exists())


if __name__=='__main__':unittest.main()
