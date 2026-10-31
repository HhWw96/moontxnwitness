"""Check isolated worker fixtures against the actual static module dependencies."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copied_helpers(script):
    text = (ROOT / 'scripts' / script).read_text(encoding='utf8')
    matches = re.findall(r'for\(const name of (\[[^\]]+\])\)copyFileSync', text)
    if len(matches) != 1:
        raise ValueError('Expected the original single explicit helper-copy loop')
    return set(ast.literal_eval(matches[0]))


def missing_imports(names):
    staged = names | {'core.mjs', 'real-core.mjs', 'orm-profile.mjs',
                      'classification.mjs', 'legacy-v024.mjs'}
    missing = set()
    for name in staged:
        path = ROOT / 'cmd' / name
        if not path.is_file():
            continue  # The traced core is deliberately provided by the fixture.
        text = path.read_text(encoding='utf8')
        for dependency in re.findall(r'\bfrom\s*[\'"](\./[^\'"]+\.mjs)[\'"]', text):
            relative = (Path(name).parent / dependency).as_posix()
            if relative not in staged:
                missing.add(relative)
    return missing


class IsolatedDispatchStaging(unittest.TestCase):
    def test_original_fixture_import_closures(self):
        for script in ('orm-profile-sdk-test.mjs', 'legacy-v025-worker-test.mjs'):
            with self.subTest(script=script):
                self.assertEqual(missing_imports(copied_helpers(script)), set())

    def test_actual_previous_missing_helper_is_detected(self):
        for script in ('orm-profile-sdk-test.mjs', 'legacy-v025-worker-test.mjs'):
            names = copied_helpers(script)
            self.assertIn('legacy-v034.mjs', names)
            self.assertIn('legacy-v034-binding.mjs', names)
            self.assertIn('legacy-v034.mjs', missing_imports(names - {'legacy-v034.mjs'}))
            self.assertIn('legacy-v034-binding.mjs', missing_imports(names - {'legacy-v034-binding.mjs'}))

    def test_traced_copy_hash_watch_and_report_binding_agree(self):
        text = (ROOT / 'scripts/orm-profile-sdk-test.mjs').read_text(encoding='utf8')
        bound = set(ast.literal_eval(re.search(r'const bound=(\[[^\]]+\]);', text)[1]))
        watched = set(ast.literal_eval(re.search(r'for\(const name of (\[[^\]]+\])\)assert.equal\(hash', text)[1]))
        copied = copied_helpers('orm-profile-sdk-test.mjs')
        self.assertEqual(copied, watched)
        self.assertTrue(copied.issubset(bound))


if __name__ == '__main__':
    unittest.main()
