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
        put('examples/model-profile-roundtrip.mjs', '// offline configured model source consumer\n')
        put('examples/classification-roundtrip.mjs', '// offline category source consumer\n')
        put('examples/classification-models-roundtrip.mjs', '// offline explicit model consumer\n')
        put('fixtures/classification-models-v3/list-skew.json', {'syntheticInputs': True})
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
        put('dist/model-profile.mjs', 'export const analyzeModelProfileV3 = true;\n')
        put('dist/classification.mjs', 'export const classifyV3 = true;\n')
        put('dist/classification-models.mjs', 'export const classifyModelsV3 = true;\n')
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

    def test_public033_audit_dependency_list_matches_actual_consumer(self):
        import ast, re
        script = (ROOT / 'scripts/v033-independent-anomalies-test.mjs').read_text('utf8')
        match = re.search(r'const sourceNames=(\[[^\n]*\]);', script)
        self.assertIsNotNone(match)
        observed = set(ast.literal_eval(match.group(1)))
        self.assertEqual(set(inventory.V033_ANOMALY_AUDIT_SOURCES),
                         {name for name in observed if name.startswith(('src/', 'cmd/'))})


    def test_public033_portable_retains_current_audit_sources(self):
        public = set(self.public)
        for name in inventory.V033_ANOMALY_AUDIT_SOURCES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('current fixture source\n', encoding='utf8')
            public.add(name)
        selection = inventory.select_distribution_files(self.root, public, self.tested, '0.3.3')
        for name in inventory.V033_ANOMALY_AUDIT_SOURCES:
            self.assertIn(name, selection['portable'])
            self.assertIn(name, selection['requiredInputs'])
        excluded = 'src/anomalies_v4.mbt'
        bad = inventory.select_distribution_files(self.root, public - {excluded}, self.tested, '0.3.3')
        self.assertTrue(any(row.get('file') == excluded and
                            'not in public inventory' in row.get('problem', '')
                            for row in bad['missingInputs']))


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

    def test_model_classification_runtime_example_and_source_remain(self):
        self.assertIn('dist/classification-models.mjs',self.selection['portable'])
        for kind in ('source','portable'):
            self.assertIn('examples/classification-models-roundtrip.mjs',self.selection[kind])
            self.assertIn('fixtures/classification-models-v3/list-skew.json',self.selection[kind])

    def test_configured_model_runtime_example_and_original_evidence_remain(self):
        self.assertIn('dist/model-profile.mjs',self.selection['portable'])
        for kind in ('source','portable'):
            self.assertIn('examples/model-profile-roundtrip.mjs',self.selection[kind])
            self.assertIn('verification/model-profile-v3/v027-initial/fixture.json',self.selection[kind])

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

    def test_public25_exact_worker_and_original_producer_closure_is_selected(self):
        additions = {name: '// synthetic inventory placeholder; never executed\n' for name in (
            'cmd/legacy/v025/core.mjs', 'cmd/legacy/v025/orm-profile.mjs',
            'cmd/legacy/v025/classification.mjs', 'cmd/legacy/v025/LICENSE',
            'cmd/legacy/v025/legacy-v024.mjs', 'cmd/legacy/v025/build-manifest.json',
            'cmd/legacy/v025/THIRD_PARTY_NOTICES.txt', 'cmd/legacy/v025/origin.json',
            'cmd/legacy/v025/manifest.json', 'fixtures/compat-v025/manifest.json',
            'fixtures/compat-v025/producer-runtime/core.mjs',
            'cmd/legacy-v025.mjs', 'cmd/legacy-v025-runtime.mjs',
            'cmd/legacy-v025-worker.mjs', 'cmd/legacy-v025-binding.mjs',
            'scripts/legacy-v025-runtime.mjs', 'scripts/compat-v025-test.mjs',
            'verification/compatibility/public-v025-producer-2026-10-24/receipt.json')}
        additions['cmd/legacy/v025/manifest.json'] = '{}'
        for name, value in additions.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding='utf8')
        for name in ('core.mjs', 'orm-profile.mjs', 'classification.mjs', 'LICENSE', 'manifest.json'):
            target = self.root / 'dist/legacy/v025' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// synthetic inventory placeholder; never executed\n', encoding='utf8')
        public = self.public | set(additions)
        selection = inventory.select_distribution_files(self.root, public, self.tested, '0.1.2')
        inventory.assert_complete(selection)
        for name in ('core.mjs', 'orm-profile.mjs', 'classification.mjs', 'LICENSE', 'manifest.json'):
            self.assertIn('cmd/legacy/v025/' + name, selection['source'])
            self.assertIn('dist/legacy/v025/' + name, selection['portable'])
        self.assertIn('fixtures/compat-v025/producer-runtime/core.mjs', selection['portable'])
        self.assertIn('scripts/compat-v025-test.mjs', selection['portable'])
        broken = inventory.select_distribution_files(self.root,
            public - {'cmd/legacy/v025/LICENSE'}, self.tested, '0.1.2')
        with self.assertRaises(AssertionError):
            inventory.assert_complete(broken)

    def test_v026_cannot_omit_actual_public25_inputs(self):
        selection = inventory.select_distribution_files(self.root, self.public, self.tested, '0.2.6')
        names = {item['file'] for item in selection['missingInputs']}
        self.assertIn('cmd/legacy/v025/', names)
        self.assertIn('fixtures/compat-v025/', names)
        self.assertIn('scripts/compat-v025-test.mjs', names)

    def test_ci_reuse_is_refused(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), self.assertRaises(FileExistsError):
            ci.stage(self.root)



