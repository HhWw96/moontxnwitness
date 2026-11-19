"""Source-window observations for owned psycopg async business connections."""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid
from contextlib import asynccontextmanager

from .configured_effects import WRITER_PROBE_SQL
from .configured_factory_v2 import record_factory_gap_v2
from .configured_point_capture_v2 import (
    PointCaptureV2, _PointProjectionState, _idle_commit_v2, _native, _retain_writer_checkpoint, _tuple_factory,
)
from .configured_window_v2 import ConfiguredCaptureWindowV2
from .instrumentation import (
    DiagnosticAsyncConnection, DiagnosticAsyncCursor, _AdapterConnection, _AdapterCursor,
    _end_call, _start_call,
)


def _owned_async_connection(raw):
    from psycopg import AsyncConnection, __version__

    return (__version__ == '3.3.6' and type(raw) is AsyncConnection
            and not getattr(raw, '_pool', None))


class ConfiguredAsyncCaptureWindowV2(ConfiguredCaptureWindowV2):
    """Synchronous dedicated control snapshots, async business I/O on one loop.

    Construct and seal on the control connection's owner thread. Between those
    calls, use the local factory from a single event loop on that thread.
    """

    def __init__(self, *args, sqlalchemy_pool_size=None, **kwargs):
        if sqlalchemy_pool_size is not None and (type(sqlalchemy_pool_size) is not int or not 1 <= sqlalchemy_pool_size <= 8):
            raise ValueError('A configured SQLAlchemy pool must have one to eight physical connections')
        self._owner_thread = threading.get_ident()
        self._loop = None
        self._engine_open = False
        self._pool_size = sqlalchemy_pool_size
        super().__init__(*args, **kwargs)

    def _require_loop(self):
        if threading.get_ident() != self._owner_thread:
            raise ValueError('Use the configured window on its control connection thread')
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise ValueError('All business connections must use the same event loop')

    def _wrap_participant(self, raw):
        return self.observer.wrap_async(raw)

    def _make_observer(self, path, config, **options):
        producer = _PooledAsyncPointCaptureV2 if self._pool_size is not None else _AsyncPointCaptureV2
        return producer(path, config, **options)

    def wrap_connection(self, raw):
        self._require_loop()
        if self._pool_size is not None:
            raise ValueError('Use the owned SQLAlchemy engine to enroll pooled connections')
        return super().wrap_connection(raw)

    def psycopg_factory(self, factory):
        if self._pool_size is not None or not callable(factory):
            raise ValueError('An owned async connection factory is required')

        async def connect(*args, **kwargs):
            self._require_loop()
            if self._state != 'open' or self._pending_factories >= 32:
                raise ValueError('Window is closed or its concurrent acquisition budget is exhausted')
            return await self._acquire(factory, args, kwargs, self.wrap_connection)

        return connect

    async def _acquire(self, factory, args, kwargs, admit):
        self._pending_factories += 1
        raw = None
        try:
            pending = factory(*args, **kwargs)
            if not inspect.isawaitable(pending):
                raise ValueError('Configured async factory must return an awaitable')
            raw = await pending
            return admit(raw)
        except BaseException:
            self._factory_gap()
            if raw is not None and not any(raw is p._raw for p in self._participants):
                try:
                    if _owned_async_connection(raw):
                        await raw.close()
                except BaseException:
                    pass
            raise
        finally:
            self._pending_factories -= 1

    def _factory_gap(self):
        if not record_factory_gap_v2(self.observer):
            self._factory_observation_failed = True

    @asynccontextmanager
    async def sqlalchemy_engine(self, factory):
        """Own a scoped SQLAlchemy 2.0.55 async engine and its physical connections."""
        import sqlalchemy
        from sqlalchemy.dialects.postgresql.psycopg import AsyncAdapt_psycopg_connection
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

        self._require_loop()
        if (sqlalchemy.__version__ != '2.0.55' or not callable(factory)
                or self._engine_open or self._state != 'open'):
            raise ValueError('An open window and a new owned SQLAlchemy 2.0.55 engine are required')
        active = True
        self._engine_open = True
        engine = None
        pool = _PointPoolLifecycleV2(self) if self._pool_size is not None else None

        def admit(raw):
            if not active or not _ready_async_connection(raw):
                raise ValueError('New idle owned psycopg 3.3.6 async tuple connection required')
            if any(raw is participant._raw for participant in self._participants):
                raise ValueError('The SQLAlchemy factory must open a fresh physical connection')
            return raw

        async def connect():
            self._require_loop()
            if not active or self._pending_factories >= 32:
                raise ValueError('Engine scope is closed or its concurrent acquisition budget is exhausted')
            return await self._acquire(factory, (), {}, admit)

        def enroll(dbapi, record):
            try:
                if not active or type(dbapi) is not AsyncAdapt_psycopg_connection:
                    raise ValueError('Unexpected scoped SQLAlchemy async connection adapter')
                self._require_loop()
                observed = super(ConfiguredAsyncCaptureWindowV2, self).wrap_connection(dbapi.driver_connection)
                dbapi._connection = observed
                record.dbapi_connection = _PointAdapterConnection(dbapi, observed)
                if pool is not None:
                    pool.enrolled(observed)
            except BaseException:
                self._factory_gap()
                raise

        try:
            options = {'poolclass': NullPool}
            if pool is not None:
                options = {'poolclass': AsyncAdaptedQueuePool, 'pool_size': self._pool_size, 'max_overflow': 0}
            engine = create_async_engine('postgresql+psycopg://', async_creator=connect,
                                         pool_reset_on_return=None, **options)
            sqlalchemy.event.listen(engine.sync_engine, 'connect', enroll)
            if pool is not None:
                sqlalchemy.event.listen(engine.sync_engine, 'checkout', pool.checkout)
                sqlalchemy.event.listen(engine.sync_engine, 'checkin', pool.checkin)
                sqlalchemy.event.listen(engine.sync_engine, 'invalidate', pool.invalidate)
            yield engine
        finally:
            active = False
            try:
                if engine is not None:
                    await engine.dispose()
            finally:
                self._engine_open = False

    def seal(self):
        if threading.get_ident() != self._owner_thread:
            raise ValueError('Seal the configured window on its control connection thread')
        if self._engine_open:
            raise ValueError('Finish the owned SQLAlchemy engine scope before sealing')
        if any(participant._point_lock.locked() for participant in self._participants):
            raise ValueError('Finish all participant operations before sealing')
        return super().seal()


