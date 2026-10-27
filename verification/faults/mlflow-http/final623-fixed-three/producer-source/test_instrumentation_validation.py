"""Reject invalid startup arguments before creating diagnostic resources."""
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.instrumentation import instrument_psycopg
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(Path.cwd()/'artifacts/instrumentation-validation')))
BASE.mkdir(parents=True,exist_ok=True)
class Tests(unittest.TestCase):
    def fresh(self):return BASE/('case-'+uuid.uuid4().hex)
    def test_invalid_factory_does_not_create_a_diagnostic_directory(self):
        for factory in (None,7,object()):
            with self.subTest(factory=type(factory).__name__):
                path=self.fresh()
                with self.assertRaises(ValueError):instrument_psycopg(factory,path)
                self.assertFalse(path.exists(),'Rejected factory must not allocate an observer, files or worker')
    def test_invalid_async_flag_does_not_create_a_diagnostic_directory(self):
        for flag in (0,1,None,'async'):
            with self.subTest(flag=repr(flag)):
                path=self.fresh()
                with self.assertRaises(ValueError):instrument_psycopg(lambda:None,path,asynchronous=flag)
                self.assertFalse(path.exists(),'Only a boolean async mode is accepted before resource allocation')
    def test_invalid_arguments_leave_an_existing_path_untouched(self):
        path=self.fresh();path.mkdir();(path/'marker').write_bytes(b'original')
        with self.assertRaises(ValueError):instrument_psycopg(None,path)
        self.assertEqual([p.name for p in path.iterdir()],['marker'])
        self.assertEqual((path/'marker').read_bytes(),b'original')
    def test_valid_factories_remain_lazy_and_can_be_closed(self):
        for asynchronous in (False,True):
            path=self.fresh();calls=[]
            def factory():calls.append(True);raise RuntimeError('must stay lazy')
            observer,connect=instrument_psycopg(factory,path,asynchronous=asynchronous)
            self.assertEqual(calls,[]);self.assertTrue(callable(connect))
            observer.close();self.assertTrue((path/'instrumentation.json').exists())
if __name__=='__main__':
    result=unittest.main(verbosity=2,exit=False).result
    receipt={'schema':1,'kind':'instrumentation-invalid-argument-resource-regressions','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),'actualDatabaseExecution':False}
    print(json.dumps(receipt));raise SystemExit(0 if result.wasSuccessful() else 1)
