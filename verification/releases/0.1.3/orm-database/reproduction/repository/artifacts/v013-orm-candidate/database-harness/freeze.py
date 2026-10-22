"""Freeze this supplemental harness; exclude mutable execution/private trees."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
target = HERE / 'execution-inputs.json'
assert not target.exists(), 'Preserve the prior harness freeze'
files = []
for path in sorted(HERE.rglob('*')):
    relative = path.relative_to(HERE)
    if not path.is_file() or any(part in ('executions','unit-runs','__pycache__') for part in relative.parts):
        continue
    if path.name in ('execution-inputs.json','SHA256SUMS'): continue
    raw = path.read_bytes()
    files.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
manifest = {'schema': 1, 'kind': 'isolated-v013-orm-db-harness-prepared-inputs', 'files': files,
    'candidateManifestSha256': 'b5f7e88396931f0051f205cb845ff05c83224e622ea02ddf06115ab4b6fd38f5',
    'actualDatabaseExecution': False, 'buildExecuted': False, 'dependenciesInstalled': False}
target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
sha = hashlib.sha256(target.read_bytes()).hexdigest()
(HERE / 'SHA256SUMS').write_text(sha + '  execution-inputs.json\n', encoding='utf8')
print(json.dumps({'files':len(files),'sha256':sha,'databaseExecuted':False}))
