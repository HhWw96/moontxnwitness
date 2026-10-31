"""Reject changed baseline identities while allowing pinned archive reuse."""
import gzip
import json
from pathlib import Path
import re
import tempfile
import unittest
from prepare import validate_baseline_index_row, stage_candidate_notices, refs, configured_bridge_plan, CONFIGURED_BRIDGES


class PublicBaselineIndexTests(unittest.TestCase):
    def setUp(self):
        self.pin = {'sourceCommit': 'a' * 40}
        self.expected = {'sha256': 'b' * 64, 'bytes': 123}
        self.header = {'sourceCommits': {'source031': 'a' * 40, 'portable031': 'a' * 40}}
        self.row = {**self.expected, 'provider': 'source031', 'member': 'MoonTxnWitness-v0.3.1/LICENSE'}

    def check(self):
        validate_baseline_index_row(self.row, self.expected, self.pin, self.header, 'LICENSE')

    def test_identical_original_source_member_is_valid(self):
        self.check()

    def test_original_portable_member_is_valid(self):
        self.row['provider'] = 'portable031'
        self.check()

    def test_changed_digest_is_rejected(self):
        self.row['sha256'] = 'c' * 64
        with self.assertRaises(ValueError): self.check()

    def test_changed_length_is_rejected(self):
        self.row['bytes'] += 1
        with self.assertRaises(ValueError): self.check()

    def test_later_release_provider_is_rejected(self):
        self.row['provider'] = 'component033'
        with self.assertRaises(ValueError): self.check()

    def test_changed_source_commit_is_rejected(self):
        self.header['sourceCommits']['source031'] = 'd' * 40
        with self.assertRaises(ValueError): self.check()

    def test_member_escape_is_rejected(self):
        for member in ['../LICENSE', 'MoonTxnWitness-v0.3.1/../LICENSE', 'MoonTxnWitness-v0.3.1/C:LICENSE']:
            self.row['member'] = member
            with self.assertRaises(ValueError): self.check()

    def test_actual_frozen_licence_binding_is_valid(self):
        root = Path(__file__).resolve().parents[3]
        text = (root/'cmd/legacy-v031-binding.mjs').read_text('utf8')
        pin = json.loads(re.search(r'PUBLIC031=Object.freeze\((\{.*\})\);', text).group(1))
        header = json.loads((root/'scripts/frozen-inputs.json').read_bytes())
        index = json.loads(gzip.decompress((root/'scripts'/header['index']).read_bytes()))
        validate_baseline_index_row(index['artifacts/compat-v031/runtime/LICENSE'], pin['files']['LICENSE'], pin, header, 'LICENSE')

    def test_notices_keep_actual_compiler_bytes(self):
        with tempfile.TemporaryDirectory(prefix='mtw-runtime-notices-') as directory:
            root = Path(directory)
            home, stage = root/'compiler', root/'subject'
            (home/'lib/core').mkdir(parents=True)
            stage.mkdir()
            (root/'LICENSE').write_bytes(b'project licence\n')
            licence, notice = b'\xef\xbb\xbfruntime licence\r\n', b'runtime notice\r\n'
            (home/'lib/core/LICENSE').write_bytes(licence)
            (home/'lib/core/NOTICE').write_bytes(notice)
            stage_candidate_notices(root, home, stage, '0.3.6')
            self.assertEqual((stage/'LICENSE').read_bytes(), (root/'LICENSE').read_bytes())
            self.assertTrue((stage/'THIRD_PARTY_NOTICES.txt').read_bytes().endswith(b'\n'+licence+b'\n'+notice))

    def test_missing_runtime_notice_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='mtw-runtime-notices-') as directory:
            root = Path(directory)
            (root/'LICENSE').write_bytes(b'project licence\n')
            (root/'subject').mkdir()
            with self.assertRaises(FileNotFoundError):
                stage_candidate_notices(root, root/'missing-toolchain', root/'subject', '0.3.6')


class ConfiguredBridgePreparationTests(unittest.TestCase):
    def make_sources(self, root):
        for folder in CONFIGURED_BRIDGES.values():
            target=root/'src'/folder
            target.mkdir(parents=True)
            for leaf in ('moon.pkg','bridge.mbt'):
                (target/leaf).write_text('// setup-only fixture\n', encoding='utf8')

    def test_original_two_bridge_candidate_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(configured_bridge_plan(Path(directory)), [])

    def test_all_four_actual_package_filenames_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.make_sources(root)
            self.assertEqual(configured_bridge_plan(root),list(CONFIGURED_BRIDGES.items()))
            self.assertEqual(len({folder for _,folder in configured_bridge_plan(root)}),4)

    def test_partial_optional_closure_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.make_sources(root)
            import shutil
            shutil.rmtree(root/'src'/'sql_fetch_bridge')
            with self.assertRaisesRegex(ValueError,'Incomplete'):
                configured_bridge_plan(root)

    def test_package_and_source_are_independently_mandatory(self):
        for leaf in ('moon.pkg','bridge.mbt'):
            with self.subTest(leaf=leaf),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.make_sources(root)
                (root/'src'/'configured_session_bridge'/leaf).unlink()
                with self.assertRaisesRegex(ValueError,'Missing or linked'):
                    configured_bridge_plan(root)


class StaticSDKReferenceTests(unittest.TestCase):
    def test_multiline_import_uses_the_module_parser(self):
        self.assertEqual(refs(b"import {\n analyze,\n verify\n} from './model-profile.mjs';", 'sdk.mjs'), ['model-profile.mjs'])

    def test_reexports_and_builtins_have_distinct_roles(self):
        self.assertEqual(refs(b"import fs from 'node:fs'; export {\n analyze\n} from './core.mjs';", 'nested/sdk.mjs'), ['nested/core.mjs'])

    def test_mock_imports_in_comments_and_strings_are_not_dependencies(self):
        self.assertEqual(refs(b"// import './fake.mjs';\nconst text=\"export * from './also-fake.mjs'\";", 'sdk.mjs'), [])

    def test_dynamic_imports_do_not_claim_a_static_closure(self):
        self.assertEqual(refs(b"const lazy=()=>import('./not-linked.mjs');", 'sdk.mjs'), [])

    def test_bare_imports_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Bare or absolute'):
            refs(b"import value from 'other-package';", 'sdk.mjs')

    def test_root_escape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'escaped'):
            refs(b"export * from '../outside.mjs';", 'sdk.mjs')


if __name__ == '__main__': unittest.main()
