"""Small-file/static capacity integration checks. No actual DB or benchmarks."""
from pathlib import Path
import collections
import importlib.util
import json
import os
import sys
import threading
import types
import unittest
import uuid
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/provenance'))
sys.path.insert(0,str(ROOT/'integrations/python'))
import capacity_budget as budget
import cell_archive as archives
spec=importlib.util.spec_from_file_location('capacity_harness',ROOT/'experiments/provenance/full_capture_cost.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from moontxnwitness_capture._experimental_budget import PROFILE,LIMITS
from moontxnwitness_capture.instrumentation import Instrumentation,verify_lifecycle_storage
from moontxnwitness_capture.journal_v3 import SegmentedJournal,JournalIOError,JournalReader,LOCK,TRANSACTIONS
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(ROOT/'artifacts/capacity-small-files')))/('capacity-integration-'+uuid.uuid4().hex);BASE.mkdir(parents=True)

class Tests(unittest.TestCase):
    def path(self,name):return BASE/(self._testMethodName+'-'+name+'-'+uuid.uuid4().hex)
    def args(self,profile=None):return types.SimpleNamespace(quick=False,workload='all',profile='column',seed=20261023,archive_cells=True,max_cells=None,experimental_budget=profile)
    def cell(self):return m.plan(self.args(PROFILE))['cells'][0]
    def archive_fixture(self):
        root=self.path('run');cell=root/'cell-0';cell.mkdir(parents=True)
        (cell/'receipt.json').write_text(json.dumps({'status':'failed','formalProtocolCompleted':False,'protocolFailures':[{'errorClass':'kept-first-failure','sqlstate':None}]}),encoding='utf8')
        (cell/'observations.jsonl').write_bytes(b'{"original":"retained"}\n');return root,cell
    def test_default_plan_keeps_one_hundred_thousand_and_no_experiment(self):
        plan=m.plan(self.args());self.assertNotIn('experimentalBudget',plan)
        self.assertEqual(len(plan['cells']),36)
        for cell in plan['cells']:
            self.assertEqual(cell['maxAttemptsPerWorker'],100000);self.assertNotIn('experimentalBudget',cell);self.assertNotIn('maxWarmupAttemptsPerWorker',cell)
    def test_optin_plan_freezes_same_times_order_all_cells_and_actual_limits(self):
        plan=m.plan(self.args(PROFILE));legacy=m.plan(self.args())
        self.assertEqual(len(plan['cells']),36)
        for cell,old in zip(plan['cells'],legacy['cells']):
            for key in ('workload','batch','mode','profile','seed','warmupSeconds','durationSeconds','drainSeconds'):self.assertEqual(cell[key],old[key])
            self.assertEqual(cell['storageLimits'],LIMITS);self.assertEqual(cell['maxAttemptsPerWorker'],1000000);self.assertEqual(cell['maxWarmupAttemptsPerWorker'],250000)
    def test_disk_boundary_refuses_below_and_accepts_exact_without_assumed_compression(self):
        root=self.path('disk');root.mkdir()
        needed=budget.preparation(root)['minimumFreeRequiredBeforeCell']
        self.assertFalse(budget.preparation(root,free_bytes=needed-1)['eligibleToStart'])
        exact=budget.preparation(root,free_bytes=needed);self.assertTrue(exact['eligibleToStart']);self.assertTrue(exact['noCompressionRatioAssumed'])
        self.assertFalse(exact['fullThirtySixCellCompletionGuaranteed'])
    def test_retained_archives_are_reported_but_not_double_subtracted(self):
        root=self.path('disk');(root/'archives').mkdir(parents=True);(root/'archives/old.zip').write_bytes(b'retained')
        first=budget.preparation(root,free_bytes=100*1024**3)
        self.assertEqual(first['alreadyRetainedArchiveBytes'],8)
        self.assertEqual(first['observedFreeBytes'],100*1024**3)
        self.assertTrue(first['eligibleToStart'])
    def test_separate_verification_scratch_capacity_refuses_before_index_growth(self):
        root=self.path('disk');root.mkdir();scratch=self.path('scratch');scratch.mkdir()
        usage=types.SimpleNamespace(free=LIMITS['transactionIndexBytes']-1)
        with mock.patch.dict(os.environ,{'MTW_JOURNAL_SCRATCH':str(scratch)}),mock.patch.object(budget.shutil,'disk_usage',return_value=usage):
            result=budget.scratch_preparation(root)
        self.assertFalse(result['eligibleToStart']);self.assertEqual(result['reason'],'insufficient_verification_scratch')
    def test_missing_verification_scratch_is_visible(self):
        root=self.path('disk');root.mkdir()
        with mock.patch.dict(os.environ,{'MTW_JOURNAL_SCRATCH':str(self.path('missing'))}):result=budget.scratch_preparation(root)
        self.assertFalse(result['eligibleToStart']);self.assertEqual(result['reason'],'verification_scratch_missing')
    def test_raw_plus_zip_rebuild_database_and_reserve_arithmetic(self):
        root=self.path('disk');root.mkdir();result=budget.preparation(root)
        self.assertEqual(result['rawCellEnvelopeBytes'],LIMITS['rawCellBytes'])
        self.assertEqual(result['minimumFreeRequiredBeforeCell'],2*LIMITS['rawCellBytes']+LIMITS['transactionIndexBytes']+LIMITS['databaseAndWalBytes']+LIMITS['storageReserveBytes'])
    def test_actual_first_host_free_exceeds_preparation_floor_without_guaranteeing_run(self):
        root=self.path('disk');root.mkdir();result=budget.preparation(root,free_bytes=89333989376)
        self.assertTrue(result['eligibleToStart']);self.assertFalse(result['fullThirtySixCellCompletionGuaranteed'])
    def test_invalid_observed_free_not_accepted(self):
        root=self.path('disk');root.mkdir()
        for value in (True,-1,None):
            if value is None:continue
            with self.subTest(value=value),self.assertRaises(ValueError):budget.preparation(root,free_bytes=value)
    def test_byte_reservation_refuses_before_second_operation(self):
        value=budget.AttemptByteBudget(512);operations=[]
        if value.reserve(512):operations.append('first')
        if value.reserve(512):operations.append('second')
        self.assertEqual(operations,['first']);value.complete(512,111)
        self.assertEqual(value.written,111);self.assertEqual(value.reserved,0);self.assertFalse(value.reserve(512))
    def test_byte_reservation_release_preserves_capacity_after_abandoned_write(self):
        value=budget.AttemptByteBudget(512);self.assertTrue(value.reserve(512));value.release(512)
        self.assertTrue(value.reserve(512));value.complete(512,512);self.assertFalse(value.reserve(1))
    def test_byte_reservation_two_workers_share_one_cap(self):
        value=budget.AttemptByteBudget(512);barrier=threading.Barrier(3);results=[]
        def worker():barrier.wait(2);results.append(value.reserve(512))
        threads=[threading.Thread(target=worker)for _ in range(2)]
        for thread in threads:thread.start()
        barrier.wait(2)
        for thread in threads:thread.join(2);self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(results),[False,True]);self.assertEqual(value.reserved,512)
    def test_byte_guard_rejects_oversized_completion(self):
        value=budget.AttemptByteBudget(512);value.reserve(512)
        with self.assertRaises(ValueError):value.complete(512,513)
        self.assertEqual(value.reserved,512);value.release(512)
    def test_child_preflight_refusal_does_not_open_database(self):
        output=self.path('cell');output.mkdir();connect=mock.Mock(side_effect=AssertionError('must not connect'))
        with mock.patch.object(m,'preparation',return_value={'eligibleToStart':False,'reason':'insufficient_capacity_before_cell'}):result=m.run_cell(self.cell(),output,connect)
        connect.assert_not_called();self.assertFalse(result['actualDatabaseExecution']);self.assertFalse(result['formalProtocolCompleted']);self.assertEqual(result['errorClass'],'CapacityPreflightRefused')
    def test_worker_cannot_expand_frozen_profile(self):
        cell=self.cell();cell['storageLimits']={**LIMITS,'sourceBytes':LIMITS['sourceBytes']+1}
        connect=mock.Mock()
        with self.assertRaises(ValueError):m.run_cell(cell,self.path('cell'),connect)
        connect.assert_not_called()
    def test_worker_attempt_bound_cannot_be_unbounded(self):
        for key in ('maxAttemptsPerWorker','maxWarmupAttemptsPerWorker'):
            cell=self.cell();cell[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):m.run_cell(cell,self.path('cell'),mock.Mock())
    def test_budget_failure_never_qualifies_as_performance_success(self):
        cell={'formalProtocolCompleted':False,'protocolFailures':[{'errorClass':'AttemptBudgetExhausted','sqlstate':None}],'failures':0,'warmupFailures':0,'endToEndCommittedTps':1,'allAttemptP95Ns':1}
        reasons=m.target_eligibility_reasons(cell);self.assertIn('formal_protocol_incomplete',reasons);self.assertIn('protocol_failures',reasons)
    def test_experimental_archive_requires_matching_reader_and_keeps_failure(self):
        root,cell=self.archive_fixture();pointer=archives.archive_cell(root,cell,experimental_budget=PROFILE)
        original=cell/'receipt.json';self.assertTrue(original.exists());self.assertEqual(pointer['cellStatus'],'failed')
        archive=root/pointer['archive']
        with self.assertRaises(ValueError):archives.verify_archive(archive)
        result=archives.verify_archive(archive,experimental_budget=PROFILE);self.assertEqual(result['manifest']['cellStatus'],'failed')
    def test_experimental_archive_release_restore_exact_small_files(self):
        root,cell=self.archive_fixture();expected=(cell/'observations.jsonl').read_bytes();pointer=archives.archive_cell(root,cell,experimental_budget=PROFILE)
        result=archives.release_cell(root,cell,pointer,experimental_budget=PROFILE);self.assertTrue(result['rawReleased']);self.assertFalse((cell/'observations.jsonl').exists())
        restored=self.path('restore');archives.restore_archive(root/pointer['archive'],restored,expected_sha256=pointer['archiveSha256'],experimental_budget=PROFILE)
        self.assertEqual((restored/'observations.jsonl').read_bytes(),expected);self.assertEqual(json.loads((restored/'receipt.json').read_text(encoding='utf8'))['status'],'failed')
    def test_archive_explicit_small_reader_bound_still_refuses(self):
        root,cell=self.archive_fixture();pointer=archives.archive_cell(root,cell,experimental_budget=PROFILE)
        with self.assertRaises(ValueError):archives.verify_archive(root/pointer['archive'],experimental_budget=PROFILE,max_total_bytes=2)
    def test_lifecycle_verifier_streams_without_whole_file_read(self):
        observer=Instrumentation(self.path('observer'),experimental_budget=PROFILE);observer.note('example',value=1);observer.close()
        meta=json.loads((observer.output/'instrumentation.json').read_text(encoding='utf8'))['lifecycle']
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read forbidden')):self.assertTrue(verify_lifecycle_storage(observer.output/'lifecycle.jsonl',meta,experimental_budget=PROFILE)['storageSealed'])
    def test_public_journal_sqlite_full_preserves_failure_guard(self):
        journal=SegmentedJournal(self.path('journal'),experimental_budget=PROFILE,transaction_index_bytes=8192)
        journal.append({'seq':1,'time':0,'kind':'snapshot','initial':{},'consistent':True});seq=2
        for i in range(120):
            for kind in ('begin','commit_request','commit_ok'):
                accepted=journal.append({'seq':seq,'time':seq,'kind':kind,'tx':'transaction-'+str(i)+'-'+'x'*128}).accepted;seq+=1
                if not accepted:break
            if not accepted:break
        with self.assertRaises(JournalIOError):journal.close(source_closed=True)
        self.assertTrue((journal.path/LOCK).exists());self.assertLessEqual((journal.path/TRANSACTIONS).stat().st_size,8192)
        self.assertFalse(JournalReader(journal.path,experimental_budget=PROFILE).verify().complete)

if __name__=='__main__':unittest.main(verbosity=2)
