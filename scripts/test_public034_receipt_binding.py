"""Synthetic identity faults; no runtime, compiler, database or acceptance is executed."""
import ast
import copy
import hashlib
import unittest
from pathlib import Path

tree = ast.parse((Path(__file__).with_name('release.py')).read_bytes())
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == 'validate_public034_candidate_files')
env = {}
exec(compile(ast.Module([node], []), 'release[public034-binding]', 'exec'), env)
validate = env[node.name]


class Public034ReceiptBinding(unittest.TestCase):
    def setUp(self):
        self.names = ['core.mjs', 'capture-core.mjs', 'sdk.mjs', 'moontxnwitness.mjs',
                      'evidence.mjs', 'build-manifest.json', 'compact-runtime.mjs',
                      'legacy-v028-dispatch.mjs', 'legacy-v034.mjs', 'legacy-v034-binding.mjs',
                      'configured-session-core.mjs', 'source-components-core.mjs',
                      'sql-projection-core.mjs', 'sql-fetch-core.mjs', 'extra-executed.mjs']
        digest = lambda n: hashlib.sha256(n.encode()).hexdigest()
        self.tested = {'dist/' + n: digest(n) for n in self.names}
        # Deep legacy files do not pretend to be observed top-level members.
        self.tested['dist/legacy/v031/core.mjs'] = digest('old')
        slots = {n: digest(n) for n in self.names if n.endswith('-core.mjs')
                 and n != 'capture-core.mjs'}
        self.summary = {'testedFileSha256': self.tested, 'buildManifest': {
            'coreSha256': digest('core.mjs'), 'captureCoreSha256': digest('capture-core.mjs'),
            'configuredCoreSha256': slots}}
        self.notice = digest('not executable compiler notices')
        self.value = {'candidateRuntimeFiles': {
            **{n: {'bytes': 17, 'sha256': digest(n)} for n in self.names},
            'THIRD_PARTY_NOTICES.txt': {'bytes': 19, 'sha256': self.notice}}}

    def test_complete_observed_map_and_separate_notice_pass(self):
        self.assertEqual(validate(self.value, self.summary, self.notice), self.value['candidateRuntimeFiles'])
        self.assertNotIn('dist/THIRD_PARTY_NOTICES.txt', self.tested)

    def test_each_core_helper_binding_and_additional_execution_hash_is_bound(self):
        for name in self.names:
            value = copy.deepcopy(self.value)
            value['candidateRuntimeFiles'][name]['sha256'] = '0' * 64
            with self.subTest(name=name), self.assertRaises(AssertionError):
                validate(value, self.summary, self.notice)

    def test_notice_is_checked_against_actual_bytes_digest(self):
        with self.assertRaises(AssertionError):
            validate(self.value, self.summary, '0' * 64)

    def test_missing_or_extra_observed_member_rejected(self):
        for name in self.value['candidateRuntimeFiles']:
            value = copy.deepcopy(self.value)
            del value['candidateRuntimeFiles'][name]
            with self.subTest(name=name), self.assertRaises(AssertionError):
                validate(value, self.summary, self.notice)
        value = copy.deepcopy(self.value)
        value['candidateRuntimeFiles']['unexecuted.mjs'] = {'bytes': 1, 'sha256': '0' * 64}
        with self.assertRaises(AssertionError):
            validate(value, self.summary, self.notice)

    def test_missing_mandatory_binding_cannot_be_hidden_in_both_maps(self):
        for name in self.names[:-1]:
            value, summary = copy.deepcopy(self.value), copy.deepcopy(self.summary)
            del value['candidateRuntimeFiles'][name]
            del summary['testedFileSha256']['dist/' + name]
            with self.subTest(name=name), self.assertRaises(AssertionError):
                validate(value, summary, self.notice)

    def test_all_six_manifest_core_digests_and_slot_set_are_checked(self):
        for field in ['coreSha256', 'captureCoreSha256']:
            summary = copy.deepcopy(self.summary)
            summary['buildManifest'][field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate(self.value, summary, self.notice)
        for name in self.summary['buildManifest']['configuredCoreSha256']:
            summary = copy.deepcopy(self.summary)
            summary['buildManifest']['configuredCoreSha256'][name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(AssertionError):
                validate(self.value, summary, self.notice)
        summary = copy.deepcopy(self.summary)
        summary['buildManifest']['configuredCoreSha256'].pop('sql-fetch-core.mjs')
        with self.assertRaises(AssertionError):
            validate(self.value, summary, self.notice)

    def test_false_sizes_and_extra_claim_fields_rejected(self):
        for change in [{'bytes': True}, {'bytes': -1}, {'bytes': 768 * 1024 * 1024 + 1}, {'trusted': True}]:
            value = copy.deepcopy(self.value)
            value['candidateRuntimeFiles']['core.mjs'].update(change)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                validate(value, self.summary, self.notice)


if __name__ == '__main__':
    unittest.main()