class _AsyncPointCaptureV2(PointCaptureV2):
    _producer_format = 'moontxnwitness-async-point-producer/v2'

    def _wrap(self, raw, *, asynchronous):
        if not self._enabled or not asynchronous or not _ready_async_connection(raw):
            raise ValueError('New idle owned psycopg 3.3.6 async tuple connection required')
        return self._enroll_connection(raw, _AsyncPointConnectionV2, asynchronous=True)


class _PooledAsyncPointCaptureV2(_AsyncPointCaptureV2):
    _producer_format = 'moontxnwitness-async-point-pool-producer/v1'


class _PointPoolLifecycleV2:
    def __init__(self, window):
        self.window = window
        self.generations = {}
        self.borrowed = set()

    def _record(self, kind, connection, lease):
        try:
            raw = connection._raw
            if (raw.closed or int(raw.info.transaction_status) != 0 or connection._tx is not None
                    or connection._point_lock.locked() or any(cursor._pending for cursor in connection._cursors)):
                raise ValueError('Connection has unfinished operations')
            note = self.window.observer.frame('configured-point-pool-' + kind, {
                'format': 'moontxnwitness-configured-point-pool/v1', 'connection': connection._identity,
                'backendPid': raw.info.backend_pid, 'lease': lease, 'transactionStatus': 0,
            })
            if note is None:
                raise ValueError('Pool boundary not recorded')
        except Exception:
            self.window._factory_gap()

    def enrolled(self, connection):
        self.generations[connection._identity] = 0
        self._record('enroll', connection, 0)

    def checkout(self, adapter, _record, _proxy):
        if not isinstance(adapter, _PointAdapterConnection):
            self.window._factory_gap()
            return
        connection = adapter._observed
        identity = connection._identity
        if identity in self.borrowed or identity not in self.generations:
            self.window._factory_gap()
            return
        generation = self.generations[identity] + 1
        self.generations[identity] = generation
        self.borrowed.add(identity)
        self._record('checkout', connection, generation)

    def checkin(self, adapter, _record):
        if not isinstance(adapter, _PointAdapterConnection) or adapter._observed._identity not in self.borrowed:
            self.window._factory_gap()
            return
        connection = adapter._observed
        identity = connection._identity
        self.borrowed.discard(identity)
        self._record('checkin', connection, self.generations[identity])

    def invalidate(self, _adapter, _record, _exception):
        self.window._factory_gap()


