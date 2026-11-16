import ast
import copy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'scripts/release.py').read_bytes())
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_native051_receipts')
scope = {}
exec(compile(ast.Module([node], []), 'release[native-model-contract]', 'exec'), scope)
validate = scope['validate_native051_receipts']


class NativeModelContract(unittest.TestCase):
    def setUp(self):
        current = {'passed': True, 'tests': 83,
                   'results': [{'name': 'case-' + str(i), 'passed': True} for i in range(83)],
                   'coreSha256': 'core', 'modelSdkSha256': 'models', 'relationSdkSha256': 'relation',
                   'runtimeUnchanged': True, 'legacyCapsuleTextUnchanged': True, 'formalPerformanceMeasurement': False}
        self.summary = {'nativeModelReportTransport': current, 'buildManifest': {'coreSha256': 'core'},
                        'testedFileSha256': {'dist/core.mjs': 'core', 'dist/models-v4.mjs': 'models', 'dist/relation-models-v4.mjs': 'relation'}}
        self.package = {'native051Consumers': {kind: copy.deepcopy(current) for kind in ('source', 'portable')},
                        'checks': [kind + ' native model SDK full report and fallback checks' for kind in ('source', 'portable')]}

    def test_fresh_consumers_and_original_version_fallback(self):
        validate(self.summary, self.package, '0.5.1')
        validate({}, {}, '0.5.0')

    def test_missing_portable_execution_is_rejected(self):
        del self.package['native051Consumers']['portable']
        with self.assertRaises(KeyError): validate(self.summary, self.package, '0.5.1')

    def test_each_measured_runtime_component_is_bound(self):
        for key in ('coreSha256', 'modelSdkSha256', 'relationSdkSha256'):
            changed = copy.deepcopy(self.package)
            changed['native051Consumers']['source'][key] = 'stale'
            with self.subTest(key=key), self.assertRaises(AssertionError): validate(self.summary, changed, '0.5.1')

    def test_missing_or_duplicate_checks_cannot_claim_coverage(self):
        for duplicate in (False, True):
            changed = copy.deepcopy(self.summary)
            rows = changed['nativeModelReportTransport']['results']
            if duplicate: rows[-1] = copy.deepcopy(rows[0])
            else: rows.pop()
            with self.subTest(duplicate=duplicate), self.assertRaises(AssertionError): validate(changed, self.package, '0.5.1')

    def test_changed_capsules_or_unexecuted_results_are_rejected(self):
        for key in ('legacyCapsuleTextUnchanged', 'runtimeUnchanged', 'passed'):
            changed = copy.deepcopy(self.summary)
            changed['nativeModelReportTransport'][key] = False
            with self.subTest(key=key), self.assertRaises(AssertionError): validate(changed, self.package, '0.5.1')

    def test_functional_checks_cannot_claim_formal_performance(self):
        self.summary['nativeModelReportTransport']['formalPerformanceMeasurement'] = True
        with self.assertRaises(AssertionError): validate(self.summary, self.package, '0.5.1')


if __name__ == '__main__': unittest.main()
