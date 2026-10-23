"""Isolated AST execution of only the public25 fresh-consumer package gate."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def gate():
    tree = ast.parse((ROOT / 'scripts/package_release.py').read_text(encoding='utf8'))
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.If)
               and any(isinstance(item, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'original25' for t in item.targets)
                       for item in node.body)]
    assert len(matches) == 1
    original = matches[0]
    only = [item for item in original.body
            if any(isinstance(n, ast.Name) and n.id == 'original25' for n in ast.walk(item))
            or any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                   and 'actual public25 21-family' in n.value for n in ast.walk(item))]
    selected = copy.deepcopy(original)
    selected.body = only
    return original, ast.fix_missing_locations(ast.Module(body=[selected], type_ignores=[]))


class Public25PackageGateTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'artifacts/public25-package-gate-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='run-', dir=parent))

    def execute(self, version, kinds, wrong=False):
        calls = []
        _, node = gate()
        def run(args, consumer):
            self.assertEqual(args[1], 'scripts/compat-v025-test.mjs')
            target = Path(args[-1])
            target.mkdir()  # Same exclusive contract as the actual JS runner.
            calls.append(target)
            return json.dumps({'passed': True, 'currentRuntimeVersion': version,
                               'checks': 172 if wrong else 173,
                               'originalProducerFamilies': 21,
                               'normalAnalysisHistoricalWorkersStarted': 0,
                               'inProcessObservedHistoricalWorkerLaunches': 143,
                               'expectedRegenerated': False})
        env = {'VERSION': version, 'NODE': 'fixture-node', 'work': self.work,
               'consumer': self.work, 'checks': [], 'run': run, 'json': json}
        for kind in kinds:
            env['kind'] = kind
            exec(compile(node, '<isolated-public25-package-gate>', 'exec'), env)
        return calls, env['checks']

    def test_gate_is_independent_v026_condition(self):
        original, selected = gate()
        self.assertEqual(ast.literal_eval(original.test.comparators[0]), (0, 2, 6))
        self.assertEqual(len(original.body), len(selected.body[0].body))

    def test_public25_release_does_not_require_future_compatibility(self):
        calls, checks = self.execute('0.2.5', ['source', 'portable'])
        self.assertEqual(calls, [])
        self.assertEqual(checks, [])

    def test_source_and_portable_use_distinct_exclusive_directories(self):
        calls, checks = self.execute('0.2.6', ['source', 'portable'])
        self.assertEqual([p.name for p in calls], ['public25-source', 'public25-portable'])
        self.assertEqual(len(checks), 2)

    def test_wrong_actual_check_count_is_refused(self):
        with self.assertRaises(AssertionError):
            self.execute('0.2.6', ['source'], wrong=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
