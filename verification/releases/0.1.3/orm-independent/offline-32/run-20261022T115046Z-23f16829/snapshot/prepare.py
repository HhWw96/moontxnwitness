"""Create only this ignored standalone ORM candidate; no build/DB/install."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = HERE / 'payload/integrations/python/moontxnwitness_capture'
PACKAGE.mkdir(parents=True, exist_ok=True)
baseline = HERE / 'baseline'
baseline.mkdir(exist_ok=True)
inputs = {}
def read(name):
    raw = (ROOT / name).read_bytes()
    inputs[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    return raw.decode('utf8')
for name in ('__init__.py', 'capture.py', 'capture_v3.py', 'journal_v3.py'):
    source = 'integrations/python/moontxnwitness_capture/' + name
    raw = read(source).encode('utf8')
    (PACKAGE / name).write_bytes(raw)
policy = read('artifacts/orm-v3-draft/provenance_policy.py')
(baseline / 'provenance_policy.py').write_text(policy, encoding='utf8', newline='\n')
observer = read('artifacts/orm-v3-draft/slice3/async_adapter.py')
(baseline / 'async_adapter.py').write_text(observer, encoding='utf8', newline='\n')
raw = read('artifacts/orm-v3-draft/async_adapter.py')
(baseline / 'raw_async_adapter.py').write_text(raw, encoding='utf8', newline='\n')
raw = raw.replace('from moontxnwitness_capture.capture_v3 import', 'from .capture_v3 import').replace('from moontxnwitness_capture.capture import', 'from .capture import')
(PACKAGE / '_orm_raw_async.py').write_text(raw, encoding='utf8', newline='\n')

# Preserve original SQL templates and source/result decoders; move imports only.
sql = policy[policy.index('def _table(scope):'):policy.index('class StructuredSQLCache:')]
sql = sql.replace('def build(scope, operation, fields=(), pk_bind="id_1"):',
    'def build(scope, operation, fields=(), pk_bind="id_1", *, context=DEFAULT_CONTEXT):\n'
    '    if type(context) is not SQLContext or sqlalchemy.__version__ != context.sqlalchemy_version:\n'
    '        raise CoverageRequired("The fixed ORM compiler requires SQLAlchemy " + context.sqlalchemy_version)')
old = 'return SQLPlan(key, original, observed, "fastapi-users.base-user." + operation + "." + str(bits) + "/1", business, mode)'
new = 'return SQLPlan(key, original, observed, "fastapi-users.base-user." + operation + "." + str(bits) + "/1", business, mode, context)'
assert old in sql
sql = sql.replace(old, new)
helpers = policy[policy.index('def _image(value, key):'):]
header = '''"""Relocated fixed ORM SQL and source decoders; no general SQL coverage."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import json
import threading
import uuid
import sqlalchemy
from sqlalchemy import Boolean, Column, MetaData, String, Table, bindparam, delete, insert, select, update
from sqlalchemy.dialects.postgresql import UUID, psycopg as pg_dialect
from .capture import CaptureSession, _Budget, _CaptureBudgetError, _measure_json
from .orm import (CoverageRequired, UserScope, PlanKey, SQLPlan, SQLContext,
    DEFAULT_CONTEXT, PROFILE, FIELDS, VALUES, VERSION, PAYLOAD_CHARS)

'''
(PACKAGE / '_orm_policy.py').write_text(header + sql + helpers, encoding='utf8', newline='\n')

observer = observer.replace('import importlib.util\n', '').replace('import bootstrap\n', '')
observer = observer.replace('from provenance_policy import (VALUES, FIELDS, build, StructuredSQLCache, CoverageRequired,',
    'from .orm import VALUES, FIELDS, StructuredSQLCache, CoverageRequired, DEFAULT_CONTEXT\nfrom ._orm_policy import (')
observer = observer.replace('from moontxnwitness_capture.capture_v3 import CaptureV3Session', 'from .capture_v3 import CaptureV3Session')
start = observer.index('spec = importlib.util.spec_from_file_location')
end = observer.index('\n\nclass SourceResult:', start)
observer = observer[:start] + 'from . import _orm_raw_async as raw_module' + observer[end:]
observer = observer.replace('def __init__(self, path, installation, sink):',
    'def __init__(self, path, installation, sink, *, cache_enabled=True, cache_max_entries=128,\n'
    '                 cache_max_bytes=1024 * 1024, sql_context=DEFAULT_CONTEXT):')
observer = observer.replace('self.cache, self.plans = StructuredSQLCache(), {}',
    'self.cache, self.plans = StructuredSQLCache(enabled=cache_enabled, max_entries=cache_max_entries,\n'
    '            max_bytes=cache_max_bytes, context=sql_context), {}')
observer = observer.replace('build(self.scope,', 'self.cache.prepare(self.scope,')
observer = observer.replace('        super().__init__(path, exclusive_writers=True)\n', '')
observer = observer.replace('        self.plans = {plan.original_sql: plan for plan in plans}',
    '        super().__init__(path, exclusive_writers=True)\n'
    '        self.plans = {plan.original_sql: plan for plan in plans}')
(PACKAGE / '_orm_async.py').write_text(observer, encoding='utf8', newline='\n')
sink = read('artifacts/orm-v3-draft/slice3/source_sink.py').replace('from moontxnwitness_capture.capture import', 'from .capture import')
(PACKAGE / '_orm_source_sink.py').write_text(sink, encoding='utf8', newline='\n')
license_raw = (ROOT / 'LICENSE').read_bytes()
(HERE / 'payload/LICENSE').write_bytes(license_raw)
inputs['LICENSE'] = {'sha256': hashlib.sha256(license_raw).hexdigest(), 'bytes': len(license_raw)}
(HERE / 'source-inputs.json').write_text(json.dumps({'schema': 1, 'files': inputs,
    'actualDatabaseExecution': False, 'buildExecuted': False}, indent=2) + '\n', encoding='utf8')
print('Prepared standalone ORM candidate copies only')
