"""Run real-file grouped storage, watermark and cost-protocol regressions."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib, importlib.util, json, os
from pathlib import Path
import sys, unittest, uuid
ROOT=Path(__file__).resolve().parents[1]
SUITES=['integrations/python/moontxnwitness_capture/test_source_sink.py',
        'integrations/python/moontxnwitness_capture/test_sync_watermark.py',
        'experiments/provenance/test_full_capture_cost.py',
        'experiments/provenance/test_formal_harness_fix.py',
        'experiments/provenance/test_formal_startup_failure.py',
        'experiments/provenance/test_formal_workflow_contexts.py',
        'experiments/provenance/test_cell_archive.py']
def bindings():
    files=[Path(__file__),*(ROOT/'integrations/python/moontxnwitness_capture').glob('*.py'),
           *(ROOT/'experiments/provenance').glob('*.py')]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
def main():
    out=ROOT/'verification/capture-persistence'/('unit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True,exist_ok=False)
    before=bindings();result=None
    receipt={'schema':1,'kind':'grouped-storage-and-cost-protocol-regression','passed':False,
             'actualDatabaseExecution':False,'formalPerformanceMeasurement':False,'sourceBindingsBefore':before}
    try:
        with (out/'first.log').open('x',encoding='utf8') as log,redirect_stdout(log),redirect_stderr(log):
            suite=unittest.TestSuite()
            for i,name in enumerate(SUITES):
                spec=importlib.util.spec_from_file_location('mtw_persistence_suite_'+str(i),ROOT/name)
                module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        receipt.update(passed=result.wasSuccessful(),testsRun=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                       skipped=[{'test':t.id(),'reason':reason} for t,reason in result.skipped])
    except Exception as error:receipt.update(errorClass=type(error).__name__,error=str(error))
    receipt['sourceBindingsAfter']=bindings();receipt['sourceUnchanged']=before==receipt['sourceBindingsAfter']
    receipt['passed']=receipt['passed'] and receipt['sourceUnchanged']
    receipt['log']={'file':'first.log','sha256':hashlib.sha256((out/'first.log').read_bytes()).hexdigest()}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('sourceBindingsBefore','sourceBindingsAfter')}|{'receipt':(out/'receipt.json').relative_to(ROOT).as_posix()}))
    return 0 if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