class Public027PortableRegressionTests(unittest.TestCase):
    """Consumer dependencies must survive the portable inventory, including nested producer files."""
    @classmethod
    def setUpClass(cls):
        # Reuse the existing tiny retained-checkout fixture, without rerunning its tests.
        fixture_type = type('_Public027InventoryFixture', (DistributionTests,), {})
        fixture_type.setUpClass()
        cls.root = fixture_type.root
        cls.public = set(fixture_type.public)
        cls.tested = dict(fixture_type.tested)

        def put(name, value='synthetic inventory member\n'):
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf8')
            cls.public.add(name)

        runtime_names = ('core.mjs', 'capture-core.mjs', 'orm-profile.mjs',
                         'classification.mjs', 'classification-models.mjs', 'model-profile.mjs',
                         'legacy-v026.mjs', 'legacy-v026-runtime.mjs', 'legacy-v026-worker.mjs',
                         'legacy-v026-binding.mjs', 'legacy-v024.mjs', 'legacy-v025.mjs',
                         'legacy-v025-runtime.mjs', 'legacy-v025-worker.mjs', 'legacy-v025-binding.mjs',
                         'build-manifest.json', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'origin.json')
        put('cmd/legacy/v027/manifest.json', {'files': {name: {} for name in runtime_names}})
        for name in runtime_names:
            put('cmd/legacy/v027/' + name)
        for name in ('legacy-v027.mjs', 'legacy-v027-runtime.mjs', 'legacy-v027-worker.mjs', 'legacy-v027-binding.mjs'):
            put('cmd/' + name)
            put('dist/' + name)
        for name in ('legacy-v027-runtime.mjs', 'freeze-public027-runtime.mjs', 'legacy-v027-worker-test.mjs',
                     'public027-worker-smoke.mjs', 'compat-v027-test.mjs', 'public027-fixture-binding.mjs'):
            put('scripts/' + name)
        cls.fixture_files = {'fixtures/compat-v027/' + suffix for suffix in
                             ('manifest.json', 'case.input.json', 'case.report.json', 'case.capsule.json',
                              'producer-runtime/sdk.mjs', 'producer-runtime/legacy/v026/core.mjs')}
        for name in cls.fixture_files:
            put(name, {})
        put('verification/compatibility/public-v027-producer-2026-10-26/receipt.json',
            {'syntheticInventoryOnly': True, 'SDKExecuted': False, 'databaseExecuted': False})

    def select(self, omitted=()):
        # Omitting a name models the public archive inventory losing a consumer dependency.
        return inventory.select_distribution_files(self.root, self.public - set(omitted), self.tested, '0.1.2')

    def test_public027_portable_keeps_entire_fixture_tree_including_nested_runtime(self):
        selected = self.select()
        inventory.assert_complete(selected)
        self.assertTrue(self.fixture_files.issubset(selected['source']))
        self.assertTrue(self.fixture_files.issubset(selected['portable']))

    def test_public027_portable_keeps_both_current_consumer_script_dependencies(self):
        selected = self.select()
        inventory.assert_complete(selected)
        for name in ('scripts/compat-v027-test.mjs', 'scripts/public027-fixture-binding.mjs'):
            self.assertIn(name, selected['portable'])

    def require_refusal(self, name):
        selected = self.select([name])
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError):
            inventory.assert_complete(selected)

    def test_public027_missing_consumer_test_script_is_explicitly_refused(self):
        self.require_refusal('scripts/compat-v027-test.mjs')

    def test_public027_missing_fixture_binding_is_explicitly_refused(self):
        self.require_refusal('scripts/public027-fixture-binding.mjs')

    def test_public027_missing_fixture_manifest_is_explicitly_refused(self):
        self.require_refusal('fixtures/compat-v027/manifest.json')

    def test_public027_missing_whole_fixture_group_is_explicitly_refused(self):
        selected = self.select(self.fixture_files)
        self.assertTrue(any(row['file'] == 'fixtures/compat-v027/' for row in selected['missingInputs']))
        with self.assertRaises(AssertionError):
            inventory.assert_complete(selected)

