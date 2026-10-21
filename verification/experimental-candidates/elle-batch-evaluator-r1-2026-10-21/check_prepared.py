"""Reuse the previously independent raw converter/EDN reader, without its runner."""
from pathlib import Path
import ast
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / 'verification/experimental-candidates/elle-smoke-r2-2026-10-21/actual-ci-39599513353/independent-r2/audit-smoke-r2.py'
DATA = ROOT / 'verification/experimental-candidates/elle-expansion-generation-v2-2026-10-21/actual-ci-39606834359/inputs.jsonl'
raw = REFERENCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'fc41c98a35b8ba5f7fca9dbfa8c1eaee7cb6968e1c53bb345a693b7bf7d97419'
tree = ast.parse(raw)
wanted = {'Invalid', 'Outside', 'require', 'identity', 'convert', 'EDN'}
definitions = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted]
assert {node.name for node in definitions} == wanted
namespace = {'json': json, 're': re}
# Execute only these six pure parser/converter definitions. The independent
# review's filesystem/network audit and any checker are never imported or run.
exec(compile(ast.Module(body=definitions, type_ignores=[]), '<fixed-independent-definitions>', 'exec'), namespace)
prepared = HERE / 'prepared-first'
receipt = json.loads((prepared / 'preparation-receipt.json').read_bytes())
inputs = {}
with DATA.open('rb') as source:
    for line in source:
        row = json.loads(line)
        inputs[row['id']] = row
seen, checks = set(), []
assert receipt['passed'] is True and len(receipt['batches']) == 40
for batch in receipt['batches']:
    path = prepared / batch['file']
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == batch['sha256'] and len(raw) == batch['bytes']
    lines = raw.decode('utf8').splitlines()
    assert len(lines) == batch['cases'] == 50
    for line, expected_id in zip(lines, batch['ids'], strict=True):
        request = namespace['EDN'](line).parse()
        assert request['id'] == expected_id and expected_id not in seen
        original = inputs[expected_id]
        expected = {'id': expected_id, 'inputSha256': original['inputSha256'],
                    **namespace['convert'](original['input'])}
        assert request == expected, 'Independent raw representation differs: ' + expected_id
        assert not any(name.startswith('expected') for name in request)
        seen.add(expected_id)
        checks.append({'id': expected_id, 'passed': True, 'inputSha256': original['inputSha256']})
assert seen == set(inputs) and len(seen) == 2000
result = {'schema': 1, 'passed': True, 'originalInputs': 2000, 'independentConvertedInputs': 2000,
          'exactEDNRoundTrips': 2000, 'batches': 40, 'maxInputsPerBatch': 50,
          'actualCheckerExecuted': False, 'generatorExecuted': False,
          'method': 'Previously independently authored raw converter and EDN reader reused byte-bound; only pure definitions loaded, not its runner.',
          'newBatchHarnessIndependentlyAccepted': False,
          'referenceFileSha256': hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), 'checks': checks}
(HERE / 'independent-converter-comparison.json').write_bytes(json.dumps(result, indent=2).encode() + b'\n')
print(json.dumps({k: result[k] for k in ['passed', 'originalInputs', 'independentConvertedInputs', 'exactEDNRoundTrips', 'batches']}))
