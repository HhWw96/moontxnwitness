"""Full capture cost protocol unit checks, no PostgreSQL/network execution."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest
import uuid
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('capture_cost',ROOT/'experiments/provenance/full_capture_cost.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(ROOT/'artifacts/cost-runner-unit')))
RUN=BASE/('cost-'+uuid.uuid4().hex);RUN.mkdir(parents=True)


class Tests(unittest.TestCase):
    def args(self,**extra):return argparse.Namespace(quick=False,profile='column',workload='all',seed=123,**extra)
    def test_plan_has_four_workloads_three_batches_and_modes(self):
        p=m.plan(self.args());self.assertEqual(len(p['cells']),36)
        for cell in p['cells']:
            self.assertEqual((cell['warmupSeconds'],cell['durationSeconds'],cell['drainSeconds']),(15,60,30))
    def test_source_binding_covers_all_loaded_package_helpers(self):
        files=m.runtime_sources();names={path.name for path in files}
        expected={path.name for path in (ROOT/'integrations/python/moontxnwitness_capture').glob('*.py') if not path.name.startswith('test_')}
        self.assertTrue(expected<=names);self.assertIn('cell_archive.py',names)
        self.assertTrue(all(path.is_file() for path in files))
    def test_rotations_are_abc_bca_cab(self):
        cells=m.plan(self.args())['cells']
        for batch,order in enumerate(['ABC','BCA','CAB']):
            self.assertEqual(''.join(c['mode'] for c in cells if c['workload']=='serial' and c['batch']==batch),order)
    def test_quick_plan_never_claims_formal_measurement(self):
        args=self.args();args.quick=True;p=m.plan(args)
        self.assertFalse(p['formalPerformanceMeasurement'])
        self.assertTrue(all(c['quick'] for c in p['cells']))
    def test_workload_sequence_is_repeatable_across_modes(self):
        a,b=random.Random(123),random.Random(123);spec=m.WORKLOADS['hot']
        self.assertEqual([m.operation(a,spec) for _ in range(100)],[m.operation(b,spec) for _ in range(100)])
    def test_hot_updates_select_only_declared_key_domain(self):
        rng=random.Random(12);ops=[m.operation(rng,m.WORKLOADS['hot']) for _ in range(10000)]
        hot=sum(int(x['key'][4:])<4 for x in ops)
        self.assertTrue(8800<hot<9200)
        self.assertTrue(all(0<=int(x['key'][4:])<32 for x in ops))
    def test_crud_plan_preserves_four_actions_and_negative_reads(self):
        rng=random.Random(5);ops=[m.operation(rng,m.WORKLOADS['crud']) for _ in range(100)]
        self.assertEqual({x['action'] for x in ops},{0,1,2,3})
        self.assertTrue(all(x['missing'].startswith('missing-') for x in ops))
    def cells(self):
        result=[]
        for batch in range(3):
            for mode,tps,p95 in [('A',100,10),('B',1000,5),('C',50,20)]:
                result.append({'configuration':{'workload':'serial','batch':batch,'mode':mode},
                               'status':'passed','endToEndCommittedTps':tps,'allAttemptP95Ns':p95,
                               'formalProtocolCompleted':True,'captureBudgetExhausted':False,
                               'failures':0,'protocolFailures':[]})
        return result
    def test_comparison_uses_c_over_a_not_b_over_a(self):
        result=m.compare(self.cells())['serial']
        self.assertAlmostEqual(result['fullCaptureThroughputCOverA'],.5)
        self.assertAlmostEqual(result['fullCaptureP95COverA'],2)
        self.assertTrue(result['eligibleForTargets'])
        self.assertFalse(result['performanceTargetsPassed'])
    def test_fixed_targets_require_both_ratios(self):
        cells=self.cells()
        for cell in cells:
            if cell['configuration']['mode']=='C':
                cell['endToEndCommittedTps']=95;cell['allAttemptP95Ns']=11
        self.assertTrue(m.compare(cells)['serial']['performanceTargetsPassed'])
        cells[2]['allAttemptP95Ns']=20
        self.assertFalse(m.compare(cells)['serial']['performanceTargetsPassed'])
    def test_sql_failures_do_not_qualify_even_when_protocol_completed(self):
        for mode in ('A','B','C'):
            cells=self.cells()
            for cell in cells:
                if cell['configuration']['mode']=='C':
                    cell['endToEndCommittedTps']=95;cell['allAttemptP95Ns']=11
            cell=next(x for x in cells if x['configuration']['mode']==mode)
            cell['failures']=1;cell['sqlstateCounts']={'23505':1}
            result=m.compare(cells)['serial']
            self.assertEqual(result['status'],'complete')
            self.assertFalse(result['eligibleForTargets'])
            self.assertFalse(result['performanceTargetsPassed'])
            self.assertEqual(cell['sqlstateCounts'],{'23505':1})
    def test_unknown_failure_count_does_not_qualify(self):
        cells=self.cells();del cells[2]['failures']
        self.assertFalse(m.compare(cells)['serial']['eligibleForTargets'])
    def test_registered_contention_and_warmup_failures_remain_ineligible(self):
        for field,value in [('failures',1),('warmupFailures',1),('sqlstateCounts',{'40001':1}),('protocolFailures',[{'sqlstate':'55P03'}])]:
            with self.subTest(field=field):
                cells=self.cells();cells[2][field]=value
                self.assertFalse(m.compare(cells)['serial']['eligibleForTargets'])
    def test_partial_archive_plan_keeps_all_36_preregistered_cells(self):
        args=self.args(archive_cells=True,max_cells=3);p=m.plan(args)
        self.assertEqual(len(p['cells']),36);self.assertEqual(p['maximumCellsThisInvocation'],3)
        self.assertIn('post-child',p['retentionPolicy'])
        self.assertTrue(all(cell['storageReserveBytes']==512*1024*1024 for cell in p['cells']))
        self.assertEqual(p['performanceTargets'],{'fullCaptureThroughputCOverAAtLeast':.90,'fullCaptureP95COverAAtMost':1.15})
    def test_incomplete_or_budget_exhausted_cell_is_ineligible(self):
        cells=self.cells();cells[2]['captureBudgetExhausted']=True
        self.assertFalse(m.compare(cells)['serial']['eligibleForTargets'])
        cells=self.cells();cells.pop()
        self.assertFalse(m.compare(cells)['serial']['eligibleForTargets'])
    def test_smoke_results_are_not_formal_targets(self):
        cells=self.cells()
        for c in cells:c['status']='smoke-passed';c['formalProtocolCompleted']=False
        self.assertFalse(m.compare(cells)['serial']['eligibleForTargets'])
    def test_plan_only_runs_without_database(self):
        out=RUN/'plan-only';env=dict(os.environ)
        env.pop('MTW_PG_DSN',None);env.pop('MTW_PG_CONNECTION_FILE',None)
        result=subprocess.run([sys.executable,'-B',m.__file__,'--output',str(out),'--plan-only'],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        receipt=json.loads((out/'receipt.json').read_text())
        self.assertFalse(receipt['actualDatabaseExecution']);self.assertEqual(receipt['status'],'not-executed')
    def test_formal_without_exclusivity_is_not_executed(self):
        out=RUN/'no-exclusive'
        result=subprocess.run([sys.executable,'-B',m.__file__,'--output',str(out)],capture_output=True)
        self.assertEqual(result.returncode,3)
        self.assertFalse(json.loads((out/'receipt.json').read_text())['actualDatabaseExecution'])
    def test_missing_database_worker_is_not_executed(self):
        out=RUN/'no-db';config=RUN/'worker.json';config.write_text(json.dumps(m.plan(self.args())['cells'][0]))
        env=dict(os.environ);env.pop('MTW_PG_DSN',None);env.pop('MTW_PG_CONNECTION_FILE',None)
        result=subprocess.run([sys.executable,'-B',m.__file__,'--output',str(out),'--worker-config',str(config)],env=env,capture_output=True)
        self.assertEqual(result.returncode,3,result.stderr.decode(errors='replace'))
        self.assertEqual(json.loads((out/'receipt.json').read_text())['status'],'not-executed')
    def test_owned_runner_refuses_without_exclusive_host_before_creating_cluster(self):
        out=RUN/'owned-no-host'
        result=subprocess.run([sys.executable,'-B',str(Path(m.__file__).with_name('owned_full_capture_cost.py')),
            '--bin',str(RUN/'no-binaries'),'--output',str(out)],capture_output=True)
        self.assertEqual(result.returncode,2);self.assertFalse(out.exists())
    def test_owned_runner_refuses_invalid_prefix_before_creating_cluster(self):
        out=RUN/'owned-invalid-prefix'
        result=subprocess.run([sys.executable,'-B',str(Path(m.__file__).with_name('owned_full_capture_cost.py')),
            '--bin',str(RUN/'no-binaries'),'--output',str(out),'--exclusive-host','--max-cells','0'],capture_output=True)
        self.assertEqual(result.returncode,2);self.assertFalse(out.exists())


if __name__=='__main__':unittest.main(verbosity=2)
