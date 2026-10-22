"""Bind the frozen real database phase before independent semantic review."""
import hashlib
import json
import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[3]
phase_path = root / 'verification/releases/0.1.5/relation-database-20261022T132231Z-c9085b9c.json'
phase = json.loads(phase_path.read_text(encoding='utf-8'))
assert phase['version'] == '0.1.5' and phase['passed'] and phase['actualDatabaseExecution']
assert phase['closureChecks'] == {'databaseCases': 160, 'modelCases': 160,
                                  'sourceBindingsVerified': True, 'allRawAndModelArtifactsVerified': True}
build = json.loads((root / 'dist/build-manifest.json').read_text(encoding='utf-8'))
assert phase['buildManifestBefore'] == phase['buildManifestAfter'] == build
expected_path = here / 'expected.actual.json'
expected = json.loads(expected_path.read_text(encoding='utf-8'))
assert expected['version'] == build['version']
for name in ['sourceSha256', 'coreSha256', 'captureCoreSha256']:
    assert expected[name] == build[name]

def binding(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

before = binding(expected_path)
pending = here / 'preparation-expected.pending-database.json'
assert not pending.exists()
shutil.copyfile(expected_path, pending)
raw, model = phase['receipts']['relation'], phase['receipts']['relationModel']
raw_path = root / 'verification' / raw['path'] / raw['receiptFile']
model_path = root / 'verification' / model['path'] / model['receiptFile']
assert str(model_path.parent) == str(raw_path.parent) + '-model'
assert binding(raw_path) == {'bytes': raw['bytes'], 'sha256': raw['sha256']}
assert binding(model_path) == {'bytes': model['bytes'], 'sha256': model['sha256']}
expected['database'] = {'rawDirectory': raw_path.parent.relative_to(root).as_posix(),
                        'modelDirectory': model_path.parent.relative_to(root).as_posix(),
                        'rawReceiptSha256': raw['sha256'], 'modelReceiptSha256': model['sha256']}
expected_path.write_text(json.dumps(expected, indent=2) + '\n', encoding='utf-8')
record = {'schema': 1, 'kind': 'frozen-v015-database-execution-input-binding',
          'phase': {'path': phase_path.relative_to(root).as_posix(), **binding(phase_path)},
          'pendingExpectedRetained': {'path': pending.name, **before},
          'actualExpected': {'path': expected_path.name, **binding(expected_path)},
          'actualV015SemanticReviewExecuted': False,
          'databaseInputs': expected['database']}
with (here / 'database-binding.json').open('x', encoding='utf-8') as output:
    output.write(json.dumps(record, indent=2) + '\n')
print(json.dumps({'expected': binding(expected_path), 'phase': binding(phase_path)}))
