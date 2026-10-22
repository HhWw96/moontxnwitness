"""Preserve the reviewed v0.1.4 candidate and prepare, but do not execute, v0.1.5 review."""
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

here = Path(__file__).resolve().parent
root = here.parents[3]
source = root / 'artifacts/v015-relation-independent/public-v2'
destination = here / 'candidate-v014'
expected_manifest = 'efb702d4f271b6a83f9861bbde4153b3b3f338c12e52efa59a3ac44316fb38b6'
expected_build = {
    'version': '0.1.5',
    'sourceSha256': '2c5159d76538a5343c8083df4c246892d034fbaa4de4ee5f33ce64e4444acd48',
    'coreSha256': 'a42c29e0ffcb516d6b6cd84ee273d50aa99ad6c989ad4d3e6f97d6c433ec0cef',
    'captureCoreSha256': '60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee',
}

def binding(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def save(name, value):
    with (here / name).open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(value, ensure_ascii=True, indent=2) + '\n')

manifest_path = source / 'closure-manifest.json'
assert binding(manifest_path)['sha256'] == expected_manifest
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
copied = {}
for name, value in manifest['files'].items():
    relative = PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    original, target = source / name, destination / name
    assert binding(original) == value
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(original, target)
    assert binding(target) == value
    copied[name] = value
destination.mkdir(parents=True, exist_ok=True)
shutil.copyfile(manifest_path, destination / 'closure-manifest.json')
assert binding(destination / 'closure-manifest.json') == binding(manifest_path)
save('candidate-copy-record.json', {
    'schema': 1, 'kind': 'exact-public-candidate-archive-copy', 'passed': True,
    'scope': 'Candidate based on the v0.1.4 runtime, not actual v0.1.5 acceptance',
    'source': source.relative_to(root).as_posix(),
    'destination': destination.relative_to(root).as_posix(),
    'sourceAndCopiedManifest': binding(manifest_path),
    'files': copied, 'rawBytes': sum(value['bytes'] for value in copied.values()),
    'originalFailureAndRedactionRecordRetained': True,
})

prepared = root / 'artifacts/v015-actual-review'
for name in ['check.mjs', 'raw-review.mjs', 'oracle-batch.py', 'expected.template.json']:
    shutil.copyfile(prepared / name, here / name)
    assert binding(prepared / name) == binding(here / name)
build = json.loads((root / 'dist/build-manifest.json').read_text(encoding='utf-8'))
for name, value in expected_build.items():
    assert build[name] == value
assert binding(root / 'dist/core.mjs')['sha256'] == expected_build['coreSha256']
assert binding(root / 'dist/capture-core.mjs')['sha256'] == expected_build['captureCoreSha256']
source_names = sorted(['moon.mod'] + [path.relative_to(root).as_posix() for path in (root / 'src').rglob('*')
                                    if path.is_file() and (path.suffix == '.mbt' or path.name == 'moon.pkg')])
digest = hashlib.sha256()
for name in source_names:
    digest.update(name.encode() + b'\x00' + (root / name).read_bytes() + b'\x00')
assert digest.hexdigest() == expected_build['sourceSha256']
expected = json.loads((prepared / 'expected.template.json').read_text(encoding='utf-8'))
expected.update(expected_build)
expected['runtimeBindings'] = {name: binding(root / name) for name in [
    'dist/build-manifest.json', 'dist/core.mjs', 'dist/capture-core.mjs', 'dist/sdk.mjs', 'dist/evidence.mjs']}
save('expected.actual.json', expected)
save('preparation-receipt.json', {
    'schema': 1, 'kind': 'actual-v015-review-preparation-awaiting-database',
    'candidateArchiveCopyPassed': True,
    'candidateClosureManifest': binding(destination / 'closure-manifest.json'),
    'actualV015SourceAndRuntimeBindingVerified': True,
    'expectedBuild': expected_build,
    'expectedInput': binding(here / 'expected.actual.json'),
    'databaseEvidencePending': True,
    'actualV015SemanticReviewExecuted': False,
    'databaseExecuted': False, 'buildExecuted': False, 'downloaded': False,
    'reviewImplementation': {name: binding(here / name) for name in ['check.mjs', 'raw-review.mjs', 'oracle-batch.py']},
})
blocked = [str(root).encode(), root.as_posix().encode(),
           ('C:' + chr(92) + 'Users' + chr(92)).encode(), ('C:/' + 'Users/').encode(),
           ('D:' + chr(92) + 'CodexScratch').encode(), ('D:/' + 'CodexScratch').encode()]
for path in here.rglob('*'):
    if path.is_file():
        for prefix in blocked:
            assert prefix not in path.read_bytes(), path.relative_to(here)
save('privacy-check.json', {
    'schema': 1, 'passed': True, 'kind': 'local-absolute-path-prefix-scan',
    'scannedFiles': len([path for path in here.rglob('*') if path.is_file()]),
    'scope': 'No private original directory read or copied; candidate redacted-copy records retain original digests.',
})
print(json.dumps({'candidateFilesCopied': len(copied), 'candidateRawBytes': manifest['rawBytes'],
                  'candidateManifest': binding(destination / 'closure-manifest.json'),
                  'preparation': binding(here / 'preparation-receipt.json'),
                  'actualV015SemanticReviewExecuted': False}))
