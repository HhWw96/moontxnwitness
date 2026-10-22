"""Independent offline review of a byte-bound ORM candidate; never uses a DB."""
from __future__ import annotations
import asyncio
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = ROOT / 'artifacts/v013-orm-candidate'
MANIFEST_SHA = 'b5f7e88396931f0051f205cb845ff05c83224e622ea02ddf06115ab4b6fd38f5'
RUN = HERE / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
RUN.mkdir(parents=True)
SNAPSHOT = RUN / 'snapshot'
SNAPSHOT.mkdir()

def binding(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

manifest_path = CANDIDATE / 'candidate-manifest.json'
assert binding(manifest_path)['sha256'] == MANIFEST_SHA
manifest = json.loads(manifest_path.read_text(encoding='utf8'))
candidate_before = {}
for entry in manifest['files']:
    rel = entry['path']
    actual = binding(CANDIDATE / rel)
    assert actual == {key: entry[key] for key in ('sha256', 'bytes')}, rel
    candidate_before[rel] = actual
    target = SNAPSHOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CANDIDATE / rel, target)
sources = json.loads((CANDIDATE / 'source-inputs.json').read_text())['files']
sources_before = {name: binding(ROOT / name) for name in sources}
assert sources_before == sources
spec = importlib.util.spec_from_file_location('independent_candidate_fixture', SNAPSHOT / 'test_candidate.py')
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
orm, adapter = fixture.orm, fixture.adapter
import psycopg

class AdditionalCacheTests(unittest.TestCase):
    def test_same_sql_distinct_domains_and_epochs_never_share_objects(self):
        cache = orm.StructuredSQLCache()
        a = fixture.SCOPE
        b = orm.UserScope(a.schema, a.table, (fixture.KEY,))
        p1, p2 = cache.prepare(a, 'get'), cache.prepare(b, 'get')
        p3 = cache.prepare(a, 'get', context=orm.SQLContext(registry_epoch=1))
        self.assertEqual(p1.original_sql, p2.original_sql)
        self.assertEqual(p1.original_sql, p3.original_sql)
        self.assertIsNot(p1, p2)
        self.assertIsNot(p1, p3)
        self.assertEqual(cache.retained['entries'], 3)
        self.assertIs(cache.match(b, p1.original_sql, 'get'), p2)
        self.assertEqual(cache.compilations, 3)

    def test_failed_compiler_does_not_evict_a_good_warm_entry(self):
        cache = orm.StructuredSQLCache(max_entries=1)
        good = cache.prepare(fixture.SCOPE, 'get')
        sentinel = RuntimeError('independent compile failure')
        before = cache.retained.copy()
        with patch.object(orm, 'build', side_effect=sentinel):
            with self.assertRaises(RuntimeError) as error:
                cache.prepare(fixture.SCOPE, 'delete', pk_bind='id')
            self.assertIs(error.exception, sentinel)
        self.assertEqual(cache.retained, before)
        self.assertIs(cache.prepare(fixture.SCOPE, 'get'), good)

    def test_warm_hit_still_rejects_wrong_bind_unknown_fields_and_subclass(self):
        cache = orm.StructuredSQLCache()
        cache.prepare(fixture.SCOPE, 'get')
        class ScopeSubclass(orm.UserScope): pass
        with self.assertRaises(orm.CoverageRequired):
            cache.prepare(fixture.SCOPE, 'get', pk_bind='id')
        with self.assertRaises(orm.CoverageRequired):
            cache.prepare(fixture.SCOPE, 'get', fields=('email',))
        with self.assertRaises(orm.CoverageRequired):
            cache.prepare(ScopeSubclass(fixture.SCOPE.schema, fixture.SCOPE.table, fixture.SCOPE.known_ids), 'get')

    def test_mutating_supplied_fields_list_cannot_mutate_retained_shape(self):
        cache = orm.StructuredSQLCache()
        fields = ['email']
        plan = cache.prepare(fixture.SCOPE, 'update', fields, fixture.SCOPE.table + '_id')
        fields[0] = 'hashed_password'
        self.assertEqual(plan.key.fields, ('email',))
        other = cache.prepare(fixture.SCOPE, 'update', fields, fixture.SCOPE.table + '_id')
        self.assertIsNot(plan, other)
        self.assertEqual(plan.key.fields, ('email',))

    def test_copyable_compile_has_no_psycopg_dependency(self):
        code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'from moontxnwitness_capture.orm import UserScope,StructuredSQLCache;'
            'p=StructuredSQLCache().prepare(UserScope("mtw_orm_v3_independent","users",'
            '("00000000-0000-4000-8000-000000000001",)),"get");'
            'assert "psycopg" not in sys.modules;print(p.result_mode)')
        import subprocess
        output = subprocess.check_output([sys.executable, '-I', '-B', '-c', code, str(fixture.PAYLOAD)], text=True)
        self.assertEqual(output.strip(), 'row-or-absence')

class AdditionalCursorTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_never_calls_any_fetch_for_four_shapes(self):
        for enabled in (False, True):
            for operation in ('get', 'create', 'update', 'delete'):
                with self.subTest(enabled=enabled, operation=operation):
                    session, raw, cursor = fixture.cursor_fixture(enabled=enabled, read=operation == 'get')
                    plan = next(p for p in session.plans.values() if p.key.operation == operation and
                        (operation != 'update' or p.key.fields == ('email',)))
                    params = dict(fixture.images()) if operation == 'create' else {plan.key.pk_bind: fixture.KEY}
                    if operation == 'update': params['email'] = 'new@example.invalid'
                    async def forbidden(*args):
                        self.fail('execute consumed a fetch method')
                    raw.fetchone = raw.fetchmany = raw.fetchall = forbidden
                    await cursor.execute(plan.original_sql, params)
                    self.assertEqual(raw.rownumber, 0)
                    self.assertIs(raw.executed[-1][1], params)
                    self.assertEqual(raw.executed[-1][0], plan.observed_sql)
                    if operation == 'get': self.assertEqual(session.sink_records, [])

    async def test_fetched_positive_leaf_objects_are_preserved(self):
        for enabled in (False, True):
            for method in ('fetchone', 'fetchmany', 'fetchall'):
                session, raw, cursor = fixture.cursor_fixture(enabled=enabled, read=True)
                original_row = raw.rows[0]
                plan = next(p for p in session.plans.values() if p.key.operation == 'get')
                await cursor.execute(plan.original_sql, {plan.key.pk_bind: fixture.KEY})
                result = await getattr(cursor, method)()
                business = result if method == 'fetchone' else result[0]
                self.assertEqual(len(business), 6)
                for index in range(6): self.assertIs(business[index], original_row[index])

    async def test_unmapped_results_and_parameter_object_keep_identity(self):
        for enabled in (False, True):
            for method in ('fetchone', 'fetchmany', 'fetchall'):
                session, raw, cursor = fixture.cursor_fixture(enabled=enabled, read=True)
                parameters = {'private': object()}
                await cursor.execute('SELECT unmapped_original', parameters)
                self.assertIs(raw.executed[-1][1], parameters)
                sentinel = (object(),) if method == 'fetchone' else [(object(),)]
                async def fetch(): return sentinel
                setattr(raw, method, fetch)
                self.assertIs(await getattr(cursor, method)(), sentinel)
                self.assertEqual(session.sink_records, [])

    async def test_negative_source_waits_for_original_eof_delivery(self):
        for enabled in (False, True):
            session, raw, cursor = fixture.cursor_fixture(enabled=enabled, read=True, present=False)
            plan = next(p for p in session.plans.values() if p.key.operation == 'get')
            await cursor.execute(plan.original_sql, {plan.key.pk_bind: fixture.KEY})
            self.assertEqual(session.sink_records, [])
            self.assertEqual(raw.rownumber, 0)
            self.assertIsNone(await cursor.fetchone())
            self.assertEqual(len(session.sink_records), 1)
            self.assertEqual(raw.rownumber, 1)

    async def test_fetch_error_cancellation_identity_and_timing_all_methods(self):
        for enabled in (False, True):
            for method in ('fetchone', 'fetchmany', 'fetchall'):
                for error in (ValueError('native row loader error'), asyncio.CancelledError('native cancellation')):
                    session, raw, cursor = fixture.cursor_fixture(enabled=enabled, read=True)
                    plan = next(p for p in session.plans.values() if p.key.operation == 'get')
                    await cursor.execute(plan.original_sql, {plan.key.pk_bind: fixture.KEY})
                    async def fetch(): raise error
                    setattr(raw, method, fetch)
                    with self.assertRaises(type(error)) as caught:
                        await getattr(cursor, method)()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(session.sink_records, [])

    async def test_failed_parameter_encoding_falls_back_without_rewrite_or_capture_fact(self):
        session, raw, cursor = fixture.cursor_fixture(read=True)
        plan = next(p for p in session.plans.values() if p.key.operation == 'get')
        params = {plan.key.pk_bind: fixture.KEY}
        def encode(value): raise ValueError('bounded encoder refused')
        session.encode = encode
        await cursor.execute(plan.original_sql, params)
        self.assertEqual(raw.executed[-1][0], plan.original_sql)
        self.assertIs(raw.executed[-1][1], params)
        self.assertEqual(session.sink_records, [])
        self.assertTrue(any(code == 'orm_parameters_unmapped' for code, _ in session.gaps))

