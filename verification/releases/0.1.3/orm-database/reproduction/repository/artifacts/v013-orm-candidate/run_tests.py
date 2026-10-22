"""Run lightweight owned fixtures and retain the first result on every attempt."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = HERE / 'runs' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)
def inventory():
    names = [path for directory in ('payload', 'baseline') for path in (HERE / directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    names += [HERE / name for name in ('prepare.py', 'run_tests.py', 'test_candidate.py', 'source-inputs.json')]
    return {path.relative_to(HERE).as_posix(): {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size} for path in sorted(names)}
before = inventory()
upstream_before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in json.loads((HERE / 'source-inputs.json').read_text())['files']}
with (RUN / 'first.log').open('x', encoding='utf8') as log:
    with redirect_stdout(log), redirect_stderr(log):
        spec = importlib.util.spec_from_file_location('v013_orm_candidate_tests', HERE / 'test_candidate.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        import psycopg
        with patch.object(psycopg, 'connect', side_effect=AssertionError('Database access forbidden in this fixture')):
            with patch.object(psycopg.AsyncConnection, 'connect', side_effect=AssertionError('Database access forbidden in this fixture')):
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
after = inventory()
upstream_after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in upstream_before}
receipt = {'schema': 1, 'kind': 'isolated-orm-cache-candidate-offline-checks',
    'passed': result.wasSuccessful() and before == after and upstream_before == upstream_after,
    'testsRun': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
    'candidateBindingsBefore': before, 'candidateBindingsAfter': after,
    'candidateUnchanged': before == after, 'originalSourcesUnchanged': upstream_before == upstream_after,
    'runtime': {'python': sys.version.split()[0], 'sqlalchemy': module.policy.sqlalchemy.__version__, 'psycopg': psycopg.__version__},
    'actualDatabaseExecution': False, 'buildExecuted': False, 'installationExecuted': False,
    'formalPerformanceMeasurement': False,
    'compilerWorkComparison': module.COMPILATION_COMPARISON,
    'failedTests': [case.id() for case, _ in result.failures + result.errors]}
path = RUN / 'receipt.json'
path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'passed': receipt['passed'], 'testsRun': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'receipt': path.relative_to(ROOT).as_posix()}))
raise SystemExit(0 if receipt['passed'] else 1)
