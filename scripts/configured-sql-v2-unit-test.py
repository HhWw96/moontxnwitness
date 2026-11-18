"""Run offline V2 candidate and V1 regression tests with explicit dependencies."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dependency-root', default=os.environ.get('MTW_SQLGLOT_PATH'))
    parser.add_argument('--output-dir', default=str(ROOT / 'artifacts/configured-sql-v2'))
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / 'integrations/python'))
    dependency = Path(args.dependency_root).resolve() if args.dependency_root else None
    if dependency is not None:
        if not dependency.is_dir(): parser.error('Explicit dependency directory is missing')
        sys.path.insert(0, str(dependency))
    output = Path(args.output_dir).resolve()
    originals = ['integrations/python/moontxnwitness_capture/configured_sql.py',
        'integrations/python/moontxnwitness_capture/test_configured_sql.py',
        'integrations/python/requirements-configured-sql.txt',
        'integrations/python/moontxnwitness_capture/instrumentation.py',
        'integrations/python/moontxnwitness_capture/configured_fetch.py',
        'integrations/python/moontxnwitness_capture/configured_source.py',
        'integrations/python/moontxnwitness_capture/configured_session.py',
        'integrations/python/moontxnwitness_capture/profiles/orm_cursor.py']
    source = ['integrations/python/moontxnwitness_capture/configured_sql_v2.py',
        'integrations/python/moontxnwitness_capture/test_configured_sql_v2.py',
        'scripts/configured-sql-v2-unit-test.py']
    before = {name: sha(ROOT / name) for name in originals}
    stream, rows, subtests = io.StringIO(), [], []
    class Result(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test); rows.append({'test': test.id(), 'passed': True})
        def addSubTest(self, test, subtest, error):
            super().addSubTest(test, subtest, error)
            row = {'test': str(subtest), 'passed': error is None}
            if error is not None: row['error'] = self._exc_info_to_string(error, test)
            subtests.append(row)
        def addFailure(self, test, error):
            super().addFailure(test, error)
            rows.append({'test': test.id(), 'passed': False, 'error': self._exc_info_to_string(error, test)})
        def addError(self, test, error):
            super().addError(test, error)
            rows.append({'test': test.id(), 'passed': False, 'error': self._exc_info_to_string(error, test)})
    versions, origins, result, setup_error = {}, {}, None, None
    try:
        for package, expected in [('sqlglot', '30.26.0'), ('sqlalchemy', '2.0.55')]:
            versions[package] = importlib.metadata.version(package)
            if versions[package] != expected:
                raise RuntimeError(package + ' must be exactly ' + expected)
            origin = Path(importlib.util.find_spec(package).origin).resolve()
            origins[package] = str(origin)
            if dependency is not None and not origin.is_relative_to(dependency):
                raise RuntimeError(package + ' resolved outside the explicit read-only dependency root')
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'moontxnwitness_capture.test_configured_sql_v2', 'moontxnwitness_capture.test_configured_sql'])
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
        passed = result.wasSuccessful()
    except Exception:
        setup_error = traceback.format_exc(); passed = False
    after = {name: sha(ROOT / name) for name in originals}
    drivers = sorted(name for name in sys.modules if name == 'psycopg' or name.startswith('psycopg.'))
    passed = passed and before == after and not drivers
    receipt = {'format': 'configured-sql-v2-offline-candidate-validation/v1',
        'createdUtc': datetime.now(timezone.utc).isoformat(), 'passed': passed,
        'testsRun': result.testsRun if result else 0,
        'failed': len(result.failures) + len(result.errors) if result else 1,
        'subtestsRun': len(subtests), 'parserAndCompilerVersions': versions,
        'dependencyOrigins': origins, 'dependencyInstallationPerformed': False,
        'setupError': setup_error, 'originalFilesUnchanged': before == after,
        'originalBeforeSha256': before, 'originalAfterSha256': after,
        'sourceSha256': {name: sha(ROOT / name) for name in source},
        'driverModulesLoaded': drivers, 'actualDatabaseExecution': False, 'ddlExecuted': False,
        'sourceFactsProduced': False, 'modelCoverageAccepted': False, 'moonbitProjectionVerified': False,
        'formalPerformanceMeasurement': False, 'publicReleasePerformed': False,
        'results': rows, 'subtestResults': subtests}
    output.mkdir(parents=True, exist_ok=True)
    prior = output / 'validation.json'
    failure = output / 'validation-first-failure.json'
    if prior.exists() and not failure.exists() and not json.loads(prior.read_text(encoding='utf-8')).get('passed'):
        failure.write_bytes(prior.read_bytes())
        prior_log = output / 'tests.txt'
        if prior_log.exists(): (output / 'tests-first-failure.txt').write_bytes(prior_log.read_bytes())
    (output / 'validation.json').write_text(json.dumps(receipt, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    (output / 'tests.txt').write_text(stream.getvalue() + (setup_error or ''), encoding='utf-8')
    print(json.dumps({'passed': passed, 'tests': receipt['testsRun'], 'failed': receipt['failed'],
                      'receipt': str(output / 'validation.json')}))
    if not passed: print(stream.getvalue() + (setup_error or ''), file=sys.stderr)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
