"""Package closure checks use isolated text files, not a compiler or database."""
import copy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from configured_window_runtime import (CONFIGURED_WINDOW_V2_RUNTIME,
                                       CONFIGURED_WINDOW_V2_WRAPPERS,
                                       STRUCTURED_WINDOW_RUNTIME,
                                       STRUCTURED_WINDOW_WRAPPERS,
                                       structured_window_available,
                                       verify_structured_window_runtime,
                                       CONFIGURED_WINDOW_CAPSULE_RUNTIME,
                                       configured_window_capsule_available,
                                       verify_configured_window_capsule_runtime,
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


class StructuredWindowRuntimeTests(ConfiguredWindowRuntimeTests):
    def setUp(self):
        super().setUp()
        slots = {}
        for name in STRUCTURED_WINDOW_RUNTIME:
            value = ('// separate opt-in ' + name + '\n').encode()
            (self.root / 'dist' / name).write_bytes(value)
            slots[name] = sha256(value).hexdigest()
            if name in STRUCTURED_WINDOW_WRAPPERS:
                (self.root / 'cmd' / name).write_bytes(value)
        self.manifest['structuredWindowRuntimeSha256'] = slots

    def test_separate_exact_inventory_and_default_slots_unchanged(self):
        self.assertTrue(structured_window_available(self.root))
        self.assertEqual(set(self.manifest['configuredWindowRuntimeSha256']),
                         set(CONFIGURED_WINDOW_V2_RUNTIME))
        self.assertEqual(verify_structured_window_runtime(self.root, self.manifest),
                         self.manifest['structuredWindowRuntimeSha256'])

    def test_missing_extra_or_default_slots_in_structured_manifest_fail(self):
        for change in ('missing-field', 'missing-slot', 'extra-slot', 'merged-default'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'missing-field':
                manifest.pop('structuredWindowRuntimeSha256')
            elif change == 'missing-slot':
                manifest['structuredWindowRuntimeSha256'].pop(STRUCTURED_WINDOW_RUNTIME[0])
            elif change == 'extra-slot':
                manifest['structuredWindowRuntimeSha256']['other.mjs'] = '0' * 64
            else:
                manifest['structuredWindowRuntimeSha256'].update(manifest['configuredWindowRuntimeSha256'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_structured_window_runtime(self.root, manifest)

    def test_changed_structured_core_fails(self):
        (self.root / 'dist' / STRUCTURED_WINDOW_RUNTIME[0]).write_text('// stale', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'Structured window runtime digest differs'):
            verify_structured_window_runtime(self.root, self.manifest)

    def test_structured_wrapper_changed_after_build_fails(self):
        (self.root / 'cmd' / STRUCTURED_WINDOW_WRAPPERS[0]).write_text('// stale', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'Structured window wrapper changed'):
            verify_structured_window_runtime(self.root, self.manifest)

    def test_shared_host_missing_fails_structured_closure(self):
        (self.root / 'dist/configured-window-v2-host.mjs').unlink()
        with self.assertRaisesRegex(ValueError, 'Configured window V2 runtime digest differs'):
            verify_structured_window_runtime(self.root, self.manifest)

    def test_missing_structured_asset_fails(self):
        (self.root / 'dist' / STRUCTURED_WINDOW_RUNTIME[0]).unlink()
        with self.assertRaisesRegex(ValueError, 'Structured window runtime digest differs'):
            verify_structured_window_runtime(self.root, self.manifest)


class ConfiguredWindowCapsuleRuntimeTests(unittest.TestCase):
    def setUp(self):
        ConfiguredWindowRuntimeTests.setUp(self)
        name = CONFIGURED_WINDOW_CAPSULE_RUNTIME[0]
        value = b'// independently distributed window capsule transport\n'
        (self.root / 'dist' / name).write_bytes(value)
        (self.root / 'cmd' / name).write_bytes(value)
        self.manifest['configuredWindowCapsuleRuntimeSha256'] = {name: sha256(value).hexdigest()}

    def test_single_capsule_slot_preserves_default_inventory(self):
        self.assertTrue(configured_window_capsule_available(self.root))
        self.assertEqual(set(self.manifest['configuredWindowRuntimeSha256']), set(CONFIGURED_WINDOW_V2_RUNTIME))
        self.assertEqual(verify_configured_window_capsule_runtime(self.root, self.manifest),
                         self.manifest['configuredWindowCapsuleRuntimeSha256'])

    def test_missing_or_additional_capsule_slots_are_rejected(self):
        for change in ('missing-field', 'empty', 'extra-slot', 'merged-default'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'missing-field':
                manifest.pop('configuredWindowCapsuleRuntimeSha256')
            elif change == 'empty':
                manifest['configuredWindowCapsuleRuntimeSha256'].clear()
            elif change == 'extra-slot':
                manifest['configuredWindowCapsuleRuntimeSha256']['other.mjs'] = '0' * 64
            else:
                manifest['configuredWindowCapsuleRuntimeSha256'].update(manifest['configuredWindowRuntimeSha256'])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'capsule runtime inventory differs'):
                verify_configured_window_capsule_runtime(self.root, manifest)

    def test_corrupt_capsule_file_is_rejected(self):
        (self.root / 'dist' / CONFIGURED_WINDOW_CAPSULE_RUNTIME[0]).write_bytes(b'// corrupt')
        with self.assertRaisesRegex(ValueError, 'capsule runtime digest differs'):
            verify_configured_window_capsule_runtime(self.root, self.manifest)

    def test_source_mismatch_cannot_be_authorized_by_a_rehashed_runtime(self):
        name = CONFIGURED_WINDOW_CAPSULE_RUNTIME[0]
        changed = b'// changed after the source build'
        (self.root / 'dist' / name).write_bytes(changed)
        self.manifest['configuredWindowCapsuleRuntimeSha256'][name] = sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError, 'capsule wrapper changed'):
            verify_configured_window_capsule_runtime(self.root, self.manifest)

    def test_missing_capsule_file_is_rejected(self):
        (self.root / 'dist' / CONFIGURED_WINDOW_CAPSULE_RUNTIME[0]).unlink()
        with self.assertRaisesRegex(ValueError, 'capsule runtime digest differs'):
            verify_configured_window_capsule_runtime(self.root, self.manifest)

    def test_missing_standalone_dependency_is_rejected(self):
        (self.root / 'dist/configured-window-v2-standalone.mjs').unlink()
        with self.assertRaisesRegex(ValueError, 'Configured window V2 runtime digest differs'):
            verify_configured_window_capsule_runtime(self.root, self.manifest)

    def test_missing_source_remains_an_active_rejected_dependency(self):
        (self.root / 'cmd' / CONFIGURED_WINDOW_CAPSULE_RUNTIME[0]).unlink()
        self.assertTrue(configured_window_capsule_available(self.root))
        with self.assertRaisesRegex(ValueError, 'capsule wrapper changed'):
            verify_configured_window_capsule_runtime(self.root, self.manifest)


if __name__ == '__main__':
    unittest.main()
