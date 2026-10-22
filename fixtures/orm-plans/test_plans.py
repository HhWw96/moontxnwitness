"""Offline actual-compiler/cache and DBAPI-double tests; no DB/build/install."""
from __future__ import annotations
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE.parents[1] / 'integrations/python'
sys.path.insert(0, str(PAYLOAD))
from moontxnwitness_capture import orm
from moontxnwitness_capture import _orm_policy as policy
from moontxnwitness_capture import _orm_async as adapter
from moontxnwitness_capture import _orm_raw_async as raw_adapter

def load_baseline():
    spec = importlib.util.spec_from_file_location('v013_original_policy', HERE / 'provenance_policy.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
baseline = load_baseline()
COMPILATION_COMPARISON = None
KEY = '00000000-0000-4000-8000-000000000001'
OTHER_KEY = '00000000-0000-4000-8000-000000000004'
BEFORE, AFTER = '00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000003'
SCOPE = orm.UserScope('mtw_orm_v3_candidate', 'observed_user', (KEY, OTHER_KEY))
OLD_SCOPE = baseline.UserScope(SCOPE.schema, SCOPE.table, SCOPE.known_ids)

def shapes(scope):
    result = [('get', (), 'id_1'), ('get', (), 'pk_1'), ('create', (), 'id'), ('delete', (), 'id')]
    for mask in range(1, 32):
        fields = tuple(name for i, name in enumerate(orm.VALUES) if mask & (1 << i))
        result.append(('update', fields, scope.schema + '_' + scope.table + '_id'))
    return result

def images(key=KEY, email='fixture@example.invalid'):
    return {'id': key, 'email': email, 'hashed_password': 'controlled-fixture',
        'is_active': True, 'is_superuser': False, 'is_verified': False}

class Result:
    status, nfields, ntuples, command_tuples, binary_tuples = 2, 8, 1, 1, 0
    def __init__(self, *, read=False, present=True, key=KEY):
        self.read, self.calls = read, 0
        if read:
            values = [key, *list(images(key).values())[1:]] if present else [None] * 6
            values += [BEFORE, present]
            self.command_status = b'SELECT 1'
        else:
            values = [key, BEFORE, AFTER, True, True, images(key), images(key, 'changed@example.invalid'), 'UPDATE']
            self.command_status = b'UPDATE 1'
        self.values = [None if value is None else
            (b't' if value else b'f') if type(value) is bool else
            json.dumps(value).encode() if isinstance(value, dict) else value.encode() for value in values]
    def get_value(self, row, column):
        self.calls += 1
        return self.values[column]
    def fformat(self, column): return 0
    def ftype(self, column):
        return (2950, 1043, 1043, 16, 16, 16, 25, 16)[column] if self.read else (16 if column in (3, 4) else 1043 if column in (5, 6) else 25)
    def fmod(self, column):
        return (324 if column == 1 else 1028 if column == 2 else -1) if self.read else (orm.PAYLOAD_CHARS + 4 if column in (5, 6) else -1)

class RawCursor:
    def __init__(self, *, read=False, present=True, key=KEY, execute_error=None, fetch_error=None):
        self.pgresult = Result(read=read, present=present, key=key)
        self.rowcount, self.rownumber = 1, 0
        self.statusmessage = 'SELECT 1' if read else 'UPDATE 1'
        self.description = tuple(SimpleNamespace(name=name, type_code=self.pgresult.ftype(i))
            for i, name in enumerate((*orm.FIELDS, 'source_version', 'source_present')))
        values = list(images(key).values())
        values[0] = uuid.UUID(key)
        self.rows = [(tuple(values) if present else (None,) * 6) + (BEFORE, present)] if read else []
        self.executed, self.execute_error, self.fetch_error = [], execute_error, fetch_error
    async def execute(self, query, params=None, **kwargs):
        self.executed.append((query, params, kwargs))
        if self.execute_error is not None: raise self.execute_error
        return self
    async def fetchone(self):
        if self.fetch_error is not None: raise self.fetch_error
        if self.pgresult.status == 1: raise RuntimeError('original no-result exception')
        self.rownumber += bool(self.rows)
        return self.rows.pop(0) if self.rows else None
    async def fetchmany(self, count=1):
        if self.fetch_error is not None: raise self.fetch_error
        rows, self.rows = self.rows[:count], self.rows[count:]
        self.rownumber += len(rows)
        return rows
    async def fetchall(self):
        if self.fetch_error is not None: raise self.fetch_error
        rows, self.rows = self.rows, []
        self.rownumber += len(rows)
        return rows

class Session:
    def __init__(self, *, enabled=True, old=False):
        self.scope = OLD_SCOPE if old else SCOPE
        self.cache = baseline.StructuredSQLCache() if old else orm.StructuredSQLCache(enabled=enabled)
        prepare = (lambda op, fields, bind: baseline.build(self.scope, op, fields, bind)) if old else (
            lambda op, fields, bind: self.cache.prepare(self.scope, op, fields, bind))
        plans = [prepare(*shape) for shape in shapes(self.scope)]
        self.plans = {plan.original_sql: plan for plan in plans}
        self.events, self.gaps, self.sink_records = [], [], []
        self.sink = SimpleNamespace(append=self.sink_records.append)
    def activity(self, name): pass
    def gap(self, code, message): self.gaps.append((code, message))
    def encode(self, value): return deepcopy(value)
    def emit(self, kind, **fields):
        self.events.append({'kind': kind, **fields})
        return len(self.events)

def old_cursor_class():
    tree = ast.parse((HERE / 'async_adapter.py').read_text(encoding='utf8'))
    definitions = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in ('SourceResult', 'ReadResultFacade', 'Cursor')]
    namespace = {'raw_module': raw_adapter, 'FIELDS': baseline.FIELDS,
        'CoverageRequired': baseline.CoverageRequired, 'observe_command': baseline.observe_command,
        'observe_get': baseline.observe_get, 'AsyncCommandCursorView': baseline.AsyncCommandCursorView}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'frozen-baseline-cursor', 'exec'), namespace)
    return namespace['Cursor']
