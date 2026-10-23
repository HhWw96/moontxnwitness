"""Diagnostic instrumentation contract tests. Fake drivers, no database/network."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture import instrumentation as m
from moontxnwitness_capture import capture_v3

BASE = Path(os.environ.get('MTW_JOURNAL_TEST_ROOT', str(Path.cwd() / 'artifacts' / 'instrumentation-unit')))
RUN = BASE / ('instrumentation-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)


class BusinessError(Exception):
    sqlstate = 'XX000'


class Raw:
    def __init__(self):
        self.info = types.SimpleNamespace(transaction_status=0, encoding='utf-8')
        self.autocommit = self.closed = False
        self._pipeline = self._tpc = None
        self.commit_tag = b'COMMIT'
        self.commit_error = self.execute_error = self.fetch_error = None
        self.rows = [(1,), (2,)]
        self.executions, self.batches, self.cursors = [], [], []
        self.commit_value = object()
        self.batch_error_after = None
    def cursor(self, *args, **kwargs):
        cursor = RawCursor(self); self.cursors.append(cursor); return cursor
    def _exec_command(self, command):
        if False: yield None
        return types.SimpleNamespace(command_status=self.commit_tag)
    def commit(self):
        if self.commit_error:
            self.info.transaction_status = 0; raise self.commit_error
        list(self._exec_command(b'COMMIT'))
        self.info.transaction_status = 0
        return self.commit_value
    def rollback(self): self.info.transaction_status = 0
    def close(self): self.closed = True
    def __enter__(self): return self


class RawCursor:
    def __init__(self, connection):
        self.connection, self.description, self.pgresult = connection, None, None
        self.rowcount, self.rownumber, self.arraysize = -1, 0, 1
        self.row_factory = None
        self.closed, self.fetches = False, 0
        self.rows, self.sets = [], []
    def execute(self, sql, params=None, **kwargs):
        self.connection.executions.append((sql, params, kwargs))
        self.connection.info.transaction_status = 2
        if self.connection.execute_error: raise self.connection.execute_error
        self.rows = list(self.connection.rows)
        self.rownumber, self.rowcount = 0, len(self.rows)
        self.description = [types.SimpleNamespace(name='value', type_code=23)] if sql.startswith('SELECT') else None
        self.pgresult = types.SimpleNamespace(status=2 if self.description else 1)
        return self
    def executemany(self, sql, values, **kwargs):
        self.connection.info.transaction_status = 2
        self.sets = []
        for value in values:
            self.connection.batches.append(value)
            if self.connection.batch_error_after == len(self.connection.batches):
                raise self.connection.execute_error
            if kwargs.get('returning'): self.sets.append([(value[0],)])
        self.rowcount = len(self.connection.batches)
        self.description = [types.SimpleNamespace(name='value', type_code=23)] if self.sets else None
        self.rows = self.sets.pop(0) if self.sets else []
        self.rownumber = 0
        return None
    def fetchone(self):
        self.fetches += 1
        if self.connection.fetch_error: raise self.connection.fetch_error
        if self.rownumber >= len(self.rows): return None
        value = self.rows[self.rownumber]; self.rownumber += 1; return value
    def fetchmany(self, size=None):
        self.fetches += 1
        if self.connection.fetch_error: raise self.connection.fetch_error
        size = self.arraysize if size is None else size
        if size == 0: size = len(self.rows)
        value = self.rows[self.rownumber:self.rownumber + size]
        self.rownumber += len(value); return value
    def fetchall(self):
        self.fetches += 1
        if self.connection.fetch_error: raise self.connection.fetch_error
        value = self.rows[self.rownumber:]; self.rownumber = len(self.rows); return value
    def nextset(self):
        if not self.sets: return None
        self.rows = self.sets.pop(0); self.rownumber = 0; return True
    def close(self): self.closed = True
    def _close(self): self.close()
    def __enter__(self): return self


class AsyncRaw(Raw):
    def cursor(self, *args, **kwargs):
        cursor = AsyncRawCursor(self); self.cursors.append(cursor); return cursor
    async def commit(self): return super().commit()
    async def rollback(self): return super().rollback()
    async def close(self): return super().close()
    async def __aenter__(self): return self


class AsyncRawCursor(RawCursor):
    async def execute(self, *args, **kwargs): return super().execute(*args, **kwargs)
    async def executemany(self, *args, **kwargs): return super().executemany(*args, **kwargs)
    async def fetchone(self): return super().fetchone()
    async def fetchmany(self, *args): return super().fetchmany(*args)
    async def fetchall(self): return super().fetchall()
    async def close(self): return super().close()
    def _close(self): return RawCursor.close(self)
    async def __aenter__(self): return self


class Helpers:
    def observer(self, **kwargs):
        observer = m.Instrumentation(RUN / (self.id().split('.')[-1] + '-' + uuid.uuid4().hex), **kwargs)
        self.observers.append(observer); return observer
    def events(self, observer):
        observer.flush()
        return [json.loads(line) for p in sorted(observer.journal.path.glob('segment-*.jsonl'))
                for line in p.read_text(encoding='utf8').splitlines()]
    def notes(self, observer):
        observer.lifecycle.file.flush()
        return [json.loads(line) for line in (observer.output / 'lifecycle.jsonl').read_text(encoding='utf8').splitlines()]
    def codes(self, observer): return {x['code'] for x in observer.gaps}
    def finish(self):
        for observer in self.observers:
            observer.close()


class SyncTests(Helpers, unittest.TestCase):
    def setUp(self): self.observers = []
    def tearDown(self): self.finish()

    def test_factory_is_local_and_does_not_save_credentials(self):
        observer = self.observer(); raw = Raw(); calls = []
        def original(*args, **kwargs): calls.append((args, kwargs)); return raw
        connect = observer.psycopg_factory(original)
        result = connect('secret-dsn', password='secret-pass')
        self.assertIs(result._raw, raw)
        self.assertEqual(calls, [(('secret-dsn',), {'password': 'secret-pass'})])
        self.assertNotIn('secret', json.dumps(self.notes(observer)))

    def test_factory_exception_identity(self):
        observer = self.observer(); error = BusinessError('connect')
        def original(): raise error
        with self.assertRaises(BusinessError) as caught: observer.psycopg_factory(original)()
        self.assertIs(caught.exception, error)

    def test_factory_recording_failure_returns_original_connection(self):
        observer = self.observer(); raw = Raw()
        with mock.patch.object(observer, 'wrap', side_effect=OSError('observer')):
            self.assertIs(observer.psycopg_factory(lambda: raw)(), raw)
        self.assertIn('factory_connection_unobserved', self.codes(observer))

    def test_no_prefetch_and_exact_sql_params(self):
        observer = self.observer(); raw = Raw(); conn = observer.wrap(raw)
        params = {'x': object()}; cursor = conn.execute('SELECT exact', params, prepare=False)
        self.assertIs(raw.executions[0][1], params)
        self.assertEqual(raw.executions[0][0], 'SELECT exact')
        self.assertEqual(raw.executions[0][2], {'prepare': False})
        self.assertEqual(raw.cursors[0].fetches, 0)
        self.assertFalse([e for e in self.events(observer) if e['kind'] == 'rows'])
        self.assertEqual(cursor.fetchone(), (1,))
        self.assertEqual(cursor.fetchall(), [(2,)])
        rows = [e for e in self.events(observer) if e['kind'] == 'rows']
        self.assertEqual([e['rows'] for e in rows], [[[1]], [[2]]])

    def test_execute_exception_identity_and_raw_error(self):
        observer = self.observer(); raw = Raw(); error = raw.execute_error = BusinessError('statement')
        with self.assertRaises(BusinessError) as caught: observer.wrap(raw).execute('SELECT failure')
        self.assertIs(caught.exception, error)
        event = next(e for e in self.events(observer) if 'error' in e)
        self.assertEqual(event['error'], {'class': 'BusinessError', 'sqlstate': 'XX000'})

    def test_fetch_exception_identity_and_diagnostic(self):
        observer = self.observer(); raw = Raw(); cursor = observer.wrap(raw).execute('SELECT value')
        error = raw.fetch_error = BusinessError('fetch')
        with self.assertRaises(BusinessError) as caught: cursor.fetchone()
        self.assertIs(caught.exception, error)
        self.assertTrue(any(e.get('phase') == 'fetchone' for e in self.notes(observer)))
        self.assertTrue(any('error' in e for e in self.events(observer)))

    def test_commit_needs_real_tag_not_idle_status(self):
        observer = self.observer(); conn = observer.wrap(Raw())
        conn.execute('SELECT 1').fetchall(); conn.commit()
        events = self.events(observer)
        self.assertFalse(any(e['kind'] == 'commit_ok' for e in events))
        self.assertTrue(any(e['kind'] == 'disconnect' for e in events))
        self.assertIn('commit_ack_not_confirmed', self.codes(observer))

    def test_commit_tag_and_original_instance_method_restored(self):
        observer = self.observer(); raw = Raw(); conn = observer.wrap(raw)
        conn.execute('SELECT 1').fetchall(); original = raw._exec_command
        with mock.patch.object(capture_v3, '_pinned_connection', return_value=True):
            self.assertIs(conn.commit(), raw.commit_value)
        self.assertEqual(raw._exec_command, original)
        self.assertNotIn('_exec_command', raw.__dict__)
        self.assertTrue(any(e['kind'] == 'commit_ok' for e in self.events(observer)))

    def test_commit_rollback_tag_does_not_become_success(self):
        observer = self.observer(); raw = Raw(); conn = observer.wrap(raw)
        conn.execute('SELECT 1').fetchall(); raw.commit_tag = b'ROLLBACK'
        with mock.patch.object(capture_v3, '_pinned_connection', return_value=True): conn.commit()
        events = self.events(observer)
        self.assertFalse(any(e['kind'] == 'commit_ok' for e in events))
        self.assertEqual(next(e for e in events if e['kind'] == 'rollback_ok')['commitResponse']['commandTag'], 'ROLLBACK')

    def test_commit_exception_then_idle_rollback_stays_unknown(self):
        observer = self.observer(); raw = Raw(); conn = observer.wrap(raw)
        conn.execute('SELECT 1').fetchall(); error = raw.commit_error = BusinessError('lost response')
        with self.assertRaises(BusinessError) as caught: conn.commit()
        self.assertIs(caught.exception, error)
        conn.rollback()
        events = self.events(observer)
        self.assertFalse(any(e['kind'] in ('commit_ok', 'rollback_ok') for e in events))

    def test_executemany_consumes_only_when_driver_requests(self):
        observer = self.observer(); raw = Raw(); cursor = observer.wrap(raw).cursor(); consumed = []
        def values():
            for i in range(3): consumed.append(i); yield (i,)
        generator = values()
        self.assertEqual(consumed, [])
        self.assertIsNone(cursor.executemany('INSERT values', generator))
        self.assertEqual(consumed, [0, 1, 2]); self.assertEqual(raw.batches, [(0,), (1,), (2,)])
        notes = [e for e in self.notes(observer) if e['kind'] == 'executemany-parameters']
        self.assertEqual([e['parameters'] for e in notes], [[0], [1], [2]])
        self.assertEqual(len([e for e in self.events(observer) if e['kind'] == 'statement']), 1)

    def test_executemany_partial_failure_preserves_unconsumed_tail(self):
        observer = self.observer(); raw = Raw(); cursor = observer.wrap(raw).cursor()
        error = raw.execute_error = BusinessError('batch'); raw.batch_error_after = 2
        values = iter([(1,), (2,), (3,)])
        with self.assertRaises(BusinessError) as caught: cursor.executemany('INSERT values', values)
        self.assertIs(caught.exception, error); self.assertEqual(next(values), (3,))
        note = next(e for e in self.notes(observer) if e['kind'] == 'executemany-end')
        self.assertFalse(note['successful']); self.assertEqual(note['consumedParameters'], 2)

    def test_executemany_returning_sets_not_merged_as_complete_reads(self):
        observer = self.observer(); cursor = observer.wrap(Raw()).cursor()
        cursor.executemany('INSERT RETURNING', [(1,), (2,)], returning=True)
        self.assertEqual(cursor.fetchall(), [(1,)])
        self.assertTrue(cursor.nextset()); self.assertEqual(cursor.fetchall(), [(2,)])
        self.assertIsNone(cursor.nextset())
        rows = [e for e in self.events(observer) if e['kind'] == 'rows']
        self.assertEqual([e['complete'] for e in rows], [False, False, True])
        self.assertFalse(any(e['kind'] in ('read', 'write', 'condition') for e in self.events(observer)))

    def test_metadata_failure_does_not_change_business_return(self):
        observer = self.observer(); raw = Raw(); cursor = observer.wrap(raw).cursor()
        with mock.patch.object(observer.lifecycle, 'append', side_effect=OSError('disk full')):
            self.assertIsNone(cursor.executemany('INSERT values', [(1,), (2,)]))
        self.assertEqual(raw.batches, [(1,), (2,)])
        self.assertIn('instrumentation_metadata_missing', self.codes(observer))

    def test_savepoint_instances_are_not_names(self):
        observer = self.observer(); conn = observer.wrap(Raw())
        for sql in ['SAVEPOINT x', 'SAVEPOINT x', 'ROLLBACK TO x', 'RELEASE x', 'ROLLBACK TO x']:
            conn.execute(sql)
        savepoints = [e for e in self.events(observer) if e['kind'] == 'savepoint']
        self.assertEqual(len(savepoints), 2)
        self.assertNotEqual(savepoints[0]['instance'], savepoints[1]['instance'])

    def test_new_retry_and_reconnect_use_new_identity(self):
        observer = self.observer(); conn = observer.wrap(Raw())
        conn.execute('SELECT 1').fetchall(); conn.rollback()
        conn.execute('SELECT 2').fetchall(); conn.rollback()
        other = observer.wrap(Raw()); other.execute('SELECT 3').fetchall(); other.rollback()
        begin = [e for e in self.events(observer) if e['kind'] == 'begin']
        self.assertEqual(len({e['tx'] for e in begin}), 3)
        self.assertNotEqual(conn._identity, other._identity)

    def test_detach_keeps_business_connections_live(self):
        observer = self.observer(); raw = Raw(); conn = observer.wrap(raw)
        conn.execute('SELECT 1').fetchall(); conn.rollback(); observer.close()
        before = (observer.output / 'lifecycle.jsonl').read_bytes()
        self.assertFalse(raw.closed)
        self.assertEqual(conn.execute('SELECT 2').fetchall(), [(1,), (2,)])
        conn.commit(); self.assertEqual((observer.output / 'lifecycle.jsonl').read_bytes(), before)

    def test_close_and_export_are_explicitly_partial(self):
        observer = self.observer(); conn = observer.wrap(Raw())
        conn.execute('SELECT 1').fetchall(); conn.rollback()
        result = observer.close(source_closed=True)
        self.assertTrue(result.valid); self.assertFalse(result.complete)
        destination = observer.output / 'trace.json'
        receipt = observer.export_diagnostic(destination)
        self.assertFalse(receipt['complete'])
        self.assertIn('diagnostic_only', {g['code'] for g in json.loads(destination.read_text())['gaps']})
        with self.assertRaises(ValueError): observer.export(observer.output / 'history.json')

    def test_duplicate_directory_never_overwritten(self):
        observer = self.observer()
        with self.assertRaises(FileExistsError): m.Instrumentation(observer.output)

    def test_cursor_and_connection_budgets_keep_original_business(self):
        observer = self.observer(max_connections=1, max_cursors=1)
        first = observer.wrap(Raw()); raw = Raw()
        self.assertIs(observer.wrap(raw), raw)
        a = first.cursor(); b = first.cursor()
        self.assertIsInstance(a, m.DiagnosticCursor); self.assertIsInstance(b, RawCursor)
        self.assertIn('cursor_budget', self.codes(observer)); self.assertIn('connection_budget', self.codes(observer))


class EngineTests(Helpers, unittest.TestCase):
    def setUp(self): self.observers = []; self.engines = []
    def tearDown(self):
        self.finish()
        for engine in self.engines: engine.dispose()
    def engine(self):
        from sqlalchemy import create_engine
        engine = create_engine('postgresql+psycopg://')
        self.engines.append(engine); return engine
    def callbacks(self, observer): return {name: callback for target, name, callback in observer._listeners}

    def test_engine_registration_is_scoped_and_removable(self):
        from sqlalchemy import event
        observer = self.observer(); engine = self.engine(); observer.attach_engine(engine)
        listeners = list(observer._listeners)
        self.assertEqual(len(listeners), 7)
        for target, name, callback in listeners: self.assertTrue(event.contains(target, name, callback))
        observer.detach()
        for target, name, callback in listeners: self.assertFalse(event.contains(target, name, callback))
        self.assertFalse(observer._listeners)

    def test_pool_connect_checkout_reset_checkin_and_invalidate(self):
        observer = self.observer(); observer.attach_engine(self.engine()); hooks = self.callbacks(observer)
        raw = Raw(); record = types.SimpleNamespace(dbapi_connection=raw)
        hooks['connect'](raw, record); wrapped = record.dbapi_connection
        self.assertIsInstance(wrapped, m.DiagnosticConnection)
        hooks['checkout'](wrapped, record, object())
        state = types.SimpleNamespace(transaction_was_reset=True, terminate_only=False, asyncio_safe=True)
        hooks['reset'](wrapped, record, state)
        wrapped.execute('SELECT 1').fetchall()
        hooks['soft_invalidate'](wrapped, record, BusinessError('network'))
        hooks['invalidate'](wrapped, record, BusinessError('network'))
        hooks['checkin'](None, record); hooks['close'](wrapped, record)
        kinds = {e['kind'] for e in self.notes(observer)}
        self.assertTrue({'pool-connect','pool-checkout','pool-reset','pool-invalidate','pool-soft-invalidate','pool-checkin','pool-close'} <= kinds)
        self.assertFalse(observer._borrowed)
        self.assertIn('pool_connection_invalidated', self.codes(observer))

    def test_late_attach_does_not_mutate_unobserved_checkout(self):
        observer = self.observer(); observer.attach_engine(self.engine()); hooks = self.callbacks(observer)
        raw = Raw(); record = types.SimpleNamespace(dbapi_connection=raw)
        hooks['checkout'](raw, record, object())
        self.assertIs(record.dbapi_connection, raw)
        self.assertIn('late_engine_attachment', self.codes(observer))

    def test_borrowed_connection_at_detach_is_visible(self):
        observer = self.observer(); observer.attach_engine(self.engine()); hooks = self.callbacks(observer)
        raw = Raw(); record = types.SimpleNamespace(dbapi_connection=raw)
        hooks['connect'](raw, record); hooks['checkout'](record.dbapi_connection, record, object())
        observer.detach()
        self.assertIn('engine_detached_with_borrowed_connections', self.codes(observer))
        self.assertFalse(raw.closed)

    def test_other_dialect_rejected_before_hooks(self):
        from sqlalchemy import create_engine
        observer = self.observer(); engine = create_engine('sqlite://'); self.engines.append(engine)
        with self.assertRaises(ValueError): observer.attach_engine(engine)
        self.assertFalse(observer._listeners)

    def test_only_one_attach_per_observer(self):
        observer = self.observer(); observer.attach_engine(self.engine())
        with self.assertRaises(ValueError): observer.attach_engine(self.engine())


class AsyncTests(Helpers, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.observers = []
    async def asyncTearDown(self): self.finish()

    async def test_local_async_factory(self):
        observer = self.observer(); raw = AsyncRaw(); calls = []
        async def factory(*args, **kwargs): calls.append((args, kwargs)); return raw
        conn = await observer.psycopg_factory(factory, asynchronous=True)('private', password='hidden')
        self.assertIs(conn._raw, raw); self.assertEqual(calls[0][0], ('private',))
        self.assertNotIn('private', json.dumps(self.notes(observer)))

    async def test_async_no_prefetch_and_iterator(self):
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        cursor = await conn.execute('SELECT 1')
        self.assertEqual(raw.cursors[0].fetches, 0)
        result = [row async for row in cursor]
        self.assertEqual(result, [(1,), (2,)])
        self.assertEqual([e['rows'] for e in self.events(observer) if e['kind'] == 'rows'], [[[1]], [[2]]])

    async def test_async_execute_exception_identity(self):
        observer = self.observer(); raw = AsyncRaw(); error = raw.execute_error = BusinessError('execute')
        with self.assertRaises(BusinessError) as caught: await observer.wrap_async(raw).execute('SELECT failure')
        self.assertIs(caught.exception, error)

    async def test_async_fetch_exception_identity(self):
        observer = self.observer(); raw = AsyncRaw(); cursor = await observer.wrap_async(raw).execute('SELECT 1')
        error = raw.fetch_error = BusinessError('fetch')
        with self.assertRaises(BusinessError) as caught: await cursor.fetchall()
        self.assertIs(caught.exception, error)
        self.assertTrue(any(e.get('phase') == 'fetchall' for e in self.notes(observer)))

    async def test_async_commit_idle_is_not_confirmation(self):
        observer = self.observer(); conn = observer.wrap_async(AsyncRaw())
        cursor = await conn.execute('SELECT 1'); await cursor.fetchall(); await conn.commit()
        self.assertFalse(any(e['kind'] == 'commit_ok' for e in self.events(observer)))
        self.assertIn('commit_ack_not_confirmed', self.codes(observer))

    async def test_async_commit_actual_tag_restored(self):
        import psycopg
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        cursor = await conn.execute('SELECT 1'); await cursor.fetchall(); original = raw._exec_command
        with mock.patch.object(psycopg, 'AsyncConnection', AsyncRaw): result = await conn.commit()
        self.assertIs(result, raw.commit_value)
        self.assertEqual(raw._exec_command, original); self.assertNotIn('_exec_command', raw.__dict__)
        self.assertTrue(any(e['kind'] == 'commit_ok' for e in self.events(observer)))

    async def test_async_commit_error_then_idle_rollback_unknown(self):
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        cursor = await conn.execute('SELECT 1'); await cursor.fetchall()
        error = raw.commit_error = BusinessError('commit')
        with self.assertRaises(BusinessError) as caught: await conn.commit()
        self.assertIs(caught.exception, error); await conn.rollback()
        self.assertFalse(any(e['kind'] in ('commit_ok','rollback_ok') for e in self.events(observer)))

    async def test_async_executemany_and_partial_generator_failure(self):
        observer = self.observer(); raw = AsyncRaw(); cursor = observer.wrap_async(raw).cursor()
        error = BusinessError('generator')
        def values():
            yield (1,)
            raise error
        with self.assertRaises(BusinessError) as caught: await cursor.executemany('INSERT values', values())
        self.assertIs(caught.exception, error); self.assertEqual(raw.batches, [(1,)])
        self.assertFalse(next(e for e in self.notes(observer) if e['kind'] == 'executemany-end')['successful'])

    async def test_async_executemany_returning(self):
        observer = self.observer(); cursor = observer.wrap_async(AsyncRaw()).cursor()
        self.assertIsNone(await cursor.executemany('INSERT RETURNING', [(1,), (2,)], returning=True))
        self.assertEqual(await cursor.fetchall(), [(1,)]); self.assertTrue(cursor.nextset())
        self.assertEqual(await cursor.fetchall(), [(2,)]); self.assertIsNone(cursor.nextset())
        self.assertEqual([e['complete'] for e in self.events(observer) if e['kind'] == 'rows'], [False,False,True])

    async def test_real_sqlalchemy_adapter_prefetch_not_published_as_delivery(self):
        import psycopg
        from sqlalchemy.dialects.postgresql.psycopg import AsyncAdapt_psycopg_connection, AsyncAdapt_psycopg_cursor
        from sqlalchemy.util.concurrency import greenlet_spawn
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        adapter = AsyncAdapt_psycopg_connection(conn)
        cursor = m._AdapterConnection(adapter, conn).cursor()
        with mock.patch.object(AsyncAdapt_psycopg_cursor, '_psycopg_ExecStatus', psycopg.pq.ExecStatus):
            await greenlet_spawn(cursor.execute, 'SELECT 1')
        self.assertEqual(raw.cursors[0].fetches, 1)  # Original adapter's own prefetch.
        self.assertFalse(any(e['kind'] == 'rows' for e in self.events(observer)))
        self.assertEqual(cursor.fetchone(), (1,))
        self.assertEqual([e['rows'] for e in self.events(observer) if e['kind'] == 'rows'], [[[1]]])
        self.assertEqual(cursor.fetchall(), [(2,)])
        self.assertEqual(raw.cursors[0].fetches, 1)  # No added driver fetch.
        self.assertEqual([e['complete'] for e in self.events(observer) if e['kind'] == 'rows'], [False,True])

    async def test_prefetched_but_unconsumed_result_keeps_gap(self):
        import psycopg
        from sqlalchemy.dialects.postgresql.psycopg import AsyncAdapt_psycopg_connection, AsyncAdapt_psycopg_cursor
        from sqlalchemy.util.concurrency import greenlet_spawn
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        cursor = m._AdapterConnection(AsyncAdapt_psycopg_connection(conn), conn).cursor()
        with mock.patch.object(AsyncAdapt_psycopg_cursor, '_psycopg_ExecStatus', psycopg.pq.ExecStatus):
            await greenlet_spawn(cursor.execute, 'SELECT 1')
        cursor.close()
        self.assertIn('orm_unconsumed_result', self.codes(observer))
        self.assertFalse(any(e['kind'] == 'rows' for e in self.events(observer)))

    async def test_async_after_detach_keeps_driver_usable(self):
        observer = self.observer(); raw = AsyncRaw(); conn = observer.wrap_async(raw)
        cursor = await conn.execute('SELECT 1'); await cursor.fetchall(); await conn.rollback()
        observer.close(); cursor = await conn.execute('SELECT after')
        self.assertEqual(await cursor.fetchall(), [(1,), (2,)])
        self.assertFalse(raw.closed)


if __name__ == '__main__':
    result = unittest.main(verbosity=2, exit=False).result
    receipt = {'schema': 1, 'kind': 'diagnostic-instrumentation-fake-driver-unit-tests',
               'actualDatabaseExecution': False, 'networkExecution': False,
               'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'skipped': len(result.skipped), 'passed': result.wasSuccessful()}
    (RUN / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps(receipt))
    raise SystemExit(0 if result.wasSuccessful() else 1)
