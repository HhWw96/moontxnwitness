"""Reject changed baseline identities while allowing pinned archive reuse."""
import gzip
import json
from pathlib import Path
import re
import unittest
from prepare import validate_baseline_index_row


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


if __name__ == '__main__': unittest.main()
