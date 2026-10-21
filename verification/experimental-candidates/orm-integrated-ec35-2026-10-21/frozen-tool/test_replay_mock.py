"""Lightweight read-only preflight and mock checks; never launches Node."""
from pathlib import Path
import importlib.util
import io
import json
import os
import py_compile
import sys
import unittest
from unittest.mock import patch
import uuid
import hashlib
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated24_candidate',HERE/'replay.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
RUN=HERE/'unit-artifacts'/('run-'+uuid.uuid4().hex);RUN.mkdir(parents=True)

class ReplayTests(unittest.TestCase):
    def test_python_syntax(self):
        for name in ('replay.py','test_replay_mock.py'):
            py_compile.compile(str(HERE/name),cfile=str(RUN/(name+'.pyc')),doraise=True)
    def test_readonly_exact_current_preflight(self):
        p=m.preflight(m.ROOT,m.ROOT/'dist')
        self.assertEqual(p['sourceSha256'],'ec35d4a61267af9c5600baf6e62197219aa979fdc1f36ca17a9a4bc40f1d9787')
        self.assertEqual(p['files']['capture-core.mjs']['sha256'],'82294d92bdad14997bd649a8cb732de6c8681229e27247371a3eb0a801658363')
    def test_original_driver_and24_expectations_are_fixed_bytes(self):
        self.assertEqual(m.binding(HERE/'runtime.mjs')['sha256'],m.DRIVER_SHA)
        self.assertEqual(m.binding(HERE/'contract-v1.json')['sha256'],m.CONTRACT_SHA)
        base=m.load(HERE/'baseline-bindings.json')['cases'];contract=m.load(HERE/'contract-v1.json')['cases']
        self.assertEqual([(x['name'],x['expected']) for x in base],[(x['name'],x['expected']) for x in contract])
        self.assertEqual(len(base),24)
    def test_child_environment_removes_credentials(self):
        with patch.dict(os.environ,{'GITHUB_TOKEN':'test-only','GH_TOKEN':'test-only','OPENAI_API_KEY':'test-only','PATH':'known'},clear=True):
            self.assertEqual(m.child_environment(),{'PATH':'known'})
    def test_structural_difference_keeps_exact_failure_reason(self):
        previous={'gaps':[{'message':'Failure(src/a.mbt:24)'}]};current={'gaps':[{'message':'Failure(src/a.mbt:38)'}]}
        self.assertEqual(m.differences(previous,current),[{'path':'$.gaps[0].message','expected':'Failure(src/a.mbt:24)','actual':'Failure(src/a.mbt:38)'}])
    def test_readonly_preflight_rejects_target_binding_before_child(self):
        with patch.object(m,'binding',return_value={'sha256':'wrong','bytes':1}),patch.object(m.subprocess,'Popen',side_effect=AssertionError('No child allowed')):
            with self.assertRaises(AssertionError):m.preflight(m.ROOT,m.ROOT/'dist')

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReplayTests))
    receipt={'schema':1,'passed':result.wasSuccessful(),'testsRun':result.testsRun,'scope':'Python syntax, strict readonly byte preflight and mocked refusal/environment only',
             'nodeExecuted':False,'databaseCompiledOrBenchmarked':False,
             'failures':[s.replace(str(HERE),'<candidate>') for _,s in result.errors+result.failures]}
    b=m.save(RUN/'receipt.json',receipt)
    print(json.dumps({'passed':receipt['passed'],'testsRun':result.testsRun,'receipt':str((RUN/'receipt.json').relative_to(HERE)),**b}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