OLD_CURSOR = old_cursor_class()

def cursor_fixture(*, enabled=True, old=False, **raw_options):
    session = Session(enabled=enabled, old=old)
    raw = RawCursor(**raw_options)
    connection = SimpleNamespace(_session=session, _lock=asyncio.Lock(), _tx='fixture-tx', _last_error=None)
    connection._begin = lambda: None
    return session, raw, (OLD_CURSOR if old else adapter.Cursor)(connection, raw)

class CacheTests(unittest.TestCase):
    def test_standalone_public_import_without_optional_packages(self):
        result = subprocess.check_output([sys.executable, '-I', '-S', '-B', '-c',
            'import sys;sys.path.insert(0,sys.argv[1]);from moontxnwitness_capture.orm import UserScope,SQLContext,StructuredSQLCache;'
            'assert "sqlalchemy" not in sys.modules;assert "psycopg" not in sys.modules;print("isolated-import-ok")', str(PAYLOAD)], text=True)
        self.assertEqual(result.strip(), 'isolated-import-ok')

    def test_exact_35_templates_and_both_update_bind_layouts_unchanged(self):
        for operation, fields, bind in shapes(SCOPE):
            for actual_bind in ((bind, SCOPE.table + '_id') if operation == 'update' else (bind,)):
                with self.subTest(operation=operation, fields=fields, bind=actual_bind):
                    old, new = baseline.build(OLD_SCOPE, operation, fields, actual_bind), orm.build(SCOPE, operation, fields, actual_bind)
                    for name in ('original_sql', 'observed_sql', 'mapping_id', 'business_columns', 'result_mode'):
                        self.assertEqual(getattr(old, name), getattr(new, name))

    def test_prepared_plan_avoids_second_real_compilation(self):
        cache = orm.StructuredSQLCache()
        plans = [cache.prepare(SCOPE, *shape) for shape in shapes(SCOPE)]
        self.assertEqual(cache.compilations, 35)
        for _ in range(3):
            for plan in plans:
                self.assertIs(cache.match(SCOPE, plan.original_sql, plan.key.operation, plan.key.fields, plan.key.pk_bind), plan)
        self.assertEqual(cache.compilations, 35)
        self.assertEqual(cache.hits, 105)

    def test_real_original_and_candidate_compilation_work(self):
        global COMPILATION_COMPARISON
        with patch.object(baseline, 'build', wraps=baseline.build) as original_compile:
            plans = [baseline.build(OLD_SCOPE, *shape) for shape in shapes(OLD_SCOPE)]
            original_cache = baseline.StructuredSQLCache()
            self.assertEqual(original_compile.call_count, 35)
            for _ in range(3):
                for plan in plans:
                    original_cache.match(OLD_SCOPE, plan.original_sql, plan.key.operation, plan.key.fields, plan.key.pk_bind)
            original_calls = original_compile.call_count
        enabled, disabled = orm.StructuredSQLCache(), orm.StructuredSQLCache(enabled=False)
        for cache in (enabled, disabled):
            plans = [cache.prepare(SCOPE, *shape) for shape in shapes(SCOPE)]
            for _ in range(3):
                for plan in plans:
                    cache.match(SCOPE, plan.original_sql, plan.key.operation, plan.key.fields, plan.key.pk_bind)
        self.assertEqual((original_calls, enabled.compilations, disabled.compilations), (70, 35, 140))
        COMPILATION_COMPARISON = {'fixedShapes': 35, 'executionsPerShape': 3,
            'originalActualCompilerCalls': original_calls, 'candidateEnabledActualCompilerCalls': enabled.compilations,
            'candidateDisabledActualCompilerCalls': disabled.compilations,
            'interpretation': 'Actual fixed SQLAlchemy 2.0.55 compiler calls; no elapsed-time, throughput, memory or database claim'}

    def test_actual_observer_constructor_prepares_same_cache(self):
        installation = SimpleNamespace(scope=SCOPE, initial={KEY: {'version': BEFORE}}, metadata={})
        records = []
        with patch.object(adapter.CaptureV3Session, '__init__', return_value=None), \
             patch.object(adapter.CaptureV3Session, 'publish_snapshot'), \
             patch.object(adapter.CaptureV3Session, 'gap'):
            observer = adapter.ProvenanceObserver('not-created', installation, SimpleNamespace(append=records.append))
        self.assertEqual(len(observer.plans), 35)
        self.assertEqual(observer.cache.compilations, 35)
        for plan in observer.plans.values():
            self.assertIs(observer.cache.match(SCOPE, plan.original_sql, plan.key.operation, plan.key.fields, plan.key.pk_bind), plan)
        self.assertEqual(observer.cache.compilations, 35)
        self.assertEqual(records[0]['kind'], 'installation')

    def test_cache_on_off_returns_identical_plans(self):
        enabled, disabled = orm.StructuredSQLCache(), orm.StructuredSQLCache(enabled=False)
        for _ in range(2):
            for shape in shapes(SCOPE):
                left, right = enabled.prepare(SCOPE, *shape), disabled.prepare(SCOPE, *shape)
                self.assertEqual(left, right)
        self.assertEqual(enabled.compilations, 35)
        self.assertEqual(disabled.compilations, 70)
        self.assertEqual(disabled.retained, {'entries': 0, 'bytes': 0})

    def test_lru_entry_eviction_and_recent_hit(self):
        cache = orm.StructuredSQLCache(max_entries=2)
        first = cache.prepare(SCOPE, 'get')
        cache.prepare(SCOPE, 'get', pk_bind='pk_1')
        cache.match(SCOPE, first.original_sql, 'get')
        cache.prepare(SCOPE, 'delete', pk_bind='id')
        self.assertEqual(cache.retained['entries'], 2)
        self.assertEqual(cache.evictions, 1)
        self.assertIs(cache.match(SCOPE, first.original_sql, 'get'), first)
        cache.prepare(SCOPE, 'get', pk_bind='pk_1')
        self.assertEqual(cache.evictions, 2)

    def test_byte_eviction_and_oversized_entry_bypass_preserve_plan(self):
        cache = orm.StructuredSQLCache(max_entries=128, max_bytes=4096)
        for shape in shapes(SCOPE):
            cache.prepare(SCOPE, *shape)
            self.assertLessEqual(cache.retained['bytes'], 4096)
        self.assertGreater(cache.evictions + cache.bypasses, 0)
        ids = tuple(str(uuid.UUID(int=i + 1)) for i in range(128))
        large = orm.UserScope(SCOPE.schema, SCOPE.table, ids)
        bypass = orm.StructuredSQLCache(max_bytes=4096)
        self.assertEqual(bypass.prepare(large, 'get'), orm.build(large, 'get'))
        self.assertEqual(bypass.retained, {'entries': 0, 'bytes': 0})
        self.assertEqual(bypass.bypasses, 1)

    def test_scope_domain_and_profile_epoch_are_separate_keys(self):
        cache = orm.StructuredSQLCache()
        first = cache.prepare(SCOPE, 'get')
        for scope in (orm.UserScope(SCOPE.schema, SCOPE.table, (KEY,)),
                      orm.UserScope(SCOPE.schema + '2', SCOPE.table, SCOPE.known_ids),
                      orm.UserScope(SCOPE.schema, 'second_user', SCOPE.known_ids)):
            self.assertIsNot(cache.prepare(scope, 'get'), first)
        changed = orm.SQLContext(registry_epoch=1)
        updated = cache.prepare(SCOPE, 'get', context=changed)
        self.assertIsNot(updated, first)
        self.assertEqual(updated.context, changed)
        self.assertIs(cache.prepare(SCOPE, 'get'), first)
        self.assertEqual(cache.compilations, 5)

    def test_mutable_or_unsupported_contexts_are_refused(self):
        with self.assertRaises(ValueError): orm.UserScope(SCOPE.schema, SCOPE.table, list(SCOPE.known_ids))
        for options in ({'sqlalchemy_version': '2.0.45'}, {'registry_epoch': True}, {'payload_chars': 1}, {'dialect': 'sqlite'}):
            with self.assertRaises(ValueError): orm.SQLContext(**options)
        with self.assertRaises(FrozenInstanceError): SCOPE.table = 'changed'
        with self.assertRaises(FrozenInstanceError): orm.DEFAULT_CONTEXT.registry_epoch = 1
        cache = orm.StructuredSQLCache()
        with self.assertRaises(AttributeError): cache.max_bytes = 10**9

    def test_compiler_mismatch_and_failure_are_not_cached(self):
        cache = orm.StructuredSQLCache()
        with patch.object(policy.sqlalchemy, '__version__', '2.0.45'):
            with self.assertRaises(orm.CoverageRequired): cache.prepare(SCOPE, 'get')
        sentinel = RuntimeError('original compile failure')
        with patch.object(orm, 'build', side_effect=sentinel):
            with self.assertRaises(RuntimeError) as caught: cache.prepare(SCOPE, 'get')
        self.assertIs(caught.exception, sentinel)
        self.assertEqual(cache.retained['entries'], 0)
        cache.prepare(SCOPE, 'get')
        self.assertEqual(cache.retained['entries'], 1)

    def test_warm_cache_cannot_hide_runtime_compiler_change(self):
        cache = orm.StructuredSQLCache()
        plan = cache.prepare(SCOPE, 'get')
        with patch.object(policy.sqlalchemy, '__version__', '2.0.45'):
            with self.assertRaises(orm.CoverageRequired): cache.match(SCOPE, plan.original_sql, 'get')
        self.assertIs(cache.match(SCOPE, plan.original_sql, 'get'), plan)

    def test_observer_bad_configuration_does_not_create_journal(self):
        installation = SimpleNamespace(scope=SCOPE, initial={KEY: {'version': BEFORE}}, metadata={})
        target = HERE / 'runs' / ('must-stay-absent-' + uuid.uuid4().hex)
        with self.assertRaises(ValueError):
            adapter.ProvenanceObserver(target, installation, SimpleNamespace(append=lambda _: None), cache_max_entries=0)
        self.assertFalse(target.exists())

    def test_cache_hit_rechecks_shape_and_exact_sql(self):
        cache = orm.StructuredSQLCache()
        fields = ['email']
        plan = cache.prepare(SCOPE, 'update', fields, SCOPE.table + '_id')
        fields.append('unknown')
        for invalid in (fields, ('email', 'email'), ('id',), ('unknown',)):
            with self.assertRaises(orm.CoverageRequired): cache.match(SCOPE, plan.original_sql, 'update', invalid, SCOPE.table + '_id')
        for sql in (plan.original_sql + ';', plan.original_sql + ' ', 'x' * 65537):
            with self.assertRaises(orm.CoverageRequired): cache.match(SCOPE, sql, 'update', ('email',), SCOPE.table + '_id')

    def test_concurrent_same_shape_has_one_compilation(self):
        cache = orm.StructuredSQLCache()
        with ThreadPoolExecutor(max_workers=8) as pool:
            plans = list(pool.map(lambda _: cache.prepare(SCOPE, 'get'), range(24)))
        self.assertTrue(all(plan is plans[0] for plan in plans))
        self.assertEqual(cache.compilations, 1)

    def test_unmatched_actual_sql_and_business_values_are_not_retained(self):
        cache = orm.StructuredSQLCache()
        value = 'private-business-value@example.invalid'
        with self.assertRaises(orm.CoverageRequired): cache.match(SCOPE, value, 'get')
        self.assertNotIn(value, repr(cache._values))
        self.assertEqual(set(orm.SQLPlan.__dataclass_fields__), {'key','original_sql','observed_sql','mapping_id','business_columns','result_mode','context'})

    def test_relocated_source_decoders_and_raw_lifecycle_are_unchanged(self):
        def classes_and_functions(text):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(text).body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        old = classes_and_functions((HERE / 'provenance_policy.py').read_text(encoding='utf8'))
        new = classes_and_functions((PAYLOAD / 'moontxnwitness_capture/_orm_policy.py').read_text(encoding='utf8'))
        unchanged = set(old) - {'CoverageRequired','UserScope','PlanKey','SQLPlan','StructuredSQLCache','build'}
        for name in unchanged: self.assertEqual(old[name], new[name], name)
        raw_old = classes_and_functions((HERE / 'raw_async_adapter.py').read_text(encoding='utf8'))
        raw_new = classes_and_functions((PAYLOAD / 'moontxnwitness_capture/_orm_raw_async.py').read_text(encoding='utf8'))
        self.assertEqual(raw_old, raw_new)

class CursorTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_parameters_and_command_surface_cache_on_off_and_original(self):
        outcomes = []
        for options in ({'old': True}, {'enabled': False}, {'enabled': True}):
            session, raw, cursor = cursor_fixture(**options)
            plan = next(p for p in session.plans.values() if p.key.operation == 'update' and p.key.fields == ('email',))
            parameters = {'email': 'first@example.invalid', plan.key.pk_bind: KEY}
            self.assertIs(await cursor.execute(plan.original_sql, parameters), cursor)
            self.assertIs(raw.executed[-1][1], parameters)
            self.assertIsNone(cursor.description)
            self.assertEqual(cursor.rowcount, 1)
            self.assertIsNone(cursor.rownumber)
            parameters2 = {'email': 'second@example.invalid', plan.key.pk_bind: OTHER_KEY}
            raw.pgresult = Result(key=OTHER_KEY)
            self.assertIs(await cursor.execute(plan.original_sql, parameters2), cursor)
            self.assertIs(raw.executed[-1][1], parameters2)
            self.assertEqual(session.sink_records[0]['parameters']['email'], 'first@example.invalid')
            self.assertEqual(session.sink_records[1]['parameters']['email'], 'second@example.invalid')
            self.assertNotIn('first@example.invalid', repr(session.cache._values))
            self.assertNotIn('second@example.invalid', repr(session.cache._values))
            outcomes.append((session.events, session.gaps, session.sink_records))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1], outcomes[2])

    async def test_positive_and_negative_rows_are_delivered_without_consumption(self):
        for present in (True, False):
            outcomes = []
            for options in ({'old': True}, {'enabled': False}, {'enabled': True}):
                session, raw, cursor = cursor_fixture(read=True, present=present, **options)
                plan = next(p for p in session.plans.values() if p.key.operation == 'get')
                await cursor.execute(plan.original_sql, {plan.key.pk_bind: KEY})
                self.assertEqual(raw.rownumber, 0)
                self.assertEqual(len(session.sink_records), 0)
                row = await cursor.fetchone()
                self.assertEqual(row, tuple([uuid.UUID(KEY), *list(images().values())[1:]]) if present else None)
                self.assertIsNone(await cursor.fetchone())
                self.assertEqual(len(session.sink_records), 1)
                outcomes.append((row, session.events, session.gaps, session.sink_records))
            self.assertEqual(outcomes[0], outcomes[1])
            self.assertEqual(outcomes[1], outcomes[2])

    async def test_original_execute_and_fetch_exceptions_keep_identity(self):
        for enabled in (False, True):
            sentinel = RuntimeError('original database error')
            session, raw, cursor = cursor_fixture(enabled=enabled, execute_error=sentinel)
            plan = next(p for p in session.plans.values() if p.key.operation == 'get')
            with self.assertRaises(RuntimeError) as caught:
                await cursor.execute(plan.original_sql, {plan.key.pk_bind: KEY})
            self.assertIs(caught.exception, sentinel)
            self.assertIs(cursor._connection._last_error, sentinel)
            session, raw, cursor = cursor_fixture(enabled=enabled, read=True, fetch_error=sentinel)
            plan = next(p for p in session.plans.values() if p.key.operation == 'get')
            await cursor.execute(plan.original_sql, {plan.key.pk_bind: KEY})
            with self.assertRaises(RuntimeError) as caught: await cursor.fetchone()
            self.assertIs(caught.exception, sentinel)

    async def test_invalid_parameters_still_execute_original_without_cached_facts(self):
        for enabled in (False, True):
            session, raw, cursor = cursor_fixture(enabled=enabled)
            plan = next(p for p in session.plans.values() if p.key.operation == 'get')
            parameters = {plan.key.pk_bind: KEY, 'unknown': 'extra'}
            await cursor.execute(plan.original_sql, parameters)
            self.assertEqual(raw.executed[-1][0], plan.original_sql)
            self.assertIs(raw.executed[-1][1], parameters)
            self.assertEqual(session.sink_records, [])
            self.assertTrue(any(code == 'orm_parameters_unmapped' for code, _ in session.gaps))
