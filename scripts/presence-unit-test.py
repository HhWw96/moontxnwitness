"""Unified ordinary-table units with owned retained scratch; never uses a DB."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / 'experiments/provenance'
MODULES = ['test_capture_profile', 'test_returning_profile', 'test_presence_profile',
           'test_initialization_guard', 'test_presence_installation']
sys.dont_write_bytecode = True
sys.path[:0] = [str(PROFILES), str(ROOT / 'integrations/python')]


def binding(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def inputs():
    names = ['scripts/presence-unit-test.py', 'scripts/presence-producer-failure-test.mjs']
    for folder in ['integrations/python/moontxnwitness_capture', 'experiments/provenance']:
        names.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / folder).glob('*.py'))
    names += ['experiments/provenance/presence_e2e.mjs', 'experiments/provenance/capture_profile_e2e.mjs',
              'experiments/business/dislock/e2e.mjs', 'experiments/business/dislock/postgres_test.py']
    return {name: binding(ROOT / name) for name in sorted(set(names))}


def identities(suite):
    return [test.id() for group in suite for test in flatten(group)]


def flatten(suite):
    if not isinstance(suite, unittest.TestSuite):
        yield suite
    else:
        for item in suite:
            yield from flatten(item)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--node', default=os.environ.get('MTW_NODE') or shutil.which('node'))
    args = parser.parse_args()
    if not args.node:
        raise ValueError('An existing Node runtime is required for metadata-only failure units')
    os.environ['MTW_NODE'] = str(Path(args.node).resolve())
    parent = ROOT / 'artifacts/presence-unit-tests'
    parent.mkdir(parents=True, exist_ok=True)
    output = parent / ('run-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(exist_ok=False)
    scratch = output / 'scratch'
    scratch.mkdir()
    os.environ['MTW_INTEGRATION_SCRATCH'] = str(scratch.resolve())
    before = inputs()
    receipt = {'schema': 1, 'passed': False, 'actualDatabaseExecution': False, 'actualCoreBuild': False,
               'sourceBindingsBefore': before, 'python': sys.version.split()[0], 'modules': MODULES}
    try:
        with (output / 'first.log').open('x', encoding='utf8') as log, redirect_stdout(log), redirect_stderr(log):
            suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
            receipt['expectedTests'] = identities(suite)
            with patch('psycopg.connect', side_effect=AssertionError('A unit test attempted database access')):
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        receipt.update(passed=result.wasSuccessful() and not result.skipped, testsRun=result.testsRun,
                       skipped=[(test.id(), reason) for test, reason in result.skipped],
                       failures=[{'test': test.id(), 'traceback': error} for test, error in result.failures],
                       errors=[{'test': test.id(), 'traceback': error} for test, error in result.errors])
    except BaseException as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error)}
    finally:
        after = inputs()
        receipt['sourceBindingsAfter'] = after
        receipt['sourceBindingsUnchanged'] = before == after
        receipt['passed'] = receipt['passed'] and before == after
        with (output / 'receipt.json').open('x', encoding='utf8') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'passed': receipt['passed'], 'testsRun': receipt.get('testsRun'),
                      'actualDatabaseExecution': False, 'receipt': str(output / 'receipt.json')}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
