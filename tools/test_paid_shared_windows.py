"""Shared paid knowledge, separate execution windows; fixtures never touch live memory."""
import argparse
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flashcast_ops as ops

PROJECT = Path(__file__).resolve().parents[1]

def record(root, role, suffix):
    args = argparse.Namespace(department=role, task_id='test-shared-'+suffix,
        evidence='reports/fixture-only.json', observed_at='2026-10-19T10:00:00+00:00',
        source='isolated_fixture', memory_type='method', lesson='fixture '+suffix,
        signal='test', outcome='test', next_action='none', confidence='high',
        lesson_status='provisional')
    return ops.department_learning_record(Path(root), args)[0]

class PaidSharedWindows(unittest.TestCase):
    def test_same_skills_memory_and_data_separate_binding(self):
        roles=json.loads((PROJECT/'data/department-registry.json').read_text())['departments']
        rows={x['id']:x for x in roles}
        a,b=[rows[k] for k in ('paid-growth-data','paid-growth-data-2')]
        for key in ('professional_skill','department_readme','approved_subskills','approved_subskill_paths','input_paths','output_paths'):
            self.assertEqual(a[key],b[key],key)
        self.assertNotEqual(a['role_config'],b['role_config'])
        if a['chat_binding']['task_id'] or b['chat_binding']['task_id']:
            self.assertNotEqual(a['chat_binding']['task_id'],b['chat_binding']['task_id'])
        else:
            for row in (a, b):
                self.assertEqual(row['chat_binding']['status'], 'unbound')
                self.assertFalse(row['chat_binding']['dispatch_eligible'])
        ca,cb=[ops.department_learning_config(PROJECT,k) for k in (a['id'],b['id'])]
        self.assertEqual(ca['memory_path'],cb['memory_path'])

    def test_concurrent_writes_keep_both_lessons_canonical_identity_and_dedup(self):
        temp_base = PROJECT / '.test-tmp'
        temp_base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_base) as d:
            root=Path(d)
            for rel in ('data/department-registry.json','data/learning/department-learning-registry.json','data/task-contract.json'):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((PROJECT/rel).read_bytes())
            for role in ('paid-growth-data','paid-growth-data-2'):
                cfg=ops.department_learning_config(PROJECT,role)
                for rel in (cfg['professional_skill'],cfg['role_config']):
                    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((PROJECT/rel).read_bytes())
            mem=root/'data/learning/departments/paid-growth-data.json';mem.parent.mkdir(parents=True,exist_ok=True)
            mem.write_text(json.dumps({'department':'paid-growth-data','verified_lessons':[{'lesson_id':'existing'}]}))
            jobs=[multiprocessing.get_context('fork').Process(target=record,args=(d,role,str(i))) for i,role in enumerate(('paid-growth-data','paid-growth-data-2'))]
            for job in jobs:job.start()
            for job in jobs:job.join(10);self.assertEqual(job.exitcode,0)
            result=json.loads(mem.read_text());self.assertEqual(result['department'],'paid-growth-data')
            self.assertEqual(result['event_count'],2);self.assertEqual(len(result['provisional_lessons']),2)
            self.assertEqual(result['verified_lessons'],[{'lesson_id':'existing'}])
            again=record(d,'paid-growth-data-2','1');self.assertEqual(again['status'],'department_learning_duplicate_ignored')
            self.assertEqual(json.loads(mem.read_text())['event_count'],2)

if __name__=='__main__':unittest.main()