def _ready_async_connection(raw):
    return (_owned_async_connection(raw) and not raw.autocommit and not raw.closed
            and int(raw.info.transaction_status) == 0 and not raw._pipeline
            and not raw._tpc and _tuple_factory(raw))


class _PointAdapterConnection(_AdapterConnection):
    def _wrap_cursor(self, cursor, observed):
        return _PointAdapterCursor(cursor, observed)


class _PointAdapterCursor(_AdapterCursor):
    def _fetch(self, method, *args):
        observed = self._observed
        if observed._projection is None:
            return super()._fetch(method, *args)
        result = getattr(self._raw, method)(*args)
        business = observed._projection['businessResult']
        if business['mode'] == 'no-result':
            return result
        if not observed._session._enabled:
            return observed._business_delivery(method, result, business)[0]
        size = None
        if method == 'fetchmany':
            size = observed.arraysize if args[0] is None else args[0]
            if size <= 0:
                return result
        delivered, rows = observed._record_delivery(
            method, args, result, business, size, observed._delivery_position)
        observed.delivered(rows, not self._raw._rows)
        return delivered


class _AsyncPointConnectionV2(DiagnosticAsyncConnection):
    def __init__(self, session, raw):
        super().__init__(session, raw)
        self._point_lock = asyncio.Lock()

    def cursor(self, *args, **kwargs):
        from psycopg import AsyncCursor

        raw = self._raw.cursor(*args, **kwargs)
        if not self._session._enabled:
            return raw
        if len(self._session._cursors) >= self._session._max_cursors:
            self._session.gap('cursor_budget', 'Async cursor runs unchanged without point projection.')
            return raw
        cursor = _AsyncPointCursorV2(self, raw)
        cursor._mode_supported = type(raw) is AsyncCursor and not args and not any(
            kwargs.get(name) for name in ('name', 'row_factory', 'withhold', 'binary', 'scrollable'))
        self._cursors.add(cursor)
        self._session._cursors.add(cursor)
        return cursor

    async def _checkpoint(self):
        from psycopg.rows import tuple_row

        raw = self._raw
        if raw.autocommit or raw._pipeline or raw._tpc:
            raise ValueError('Writer checkpoint mode unsupported')
        pid = raw.info.backend_pid
        savepoint = '"__mtw_probe_' + uuid.uuid4().hex + '"'
        async with raw.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute('SAVEPOINT ' + savepoint, prepare=False)
            try:
                await cursor.execute(WRITER_PROBE_SQL, prepare=False)
                native = _native(cursor)
                rows = await cursor.fetchall()
            except asyncio.CancelledError:
                try:
                    await self._recover_checkpoint(cursor, savepoint)
                except BaseException:
                    self._session.gap('async_point_checkpoint_cleanup_failed', 'Cleanup after a cancelled writer probe did not complete.')
                raise
            except Exception:
                await self._recover_checkpoint(cursor, savepoint)
                raise
            else:
                await cursor.execute('RELEASE SAVEPOINT ' + savepoint, prepare=False)
        _retain_writer_checkpoint(self, pid, native, rows)

    @staticmethod
    async def _recover_checkpoint(cursor, savepoint):
        await cursor.execute('ROLLBACK TO SAVEPOINT ' + savepoint, prepare=False)
        await cursor.execute('RELEASE SAVEPOINT ' + savepoint, prepare=False)

    async def commit(self):
        async with self._point_lock:
            if _idle_commit_v2(self._raw, self._tx):
                return await self._raw.commit()
            if (self._session._enabled and self._session._automatic_writer_checkpoints
                    and self._tx and int(self._raw.info.transaction_status) == 2):
                try:
                    await self._checkpoint()
                except asyncio.CancelledError:
                    self._session.gap('async_point_commit_cancelled', 'Writer probe did not complete before cancellation.')
                    raise
                except Exception:
                    self._session.gap('point_writer_checkpoint_missing', 'Async writer identity could not be retained.')
                    if int(self._raw.info.transaction_status) != 2:
                        raise
            return await super().commit()

    async def rollback(self):
        async with self._point_lock:
            return await super().rollback()

    async def close(self):
        async with self._point_lock:
            if not self._raw.closed:
                return await super().close()


