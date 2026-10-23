"""Deterministic scheduler check; no DB and no performance measurement.

The original first writer is paused until public flush(). A duplicate constructor
is attempted only after that lawful original writer flushes. Product code and
all original equality/error assertions are unchanged except candidate flush.
"""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parent
ORIGINAL=BASE.parent/'source'
CANDIDATE=BASE/'source'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def child(which,mode):
    root=ORIGINAL if which=='original' else CANDIDATE
    scratch=BASE/'evidence'/(which+'-'+mode)
    scratch.mkdir(parents=True,exist_ok=False)
    os.environ['MTW_JOURNAL_TEST_ROOT']=str(scratch/'raw')
    package=root/'integrations/python/moontxnwitness_capture'
    sys.path.insert(0,str(package.parent))
    from moontxnwitness_capture.source_sink import GroupedSourceSink
    spec=importlib.util.spec_from_file_location('independent_source_tests',package/'test_source_sink.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    stream=io.StringIO();schedule=[]
    if mode=='race':
        gate=threading.Event();instances=[]
        real_worker=GroupedSourceSink._worker;real_flush=GroupedSourceSink.flush
        def gated_worker(self):
            if not gate.wait(5):raise RuntimeError('Independent scheduler gate was not released')
            return real_worker(self)
        def public_flush(self):
            schedule.append({'event':'public-flush','bytesBefore':self.path.stat().st_size})
            gate.set();result=real_flush(self)
            schedule.append({'event':'public-flush-complete','durableSeq':result,'bytesAfter':self.path.stat().st_size})
            return result
        def construction(*args,**kwargs):
            if instances:
                schedule.append({'event':'before-duplicate','bytesBeforeLawfulBackgroundWrite':instances[0].path.stat().st_size})
                # Legal original-writer progress may happen while a second caller
                # prepares an unrelated constructor; it does not come from it.
                instances[0].flush()
            value=GroupedSourceSink(*args,**kwargs);instances.append(value);return value
        case=module.Tests('test_duplicate_target_is_never_overwritten')
        with mock.patch.object(GroupedSourceSink,'_worker',gated_worker), mock.patch.object(GroupedSourceSink,'flush',public_flush), mock.patch.object(module,'GroupedSourceSink',construction):
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([case]))
    else:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    text=stream.getvalue();(scratch/'first.log').write_text(text,encoding='utf8',newline='\n')
    receipt={'schema':1,'variant':which,'mode':mode,'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),'testSha256':sha(package/'test_source_sink.py'),'sourceSinkSha256':sha(package/'source_sink.py'),'schedule':schedule,'firstLogSha256':sha(scratch/'first.log')}
    (scratch/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt));return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    if len(sys.argv)>1:raise SystemExit(child(sys.argv[1],sys.argv[2]))
    (BASE/'evidence').mkdir(exist_ok=False)
    results=[]
    for variant,mode,expected_pass in [('original','race',False),('candidate','race',True),('candidate','suite',True)]:
        process=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),variant,mode],capture_output=True)
        prefix=BASE/'evidence'/(variant+'-'+mode)
        (prefix/'stdout.raw').write_bytes(process.stdout);(prefix/'stderr.raw').write_bytes(process.stderr)
        receipt=json.loads((prefix/'receipt.json').read_text(encoding='utf8'))
        results.append({'variant':variant,'mode':mode,'expectedPass':expected_pass,'actualPass':receipt['passed'],'returncode':process.returncode,'expectationMet':receipt['passed'] is expected_pass,'receiptSha256':sha(prefix/'receipt.json')})
    report={'schema':1,'kind':'deterministic-original-test-race-and-public-barrier-fix','passed':all(x['expectationMet'] for x in results),'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'frozenSource':'bf28179a40aa2d1325f4f1484acb30362eea4f18','runnerSha256':sha(Path(__file__).resolve()),'results':results,'scope':'Controlled lawful background header-write race; retains original assertions and all first logs. No claim about remote repeat or full suite.'}
    (BASE/'evidence/receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report));raise SystemExit(0 if report['passed'] else 1)
