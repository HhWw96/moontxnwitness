"""Source-window observations for owned psycopg async business connections."""

from __future__ import annotations

import asyncio
import inspect
import threading
import uuid

from .configured_effects import WRITER_PROBE_SQL
from .configured_factory_v2 import record_factory_gap_v2
from .configured_point_capture_v2 import (
    PointCaptureV2, _PointProjectionState, _native, _retain_writer_checkpoint, _tuple_factory,
)
from .configured_window_v2 import ConfiguredCaptureWindowV2
from .instrumentation import DiagnosticAsyncConnection, DiagnosticAsyncCursor, _end_call, _start_call


def _owned_async_connection(raw):
    from psycopg import AsyncConnection, __version__

    return (__version__ == '3.3.6' and type(raw) is AsyncConnection
            and not getattr(raw, '_pool', None))


class ConfiguredAsyncCaptureWindowV2(ConfiguredCaptureWindowV2):
    """Synchronous dedicated control snapshots, async business I/O on one loop.

    Construct and seal on the control connection's owner thread. Between those
    calls, use the local factory from a single event loop on that thread.
    """

    def __init__(self, *args, **kwargs):
        self._owner_thread = threading.get_ident()
        self._loop = None
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
        return _AsyncPointCaptureV2(path, config, **options)

    def wrap_connection(self, raw):
        self._require_loop()
        return super().wrap_connection(raw)

    def psycopg_factory(self, factory):
        if not callable(factory):
            raise ValueError('An owned async connection factory is required')

        async def connect(*args, **kwargs):
            self._require_loop()
            if self._state != 'open' or self._pending_factories >= 32:
                raise ValueError('Window is closed or its concurrent acquisition budget is exhausted')
            self._pending_factories += 1
            raw = None
            try:
                pending = factory(*args, **kwargs)
                if not inspect.isawaitable(pending):
                    raise ValueError('Configured async factory must return an awaitable')
                raw = await pending
                return self.wrap_connection(raw)
            except BaseException:
                if not record_factory_gap_v2(self.observer):
                    self._factory_observation_failed = True
                if raw is not None and not any(raw is p._raw for p in self._participants):
                    try:
                        if _owned_async_connection(raw):
                            await raw.close()
                    except BaseException:
                        pass
                raise
            finally:
                self._pending_factories -= 1

        return connect

    def seal(self):
        if threading.get_ident() != self._owner_thread:
            raise ValueError('Seal the configured window on its control connection thread')
        if any(participant._point_lock.locked() for participant in self._participants):
            raise ValueError('Finish all participant operations before sealing')
        return super().seal()


class _AsyncPointCaptureV2(PointCaptureV2):
    _producer_format = 'moontxnwitness-async-point-producer/v2'

    def _wrap(self, raw, *, asynchronous):
        if (not self._enabled or not asynchronous or not _owned_async_connection(raw)
                or raw.autocommit or raw.closed or int(raw.info.transaction_status) != 0
                or raw._pipeline or raw._tpc or not _tuple_factory(raw)):
            raise ValueError('New idle owned psycopg 3.3.6 async tuple connection required')
        return self._enroll_connection(raw, _AsyncPointConnectionV2, asynchronous=True)


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