class ThinCachedDistributionTests(unittest.TestCase):
    """A thin source keeps restoration tools; portable retains its consumed facts."""
    @classmethod
    def setUpClass(cls):
        import hashlib
        fixture_type = type('_ThinInventoryFixture', (DistributionTests,), {})
        fixture_type.setUpClass()
        cls.root, cls.public, cls.tested = fixture_type.root, set(fixture_type.public), dict(fixture_type.tested)
        cls.name = 'fixtures/classification-v3/source-closed-noisy-g2.json'
        raw = (cls.root / cls.name).read_bytes()
        cls.cache = {cls.name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
        cls.tested[cls.name] = cls.cache[cls.name]['sha256']
        cls.public.remove(cls.name)
        cls.providers = ('scripts/input_cache.py', 'scripts/frozen-inputs.json', 'scripts/frozen-inputs-v031.json.gz')
        for name in cls.providers:
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic source inventory member; never executed')
            cls.public.add(name)

    def select(self, tested=None, public=None):
        with patch.object(inventory, 'public_cached_entries', return_value=self.cache):
            return inventory.select_distribution_files(self.root,
                self.public if public is None else public,
                self.tested if tested is None else tested, '0.1.2')

    def test_thin_source_omits_payload_and_keeps_recovery_tools(self):
        selected = self.select()
        inventory.assert_complete(selected)
        self.assertNotIn(self.name, selected['source'])
        for name in self.providers:
            self.assertIn(name, selected['source'])
        self.assertTrue((self.root / self.name).is_file())

    def test_portable_keeps_its_exact_cached_consumer_input(self):
        selected = self.select()
        inventory.assert_complete(selected)
        self.assertIn(self.name, selected['portable'])
        self.assertIn(self.name, selected['requiredInputs'])

    def test_known_cached_input_does_not_require_readding_payload_to_git(self):
        self.assertNotIn(self.name, self.public)
        inventory.assert_complete(self.select())

    def test_cached_input_requires_matching_verified_fingerprint(self):
        for tested in [dict(self.tested, **{self.name: '0' * 64}),
                       {k: v for k, v in self.tested.items() if k != self.name}]:
            with self.subTest(fingerprint=tested.get(self.name)):
                selected = self.select(tested=tested)
                self.assertTrue(any(row['file'] == self.name for row in selected['missingInputs']))
                with self.assertRaises(AssertionError):
                    inventory.assert_complete(selected)

    def test_missing_cached_payload_is_a_failure_instead_of_a_skipped_test(self):
        source = self.root / self.name
        raw = source.read_bytes()
        try:
            source.unlink()
            selected = self.select()
            self.assertTrue(any(row['file'] == self.name for row in selected['missingInputs']))
            with self.assertRaises(AssertionError):
                inventory.assert_complete(selected)
        finally:
            source.write_bytes(raw)

    def test_cached_provider_does_not_authorize_unindexed_private_input(self):
        name = 'fixtures/private-unindexed.json'
        target = self.root / name
        target.write_text('{"private":true}', encoding='utf8')
        selected = self.select(tested={**self.tested, name: 'not-a-verified-public-hash'})
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError):
            inventory.assert_complete(selected)



class IgnoredCurrentCiReceiptTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'artifacts/distribution-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='ignored-receipts-', dir=parent)).resolve()
        (self.root / '.gitignore').write_text('verification/\nartifacts/\ndist/\n', encoding='utf8')
        (self.root / 'package.json').write_text('{"version":"0.3.2"}', encoding='utf8')
        subprocess.check_call(['git','init','--quiet',str(self.root)])
        subprocess.check_call(['git','-C',str(self.root),'add','.'])
        subprocess.check_call(['git','-C',str(self.root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-q','-m','receipt fixture'])
        (self.root / 'verification').mkdir()

    def write(self, name, value):
        (self.root / 'verification' / name).write_text(json.dumps(value), encoding='utf8')

    def staged(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}), contextlib.redirect_stdout(io.StringIO()):
            ci.stage(self.root)
        index = json.loads((self.root / 'artifacts/ci-evidence/current-run-index.json').read_text())
        return {row['file']:row for row in index['files']}

    def test_ignored_current_summary_and_package_are_digest_bound(self):
        import hashlib
        for name in ('summary.json','package.json'):
            self.write(name, {'version':'0.3.2','passed':True,'checks':17})
        self.write('private.json', {'private':'not-public'})
        selected = self.staged()
        for name in ('summary.json','package.json'):
            path = 'verification/' + name
            self.assertIn(path, selected)
            self.assertEqual(selected[path]['sha256'], hashlib.sha256((self.root/path).read_bytes()).hexdigest())
        self.assertNotIn('verification/private.json', selected)

    def test_older_or_invalid_ignored_receipts_are_not_promoted(self):
        self.write('summary.json', {'version':'0.3.1','passed':True})
        (self.root/'verification/package.json').write_text('{broken', encoding='utf8')
        selected = self.staged()
        self.assertNotIn('verification/summary.json', selected)
        self.assertNotIn('verification/package.json', selected)

    def test_current_failed_receipt_is_retained_without_claiming_success(self):
        self.write('summary.json', {'version':'0.3.2','passed':False})
        self.assertIn('verification/summary.json', self.staged())
        copied = json.loads((self.root/'artifacts/ci-evidence/verification/summary.json').read_text())
        self.assertIs(copied['passed'], False)

class DirectCategoryPortableInventoryTests(unittest.TestCase):
    setUpClass = classmethod(DistributionTests.setUpClass.__func__)
    run_git = classmethod(DistributionTests.run_git.__func__)
    def test_direct_audit_is_in_both_public_downloads(self):
        name = 'scripts/register-direct-v4-audit.mjs'
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('// independent consumer audit fixture\n', encoding='utf8')
        public = self.public | {name}
        selected = inventory.select_distribution_files(self.root, public, self.tested, '0.3.2')
        for kind in ('source', 'portable'):
            self.assertIn(name, selected[kind])
        self.assertIn(name, selected['requiredInputs'])
        self.assertFalse(any(row['file'] == name for row in selected['missingInputs']))

    def test_missing_or_unlisted_direct_audit_refuses_complete_inventory(self):
        name = 'scripts/register-direct-v4-audit.mjs'
        selected = inventory.select_distribution_files(self.root, self.public - {name}, self.tested, '0.3.2')
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError):
            inventory.assert_complete(selected)


class CompatibilityReleaseReceiptTests(unittest.TestCase):
    def fixture(self):
        return {'public031CompatibilityTests': {
            'passed': True, 'publicVersion': '0.3.1', 'currentVersion': '0.3.2',
            'publishedMemberCount': 580, 'usesPublishedRuntimeOnly': True,
            'historicalSourceSnapshotCreated': False}}

    def test_actual_integration_field_is_consumed(self):
        from release import validate_public031_compatibility_receipt
        value = self.fixture()
        self.assertIs(validate_public031_compatibility_receipt(value, '0.3.2'), value['public031CompatibilityTests'])

    def test_invented_alias_does_not_replace_the_actual_receipt(self):
        from release import validate_public031_compatibility_receipt
        value = self.fixture()
        value['publicV031CompatibilityTests'] = value.pop('public031CompatibilityTests')
        with self.assertRaises(KeyError):
            validate_public031_compatibility_receipt(value, '0.3.2')

    def test_failed_stale_or_nonpublic_receipts_are_rejected(self):
        from release import validate_public031_compatibility_receipt
        for key, value in [('passed', False), ('passed', 1), ('currentVersion', '0.3.1'),
                           ('publicVersion', '0.3.0'), ('publishedMemberCount', 579),
                           ('usesPublishedRuntimeOnly', False), ('historicalSourceSnapshotCreated', True)]:
            with self.subTest(field=key, value=value):
                receipt = self.fixture()
                receipt['public031CompatibilityTests'][key] = value
                with self.assertRaises(AssertionError):
                    validate_public031_compatibility_receipt(receipt, '0.3.2')


class DirectCategoryReleaseReceiptTests(unittest.TestCase):
    def fixture(self):
        return {'buildManifest': {'coreSha256': 'a' * 64}, 'registerDirectCategoryAudit': {
            'passed': True, 'failed': 0, 'checks': 6, 'version': '0.3.2', 'runtimeUnchanged': True,
            'checkedCategories': ['G0', 'G1c', 'G2-item'],
            'testedFileSha256Before': {'core.mjs': 'a' * 64},
            'testedFileSha256After': {'core.mjs': 'a' * 64}}}

    def test_actual_direct_audit_receipt_is_bound_to_runtime(self):
        from release import validate_register_direct_category_audit
        value = self.fixture()
        self.assertIs(validate_register_direct_category_audit(value, '0.3.2'), value['registerDirectCategoryAudit'])

    def test_failed_stale_or_incomplete_direct_audit_is_rejected(self):
        from release import validate_register_direct_category_audit
        for key, value in [('passed', False), ('passed', 1), ('failed', 1), ('checks', 5),
                           ('version', '0.3.1'), ('runtimeUnchanged', False), ('checkedCategories', ['G0'])]:
            with self.subTest(field=key, value=value):
                receipt = self.fixture(); receipt['registerDirectCategoryAudit'][key] = value
                with self.assertRaises(AssertionError): validate_register_direct_category_audit(receipt, '0.3.2')

    def test_receipt_cli_preserves_the_contract_version_floor(self):
        import shutil
        import sys
        parent = ROOT / 'artifacts/distribution-tests'
        parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='receipt-cli-', dir=parent))
        (work / 'scripts').mkdir(); (work / 'verification').mkdir()
        for name in ('release.py', 'package_archive.py', 'evidence_json.py', 'publication_ci.py'):
            shutil.copyfile(ROOT / 'scripts' / name, work / 'scripts' / name)
        (work / 'package.json').write_text('{"version":"0.3.1"}', encoding='utf8')
        (work / 'verification/summary.json').write_text('{"version":"0.3.1","passed":true}', encoding='utf8')
        run = subprocess.run([sys.executable, '-X', 'utf8', str(work / 'scripts/release.py'), '--check-compatibility-receipt'],
                             cwd=work, capture_output=True, text=True, encoding='utf8', timeout=20)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('0.3.1', run.stdout)

    def test_changed_execution_bytes_or_manifest_are_rejected(self):
        from release import validate_register_direct_category_audit
        for change in ['after', 'manifest']:
            receipt = self.fixture()
            if change == 'after': receipt['registerDirectCategoryAudit']['testedFileSha256After']['core.mjs'] = 'b' * 64
            else: receipt['buildManifest']['coreSha256'] = 'b' * 64
            with self.assertRaises(AssertionError): validate_register_direct_category_audit(receipt, '0.3.2')



