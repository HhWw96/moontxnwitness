"""Public input closure and private-file regression on tiny retained checkouts."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import distribution_manifest as inventory
import stage_ci_evidence as ci

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'artifacts/distribution-tests'
        parent.mkdir(parents=True, exist_ok=True)
        cls.root = Path(tempfile.mkdtemp(prefix='run-', dir=parent)).resolve()
        assert cls.root.is_relative_to(parent.resolve())

        def put(name, value):
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf8')

        put('.gitignore', 'artifacts/\ndist/\n*.log\nverification/private.json\n')
        put('package.json', {'version': '0.1.2'})
        for folder in inventory.FIXED_VERIFICATION_ROOTS:
            put(folder + '/fixture.json', {'retained': True})
        for name in inventory.FIXED_VERIFICATION_FILES:
            put(name, {})
        put('verification/v3/dislock-sql-supplement-preregistration-2026-10-21.json', {
            'originalFailureReceipt': {'path': 'verification/failure.json'},
            'originalAuditImplementation': {'path': 'verification/original.py'}})
        put('verification/failure.json', {'passed': False})
        put('verification/original.py', '# preserved original failure implementation\n')
        put('fixtures/relation-v3/manifest.json', {
            'historyArchives': [{'file': 'verification/relation-v3/original.zip'}]})
        put('verification/relation-v3/original.zip', 'placeholder archive; never executed\n')
        for name in ('receipt.json', 'capture.json', 'rr.capsule.json', 'serial.capsule.json', 'mini.capsule.json'):
            put('verification/releases/0.1.2/postgres/' + name, {})
        put('verification/releases/0.1.2/acceptance.json', {
            'databaseEvidence': 'database.json', 'tests': {'receipt': '../../summary.json'}})
        put('verification/releases/0.1.2/database.json', {
            'receipts': {'presence': {'path': 'presence/current'}}})
        put('verification/presence/current/receipt.json', {'actualDatabaseExecution': True})
        put('verification/presence/current/trace.json', {'retained': True})
        put('verification/capture-postgres.json', {'path': 'capture/current'})
        put('verification/capture/current/trace.json', {})
        put('verification/summary.json', {'passed': True})
        put('verification/old/unneeded.json', {'retainedInGit': True})
        for name in ('README.md', 'LICENSE', 'CHANGELOG.md', 'THIRD_PARTY.md', 'run-demo.cmd'):
            put(name, 'fixture\n')
        put('cmd/sdk.mjs', 'export const fixture = true;\n')
        put('integrations/python/moontxnwitness_capture/capture.py', '# fixture\n')
        put('docs/usage.md', 'fixture\n')
        put('examples/input.json', {})
        put('examples/orm-profile-roundtrip.mjs', '// offline configured-profile consumer\n')
        put('examples/classification-roundtrip.mjs', '// offline category source consumer\n')
        put('fixtures/classification-v3/source-closed-noisy-g2.json', {'syntheticInputs': True})
        put('fixtures/orm-profile-v3/synthetic-nonrepeatable-first/profile-source.json', {'explicitlySynthetic': True})
        cls.run_git('init', '--quiet')
        cls.run_git('add', '.')
        # Fixed public baseline fixtures may live below an intentionally ignored dist/.
        # Force only these known synthetic public inputs, before private files exist.
        for folder in inventory.FIXED_VERIFICATION_ROOTS:
            cls.run_git('add', '--force', '--', folder + '/fixture.json')
        cls.run_git('-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '--quiet', '-m', 'Retained distribution fixture')
        cls.public = set(cls.run_git('ls-files', '-z').split('\0')) - {''}
        put('dist/core.mjs', 'export const actualCore = true;\n')
        put('dist/capture-core.mjs', 'export const actualCaptureCore = true;\n')
        put('dist/orm-profile.mjs', 'export const analyzeOrmProfileV3 = true;\n')
        put('dist/classification.mjs', 'export const classifyV3 = true;\n')
        cls.tested = {'cmd/sdk.mjs': 'fixture', 'dist/core.mjs': 'fixture'}
        cls.selection = inventory.select_distribution_files(cls.root, cls.public, cls.tested, '0.1.2')
        for name in ('verification/private.json', 'verification/private.log', 'cmd/private.log',
                     'integrations/python/moontxnwitness_capture/private.log'):
            put(name, 'PRIVATE\n')
        put('verification/new/failure.json', {'passed': False})
        for version in ('0.1.1', '0.1.2'):
            put('artifacts/MoonTxnWitness-v' + version + '-source.zip', 'placeholder; never executed\n')
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), contextlib.redirect_stdout(io.StringIO()):
            ci.stage(cls.root)
        cls.index = json.loads((cls.root / 'artifacts/ci-evidence/current-run-index.json').read_text())
        cls.staged = {row['file'] for row in cls.index['files']}

    @classmethod
    def run_git(cls, *args):
        return subprocess.check_output(['git', '-c', 'core.longpaths=true', *args], cwd=cls.root,
                                       text=True, encoding='utf8', stderr=subprocess.PIPE, timeout=20)

    def test_current_input_closure(self):
        inventory.assert_complete(self.selection)
        self.assertIn('cmd/sdk.mjs', self.selection['source'])
        self.assertNotIn('dist/core.mjs', self.selection['source'])
        self.assertIn('dist/core.mjs', self.selection['portable'])

    def test_fixed_public_baseline_dist_remains_and_untracked_copy_is_refused(self):
        name = 'verification/releases/0.2.0/published-package-review/public-reproduction/downloaded-components/0.2.0/portable/dist/fixture.json'
        for kind in ('source', 'portable'):
            self.assertIn(name, self.selection[kind])
        missing = inventory.select_distribution_files(self.root, self.public - {name}, self.tested, '0.1.2')
        with self.assertRaises(AssertionError):
            inventory.assert_complete(missing)

    def test_all_relation_archive_bytes_remain(self):
        for kind in ('source', 'portable'):
            self.assertIn('verification/relation-v3/original.zip', self.selection[kind])
    def test_configured_profile_module_example_and_source_packets_remain(self):
        self.assertIn('dist/orm-profile.mjs',self.selection['portable'])
        for kind in ('source','portable'):
            self.assertIn('examples/orm-profile-roundtrip.mjs',self.selection[kind])
            self.assertIn('fixtures/orm-profile-v3/synthetic-nonrepeatable-first/profile-source.json',self.selection[kind])
            self.assertIn('verification/configured-user-profile/v024-initial/fixture.json',self.selection[kind])
            self.assertIn('verification/capture-persistence/v023-initial/fixture.json',self.selection[kind])

    def test_category_runtime_example_and_synthetic_source_remain(self):
        self.assertIn('dist/classification.mjs',self.selection['portable'])
        for kind in ('source','portable'):
            self.assertIn('examples/classification-roundtrip.mjs',self.selection[kind])
            self.assertIn('fixtures/classification-v3/source-closed-noisy-g2.json',self.selection[kind])

    def test_actual_presence_and_capture_run_closures_remain(self):
        for kind in ('source', 'portable'):
            self.assertIn('verification/presence/current/trace.json', self.selection[kind])
            self.assertIn('verification/capture/current/trace.json', self.selection[kind])

    def test_nonrequired_history_is_not_deleted(self):
        name = 'verification/old/unneeded.json'
        self.assertNotIn(name, self.selection['source'])
        self.assertTrue((self.root / name).is_file())

    def test_cannot_substitute_old_database_bundle_for_new_version(self):
        result = inventory.select_distribution_files(self.root, self.public, self.tested, '0.1.3')
        with self.assertRaises(AssertionError):
            inventory.assert_complete(result)

    def test_ignored_required_input_is_refused(self):
        public = self.public - {'verification/presence/current/trace.json'}
        result = inventory.select_distribution_files(self.root, public,
                    {'verification/presence/current/trace.json': 'fixture'}, '0.1.2')
        with self.assertRaises(AssertionError):
            inventory.assert_complete(result)

    def test_unsafe_path_is_refused(self):
        for name in ('../private', '/private', 'C:/private', 'a\\private', 'a//b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inventory.safe_name(name)

    def test_current_ci_has_failures_and_actual_compiled_core(self):
        self.assertIn('verification/new/failure.json', self.staged)
        self.assertIn('dist/core.mjs', self.staged)
        self.assertNotIn('verification/old/unneeded.json', self.staged)
        self.assertTrue((self.root / 'artifacts/ci-evidence/dist/core.mjs').is_file())

    def test_ci_private_files_and_older_archives_excluded(self):
        self.assertFalse(any('private' in name for name in self.staged))
        self.assertIn('artifacts/MoonTxnWitness-v0.1.2-source.zip', self.staged)
        self.assertNotIn('artifacts/MoonTxnWitness-v0.1.1-source.zip', self.staged)

    def test_public24_lazy_and_original_producer_closure_is_selected(self):
        additions = {
            'cmd/legacy/v024/manifest.json': '{}',
            'cmd/legacy/v024/core.cjs': '// immutable test placeholder; never executed\n',
            'cmd/legacy/v024/orm-profile.cjs': '// immutable test placeholder; never executed\n',
            'cmd/legacy/v024/core.mjs': '// original test placeholder; never executed\n',
            'cmd/legacy/v024/orm-profile.mjs': '// original test placeholder; never executed\n',
            'fixtures/compat-v024/manifest.json': '{}',
            'fixtures/compat-v024/producer-runtime/core.mjs': '// original test placeholder\n',
            'verification/compatibility/public-v024-producer-2026-10-23/freeze-manifest.json': '{}',
            'scripts/compat-v024-test.mjs': '// offline test placeholder; never executed\n',
        }
        for name, value in additions.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding='utf8')
        for name in ('core.cjs', 'orm-profile.cjs'):
            target = self.root / 'dist/legacy/v024' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// immutable test placeholder; never executed\n', encoding='utf8')
        public = self.public | set(additions)
        tested = {**self.tested, 'cmd/legacy/v024/core.cjs': 'fixture',
                  'cmd/legacy/v024/orm-profile.cjs': 'fixture'}
        selection = inventory.select_distribution_files(self.root, public, tested, '0.1.2')
        inventory.assert_complete(selection)
        for name in ('core.cjs', 'orm-profile.cjs'):
            self.assertIn('cmd/legacy/v024/' + name, selection['source'])
            self.assertIn('dist/legacy/v024/' + name, selection['portable'])
        for name in ('fixtures/compat-v024/manifest.json',
                     'fixtures/compat-v024/producer-runtime/core.mjs',
                     'verification/compatibility/public-v024-producer-2026-10-23/freeze-manifest.json'):
            for kind in ('source', 'portable'):
                self.assertIn(name, selection[kind])
        self.assertIn('scripts/compat-v024-test.mjs', selection['portable'])
        missing = inventory.select_distribution_files(self.root,
            public - {'cmd/legacy/v024/core.cjs'}, tested, '0.1.2')
        with self.assertRaises(AssertionError):
            inventory.assert_complete(missing)

    def test_v025_cannot_omit_public24_compatibility_inputs(self):
        selection = inventory.select_distribution_files(self.root, self.public, self.tested, '0.2.5')
        names = {item['file'] for item in selection['missingInputs']}
        self.assertIn('cmd/legacy/v024/', names)
        self.assertIn('fixtures/compat-v024/', names)
        self.assertIn('verification/compatibility/public-v024-producer-2026-10-23/', names)

    def test_ci_reuse_is_refused(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), self.assertRaises(FileExistsError):
            ci.stage(self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