class _AsyncPointCursorV2(_PointProjectionState, DiagnosticAsyncCursor):
    _replacement_fields = _PointProjectionState._replacement_fields + ('_pending', '_statement', '_complete')

    async def execute(self, query, params=None, **kwargs):
        async with self._connection._point_lock:
            projected = self._build_projection(query, params, kwargs)
            if projected is None:
                with self._replacement():
                    result = await super().execute(query, params, **kwargs)
                self._forget_projection()
                return result
            descriptor, note = self._record_projection(projected)
            with self._replacement():
                await self._execute_projected(projected.sql, projected.parameters, kwargs)
            self._record_native(descriptor, note)
            return self

    async def _execute_projected(self, sql, parameters, kwargs):
        call = _start_call(self, 'execute')
        try:
            self._session.activity('execute')
            if self._pending:
                self._session.gap('orm_result_replaced', 'A new statement replaced an unconsumed async result.')
            self._complete = self._many = False
            fields = {'tx': self._connection._tx, 'sql': sql}
            try:
                fields['parameters'] = self._session.encode(parameters)
            except Exception:
                self._session.gap('orm_parameter_budget', 'Async parameters exceeded the bounded encoder.')
            self._statement = self._session.emit('statement', **fields)
            await self._raw.execute(sql, parameters, **kwargs)
            self._pending = self._raw.description is not None
            if not self._pending:
                self._rows([], True)
        except BaseException as error:
            self._pending = False
            self._session.gap('orm_statement_failed', 'The original async statement did not complete.')
            self._session.note('driver-error', connection=self._connection._identity, statement=self._statement,
                               phase='execute', errorClass=type(error).__name__, sqlstate=getattr(error, 'sqlstate', None))
            _end_call(self, call, False)
            raise
        _end_call(self, call, True)

    async def _fetch(self, method, *args):
        async with self._connection._point_lock:
            if self._projection is None:
                return await super()._fetch(method, *args)
            fetch = getattr(self._raw, method)
            actual_args = args if args and args[0] is not None else ()
            if self._raw.closed:
                return await fetch(*actual_args)
            if self._adapter_delivery and method == 'fetchall':
                # SQLAlchemy drains the native cursor before application fetches.
                # Only the scoped cursor proxy can deliver rows from its buffer.
                business = self._projection['businessResult']
                if business['mode'] == 'no-result':
                    return []
                return await fetch()
            observation = self._fetch_observation(method, args)
            self._session.activity(method)
            try:
                raw = await fetch(*actual_args)
            except BaseException:
                self._session.gap('async_point_fetch_failed', 'The original async result delivery did not complete.')
                raise
            result, rows = self._record_delivery(method, args, raw, *observation)
            self._rows(rows, method == 'fetchall' or (method == 'fetchone' and raw is None) or self._exhausted())
            return result

    async def executemany(self, query, params_seq, **kwargs):
        async with self._connection._point_lock:
            self._session.gap('point_executemany_unmapped', 'Async batch executes unchanged without point projection.')
            with self._replacement():
                result = await super().executemany(query, params_seq, **kwargs)
            self._forget_projection()
            return result

    def nextset(self):
        self._session.gap('point_nextset_unmapped', 'Multiple async results do not grant point coverage.')
        result = self._raw.nextset()
        if result:
            self._forget_projection()
        return result

    async def set_result(self, index):
        async with self._connection._point_lock:
            previous = self._raw.pgresult
            await self._raw.set_result(index)
            if self._raw.pgresult is not previous:
                self._session.gap('point_result_switched', 'Async result switching does not grant point coverage.')
                self._forget_projection()
            return self

    async def results(self):
        if self._raw.pgresult is not None:
            while True:
                yield self
                if not self.nextset():
                    break

    async def scroll(self, value, mode='relative'):
        async with self._connection._point_lock:
            result = await self._raw.scroll(value, mode=mode)
            self._session.gap('point_result_scrolled', 'Scrolled deliveries require independent position verification.')
            return result

    async def close(self):
        async with self._connection._point_lock:
            return await super().close()
