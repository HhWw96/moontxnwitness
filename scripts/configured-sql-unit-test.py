"""Run optional configured SQL adapter tests without changing an environment."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import sys
import traceback
import unittest

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dependency-root', default=os.environ.get('MTW_SQLGLOT_PATH'))
    args=parser.parse_args()
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(ROOT/'integrations/python'))
    if args.dependency_root:
        dependency=Path(args.dependency_root).resolve()
        if not dependency.is_dir():parser.error('Explicit optional dependency directory is missing')
        sys.path.insert(0,str(dependency))
    else:dependency=None
    existing=['integrations/python/moontxnwitness_capture/orm.py',
        'integrations/python/moontxnwitness_capture/instrumentation.py',
        'integrations/python/moontxnwitness_capture/profiles/model_sql.py',
        'integrations/python/moontxnwitness_capture/profiles/model_profile.py',
        'integrations/python/moontxnwitness_capture/profiles/orm_install.py',
        'integrations/python/moontxnwitness_capture/profiles/orm_cursor.py',
        'src/model_profile_v3.mbt','src/model_profile_sql_v3.mbt',
        'src/model_profile_plans_v3.mbt','src/model_profile_projection_v3.mbt',
        'src/orm_profile_v3.mbt','src/orm_sql_v3.mbt','src/orm_source2_v3.mbt']
    before={name:sha(ROOT/name) for name in existing}
    output=ROOT/'artifacts/configured-sql-adapter-validation.json'
    rows=[];subtests=[];stream=io.StringIO();setup_error=None
    class Result(unittest.TextTestResult):
        def addSuccess(self,test):super().addSuccess(test);rows.append({'test':test.id(),'passed':True})
        def addSubTest(self,test,subtest,error):
            super().addSubTest(test,subtest,error)
            row={'test':str(subtest),'passed':error is None}
            if error is not None:row['error']=self._exc_info_to_string(error,test)
            subtests.append(row)
        def addFailure(self,test,error):super().addFailure(test,error);rows.append({'test':test.id(),'passed':False,'error':self._exc_info_to_string(error,test)})
        def addError(self,test,error):super().addError(test,error);rows.append({'test':test.id(),'passed':False,'error':self._exc_info_to_string(error,test)})
    try:
        import sqlglot
        version=importlib.metadata.version('sqlglot')
        if version!='30.26.0':raise RuntimeError('Explicit SQLGlot 30.26.0 optional dependency required')
        origin=Path(sqlglot.__file__).resolve()
        if dependency is not None and not origin.is_relative_to(dependency):
            raise RuntimeError('SQLGlot resolved outside the explicitly supplied dependency root')
        suite=unittest.defaultTestLoader.loadTestsFromName('moontxnwitness_capture.test_configured_sql')
        result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
        passed=result.wasSuccessful()
    except Exception:
        version=None;origin=None;result=None;passed=False;setup_error=traceback.format_exc()
    after={name:sha(ROOT/name) for name in existing}
    passed=passed and before==after
    license_path=ROOT/'integrations/python/licenses/SQLGlot-30.26.0-MIT.txt'
    source_files=['integrations/python/moontxnwitness_capture/configured_sql.py',
        'integrations/python/moontxnwitness_capture/test_configured_sql.py',
        'integrations/python/requirements-configured-sql.txt','scripts/configured-sql-unit-test.py']
    receipt={'format':'configured-sql-adapter-offline-validation/v1','passed':passed,
        'testsRun':result.testsRun if result is not None else 0,'failed':len(result.failures)+len(result.errors) if result is not None else 1,
        'parserVersion':version,'parserOrigin':str(origin) if origin else None,'setupError':setup_error,
        'originalBeforeSha256':before,'originalAfterSha256':after,'originalFilesUnchanged':before==after,
        'sourceSha256':{name:sha(ROOT/name) for name in source_files},
        'license':{'name':'MIT','copyright':'Copyright (c) 2026 Toby Mao','file':license_path.relative_to(ROOT).as_posix(),'sha256':sha(license_path)},
        'actualDatabaseExecution':False,'ddlExecuted':False,'driverInstrumentationChanged':False,
        'sqlRewrittenOrExecuted':False,'moonbitProjectionVerified':False,'completeAnalysisClaimed':False,
        'formalPerformanceMeasurement':False,'publicReleasePerformed':False,'subtestsRun':len(subtests),'subtestResults':subtests,'results':rows}
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        previous=json.loads(output.read_text(encoding='utf8'))
        failure=output.with_name('configured-sql-adapter-first-failure.json')
        if not previous.get('passed') and not failure.exists():failure.write_bytes(output.read_bytes())
    temporary=output.with_suffix('.json.tmp');temporary.write_text(json.dumps(receipt,ensure_ascii=True,indent=2)+'\n',encoding='utf8');temporary.replace(output)
    (ROOT/'artifacts/configured-sql-adapter-tests.txt').write_text(stream.getvalue()+(setup_error or ''),encoding='utf8')
    print(json.dumps({'passed':passed,'tests':receipt['testsRun'],'failed':receipt['failed'],'receipt':str(output)}))
    if not passed:print(stream.getvalue(),setup_error or '',file=sys.stderr)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