with (RUN / 'first.log').open('x', encoding='utf8') as log:
    with redirect_stdout(log), redirect_stderr(log):
        suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromModule(fixture),
            unittest.defaultTestLoader.loadTestsFromTestCase(AdditionalCacheTests),
            unittest.defaultTestLoader.loadTestsFromTestCase(AdditionalCursorTests)))
        with patch.object(psycopg, 'connect', side_effect=AssertionError('Database forbidden in independent review')):
            with patch.object(psycopg.AsyncConnection, 'connect', side_effect=AssertionError('Database forbidden in independent review')):
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
candidate_after = {name: binding(CANDIDATE / name) for name in candidate_before}
sources_after = {name: binding(ROOT / name) for name in sources}
receipt = {'schema': 1, 'kind': 'independent-ai-offline-orm-candidate-review',
    'passed': result.wasSuccessful() and candidate_before == candidate_after and sources_before == sources_after,
    'candidateManifestSha256': MANIFEST_SHA, 'candidateFileCount': len(candidate_before),
    'testsRun': result.testsRun, 'authorTestsRerun': 21, 'independentAdditionalTests': 11,
    'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
    'candidateBindingsBefore': candidate_before, 'candidateBindingsAfter': candidate_after,
    'sourceBindingsBefore': sources_before, 'sourceBindingsAfter': sources_after,
    'candidateUnchanged': candidate_before == candidate_after, 'originalSourcesUnchanged': sources_before == sources_after,
    'failedTests': [case.id() for case, _ in result.failures + result.errors],
    'runtime': {'python': sys.version.split()[0], 'sqlalchemy': fixture.policy.sqlalchemy.__version__, 'psycopg': psycopg.__version__},
    'compilerWorkComparison': fixture.COMPILATION_COMPARISON,
    'databaseExecuted': False, 'buildExecuted': False, 'installationExecuted': False,
    'formalPerformanceMeasurement': False, 'humanAcceptance': False, 'contestApproval': False}
(RUN / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'passed': receipt['passed'], 'testsRun': result.testsRun, 'failedTests': receipt['failedTests'], 'receipt': (RUN / 'receipt.json').relative_to(ROOT).as_posix()}))
raise SystemExit(0 if receipt['passed'] else 1)