class Relation034InventoryTests(unittest.TestCase):
    run_git = classmethod(DistributionTests.run_git.__func__)

    @classmethod
    def setUpClass(cls):
        DistributionTests.setUpClass.__func__(cls)
        names = set(inventory.RELATION034_SOURCE_INPUTS + inventory.RELATION034_PORTABLE_INPUTS + inventory.RELATION034_RUNTIME_INPUTS)
        names.add('src/public.mbt')
        for name in names:
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('{}' if name.endswith('.json') else '// tiny public input fixture\n', encoding='utf8')
        (cls.root / 'cmd/sdk.mjs').write_text('export const classifyRelationV4 = true; export const reduceRelationCategoryV4 = true;\n', encoding='utf8')
        cls.public = cls.public | {name for name in names if not name.startswith('dist/')}

    def select034(self, omitted=()):
        # Exercise feature-based activation without requiring unrelated later-version fixtures.
        return inventory.select_distribution_files(self.root, self.public - set(omitted), self.tested, '0.1.2')

    def test_current_exports_activate_034_closure_before_version_bump(self):
        self.assertTrue(inventory.relation034_available(self.root, '0.3.3'))
        self.assertTrue(inventory.relation034_available(self.root, '0.3.4'))
        inventory.assert_complete(self.select034())

    def test_source_audits_keep_complete_source_command_and_helper_inputs(self):
        selected = self.select034()
        self.assertTrue(set(inventory.RELATION034_SOURCE_INPUTS).issubset(selected['source']))
        self.assertIn('src/public.mbt', selected['source'])
        self.assertIn('cmd/relation-v4.mjs', selected['source'])
        self.assertNotIn('dist/core.mjs', selected['source'])

    def test_portable_has_real_runtime_probe_examples_and_no_source_audits(self):
        selected = self.select034()
        self.assertTrue(set(inventory.RELATION034_PORTABLE_INPUTS).issubset(selected['portable']))
        self.assertTrue(set(inventory.RELATION034_RUNTIME_INPUTS).issubset(selected['portable']))
        for name in inventory.RELATION034_SOURCE_INPUTS:
            self.assertNotIn(name, selected['portable'])
        self.assertFalse(any(name.startswith(('src/', 'cmd/')) for name in selected['portable']))

    def test_missing_source_sdk_audit_is_a_blocking_dependency(self):
        name = 'scripts/v034-source-rules-sdk-test.mjs'
        selected = self.select034((name,))
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError): inventory.assert_complete(selected)

    def test_missing_shared_maintenance_helper_is_a_blocking_dependency(self):
        name = 'scripts/v034-maintenance-bindings.mjs'
        selected = self.select034((name,))
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError): inventory.assert_complete(selected)

    def test_missing_source_fingerprint_helper_is_not_skipped(self):
        name = 'scripts/build-fingerprint.mjs'
        selected = self.select034((name,))
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError): inventory.assert_complete(selected)

    def test_missing_portable_probe_cannot_claim_a_complete_package(self):
        name = 'scripts/v034-portable-runtime-test.mjs'
        selected = self.select034((name,))
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError): inventory.assert_complete(selected)

    def test_missing_reduction_example_input_is_not_silently_omitted(self):
        name = 'examples/relation-category-reduction.json'
        selected = self.select034((name,))
        self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
        with self.assertRaises(AssertionError): inventory.assert_complete(selected)

    def test_missing_compiled_relation_module_is_blocking(self):
        name = 'dist/relation-reduction-v4.mjs'
        path = self.root / name
        saved = path.with_suffix('.fixture-saved')
        path.rename(saved)
        try:
            selected = self.select034()
            self.assertTrue(any(row['file'] == name for row in selected['missingInputs']))
            with self.assertRaises(AssertionError): inventory.assert_complete(selected)
        finally:
            saved.rename(path)

    def test_unknown_private_script_does_not_enter_either_distribution(self):
        path = self.root / 'scripts/private-relations.mjs'
        path.write_text('// ignored/unlisted private input\n', encoding='utf8')
        selected = self.select034()
        self.assertNotIn('scripts/private-relations.mjs', selected['source'])
        self.assertNotIn('scripts/private-relations.mjs', selected['portable'])


