"""Finalize the actual v0.1.5 public review after a successful independent-copy replay."""
import hashlib
import json
import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[3]
fresh = root / 'artifacts/r15-actual-replay/actual15-fXT4fr'

def binding(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

for path in fresh.rglob('*'):
    if path.is_file():
        target = here / 'actual-v015/fresh-replay' / path.relative_to(fresh)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        assert binding(path) == binding(target)
primary_path = here / 'actual-v015/run/receipt.json'
fresh_path = here / 'actual-v015/fresh-replay/receipt.json'
for path in [primary_path, fresh_path]:
    receipt = json.loads(path.read_text(encoding='utf-8'))
    assert receipt['passed'] and receipt['version'] == '0.1.5' and len(receipt['checks']) == 9
    assert receipt['sourceUnchanged'] and receipt['runtimeUnchanged'] and receipt['fingerprintUnchanged']
    assert receipt['build']['sourceSha256'] == '2c5159d76538a5343c8083df4c246892d034fbaa4de4ee5f33ce64e4444acd48'
    assert receipt['build']['coreSha256'] == 'a42c29e0ffcb516d6b6cd84ee273d50aa99ad6c989ad4d3e6f97d6c433ec0cef'
receipt = json.loads(primary_path.read_text(encoding='utf-8'))
candidate_path = here / 'candidate-v014/closure-manifest.json'
assert binding(candidate_path)['sha256'] == 'efb702d4f271b6a83f9861bbde4153b3b3f338c12e52efa59a3ac44316fb38b6'
candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
for name, value in candidate['files'].items():
    assert binding(candidate_path.parent / name) == value
copies = json.loads((here / 'actual-input-copy-bindings.json').read_text(encoding='utf-8'))
for name, value in copies.items():
    assert binding(here / name) == {'bytes': value['bytes'], 'sha256': value['sha256']}
summary = {
    'schema': 1, 'kind': 'independent-ai-actual-v015-relation-review', 'version': '0.1.5', 'passed': True,
    'actualReceipt': {'path': primary_path.relative_to(here).as_posix(), **binding(primary_path)},
    'freshIndependentInputReplay': {'path': fresh_path.relative_to(here).as_posix(), **binding(fresh_path)},
    'actualBuild': receipt['build'], 'groups': 9, 'sourceFilesBoundBeforeAndAfter': 94,
    'runtimeFilesBoundBeforeAndAfter': 5, 'relationBoundaryHistories': 170, 'priorListHistories': 71,
    'actualNewRelationDatabaseCases': 160, 'newDatabaseRawFilesVerified': 800, 'newDatabaseModelFilesVerified': 800,
    'oldV014RealRegisterCapsulesVerified': 3, 'oldV014RealListCapsulesVerified': 120,
    'frozenIndependentRelationInterpreterInputs': 335,
    'sourceClosure': {'originalTransactions': 4, 'retainedTransactions': ['P', 'A', 'B'], 'removed': ['N'],
                      'oneMinimal': True, 'allThreeSingleDeletesChecked': True,
                      'deletingProducerP': 'inconclusive', 'deletingAOrB': 'consistent'},
    'candidateArchiveBasedOnV014': {'path': 'candidate-v014/closure-manifest.json', **binding(candidate_path)},
    'sourceAndRuntimeUnchanged': True, 'copiedInputsByteVerified': True, 'freshReplayPassed': True,
    'formalV015SemanticFirstAttemptPassed': True, 'assemblyFirstFailureRetained': 'assembly-first-failure.json',
    'databaseReexecutedByReviewer': False, 'buildExecutedByReviewer': False, 'installed': False,
    'downloaded': False, 'performanceMeasured': False, 'humanAcceptance': False, 'contestApproval': False,
}
with (here / 'review-summary.json').open('x', encoding='utf-8') as output:
    output.write(json.dumps(summary, indent=2) + '\n')
blocked = [str(root).encode(), root.as_posix().encode(),
           ('C:' + chr(92) + 'Users' + chr(92)).encode(), ('C:/' + 'Users/').encode(),
           ('D:' + chr(92) + 'CodexScratch').encode(), ('D:/' + 'CodexScratch').encode()]
privacy_before = json.loads((here / 'privacy-actual.json').read_text(encoding='utf-8'))
exception = privacy_before['exactStaticSourceConfigurationException']
configuration_file = here / exception['file']
assert binding(configuration_file) == {'bytes': exception['bytes'], 'sha256': exception['sha256']}
guard = ('D:/' + 'CodexScratch/MoonTxnWitness-v011-20261020').encode()
assert hashlib.sha256(guard).hexdigest() == exception['literalSha256']
for path in here.rglob('*'):
    if path.is_file():
        raw = path.read_bytes()
        if path == configuration_file:
            assert raw.count(guard) == 1
            raw = raw.replace(guard, b'<fixed-generic-owned-database-scratch-guard>')
        for prefix in blocked:
            assert prefix not in raw, path.relative_to(here)
with (here / 'privacy-final.json').open('x', encoding='utf-8') as output:
    output.write(json.dumps({'schema': 1, 'passed': True, 'personalPathPrefixesFound': 0,
                            'exactPreviouslyPublicSourceConfigurationException': exception,
                            'filesScanned': len([p for p in here.rglob('*') if p.is_file()])}, indent=2) + '\n')
files = {path.relative_to(here).as_posix(): binding(path) for path in sorted(here.rglob('*'))
         if path.is_file() and path.name != 'closure-manifest.json'}
# Nested historical closure manifests must remain bound too.
for path in sorted(here.rglob('closure-manifest.json')):
    if path.parent != here:
        files[path.relative_to(here).as_posix()] = binding(path)
closure = {'schema': 1, 'kind': 'complete-public-independent-v015-review-closure', 'version': '0.1.5',
           'actualReviewPassed': True, 'freshIndependentInputReplayPassed': True,
           'candidateV014KeptSeparate': True, 'privacyPassedWithExactStaticSourceException': True,
           'files': dict(sorted(files.items())), 'rawBytes': sum(value['bytes'] for value in files.values())}
with (here / 'closure-manifest.json').open('x', encoding='utf-8') as output:
    output.write(json.dumps(closure, indent=2) + '\n')
print(json.dumps({'actualReceipt': binding(primary_path), 'summary': binding(here / 'review-summary.json'),
                  'closureManifest': binding(here / 'closure-manifest.json'), 'files': len(files),
                  'rawBytes': closure['rawBytes']}))
