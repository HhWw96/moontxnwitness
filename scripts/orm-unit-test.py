"""Execute fixed ORM compiler/cache regression without a database connection."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'fixtures/orm-plans'


def inputs():
    paths = [Path(__file__), ROOT / 'examples/orm-requirements.txt']
    paths += list(FIXTURE.glob('*.py'))
    paths += list((ROOT / 'integrations/python/moontxnwitness_capture').glob('*.py'))
    return {path.relative_to(ROOT).as_posix(): {
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
        for path in sorted(paths)}


def main():
    parent = Path(os.environ.get('MTW_ORM_UNIT_WORK_ROOT', ROOT / 'artifacts/orm-unit-tests')).resolve()
    output = parent / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    before = inputs()
    receipt = {'schema': 1, 'kind': 'orm-fixed-plan-regression', 'passed': False,
        'actualDatabaseExecution': False, 'formalPerformanceMeasurement': False,
        'python': sys.version.split()[0], 'sourceBindingsBefore': before}
    try:
        with (output / 'first.log').open('x', encoding='utf8') as log, redirect_stdout(log), redirect_stderr(log):
            spec = importlib.util.spec_from_file_location('orm_fixed_plan_regression', FIXTURE / 'test_plans.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            import psycopg
            with patch.object(psycopg, 'connect', side_effect=AssertionError('Database access forbidden in offline units')):
                with patch.object(psycopg.AsyncConnection, 'connect', side_effect=AssertionError('Database access forbidden in offline units')):
                    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
            receipt.update(passed=result.wasSuccessful() and not result.skipped,
                testsRun=result.testsRun, skipped=[(case.id(), reason) for case, reason in result.skipped],
                failures=[{'test': case.id(), 'traceback': error} for case, error in result.failures],
                errors=[{'test': case.id(), 'traceback': error} for case, error in result.errors],
                runtime={'sqlalchemy': module.policy.sqlalchemy.__version__, 'psycopg': psycopg.__version__},
                compilerWorkComparison=module.COMPILATION_COMPARISON)
    except Exception as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error)}
    finally:
        receipt['sourceBindingsAfter'] = inputs()
        receipt['sourceBindingsUnchanged'] = before == receipt['sourceBindingsAfter']
        receipt['passed'] = receipt['passed'] and receipt['sourceBindingsUnchanged']
        path = output / 'receipt.json'
        path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'testsRun': receipt.get('testsRun'), 'receipt': str(path),
        'actualDatabaseExecution': False}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
