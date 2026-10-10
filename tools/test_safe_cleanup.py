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
        row.update(changes)
        self.write('tools/rebuild-input.txt','synthetic fixture recipe source')
        history={'path':rel,'task_id':row['task_id'],'source':'existing_usage_history','continuous':True,
                 'no_use_observed':True,'coverage_start':(self.now-dt.timedelta(days=days)).isoformat(),
                 'coverage_end':self.now.isoformat()}
        self.write('data/maintenance/cleanup-observations/nonuse.json',history)
        row['nonuse_evidence']=w.file_digest(self.root,'data/maintenance/cleanup-observations/nonuse.json')
        if (self.root/rel).is_file() and not (self.root/rel).is_symlink():
            recovery={'path':rel,'task_id':row['task_id'],'source_pins':[w.file_digest(self.root,'tools/rebuild-input.txt')],
                      'command':'synthetic fixture rebuild','rebuild_verified':True,'recovery_verified':True,
                      'rights_preserved':True,'output_sha256':cleanup.fingerprint(self.root/rel)['sha256']}
            self.write('data/maintenance/cleanup-observations/rebuild.json',recovery)
            row['rebuild_evidence']=w.file_digest(self.root,'data/maintenance/cleanup-observations/rebuild.json')
        if row.get('rebuild_recipe')=='':row['rebuild_evidence']=None
        return {'trusted_use_observations':True,'files':[row]}

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


    def test_last_used_alone_without_continuous_history_is_denied(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage()
        usage['files'][0].pop('nonuse_evidence')
        self.assertEqual(self.scan(usage)['items'],[])

    def test_nonuse_coverage_short_future_stale_and_wrong_identity_are_denied(self):
        self.write('runtime/cache/build.bin','tmp')
        for changes in ({'coverage_start':(self.now-dt.timedelta(days=6)).isoformat()},
                        {'coverage_end':(self.now-dt.timedelta(seconds=301)).isoformat()},
                        {'coverage_end':(self.now+dt.timedelta(seconds=1)).isoformat()},
                        {'path':'runtime/cache/other.bin'},{'task_id':'another-task'},
                        {'continuous':False},{'no_use_observed':False}):
            usage=self.usage();pin=usage['files'][0]['nonuse_evidence']
            value=w.read_json(self.root/pin['path']);value.update(changes);self.write(pin['path'],value)
            usage['files'][0]['nonuse_evidence']=w.file_digest(self.root,pin['path'])
            self.assertEqual(self.scan(usage)['items'],[])

    def test_rebuild_recipe_string_or_missing_rights_and_changed_source_cannot_admit(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage()
        row=usage['files'][0];pin=row.pop('rebuild_evidence')
        self.assertEqual(self.scan(usage)['items'],[])
        value=w.read_json(self.root/pin['path']);value['rights_preserved']=False
        self.write(pin['path'],value);row['rebuild_evidence']=w.file_digest(self.root,pin['path'])
        self.assertEqual(self.scan(usage)['items'],[])
        usage=self.usage();self.write('tools/rebuild-input.txt','changed recipe')
        self.assertEqual(self.scan(usage)['items'],[])

    def test_duplicate_complete_plan_reads_back_without_second_mutation(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage();plan=self.scan(usage)
        first=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        second=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertEqual(second['status'],'duplicate_ignored')
        self.assertEqual(first['results'],second['results']);self.assertFalse(second['production_deletion_executed'])

    def quarantine(self):
        original=self.write('drafts/intermediate/old.bin','obsolete self-owned fixture')
        usage=self.usage('drafts/intermediate/old.bin',31,'obsolete_intermediate')
        result=cleanup.simulate_execute(self.root,self.scan(usage),usage,now=self.now)
        pin=w.file_digest(self.root,result['results'][0]['quarantine_record'])
        return original,usage,result,pin


    def assert_restore_reference_protected(self, pin, target, document_rel, document):
        before=w.file_digest(self.root,pin['path'])
        target_before=cleanup.fingerprint(self.root/target)
        self.write(document_rel,document)
        document_before=w.file_digest(self.root,document_rel)
        with self.assertRaisesRegex(w.WorkflowError,'restore.*reference'):
            cleanup.simulate_restore(self.root,pin)
        self.assertEqual(w.file_digest(self.root,pin['path']),before)
        self.assertEqual(cleanup.fingerprint(self.root/target),target_before)
        self.assertEqual(w.file_digest(self.root,document_rel),document_before)
        self.assertFalse((self.root/'drafts/intermediate/old.bin').exists())

    def test_restore_rejects_new_quarantine_json_reference_without_record_mutation(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path']
        self.assert_restore_reference_protected(pin,target,'reports/evidence/new.json',{'artifact_path':target})

    def test_restore_rejects_new_quarantine_markdown_reference_without_record_mutation(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path']
        self.assert_restore_reference_protected(pin,target,'reports/evidence/new.md',f'[Retained]({target})')

    def test_restore_rejects_new_original_path_reference(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path']
        self.assert_restore_reference_protected(pin,target,'reports/evidence/new.json',{'artifact_path':'drafts/intermediate/old.bin'})

    def test_restore_rejects_new_interrupted_staging_reference(self):
        self.write('drafts/intermediate/old.bin','obsolete')
        usage=self.usage('drafts/intermediate/old.bin',31,'obsolete_intermediate')
        plan=self.scan(usage);original_link=os.link
        def stop(src,dst,*args,**kwargs):
            if dst=='old.bin' and kwargs.get('src_dir_fd') is not None:
                raise OSError('simulated interrupted quarantine')
            return original_link(src,dst,*args,**kwargs)
        with mock.patch.object(cleanup.os,'link',side_effect=stop):
            with self.assertRaises(OSError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        record=next((self.root/'data/maintenance/cleanup-recovery').glob('*.json'))
        pin=w.file_digest(self.root,str(record.relative_to(self.root)))
        target=w.read_json(record)['staging_path']
        self.assert_restore_reference_protected(pin,target,'reports/evidence/new.json',{'artifact_path':target})

    def test_restore_rejects_unknown_reference_parser_without_record_mutation(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path']
        self.assert_restore_reference_protected(pin,target,'reports/evidence/new.json','{not parseable}')

    def test_restore_rechecks_reference_membership_at_move_cas(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path'];before=cleanup.fingerprint(self.root/target)
        original_directory_fd=cleanup.directory_fd;added=False
        def add_reference(root,relative):
            nonlocal added
            fd=original_directory_fd(root,relative)
            if not added:
                self.write('reports/evidence/new.json',{'artifact_path':target});added=True
            return fd
        with mock.patch.object(cleanup,'directory_fd',side_effect=add_reference):
            with self.assertRaisesRegex(w.WorkflowError,'restore.*reference'):
                cleanup.simulate_restore(self.root,pin)
        self.assertTrue(added);self.assertFalse(original.exists())
        self.assertEqual(cleanup.fingerprint(self.root/target),before)
        self.assertEqual(w.file_digest(self.root,pin['path']),pin)


    def test_restore_unknown_reference_at_final_cas_preserves_original_recovery_record(self):
        original,usage,result,pin=self.quarantine()
        target=result['results'][0]['quarantine_path'];before=cleanup.fingerprint(self.root/target)
        original_write=w.atomic_write_json;injected=False
        def unknown_after_preparation(path,value):
            nonlocal injected
            original_write(path,value)
            if not injected and value.get('status')=='prepared' and 'restore-' in value.get('staging_path',''):
                self.write('reports/evidence/new.json','{unknown reference state}');injected=True
        with mock.patch.object(w,'atomic_write_json',side_effect=unknown_after_preparation):
            with self.assertRaisesRegex(w.WorkflowError,'restore.*reference'):
                cleanup.simulate_restore(self.root,pin)
        self.assertTrue(injected);self.assertFalse(original.exists())
        self.assertEqual(w.file_digest(self.root,pin['path']),pin)
        self.assertEqual(cleanup.fingerprint(self.root/target),before)

    def test_restore_preserves_new_holding_reference_and_prepared_recovery(self):
        original,usage,result,pin=self.quarantine()
        original_rename=os.rename;held=[]
        def add_reference_after_move(src,dst,*args,**kwargs):
            out=original_rename(src,dst,*args,**kwargs)
            record=w.read_json(self.root/pin['path']);held.append(record['staging_path'])
            self.write('reports/evidence/new.json',{'artifact_path':record['staging_path']})
            return out
        with mock.patch.object(cleanup.os,'rename',side_effect=add_reference_after_move):
            with self.assertRaisesRegex(w.WorkflowError,'restore.*reference'):
                cleanup.simulate_restore(self.root,pin)
        current=w.read_json(self.root/pin['path'])
        self.assertEqual(current['status'],'prepared')
        self.assertEqual(current['staging_path'],held[0])
        self.assertTrue((self.root/held[0]).is_file());self.assertFalse(original.exists())

    def test_duplicate_complete_reads_fresh_effect_after_new_source_preserving_history_and_wip(self):
        original=self.write('drafts/intermediate/old.bin','obsolete')
        usage=self.usage('drafts/intermediate/old.bin',31,'obsolete_intermediate')
        plan=self.scan(usage);first=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        journal_before=w.file_digest(self.root,first['journal'])
        self.write('drafts/intermediate/old.bin','new concurrent WIP')
        new_before=w.file_digest(self.root,'drafts/intermediate/old.bin')
        second=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertEqual(second['status'],'duplicate_ignored')
        self.assertEqual(second['results'],first['results'])
        self.assertEqual(second['results_observation'],'immutable_historical_completed_journal')
        fresh=second['current_effect']
        self.assertEqual(fresh['observation_scope'],'fresh_read_only_current_effect')
        self.assertIsNotNone(w._parse_observed_at(fresh['observed_at']))
        self.assertTrue(fresh['items'][0]['source_currently_exists'])
        self.assertFalse(fresh['items'][0]['source_absent_readback'])
        self.assertTrue(fresh['items'][0]['historical_source_absent_readback'])
        self.assertFalse(second['production_mutation']);self.assertFalse(fresh['reexecution_authorized'])
        self.assertEqual(w.file_digest(self.root,first['journal']),journal_before)
        self.assertEqual(w.file_digest(self.root,'drafts/intermediate/old.bin'),new_before)

    def test_duplicate_complete_fresh_effect_reports_actual_absence_when_source_stays_absent(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage();plan=self.scan(usage)
        first=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        before=w.file_digest(self.root,first['journal'])
        second=cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertTrue(second['current_effect']['items'][0]['source_absent_readback'])
        self.assertFalse(second['current_effect']['items'][0]['source_currently_exists'])
        self.assertEqual(w.file_digest(self.root,first['journal']),before)

    def test_quarantine_restore_and_repeat_are_exact_idempotent_readback(self):
        original,usage,result,pin=self.quarantine()
        self.assertFalse(original.exists());self.assertEqual(result['results'][0]['status'],'quarantined_not_freed')
        restored=cleanup.simulate_restore(self.root,pin)
        self.assertEqual(restored['status'],'restored');self.assertIn('self-owned',original.read_text())
        current=w.file_digest(self.root,pin['path'])
        again=cleanup.simulate_restore(self.root,current)
        self.assertEqual(again['status'],'duplicate_ignored');self.assertFalse(again['production_mutation'])
        self.assertTrue(again['current_effect']['original_currently_exists'])
        self.assertTrue(again['current_effect']['original_matches_recovery_fingerprint'])
        self.assertFalse(again['current_effect']['quarantine_currently_exists'])
        self.assertFalse(again['current_effect']['staging_currently_exists'])
        self.assertIsNotNone(w._parse_observed_at(again['current_effect']['observed_at']))
        self.assertFalse(again['current_effect']['reexecution_authorized'])

    def test_restore_never_overwrites_concurrent_original(self):
        original,usage,result,pin=self.quarantine();original.write_text('new user WIP')
        with self.assertRaises(w.WorkflowError):cleanup.simulate_restore(self.root,pin)
        self.assertEqual(original.read_text(),'new user WIP')
        self.assertTrue((self.root/result['results'][0]['quarantine_path']).exists())

    def test_quarantine_content_and_record_cas_preserve_changed_bytes(self):
        original,usage,result,pin=self.quarantine()
        target=self.root/result['results'][0]['quarantine_path'];target.write_text('changed retained bytes')
        with self.assertRaises(w.WorkflowError):cleanup.simulate_restore(self.root,pin)
        self.assertFalse(original.exists());self.assertEqual(target.read_text(),'changed retained bytes')

    def test_restore_project_outside_and_symlink_recovery_rejected(self):
        original,usage,result,pin=self.quarantine();value=w.read_json(self.root/pin['path'])
        for rel in ('../outside','/tmp/outside','reports/formal.txt'):
            changed={**value,'original_path':rel};self.write(pin['path'],changed)
            with self.assertRaises(w.WorkflowError):cleanup.simulate_restore(self.root,w.file_digest(self.root,pin['path']))
        self.assertFalse(original.exists())

    def test_quarantine_requires_thirty_days_then_additional_thirty_and_exact_record(self):
        original,usage,result,pin=self.quarantine();row=result['results'][0]
        self.now+=dt.timedelta(days=30)
        later=self.usage(row['quarantine_path'],61,'quarantined_intermediate',quarantined_at=row['quarantined_at'])
        later['files'][0]['quarantine_record']=pin
        plan=self.scan(later);self.assertEqual(plan['items'][0]['action'],'purge')
        later['files'][0].pop('quarantine_record');self.assertEqual(self.scan(later)['items'],[])
        self.assertTrue((self.root/row['quarantine_path']).exists())

    def test_interrupted_quarantine_after_move_can_restore_staged_exact_file(self):
        self.write('drafts/intermediate/old.bin','obsolete')
        usage=self.usage('drafts/intermediate/old.bin',31,'obsolete_intermediate');plan=self.scan(usage)
        original_link=os.link
        def stop(src,dst,*args,**kwargs):
            if dst=='old.bin' and kwargs.get('src_dir_fd') is not None:raise OSError('simulated interrupted quarantine')
            return original_link(src,dst,*args,**kwargs)
        with mock.patch.object(cleanup.os,'link',side_effect=stop):
            with self.assertRaises(OSError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        record=next((self.root/'data/maintenance/cleanup-recovery').glob('*.json'))
        self.assertEqual(w.read_json(record)['status'],'prepared')
        restored=cleanup.simulate_restore(self.root,w.file_digest(self.root,str(record.relative_to(self.root))))
        self.assertEqual(restored['status'],'restored');self.assertEqual((self.root/'drafts/intermediate/old.bin').read_text(),'obsolete')

    def test_task_reopened_after_plan_protected_before_mutation(self):
        source=self.write('runtime/cache/build.bin','tmp');usage=self.usage();plan=self.scan(usage)
        self.write('data/task-end.json',{'task_id':'ended-task','status':'active'})
        with self.assertRaises(w.WorkflowError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        self.assertEqual(source.read_text(),'tmp')

    def test_original_two_paths_are_protected_negative_cases_only(self):
        paths=['drafts/creative/fc-kl-old-house-lead-20260831/remotion_precompose/node_modules',
               'reports/evidence/qa-geo-ai-admin-20261002-0010/full-app-dist']
        for rel in paths:
            source=self.write(rel,'synthetic negative case only')
            self.assertEqual(self.scan(self.usage(rel,100))['items'],[]);self.assertTrue(source.exists())

    def test_release_publish_license_and_rights_evidence_protected(self):
        for name in ('release.zip','publish.txt','license.json','rights.txt','rollback.bin','delivery.bin'):
            source=self.write('runtime/cache/'+name,'synthetic formal evidence')
            self.assertEqual(self.scan(self.usage('runtime/cache/'+name,100))['items'],[]);self.assertTrue(source.exists())

    def test_unknown_reference_parser_returns_no_eligible_plan(self):
        self.write('runtime/cache/build.bin','tmp');usage=self.usage()
        self.write('tools/dynamic.js','const path = makeDynamicPath();')
        result=self.scan(usage);self.assertEqual(result['items'],[]);self.assertEqual(result['reference_state'],'UNPROVEN')

    def test_project_root_symlink_rejected_before_resolution(self):
        link=self.root/'alias';link.symlink_to(self.root)
        with self.assertRaises(w.WorkflowError):cleanup.scan(link,{'trusted_use_observations':True,'files':[]},simulation=True)

    def test_current_goal_adoption_verifier_accepts_assistant2_manifest_and_runtime_pins(self):
        task='fixture-internal-tool-adoption'
        self.write('data/task-contract.json',{'goal_delivery_runtime':{'model':'goal_delivery_assistant_v1','assistant_decisions_enabled':True}})
        self.write('data/department-registry.json',{'departments':[
            {'id':'operations-assistant-2','coordination_authority':{'routine_decisions':True,'review_capabilities':['development']}},
            {'id':'system-development'}]})
        self.write(str(w.snapshot_path(self.root,task).relative_to(self.root)),{'task_id':task,'goal_delivery':{
            'responsible_assistant':'operations-assistant-2','producer_departments':['system-development'],'acceptance_capability':'development'}})
        self.write('tools/safe_cleanup.py','synthetic runtime source')
        runtime=w.file_digest(self.root,'tools/safe_cleanup.py')
        self.write('drafts/manifest.json',{'task_id':task,'external_writes':False,'candidate_fingerprint':'fixture-hash',
                                          'changes':[{'path':'tools/safe_cleanup.py'}]})
        manifest=w.file_digest(self.root,'drafts/manifest.json')
        self.write('logs/qa.json',{'task_id':task,'candidate_version':'fixture-tool-v1','evidence':[manifest]})
        qa=w.file_digest(self.root,'logs/qa.json')
        self.write('logs/applied.json',{'task_id':task,'candidate_version':'fixture-tool-v1','qa_outbox':qa,
            'external_writes':0,'production_permission_issued':False,'postapply_tests':{'run':1,'failures':0,'errors':0},
            'candidate_manifest':manifest,'candidate_fingerprint':'fixture-hash','applied_files':[runtime]})
        receipt={'receipt_id':'fixture-pass','receipt_type':'qa_verdict','department':'operations-assistant-2',
                 'verdict':'pass','action_class':'internal_control_candidate','evidence':[qa]}
        request={'control_qa_outbox_path':'logs/qa.json','control_applied_proof':'logs/applied.json','control_qa_receipt_id':'fixture-pass'}
        with mock.patch.object(w,'validate_outbox'),mock.patch.object(w,'_validate_receipt_chain',return_value=([receipt],[])):
            result=w._verify_operations_rework_completion(self.root,request,task)
            self.assertEqual(result['control_qa_receipt_id'],'fixture-pass');self.assertFalse(result['external_authority_granted'])
            self.write('tools/safe_cleanup.py','changed concurrent runtime')
            with self.assertRaises(w.WorkflowError):w._verify_operations_rework_completion(self.root,request,task)



    def test_interrupted_purge_staging_has_exact_restore_record(self):
        self.write('runtime/cache/build.bin','rebuildable');usage=self.usage();plan=self.scan(usage)
        original=w.atomic_write_json
        def stop(path,value):
            original(path,value)
            if value.get('status')=='staged_pending_readback':raise OSError('simulated process stop')
        with mock.patch.object(w,'atomic_write_json',side_effect=stop):
            with self.assertRaises(OSError):cleanup.simulate_execute(self.root,plan,usage,now=self.now)
        journal=next((self.root/'data/maintenance/cleanup-journals').glob('*.json'))
        readback=cleanup.readback_journal(self.root,str(journal.relative_to(self.root)))
        restored=cleanup.simulate_restore(self.root,readback['recovery_record'])
        self.assertEqual(restored['status'],'restored');self.assertEqual((self.root/'runtime/cache/build.bin').read_text(),'rebuildable')

    def test_concurrent_quarantine_replacement_during_restore_is_preserved(self):
        original,usage,result,pin=self.quarantine();target=self.root/result['results'][0]['quarantine_path']
        rename=os.rename
        def replace(src,dst,*args,**kwargs):
            if src=='old.bin' and kwargs.get('src_dir_fd') is not None:
                fd=kwargs['src_dir_fd'];os.unlink(src,dir_fd=fd)
                output=os.open(src,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd)
                os.write(output,b'new retained user content');os.close(output)
            return rename(src,dst,*args,**kwargs)
        with mock.patch.object(cleanup.os,'rename',side_effect=replace):
            with self.assertRaises(w.WorkflowError):cleanup.simulate_restore(self.root,pin)
        self.assertFalse(original.exists());self.assertEqual(target.read_text(),'new retained user content')

    def test_candidate_restore_cannot_bypass_exact_admission(self):
        original,usage,result,pin=self.quarantine()
        with self.assertRaises(w.WorkflowError):cleanup.restore_admitted_cleanup(self.root,{}, {}, {'quarantine_record':pin})
        self.assertFalse(original.exists());self.assertTrue((self.root/result['results'][0]['quarantine_path']).exists())



    def test_command_configures_four_modes_and_default_scan(self):
        import argparse
        parser=cleanup.configure_parser(argparse.ArgumentParser())
        self.assertEqual(parser.parse_args([]).mode,'scan')
        for mode in ('scan','execute','readback','restore'):
            self.assertEqual(parser.parse_args(['--mode',mode]).mode,mode)
        args=parser.parse_args(['--mode','execute'])
        with self.assertRaises(w.WorkflowError):cleanup.command(self.root,args)
        self.assertFalse((self.root/'data/maintenance/cleanup-journals').exists())

    def test_current_goal_consumer_calls_independent_review_and_adoption_then_denies_candidate(self):
        import goal_delivery_runtime as g,qa_review_plan as q
        task='fixture-cleanup-goal';self.write('data/authority.json',{'fixture':'not actual human authority'})
        authority=w.file_digest(self.root,'data/authority.json')
        self.write('data/maintenance/cleanup-plans/plan.json',{'project_root':str(self.root),'simulation_only':False,'items':[]})
        plan=w.file_digest(self.root,'data/maintenance/cleanup-plans/plan.json')
        goal={'authorized_scope':['company_cleanup:'+plan['sha256']],'producer_departments':['operations-assistant-3'],
              'responsible_assistant':'operations-assistant-2','authorization_pin':authority}
        grant={'task_id':task,'cleanup_plan':plan,'scope':'company_cleanup:'+plan['sha256'],'risk_level':'R0',
               'actor_role':'operations-assistant-3','responsible_assistant':'operations-assistant-2','authority':authority,
               'allowed_operations':['execute'],'tool_adoption':{'task_id':'fixture-adoption'}}
        self.write('data/grant.json',grant);grant_pin=w.file_digest(self.root,'data/grant.json')
        self.write('tools/safe_cleanup.py','fixture adopted runtime')
        self.write('logs/applied.json',{'applied_files':[w.file_digest(self.root,'tools/safe_cleanup.py')]})
        policy={'department_system_upgrade':{'cleanup_admitted':True,'cleanup_grants':{plan['sha256']:grant_pin}}}
        receipt={'receipt_type':'qa_verdict','department':'operations-assistant-2','verdict':'pass'}
        with mock.patch.object(w,'load_policy',return_value=policy),mock.patch.object(g,'restore_goal',return_value={'goal_delivery':goal}),mock.patch.object(g,'enabled',return_value=True),mock.patch.object(w,'_validate_receipt_chain',return_value=([receipt],[])),mock.patch.object(q,'reviewer_department',return_value='operations-assistant-2'),mock.patch.object(q,'validate_verdict') as validate,mock.patch.object(q,'load_plan',return_value={'candidate':plan}),mock.patch.object(w,'_verify_operations_rework_completion',return_value={'control_applied_proof':w.file_digest(self.root,'logs/applied.json')}) as adoption:
            with self.assertRaisesRegex(w.WorkflowError,'candidate is not executable authority'):
                cleanup._admission(self.root,plan,grant_pin,{},'execute')
            validate.assert_called_once();adoption.assert_called_once()



if __name__=='__main__':unittest.main()