class Predicate035InventoryTests(unittest.TestCase):
    run_git = classmethod(DistributionTests.run_git.__func__)

    @classmethod
    def setUpClass(cls):
        Relation034InventoryTests.setUpClass.__func__(cls)
        names = set(inventory.PREDICATE035_SOURCE_INPUTS + inventory.PREDICATE035_PORTABLE_INPUTS +
                    inventory.PREDICATE035_RUNTIME_INPUTS)
        for name in names:
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('{}' if name.endswith('.json') else '// tiny predicate fixture\n', encoding='utf8')
        sdk = cls.root / 'cmd/sdk.mjs'
        sdk.write_text(sdk.read_text('utf8') + 'export const classifyRelationPredicateV4 = true;\n', encoding='utf8')
        cls.public |= {name for name in names if not name.startswith('dist/')}

    def select035(self, omitted=()):
        return inventory.select_distribution_files(self.root, self.public - set(omitted), self.tested, '0.1.2')

    def test_predicate_closure_activates_from_actual_namespace_and_version(self):
        self.assertTrue(inventory.predicate035_available(self.root, '0.3.4'))
        self.assertTrue(inventory.predicate035_available(self.root, '0.3.5'))
        inventory.assert_complete(self.select035())

    def test_source_audit_has_full_source_and_preserved_semantic_body(self):
        selection = self.select035()
        self.assertTrue(set(inventory.PREDICATE035_SOURCE_INPUTS).issubset(selection['source']))
        self.assertIn('src/public.mbt', selection['source'])
        self.assertIn('scripts/v035-predicate-regression-provenance.json', selection['requiredInputs'])
        self.assertNotIn('dist/core.mjs', selection['source'])

    def test_portable_uses_runtime_probe_instead_of_complete_source_audit(self):
        selection = self.select035()
        self.assertTrue(set(inventory.PREDICATE035_PORTABLE_INPUTS).issubset(selection['portable']))
        self.assertTrue(set(inventory.PREDICATE035_RUNTIME_INPUTS).issubset(selection['portable']))
        for name in inventory.PREDICATE035_SOURCE_INPUTS:
            self.assertNotIn(name, selection['portable'])
        self.assertNotIn('scripts/v035-predicate-maintenance-test.mjs', selection['portable'])

    def test_source_regression_and_provenance_cannot_silently_disappear(self):
        for name in ('scripts/relation-predicate-sdk-test.mjs',
                     'scripts/v035-predicate-maintenance-test.mjs',
                     'scripts/v035-predicate-regression-body.mjs',
                     'scripts/v035-predicate-regression-provenance.json'):
            with self.subTest(name=name):
                result = self.select035((name,))
                self.assertTrue(any(row['file'] == name for row in result['missingInputs']))
                with self.assertRaises(AssertionError): inventory.assert_complete(result)

    def test_missing_probe_example_and_description_are_blocking(self):
        for name in inventory.PREDICATE035_PORTABLE_INPUTS:
            with self.subTest(name=name):
                result = self.select035((name,))
                self.assertTrue(any(row['file'] == name for row in result['missingInputs']))
                with self.assertRaises(AssertionError): inventory.assert_complete(result)

    def test_missing_actual_predicate_runtime_is_blocking(self):
        path = self.root / 'dist/relation-v4.mjs'
        saved = path.with_suffix('.fixture-saved')
        path.rename(saved)
        try:
            with self.assertRaises(AssertionError): inventory.assert_complete(self.select035())
        finally:
            saved.rename(path)

    def test_original_semantic_body_matches_published_provenance_marker(self):
        from hashlib import sha256
        text = (ROOT / 'scripts/v035-predicate-regression-body.mjs').read_text('utf8')
        start, end = '// BEGIN frozen semantic body\n', '// END frozen semantic body\n'
        self.assertIn(start, text)
        self.assertIn(end, text)
        body = text.split(start, 1)[1].rsplit(end, 1)[0]
        provenance = json.loads((ROOT / 'scripts/v035-predicate-regression-provenance.json').read_text('utf8'))
        self.assertEqual(sha256(body.encode()).hexdigest(), provenance['semanticBodySha256'])
        self.assertEqual(provenance['semanticAssertions'], 506)
        self.assertEqual(provenance['currentBuildGuards'], 7)
        self.assertFalse(provenance['newIndependentReviewPerformed'])

    def test_new_runner_relative_imports_have_explicit_distribution_closure(self):
        import re
        names = ('scripts/v035-predicate-maintenance-test.mjs', 'scripts/v035-predicate-regression-body.mjs',
                 'scripts/v035-portable-predicate-test.mjs')
        selection = self.select035()
        for name in names:
            for relative in re.findall(r"from\s*['\"](\.[^'\"]+)['\"]", (ROOT / name).read_text('utf8')):
                resolved = (self.root / name).parent.joinpath(relative).resolve().relative_to(self.root).as_posix()
                self.assertIn(resolved, selection['requiredInputs'], (name, relative))


