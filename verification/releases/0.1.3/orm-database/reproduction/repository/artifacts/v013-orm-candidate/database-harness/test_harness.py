"""Lightweight preflight/fixture-contract tests; cannot start a database."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
import common
import run_database as database

HERE = Path(__file__).resolve().parent
RUN = HERE / 'unit-runs' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)

class HarnessTests(unittest.TestCase):
    def test_frozen_candidate_and_harness_bindings(self):
        self.assertGreater(len(common.inputs()), 30)

    def test_source_binding_change_is_refused_without_writes(self):
        original = common.binding
        def fake(path):
            result = original(path)
            return {**result, 'sha256': '0' * 64} if Path(path).name == 'orm.py' else result
        with patch.object(common, 'binding', side_effect=fake), self.assertRaises(ValueError): common.inputs()

    def test_owned_path_and_external_connection_are_refused(self):
        with self.assertRaises(ValueError): common.under(HERE, HERE / 'executions')
        with self.assertRaises(ValueError): common.under(HERE / '../../external', HERE)
        fake_run = HERE / 'executions' / ('unit-' + uuid.uuid4().hex)
        with self.assertRaises(ValueError): common.connection_config(fake_run, HERE / 'external.json')

    def test_import_only_setup_helpers_keep_original_semantics(self):
        def body(text):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(text).body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ('install.py', 'relation_contract.py', 'control_log.py'):
            original = common.ROOT / 'artifacts/orm-v3-draft/slice3' / name
            self.assertEqual(body(original.read_text(encoding='utf8')), body((HERE / 'support' / name).read_text(encoding='utf8')))
        original = common.ROOT / 'artifacts/orm-v3-draft/slice3/run_postgres.py'
        self.assertEqual(original.read_bytes(), (HERE / 'frozen_run_postgres.py').read_bytes())

    def test_upstream_and_extracted_business_functions_are_frozen(self):
        upstream, report = database.frozen_upstream()
        self.assertEqual(report['commit'], '6397ace506d829a2ee12786da5d724c3f4c6b634')
        self.assertEqual(report['license'], 'MIT')
        sys.path[:0] = [str(common.CANDIDATE / 'payload/integrations/python'), str(upstream)]
        functions, bindings = database.definitions()
        self.assertEqual(set(bindings), {'RecordingCursor','models','work','surface'})
        self.assertEqual(len(functions['IDS']), 3)
        from moontxnwitness_capture import orm
        self.assertEqual(Path(orm.__file__).resolve(), common.CANDIDATE / 'payload/integrations/python/moontxnwitness_capture/orm.py')

    def test_ack_log_has_fixed_bound_and_cannot_replace_primary_error(self):
        connection = SimpleNamespace(_orm_native_replies=[], _orm_native_reply_gap=False)
        for _ in range(513): database.native_append(connection, {'acknowledged': False})
        self.assertEqual(len(connection._orm_native_replies), 512)
        self.assertTrue(connection._orm_native_reply_gap)
        class Broken:
            _orm_native_reply_gap = False
            @property
            def info(self): raise RuntimeError('secondary observer failure')
        broken = Broken()
        primary = ValueError('original driver failure')
        try:
            try: raise primary
            except ValueError:
                database.native_reply(broken, b'COMMIT', None, error=primary)
                raise
        except ValueError as observed:
            self.assertIs(observed, primary)
        self.assertTrue(broken._orm_native_reply_gap)

    def test_missing_reply_is_unknown_not_inferred_from_idle(self):
        connection = SimpleNamespace(_orm_native_replies=[], _orm_native_reply_gap=False,
            info=SimpleNamespace(transaction_status=0))
        database.native_reply(connection, b'COMMIT', 2, result=None)
        self.assertFalse(connection._orm_native_replies[0]['acknowledged'])
        self.assertIsNone(connection._orm_native_replies[0]['commandTag'])

    def test_cli_help_does_not_start_postgres(self):
        for name in ('run_owned.py', 'run_database.py'):
            result = subprocess.run([sys.executable, '-B', str(HERE / name), '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage:', result.stdout)

if __name__ == '__main__':
    before = common.inputs()
    with (RUN / 'first.log').open('x', encoding='utf8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HarnessTests))
    after = common.inputs()
    receipt = {'schema': 1, 'kind': 'isolated-orm-db-harness-offline-preflight',
        'passed': result.wasSuccessful() and before == after, 'testsRun': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'sourceBindingsBefore': before,
        'sourceBindingsAfter': after, 'sourceBindingsUnchanged': before == after,
        'actualDatabaseExecution': False, 'buildExecuted': False, 'installationExecuted': False}
    (RUN / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'testsRun': result.testsRun,
        'receipt': (RUN / 'receipt.json').relative_to(common.ROOT).as_posix()}))
    raise SystemExit(0 if receipt['passed'] else 1)
