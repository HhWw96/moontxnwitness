"""Package closure checks use isolated text files, not a compiler or database."""
import copy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from configured_window_runtime import (CONFIGURED_WINDOW_V2_RUNTIME,
                                       CONFIGURED_WINDOW_V2_WRAPPERS,
                                       verify_configured_window_v2_runtime)


class ConfiguredWindowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'cmd').mkdir()
        (self.root / 'dist').mkdir()
        slots = {}
        for name in CONFIGURED_WINDOW_V2_RUNTIME:
            value = ('// actual ' + name + '\n').encode()
            (self.root / 'dist' / name).write_bytes(value)
            slots[name] = sha256(value).hexdigest()
            if name in CONFIGURED_WINDOW_V2_WRAPPERS:
                (self.root / 'cmd' / name).write_bytes(value)
        self.manifest = {'configuredWindowRuntimeSha256': slots}

    def test_exact_runtime_closure(self):
        self.assertEqual(verify_configured_window_v2_runtime(self.root, self.manifest),
                         self.manifest['configuredWindowRuntimeSha256'])

    def test_missing_or_extra_slots_fail(self):
        for change in ('missing-field', 'missing-slot', 'extra-slot'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'missing-field':
                manifest.clear()
            elif change == 'missing-slot':
                manifest['configuredWindowRuntimeSha256'].pop(CONFIGURED_WINDOW_V2_RUNTIME[0])
            else:
                manifest['configuredWindowRuntimeSha256']['other-core.mjs'] = '0' * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_configured_window_v2_runtime(self.root, manifest)

    def test_changed_compiled_core_fails(self):
        (self.root / 'dist/sql-projection-v2-core.mjs').write_text('// changed', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'digest differs'):
            verify_configured_window_v2_runtime(self.root, self.manifest)

    def test_changed_source_wrapper_fails_even_with_matching_runtime_digest(self):
        (self.root / 'cmd/configured-window-v2-host.mjs').write_text('// changed', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'wrapper changed'):
            verify_configured_window_v2_runtime(self.root, self.manifest)

    def test_missing_runtime_fails(self):
        (self.root / 'dist/configured-window-v2-standalone.mjs').unlink()
        with self.assertRaisesRegex(ValueError, 'digest differs'):
            verify_configured_window_v2_runtime(self.root, self.manifest)


if __name__ == '__main__':
    unittest.main()
