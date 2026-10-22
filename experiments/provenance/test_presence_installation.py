"""Package-only import/copy, alias semantics and actual implementation bindings."""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

import capture_profile
import presence_profile
import prototype
import initialization_guard
from test_presence_profile import Connection, P
from test_capture_profile import Connection as ColumnConnection, PROFILE
from moontxnwitness_capture import presence
from moontxnwitness_capture import _column_profile, _provenance, _initialization_guard
from moontxnwitness_capture._source_inventory import SOURCE_FILES

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'integrations/python/moontxnwitness_capture'


def child(code, *args):
    return subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, *map(str, args)],
                          text=True, capture_output=True, timeout=15)


class InstallationTests(unittest.TestCase):
    def payload(self):
        base = Path(os.environ['MTW_INTEGRATION_SCRATCH']).resolve()
        owner = REPO.parents[0].resolve()
        if not base.is_relative_to(owner):
            raise ValueError('Owned retained test scratch required')
        directory = base / ('consumer-' + uuid.uuid4().hex)
        package = directory / 'moontxnwitness_capture'
        package.mkdir(parents=True, exist_ok=False)
        for name in SOURCE_FILES:
            shutil.copyfile(PACKAGE / name, package / name)
        return directory, package

    def assert_child(self, process):
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_explicit_package_import_is_legacy_class_identity(self):
        self.assertIs(presence_profile, presence)
        self.assertIs(presence_profile.PresenceCapture, presence.PresenceCapture)
        self.assertIs(presence_profile.PresencePointProfile, presence.PresencePointProfile)
        self.assertIs(capture_profile, _column_profile)
        self.assertIs(prototype, _provenance)
        self.assertIs(initialization_guard, _initialization_guard)

    def test_legacy_presence_monkeypatch_changes_canonical_initializer(self):
        session = presence.PresenceCapture(P, keys=('a', 'new'))
        error = RuntimeError('exact package-global monkeypatch sentinel')
        with patch('presence_profile._business_columns'), patch('presence_profile.verify_presence_installation', side_effect=error) as verifier:
            with self.assertRaises(RuntimeError) as caught:
                session.initialize(Connection(autocommit=True))
        self.assertIs(caught.exception, error)
        verifier.assert_called_once()
        self.assertFalse(session._initialized)

    def test_legacy_column_monkeypatch_changes_package_globals(self):
        session = _column_profile.ColumnCapture(PROFILE, keys=('a', 'b'))
        error = RuntimeError('exact legacy-global sentinel')
        with patch('capture_profile.verify_installation', side_effect=error) as verifier:
            with self.assertRaises(RuntimeError) as caught:
                session.initialize(ColumnConnection(autocommit=True))
        self.assertIs(caught.exception, error)
        verifier.assert_called_once()

    def test_legacy_reimport_keeps_same_canonical_module(self):
        old = sys.modules.pop('presence_profile')
        try:
            self.assertIs(importlib.import_module('presence_profile'), old)
        finally:
            sys.modules['presence_profile'] = old

    def test_returning_profile_still_uses_same_column_base(self):
        from returning_profile import ReturningColumnCapture
        self.assertIs(ReturningColumnCapture.__mro__[1], _column_profile.ColumnCapture)

    def test_root_initializer_and_recorder_bytes_unchanged(self):
        self.assertEqual(hashlib.sha256((PACKAGE / '__init__.py').read_bytes()).hexdigest(),
                         '82ac16660a6e0ea61da6c19d27ef4f9711d475d2901a91fda4c7b0ea6948c3aa')
        self.assertEqual(hashlib.sha256((PACKAGE / 'capture.py').read_bytes()).hexdigest(),
                         '12c81689813bb820742cb5761b17bb523f996ddf651bae9a0a6dc5bdb4691b3e')

    def test_projection_string_is_unchanged(self):
        self.assertEqual(presence.PROJECTION, 'column-presence-register-v0.1.2-experimental')

    def test_package_only_copy_imports_without_driver_or_experiments(self):
        directory, package = self.payload()
        code = """import sys;sys.path.insert(0,sys.argv[1]);before=list(sys.path)
import moontxnwitness_capture
assert 'psycopg' not in sys.modules
assert 'moontxnwitness_capture.presence' not in sys.modules
from moontxnwitness_capture.presence import PresenceCapture,PresencePointProfile,implementation_bindings
assert before==sys.path
assert 'psycopg' not in sys.modules
assert all('experiments' not in value for value in sys.path)
p=PresencePointProfile('mtw_provenance_package_only');s=PresenceCapture(p,keys=('a','never'))
assert not s._initialized;assert len(implementation_bindings())==7
assert all(name not in sys.modules for name in ['presence_profile','capture_profile','prototype','initialization_guard'])
print('standalone-package-ok')"""
        process = child(code, directory)
        self.assert_child(process)
        self.assertEqual(process.stdout.strip(), 'standalone-package-ok')
        self.assertFalse((directory / 'experiments').exists())

    def test_legacy_source_entrypoint_bootstraps_only_integrations(self):
        code = """import sys;sys.path.insert(0,sys.argv[1]);before=list(sys.path)
import presence_profile
from moontxnwitness_capture import presence
assert presence_profile is presence
added=[p for p in sys.path if p not in before];assert len(added)==1
assert added[0].replace('\\\\','/').endswith('/integrations/python')
assert 'psycopg' not in sys.modules;print('legacy-alias-ok')"""
        process = child(code, REPO / 'experiments/provenance')
        self.assert_child(process)
        self.assertEqual(process.stdout.strip(), 'legacy-alias-ok')

    def test_legacy_shims_prefer_checkout_over_unloaded_old_package(self):
        directory, _ = self.payload()
        old = directory / 'old-site/moontxnwitness_capture'
        old.mkdir(parents=True)
        (old / '__init__.py').write_text('_simulated_old_package=True\n', encoding='utf8')
        for module in ['presence_profile', 'capture_profile', 'prototype', 'initialization_guard']:
            code = """import sys,importlib,pathlib
sys.path[:0]=[sys.argv[1],sys.argv[2]]
m=importlib.import_module(sys.argv[3]);import moontxnwitness_capture as package
assert not getattr(package,'_simulated_old_package',False)
assert pathlib.Path(m.__file__).resolve().parent==pathlib.Path(sys.argv[4]).resolve()
print('checkout-preferred')"""
            with self.subTest(module=module):
                process = child(code, old.parent, REPO / 'experiments/provenance', module, PACKAGE)
                self.assert_child(process)
                self.assertEqual(process.stdout.strip(), 'checkout-preferred')

    def test_legacy_shims_refuse_loaded_other_package_without_reload(self):
        directory, _ = self.payload()
        old = directory / 'loaded-site/moontxnwitness_capture'
        old.mkdir(parents=True)
        (old / '__init__.py').write_text('_simulated_old_package=True\n', encoding='utf8')
        for module in ['presence_profile', 'capture_profile', 'prototype', 'initialization_guard']:
            code = """import sys,importlib
sys.path[:0]=[sys.argv[1],sys.argv[2]]
import moontxnwitness_capture as before
try:importlib.import_module(sys.argv[3])
except ImportError as error:assert 'already loaded' in str(error)
else:raise AssertionError('mixed package source context was silently accepted')
assert sys.modules['moontxnwitness_capture'] is before and before._simulated_old_package
assert 'moontxnwitness_capture.presence' not in sys.modules
print('loaded-package-not-replaced')"""
            with self.subTest(module=module):
                process = child(code, old.parent, REPO / 'experiments/provenance', module)
                self.assert_child(process)
                self.assertEqual(process.stdout.strip(), 'loaded-package-not-replaced')

    def test_node_producers_preserve_structured_metadata_failure_receipts(self):
        process = subprocess.run([os.environ['MTW_NODE'], '--experimental-vm-modules',
                                  str(REPO / 'scripts/presence-producer-failure-test.mjs')],
                                 cwd=REPO, text=True, capture_output=True, timeout=30)
        self.assert_child(process)
        receipt = json.loads(process.stdout)
        self.assertTrue(receipt['passed'])
        self.assertEqual(receipt['cases'], 21)
        self.assertFalse(receipt['actualDatabaseExecution'])

    def test_package_code_has_no_experiment_or_path_bootstrap(self):
        for name in SOURCE_FILES:
            path = PACKAGE / name
            tree = ast.parse(path.read_text(encoding='utf8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, ['capture_profile', 'presence_profile', 'prototype', 'initialization_guard'])
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual(ast.unparse(node.func), 'sys.path.insert', name)

    def test_inventory_hashes_actual_implementation_not_shims(self):
        bindings = presence.implementation_bindings()
        self.assertEqual(set(bindings), {'moontxnwitness_capture/' + name for name in SOURCE_FILES})
        for name, item in bindings.items():
            raw = (PACKAGE.parent / name).read_bytes()
            self.assertEqual(item, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        shim = (REPO / 'experiments/provenance/presence_profile.py').read_bytes()
        self.assertNotEqual(bindings['moontxnwitness_capture/presence.py']['sha256'], hashlib.sha256(shim).hexdigest())

    def test_copied_implementation_change_updates_its_hash(self):
        directory, package = self.payload()
        target = package / 'presence.py'
        with target.open('ab') as stream:
            stream.write(b'\n# independent consumer source change\n')
        code = """import sys,json;sys.path.insert(0,sys.argv[1]);from moontxnwitness_capture.presence import implementation_bindings
print(json.dumps(implementation_bindings()))"""
        process = child(code, directory)
        self.assert_child(process)
        actual = json.loads(process.stdout)['moontxnwitness_capture/presence.py']
        raw = target.read_bytes()
        self.assertEqual(actual, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        self.assertNotEqual(actual, presence.implementation_bindings()['moontxnwitness_capture/presence.py'])

    def test_source_stripped_copy_cannot_substitute_shim_hash(self):
        directory, package = self.payload()
        # Retain the missing file under a non-source name, never delete it.
        (package / '_provenance.py').rename(package / '_provenance.retained')
        code = """import sys;sys.path.insert(0,sys.argv[1])
try:from moontxnwitness_capture.presence import implementation_bindings
except ModuleNotFoundError:print('missing-source-refused')
else:raise AssertionError('missing dependency was silently loaded from experiments')"""
        process = child(code, directory)
        self.assert_child(process)
        self.assertEqual(process.stdout.strip(), 'missing-source-refused')

    def test_python_receipt_producers_bind_before_and_after_package_code(self):
        for name in ['experiments/provenance/presence_postgres.py', 'experiments/provenance/capture_profile_postgres.py',
                     'experiments/business/dislock/postgres_test.py']:
            text = (REPO / name).read_text(encoding='utf8')
            tree = ast.parse(text)
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == 'implementation_bindings']
            self.assertEqual(len(calls), 2, name)
            self.assertIn('receipt["implementationSources"]', text)
            self.assertIn('"legacySourceRole"', text)

    def test_node_producers_name_package_sources_separately(self):
        expected = {'integrations/python/moontxnwitness_capture/' + name for name in SOURCE_FILES}
        for name in ['experiments/provenance/presence_e2e.mjs', 'experiments/provenance/capture_profile_e2e.mjs',
                     'experiments/business/dislock/e2e.mjs']:
            text = (REPO / name).read_text(encoding='utf8')
            line = next(line for line in text.splitlines() if line.startswith('const implementationPaths='))
            actual = json.loads(line.removeprefix('const implementationPaths=').removesuffix(';'))
            self.assertEqual(set(actual), expected)
            self.assertIn('receipt.implementationSources.after', text)
            self.assertIn('captureSource.compatibilityRole=', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
