"""Run bounded source-buffer file I/O and fake-profile regressions; no DB/network."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
SUITES = ['test_source_sink.py', 'test_sync_watermark.py',
          'test_source_buffer_integration.py', 'test_instrumentation_validation.py']


def bindings():
    files = [Path(__file__), *sorted((ROOT / 'integrations/python/moontxnwitness_capture').rglob('*.py')),
             ROOT / 'docs/capture-write-buffer-candidate.md', ROOT / 'docs/grouped-source-persistence.md']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    output = ROOT / 'artifacts/source-buffer-unit-tests' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    before = bindings()
    receipt = {'schema': 1, 'kind': 'source-buffer-unit-tests', 'passed': False,
               'actualDatabaseExecution': False, 'networkExecuted': False,
               'formalPerformanceMeasurement': False, 'sourceBindingsBefore': before}
    previous_root = os.environ.get('MTW_JOURNAL_TEST_ROOT')
    os.environ['MTW_JOURNAL_TEST_ROOT'] = str(output / 'io')
    try:
        with (output / 'first.log').open('x', encoding='utf8') as log, redirect_stdout(log), redirect_stderr(log):
            import psycopg
            import sqlalchemy
            if psycopg.__version__ != '3.3.6' or sqlalchemy.__version__ != '2.0.55':
                raise RuntimeError('Pure source-buffer tests require existing pinned psycopg 3.3.6 and SQLAlchemy 2.0.55 dependencies')
            receipt['runtime'] = {'python': sys.version, 'psycopg': psycopg.__version__, 'sqlalchemy': sqlalchemy.__version__}
            forbidden = AssertionError('Database and network access forbidden in pure source-buffer tests')
            with mock.patch.object(psycopg, 'connect', side_effect=forbidden), \
                 mock.patch.object(psycopg.Connection, 'connect', side_effect=forbidden), \
                 mock.patch.object(psycopg.AsyncConnection, 'connect', side_effect=forbidden), \
                 mock.patch.object(socket.socket, 'connect', side_effect=forbidden), \
                 mock.patch.object(socket.socket, 'connect_ex', side_effect=forbidden):
                suite = unittest.TestSuite()
                for i, filename in enumerate(SUITES):
                    spec = importlib.util.spec_from_file_location('source_buffer_suite_' + str(i), ROOT / 'integrations/python/moontxnwitness_capture' / filename)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            receipt.update(passed=result.wasSuccessful() and not result.skipped, testsRun=result.testsRun,
                           failures=[{'test': t.id(), 'traceback': error} for t, error in result.failures],
                           errors=[{'test': t.id(), 'traceback': error} for t, error in result.errors],
                           skipped=[{'test': t.id(), 'reason': reason} for t, reason in result.skipped])
    except Exception as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error)}
    finally:
        if previous_root is None:
            os.environ.pop('MTW_JOURNAL_TEST_ROOT', None)
        else:
            os.environ['MTW_JOURNAL_TEST_ROOT'] = previous_root
    receipt['sourceBindingsAfter'] = bindings()
    receipt['sourceUnchanged'] = before == receipt['sourceBindingsAfter']
    receipt['passed'] = receipt['passed'] and receipt['sourceUnchanged']
    receipt['logSha256'] = hashlib.sha256((output / 'first.log').read_bytes()).hexdigest()
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: receipt.get(k) for k in ('passed', 'testsRun', 'sourceUnchanged', 'actualDatabaseExecution', 'networkExecuted', 'formalPerformanceMeasurement', 'failure')} | {'receipt': str(output / 'receipt.json')}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
