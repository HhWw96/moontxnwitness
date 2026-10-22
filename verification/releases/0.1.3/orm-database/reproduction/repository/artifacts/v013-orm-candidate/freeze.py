"""Freeze candidate inputs and an additive patch; never applies it."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
package = HERE / 'payload/integrations/python/moontxnwitness_capture'
pieces = []
for name in ('orm.py', '_orm_policy.py', '_orm_async.py', '_orm_raw_async.py', '_orm_source_sink.py'):
    relative = 'integrations/python/moontxnwitness_capture/' + name
    assert not (ROOT / relative).exists(), 'Do not replace an existing implementation'
    raw = (package / name).read_text(encoding='utf8')
    pieces.append(''.join(difflib.unified_diff([], raw.splitlines(keepends=True), fromfile='/dev/null', tofile='b/' + relative)))
(HERE / 'candidate.patch').write_text(''.join(pieces), encoding='utf8', newline='\n')
originals = json.loads((HERE / 'source-inputs.json').read_text())['files']
for name, entry in originals.items():
    raw = (ROOT / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'] and len(raw) == entry['bytes'], name
files = []
for path in sorted(HERE.rglob('*')):
    if not path.is_file() or 'runs' in path.relative_to(HERE).parts or '__pycache__' in path.parts or path.name in ('candidate-manifest.json', 'SHA256SUMS'):
        continue
    raw = path.read_bytes()
    files.append({'path': path.relative_to(HERE).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
manifest = {'schema': 1, 'kind': 'isolated-v013-orm-cache-candidate-freeze',
    'createdAt': datetime.now(timezone.utc).isoformat(), 'files': files,
    'authorTests': {'path': 'runs/run-20261022T111648Z-ca3e70dc/receipt.json', 'testsRun': 21, 'passed': True},
    'independentAcceptance': False, 'mainlineApplied': False, 'actualDatabaseExecution': False,
    'buildExecuted': False, 'installationExecuted': False, 'published': False}
target = HERE / 'candidate-manifest.json'
assert not target.exists(), 'Preserve an existing candidate freeze'
target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
sha = hashlib.sha256(target.read_bytes()).hexdigest()
(HERE / 'SHA256SUMS').write_text(sha + '  candidate-manifest.json\n', encoding='utf8')
print(json.dumps({'files': len(files), 'manifestSha256': sha}))
