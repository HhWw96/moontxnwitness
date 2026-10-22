"""Copy already-present immutable setup/workload sources; no dependency fetch."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SUPPORT = HERE / 'support'
SUPPORT.mkdir(parents=True, exist_ok=True)
(SUPPORT / '__init__.py').write_text('"""Frozen fixture-only controlled setup helpers."""\n', encoding='utf8')
sources = {}
def copy(name, target, replacements=()):
    raw = (ROOT / name).read_bytes()
    sources[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    text = raw.decode('utf8')
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new)
    (HERE / target).write_text(text, encoding='utf8', newline='\n')
base = 'artifacts/orm-v3-draft/slice3/'
copy(base + 'run_postgres.py', 'frozen_run_postgres.py')
copy('artifacts/orm-v3-draft/bootstrap.py', 'frozen_upstream_bootstrap.py')
copy(base + 'install.py', 'support/install.py', (
    ('from provenance_policy import FIELDS, VERSION', 'from moontxnwitness_capture.orm import FIELDS, VERSION'),
    ('import relation_contract', 'from . import relation_contract')))
copy(base + 'relation_contract.py', 'support/relation_contract.py', (
    ('from provenance_policy import CoverageRequired, FIELDS, VERSION', 'from moontxnwitness_capture.orm import CoverageRequired, FIELDS, VERSION'),))
copy(base + 'control_log.py', 'support/control_log.py', (
    ('from source_sink import _Encoder', 'from moontxnwitness_capture._orm_source_sink import _Encoder'),))
(HERE / 'original-source-bindings.json').write_text(json.dumps({'schema': 1, 'files': sources,
    'businessExpectationsRewritten': False, 'setupChanges': 'Import paths only; original class/function ASTs remain unchanged',
    'databaseExecuted': False}, indent=2) + '\n', encoding='utf8')
print('Prepared existing ORM fixture sources only')
