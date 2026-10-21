"""Small syntax/profile/auth checks only; no Node, network or product execution."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import py_compile
import sys
import unittest
from unittest import mock
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transport
spec = importlib.util.spec_from_file_location('orm_independent_candidate', HERE / 'audit.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
RUN = HERE / 'unit-artifacts' / ('run-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)


class CandidateTests(unittest.TestCase):
    def test_fixed_profile_and_contract(self):
        p = candidate.profile()
        contract = json.loads((HERE / 'contract-v1.json').read_bytes())
        self.assertEqual(p['moduleSha256'], '3b536b3ba28d912d04fe1ef6225c187bc4aca8dae2cf557d9e50a134a3c8945d')
        self.assertEqual(contract['profile'], p)
        self.assertEqual(len(contract['cases']), 24)
        self.assertEqual(sum(c['expected'] == 'partial-positive' for c in contract['cases']), 4)
        self.assertEqual(sum(c['expected'] == 'rejected' for c in contract['cases']), 20)

    def test_python_syntax_only(self):
        for name in ('audit.py', 'transport.py', 'test_candidate.py'):
            py_compile.compile(str(HERE / name), cfile=str(RUN / (name + '.pyc')), doraise=True)

    def test_explicit_actions_repository_guard(self):
        with self.assertRaises(ValueError):
            transport.guard_environment({})
        with self.assertRaises(ValueError):
            transport.guard_environment({'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'another/repo'})

    def test_audit_refuses_token_before_any_product_execution(self):
        with mock.patch.dict(os.environ, {'GITHUB_TOKEN': 'unit-only-not-persisted'}, clear=True), \
             mock.patch.object(candidate, 'run_bounded', side_effect=AssertionError('Must not launch a child')):
            with self.assertRaises(AssertionError):
                candidate.audit(RUN / 'not-created', candidate.profile())
        self.assertFalse((RUN / 'not-created').exists())

    def test_frozen_raw_get_parameters_and_native_identity(self):
        import base64
        import re
        raw_path = HERE.parent / 'remote-ci-39593218616/independent-orm-source2-r3/inputs/fixtures/source-observations.jsonl'
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                         '88cbaaee15e5e0faf403b2a91ce4ace53d4e2ddf656a06b1f15cf979fbf7a3ec')
        records = [json.loads(line) for line in raw_path.read_text().splitlines()]
        observed = []
        for batch in records:
            if batch.get('kind') != 'source-batch' or batch['operation'] != 'get':
                continue
            names = re.findall(r'%\(([A-Za-z_][A-Za-z0-9_]*)\)s', batch['originalSql'])
            self.assertEqual(len(names), 1)
            self.assertIn(names[0], ('id_1', 'pk_1'))
            self.assertEqual(list(batch['parameters']), names)
            key = batch['parameters'][names[0]]
            self.assertEqual(batch['observation']['source']['key'], key)
            field = batch['actualPGresult']['fields'][0]
            self.assertEqual((field['oid'], field['format']), (2950, 0))
            native = None if field['raw'] is None else base64.b64decode(field['raw']['base64']).decode()
            self.assertEqual(native, key if batch['observation']['source']['present'] else None)
            observed.append((batch['sourceSeq'], names[0]))
        self.assertEqual(len(observed), 13)
        self.assertEqual([seq for seq, name in observed if name == 'pk_1'], [82, 88, 92, 96])
        self.assertNotIn('String(batch.parameters.id_1)', (HERE / 'runtime.mjs').read_text())

    def test_driver_static_boundary_and_independence_declarations(self):
        text = (HERE / 'runtime.mjs').read_text(encoding='utf-8')
        for case in json.loads((HERE / 'contract-v1.json').read_bytes())['cases']:
            self.assertIn("'" + case['name'] + "'", text)
        imports = [line for line in text.splitlines() if line.startswith('import ')]
        self.assertTrue(all("from 'node:" in line for line in imports))
        self.assertLess(text.index('profile.moduleSha256'), text.index('await import('))
        self.assertIn('authorHarnessImported:false', text)
        self.assertEqual(hashlib.sha256((HERE / 'transport.py').read_bytes()).hexdigest(),
                         'f65c78c032f93a7b05366e04adbfc30ca49ede664d3bb4544af4b64142f22476')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests))
    receipt = {'schema': 1, 'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
               'scope': 'Python syntax, fixed profile, credential guard and driver static declarations only',
               'nodeExecuted': False, 'networkExecuted': False, 'databaseExecuted': False,
               'errors': [s.replace(str(HERE), '<candidate>') for _, s in result.errors + result.failures],
               'finishedAt': datetime.now(timezone.utc).isoformat()}
    raw = (json.dumps(receipt, indent=2) + '\n').encode()
    (RUN / 'receipt.json').open('xb').write(raw)
    print(json.dumps({'passed': receipt['passed'], 'testsRun': result.testsRun,
                      'receipt': str((RUN / 'receipt.json').relative_to(HERE)),
                      'sha256': hashlib.sha256(raw).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
