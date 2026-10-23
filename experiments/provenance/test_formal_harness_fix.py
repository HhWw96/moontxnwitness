"""Formal harness regressions: synthetic aggregation and fake startup only, never DB or timing measurement."""
from pathlib import Path
import unittest,json,copy,threading,importlib.util
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];spec=importlib.util.spec_from_file_location('formal_cost_fix',ROOT/'experiments/provenance/full_capture_cost.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def cells(self):
  return [{'configuration':{'workload':'serial','batch':batch,'mode':mode},'status':'passed','formalProtocolCompleted':True,'captureBudgetExhausted':False,'failures':0,'warmupFailures':0,'protocolFailures':[],'endToEndCommittedTps':tps,'allAttemptP95Ns':p95}for batch in range(3)for mode,tps,p95 in [('A',100.,100),('B',98.,103),('C',95.,110)]]
 def test_zero_committed_c_all_registered_failures_retains_ineligible_result(self):
  cells=self.cells()
  for c in cells:
   if c['configuration']['mode']=='C':c.update(endToEndCommittedTps=0.,failures=6,attempts=6,commits=0,sqlstateCounts={'55P03':6})
  r=m.compare(cells)['serial'];self.assertEqual(r['status'],'complete');self.assertEqual(r['fullCaptureThroughputCOverA'],0.);self.assertFalse(r['eligibleForTargets']);self.assertFalse(r['performanceTargetsPassed']);self.assertEqual(cells[2]['sqlstateCounts'],{'55P03':6})
 def test_zero_committed_c_even_without_failure_count_never_qualifies(self):
  cells=self.cells();cells[2]['endToEndCommittedTps']=0.;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertEqual(r['fullCaptureThroughputCOverA'],0.)
 def test_zero_b_throughput_invalidates_full_matched_cell_group(self):
  cells=self.cells();cells[1]['endToEndCommittedTps']=0.;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertFalse(r['performanceTargetsPassed'])
 def test_zero_a_baseline_returns_unavailable_ratio_not_exception(self):
  cells=self.cells();cells[0]['endToEndCommittedTps']=0.;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertIsNone(r['fullCaptureThroughputCOverA']);self.assertFalse(r['performanceTargetsPassed'])
 def test_empty_latency_sample_returns_ineligible_not_type_error(self):
  cells=self.cells();cells[2]['allAttemptP95Ns']=None;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertIsNone(r['fullCaptureP95COverA'])
 def test_zero_p95_a_baseline_is_ineligible(self):
  cells=self.cells();cells[0]['allAttemptP95Ns']=0;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertIsNone(r['fullCaptureP95COverA'])
 def test_nonfinite_negative_and_boolean_metrics_never_become_targets(self):
  for field in ['endToEndCommittedTps','allAttemptP95Ns']:
   for value in [float('nan'),float('inf'),-1,True]:
    with self.subTest(field=field,value=repr(value)):
     cells=self.cells();cells[2][field]=value;r=m.compare(cells)['serial'];self.assertFalse(r['eligibleForTargets']);self.assertFalse(r['performanceTargetsPassed']);json.dumps(r,allow_nan=False)
 def test_valid_geometric_comparison_and_raw_inputs_unchanged(self):
  cells=self.cells();before=copy.deepcopy(cells);r=m.compare(cells)['serial'];self.assertTrue(r['performanceTargetsPassed']);self.assertAlmostEqual(r['fullCaptureThroughputCOverA'],.95);self.assertAlmostEqual(r['fullCaptureP95COverA'],1.1);self.assertEqual(cells,before)
 def test_complete_warmup_deadline_starts_after_fake_connection_readiness(self):
  order=[];clock={'now':100.};shared={}
  class Ready:
   def wait(self,timeout):order.append(('ready',timeout));clock['now']=107.
  class Start:
   def set(self):order.append(('start',shared['warmDeadline']))
  with patch.object(m.time,'monotonic',lambda:clock['now']):started=m._begin_warmup(Ready(),Start(),shared,15,30)
  self.assertEqual(started,107.);self.assertEqual(shared['warmDeadline'],122.);self.assertEqual(order,[('ready',30),('start',122.)])
 def test_broken_connection_barrier_does_not_start_or_claim_warmup(self):
  shared={};start=threading.Event();ready=threading.Barrier(1);ready.abort()
  with patch.object(m.time,'monotonic')as clock:
   with self.assertRaises(threading.BrokenBarrierError):m._begin_warmup(ready,start,shared,15,30)
   clock.assert_not_called()
  self.assertFalse(start.is_set());self.assertEqual(shared,{})
 def test_two_fake_driver_connections_must_both_be_ready_before_business(self):
  arrived=[threading.Event(),threading.Event()];release_second=threading.Event();entered_main=threading.Event();start=threading.Event();barrier=threading.Barrier(3);shared={};observed=[];clock_calls=[];errors=[]
  class FakeDriver:
   def __init__(self,number):self.number=number
   def connect(self):
    if self.number==1:
     if not release_second.wait(3):raise TimeoutError('fake connection readiness gate')
    arrived[self.number].set();return self
   def execute(self):observed.append((self.number,shared['warmDeadline']))
  class Ready:
   def wait(self,timeout):entered_main.set();return barrier.wait(timeout)
  def worker(number):
   try:
    connection=FakeDriver(number).connect();barrier.wait(3)
    if not start.wait(3):raise TimeoutError('fake business start')
    connection.execute()
   except BaseException as e:errors.append(e)
  def begin():
   try:m._begin_warmup(Ready(),start,shared,15,3)
   except BaseException as e:errors.append(e)
  threads=[threading.Thread(target=worker,args=(i,))for i in range(2)];main=threading.Thread(target=begin)
  try:
   with patch.object(m.time,'monotonic',lambda:(clock_calls.append('clock')or 500.)):
    for t in threads:t.start()
    main.start();self.assertTrue(arrived[0].wait(2));self.assertTrue(entered_main.wait(2));self.assertFalse(start.is_set());self.assertEqual(clock_calls,[]);self.assertEqual(observed,[]);release_second.set()
    for t in threads+[main]:t.join(3);self.assertFalse(t.is_alive())
   self.assertEqual(errors,[]);self.assertTrue(arrived[1].is_set());self.assertCountEqual(observed,[(0,515.),(1,515.)])
  finally:
   release_second.set();start.set();barrier.abort()
   for t in threads+[main]:
    if t.ident is not None:t.join(1)
 def test_workflow_measurement_has_explicit_cleanup_upload_time_reserve(self):
  text=(ROOT/'.github/workflows/full-capture-cost.yml').read_text(encoding='utf8');lines=text.splitlines();job=next(int(x.split(':')[1])for x in lines if x.startswith('    timeout-minutes:'))
  timeouts={};name=None
  for line in lines:
   if line.startswith('      - name:'):name=line.split(':',1)[1].strip()
   elif line.startswith('      - uses:'):name='uses:'+line.split('@')[0].split(':',1)[1].strip()
   elif line.startswith('        timeout-minutes:'):timeouts[name]=int(line.split(':')[1])
  measure=timeouts['Execute all thirty-six preregistered full-duration cells once'];cleanup=timeouts['Retain exact plans and qualification separately from timing completion'];upload=next(v for k,v in timeouts.items()if 'upload-artifact'in k)
  self.assertGreaterEqual(measure,144);self.assertGreater(job,sum(timeouts.values()));self.assertGreaterEqual(job-measure,cleanup+upload+20)
if __name__=='__main__':unittest.main(verbosity=2)
