"""Run the original configured-profile driver contracts without a database."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib, importlib.util, json, os
from pathlib import Path
import sys, unittest, uuid
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]

def main():
    output = ROOT / 'artifacts/user-profile-unit-tests' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), *sorted((ROOT/'integrations/python/moontxnwitness_capture').rglob('*.py'))]
    bindings = lambda: {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    receipt = {'passed': False, 'actualDatabaseExecution': False, 'sourceBindingsBefore': bindings()}
    try:
        with (output/'first.log').open('x', encoding='utf8') as log, redirect_stdout(log), redirect_stderr(log):
            spec = importlib.util.spec_from_file_location('configured_user_profile_contracts', ROOT/'integrations/python/moontxnwitness_capture/test_user_profile.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            import psycopg
            with patch.object(psycopg, 'connect', side_effect=AssertionError('Database access forbidden in driver contracts')), patch.object(psycopg.AsyncConnection, 'connect', side_effect=AssertionError('Database access forbidden in driver contracts')):
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
            receipt.update(passed=result.wasSuccessful() and not result.skipped, testsRun=result.testsRun,
                skipped=[(t.id(), reason) for t, reason in result.skipped],
                failures=[{'test': t.id(), 'traceback': error} for t, error in result.failures],
                errors=[{'test': t.id(), 'traceback': error} for t, error in result.errors])
    except Exception as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error)}
    receipt['sourceBindingsAfter'] = bindings()
    receipt['passed'] = receipt['passed'] and receipt['sourceBindingsBefore'] == receipt['sourceBindingsAfter']
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'testsRun': receipt.get('testsRun'), 'receipt': str(output/'receipt.json'), 'actualDatabaseExecution': False}))
    return 0 if receipt['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