class Predicate035ReleaseReceiptTests(unittest.TestCase):
    def setUp(self):
        import copy
        self.copy = copy.deepcopy
        self.version = '0.3.5'
        manifest = {'version': self.version, 'coreSha256': 'core'}
        self.host = {'passed': True, 'checks': 40, 'failed': 0}
        self.maintained = {'passed': True, 'checks': 513, 'failed': 0, 'semanticAssertions': 506,
                          'currentBuildGuards': 7, 'sourceUnchanged': True, 'newIndependentReviewPerformed': False,
                          'buildManifest': manifest, 'version': self.version}
        self.probe = {'passed': True, 'checks': 12, 'failed': 0, 'requiresSourceTree': False,
                      'requiresCommandSource': False, 'sourceAuditPerformed': False, 'version': self.version,
                      'runtimeBefore': {'core.mjs': 'core'}, 'runtimeAfter': {'core.mjs': 'core'}}
        self.example = {'passed': True, 'predicate': 'refuted', 'item': 'checked-compatible',
                        'replayValid': True, 'acceptsIsolationModels': False}
        self.summary = {'buildManifest': manifest, 'foundation035': {
            'predicateCategoryHostTests': self.host, 'predicateMaintenanceRegression': self.maintained,
            'predicateRuntimeTests': self.probe, 'predicateCategoryExample': self.example}}
        consumers = {}
        for kind in ('source', 'portable'):
            consumers[kind] = {'sourceAuditPerformed': kind == 'source', 'runtimeOnlyPortableChecks': kind == 'portable',
                'newIndependentReviewPerformed': False, 'formalPerformanceMeasurement': False, 'actualDatabaseExecution': False,
                'results': {'completeSourceSdk': self.host, 'maintainedPredicateRegression': self.maintained}
                if kind == 'source' else {'runtimeProbe': self.probe}}
        self.package = {'predicate035Consumers': consumers, 'checks': [
            'source predicate all 40 complete-source SDK CLI and caller-budget replay checks',
            'source predicate 506 preserved semantic assertions and seven current-build integrity guards',
            'portable predicate runtime-only SDK CLI and exact scoped capsule replay',
            *[kind + ' runnable predicate versus item example and independent-option capsule replay' for kind in ('source', 'portable')]]}

    def validate(self, summary=None, package=None):
        from release import validate_predicate035_receipts
        return validate_predicate035_receipts(summary or self.summary, package or self.package, self.version)

    def test_complete_separate_source_and_portable_execution_is_required(self):
        self.validate()
        package = self.copy(self.package)
        del package['predicate035Consumers']['source']['results']['maintainedPredicateRegression']
        with self.assertRaises(KeyError): self.validate(package=package)

    def test_runtime_only_probe_cannot_be_used_as_source_audit(self):
        package = self.copy(self.package)
        package['predicate035Consumers']['portable']['sourceAuditPerformed'] = True
        with self.assertRaises(AssertionError): self.validate(package=package)

    def test_source_and_portable_runtime_digests_must_match_current_build(self):
        package = self.copy(self.package)
        package['predicate035Consumers']['portable']['results']['runtimeProbe']['runtimeBefore']['core.mjs'] = 'different'
        with self.assertRaises(AssertionError): self.validate(package=package)
        summary = self.copy(self.summary)
        summary['foundation035']['predicateMaintenanceRegression']['buildManifest'] = {'version': self.version, 'coreSha256': 'different'}
        with self.assertRaises(AssertionError): self.validate(summary=summary)

    def test_maintained_regression_cannot_be_presented_as_new_independent_review(self):
        summary = self.copy(self.summary)
        summary['foundation035']['predicateMaintenanceRegression']['newIndependentReviewPerformed'] = True
        with self.assertRaises(AssertionError): self.validate(summary=summary)

    def test_unknown_or_failed_execution_and_missing_check_labels_are_rejected(self):
        for key in ('predicateCategoryHostTests', 'predicateMaintenanceRegression', 'predicateRuntimeTests'):
            with self.subTest(key=key):
                summary = self.copy(self.summary)
                summary['foundation035'][key]['passed'] = False
                with self.assertRaises(AssertionError): self.validate(summary=summary)
        package = self.copy(self.package)
        package['checks'].pop()
        with self.assertRaises(AssertionError): self.validate(package=package)


if __name__ == '__main__':
    unittest.main(verbosity=2)
