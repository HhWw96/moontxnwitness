"""Fake startup cancellation and original-error retention; no PostgreSQL or timed workload."""
from pathlib import Path
import importlib.util,tempfile,types,threading,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('formal_startup_cost',ROOT/'experiments/provenance/full_capture_cost.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class FakeCursor:
 def __init__(self,query=''):self.query=query
 def fetchone(self):return ('PostgreSQL 18 fake driver; no database',)
 def fetchall(self):return []
 def executemany(self,*a):return None
class FakeConnection:
 def __init__(self):self.info=types.SimpleNamespace(server_version=180000,backend_pid=999);self.closed=False
 def execute(self,query,*a):return FakeCursor(query)
 def cursor(self):return FakeCursor()
 def close(self):self.closed=True
class Tests(unittest.TestCase):
 def config(self,mode):return {'workload':'serial','mode':mode,'profile':'column','seed':20261023,'warmupSeconds':15,'durationSeconds':60,'drainSeconds':1,'maxAttemptsPerWorker':100000,'storageReserveBytes':0,'quick':False}
 def bounded_run(self,config,connect,output):
  result={};errors=[]
  def run():
   try:result.update(m.run_cell(config,output,connect))
   except BaseException as e:errors.append(e)
  t=threading.Thread(target=run,daemon=True);t.start();t.join(4);self.assertFalse(t.is_alive(),'failed startup must cancel before any timed issue window');self.assertEqual(errors,[]);return result
 def test_refused_connection_aborts_startup_and_retains_original_cause(self):
  def connect(**kwargs):
   if kwargs.get('autocommit'):return FakeConnection()
   raise ConnectionRefusedError('deliberate fake startup failure')
  with tempfile.TemporaryDirectory()as d:r=self.bounded_run(self.config('A'),connect,Path(d))
  self.assertEqual(r['status'],'failed');self.assertFalse(r['formalProtocolCompleted']);self.assertNotIn('warmupStartedAfterConnectionsReady',r);self.assertTrue(any(x['errorClass']=='ConnectionRefusedError'for x in r['protocolFailures']))
 def test_failed_observer_wrap_closes_open_raw_connection_and_retains_cause(self):
  raw=[]
  def connect(**kwargs):
   c=FakeConnection()
   if not kwargs.get('autocommit'):raw.append(c)
   return c
  class FailedObserver:
   def __init__(self,*a,**kw):pass
   def wrap(self,c):raise RuntimeError('deliberate fake wrap failure')
   def close(self):return None
  with tempfile.TemporaryDirectory()as d,patch.object(m,'Instrumentation',FailedObserver),patch.object(m,'install',return_value=types.SimpleNamespace(initial={})):
   r=self.bounded_run(self.config('C'),connect,Path(d))
  self.assertEqual(r['status'],'failed');self.assertFalse(r['formalProtocolCompleted']);self.assertTrue(any(x['errorClass']=='RuntimeError'for x in r['protocolFailures']));self.assertEqual(len(raw),1);self.assertTrue(raw[0].closed)
if __name__=='__main__':unittest.main(verbosity=2)
