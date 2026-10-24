"""Scoped diagnostic instrumentation. No SQL mapping, rewriting or database DDL.

Driver wrappers observe actual result delivery and COMMIT responses. Engine
hooks observe pool ownership only. Unknown SQL never becomes a model fact.
"""
from __future__ import annotations
import asyncio
import functools
import inspect
import time
import uuid
import hashlib
import json
import os
from pathlib import Path
import threading
import weakref
from .capture import _status
from .capture_v3 import CaptureV3Session, CapturedV3Connection, CapturedV3Cursor, _server_abort
from ._orm_raw_async import DraftAsyncConnection, DraftAsyncCursor

PROCESS_MONOTONIC_DOMAIN = "mtw-process-" + uuid.uuid4().hex


class _LifecycleLog:
    """Bounded metadata outside the frozen v3 semantic event vocabulary."""
    def __init__(self, path, *, max_bytes=8*1024*1024, max_records=65536):
        self.max_bytes, self.max_records = max_bytes, max_records
        self.file = Path(path).open('xb')
        self.lock = threading.RLock()
        self.digest, self.count, self.size = hashlib.sha256(), 0, 0
        self.failed = self.closed = False
        self.append({'kind': 'header', 'format': 'moontxnwitness-instrumentation/v1', 'diagnosticOnly': True, 'processMonotonicDomain': PROCESS_MONOTONIC_DOMAIN})

    def append(self, item):
        with self.lock:
            if self.closed or self.failed:
                raise ValueError('Diagnostic lifecycle log is not writable')
            raw = (json.dumps({'seq': self.count + 1, **item}, ensure_ascii=False,
                              allow_nan=False, separators=(',', ':')) + '\n').encode('utf8')
            if len(raw) > 512 * 1024 or self.count >= self.max_records-1 or self.size + len(raw) > self.max_bytes-1024:
                self.failed = True
                raise ValueError('Diagnostic lifecycle budget exhausted')
            try:
                if self.file.write(raw) != len(raw):
                    raise OSError('Short diagnostic lifecycle write')
                self.digest.update(raw); self.size += len(raw); self.count += 1
            except BaseException:
                self.failed = True
                raise

    def close(self):
        with self.lock:
            if not self.closed:
                try:
                    if not self.failed:
                        self.append({'kind': 'seal', 'prefixSha256': self.digest.hexdigest(), 'records': self.count})
                    self.file.flush(); os.fsync(self.file.fileno())
                except BaseException:
                    self.failed = True
                    raise
                finally:
                    self.closed = True; self.file.close()
            return {'sealed': not self.failed, 'records': self.count, 'bytes': self.size,
                    'sha256': self.digest.hexdigest()}


class Instrumentation(CaptureV3Session):
    """One new bounded diagnostic directory; close after stopping workers.

    Native and SQLAlchemy connections are not closed by the observer. Export
    remains diagnostic-only, even when every recorded byte is integrity-valid.
    """
    def __init__(self, path, *, journal_options=None, max_connections=128, max_cursors=512,
                 max_value_bytes=256 * 1024, max_value_nodes=16384,
                 max_lifecycle_bytes=8*1024*1024, max_lifecycle_records=65536):
        if type(max_lifecycle_bytes) is not int or not 4096 <= max_lifecycle_bytes <= 1024**3 or type(max_lifecycle_records) is not int or not 128 <= max_lifecycle_records <= 2000000:
            raise ValueError("Lifecycle raw storage budgets exceed supported bounds")
        self.output = Path(path).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self._enabled, self._listeners, self._borrowed = True, [], set()
        self._call_events = {}
        self._active_call_depths = {}
        self._last_exported_trace = None
        super().__init__(self.output / 'journal', journal_options=journal_options,
                         max_connections=max_connections, max_cursors=max_cursors,
                         max_value_bytes=max_value_bytes, max_value_nodes=max_value_nodes)
        self.lifecycle = _LifecycleLog(self.output / 'lifecycle.jsonl', max_bytes=max_lifecycle_bytes, max_records=max_lifecycle_records)
        self.publish_snapshot({}, consistent=False)
        self.gap('diagnostic_instrumentation_only', 'No verified initial/version/predicate mapping; raw observations never grant complete analysis coverage.')

    def note(self, kind, **fields):
        if not self._enabled:
            return
        try:
            self.lifecycle.append({'kind': kind, 'processMonotonicDomain': PROCESS_MONOTONIC_DOMAIN,
                                   'monotonicNs': str(time.monotonic_ns()), **self.encode(fields)})
        except Exception:
            self.gap('instrumentation_metadata_missing', 'Diagnostic lifecycle or batch metadata could not be retained.')

    def emit(self, kind, **fields):
        seq = super().emit(kind, **fields)
        tx = fields.get('tx')
        if tx and seq is not None and kind in ('begin', 'commit_request', 'commit_ok', 'rollback_ok', 'disconnect'):
            with self._lock:
                if tx in self._call_events or len(self._call_events) < 512:
                    self._call_events.setdefault(tx, {})[kind] = seq
                    if kind in ('commit_ok', 'rollback_ok', 'disconnect') and not self._active_call_depths.get(tx):
                        self._call_events.pop(tx, None)
                else:
                    self.gap('call_reference_budget', 'Client-call journal references exceeded the bounded registry.')
        return seq

    def export_diagnostic(self, destination, **options):
        receipt = super().export_diagnostic(destination, **options)
        self._last_exported_trace = (Path(destination).resolve(), receipt['sha256'])
        return receipt

    def export_call_intervals(self, trace_path, destination):
        """Bind original diagnostic records; does not accept a model or authenticate a collector."""
        from .journal_v3 import JournalReader
        trace_path, destination = Path(trace_path).resolve(), Path(destination).resolve()
        if not self._closed or self._last_exported_trace is None or trace_path != self._last_exported_trace[0]:
            raise ValueError('First close and export this observer trace unchanged')
        with trace_path.open('rb') as file:
            trace = file.read(8 * 1024 * 1024 + 1)
        if len(trace) > 8 * 1024 * 1024 or hashlib.sha256(trace).hexdigest() != self._last_exported_trace[1]:
            raise ValueError('Original exported trace changed')
        status = JournalReader(self.journal.path).verify()
        if not status.valid: raise ValueError('Original journal is invalid')
        meta = json.loads((self.output / 'instrumentation.json').read_text(encoding='utf8'))
        with (self.output / 'lifecycle.jsonl').open('rb') as file:
            lifecycle = file.read(8 * 1024 * 1024 + 1)
        if len(lifecycle) > 8 * 1024 * 1024 or not meta['lifecycle'].get('sealed'):
            raise ValueError('Original lifecycle evidence was not sealed')
        if hashlib.sha256(lifecycle).hexdigest() != meta['lifecycle']['sha256']:
            raise ValueError('Original lifecycle digest changed')
        records = [json.loads(line) for line in lifecycle.splitlines()]
        if not records or any(record.get('seq') != i for i, record in enumerate(records, 1)):
            raise ValueError('Original lifecycle sequence is incomplete')
        lines = lifecycle.splitlines(keepends=True)
        seal = records[-1]
        if seal.get('kind') != 'seal' or seal.get('records') != len(records) - 1 or seal.get('prefixSha256') != hashlib.sha256(b''.join(lines[:-1])).hexdigest():
            raise ValueError('Original lifecycle seal is invalid')
        index = (self.journal.path / 'journal-index.json').read_bytes()
        result = {'format': 'moontxnwitness-client-intervals/v1',
                  'sourceTraceSha256': hashlib.sha256(trace).hexdigest(),
                  'sourceLifecycleSha256': hashlib.sha256(lifecycle).hexdigest(),
                  'sourceJournalIndexSha256': hashlib.sha256(index).hexdigest(),
                  'records': records}
        with destination.open('xb') as file:
            raw = (json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf8')
            file.write(raw); file.flush(); os.fsync(file.fileno())
        return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'actualDatabaseExecution': False, 'modelAccepted': False}

    def wrap(self, raw, *, role=None):
        return self._wrap(raw, asynchronous=False)

    def wrap_async(self, raw):
        return self._wrap(raw, asynchronous=True)

    def _wrap(self, raw, *, asynchronous):
        if not self._enabled:
            return raw
        with self._lock:
            if isinstance(raw, (DiagnosticConnection, DiagnosticAsyncConnection)):
                if raw._session is not self:
                    self.gap('foreign_observer', 'Connection already belongs to another observer.')
                return raw
            if len(self._connections) >= self._max_connections:
                self.gap('connection_budget', 'Connection runs without diagnostic observation.')
                return raw
            cls = DiagnosticAsyncConnection if asynchronous else DiagnosticConnection
            wrapped = cls(self, raw)
            self._connections.add(wrapped)
            self.note('connect', connection=wrapped._identity, asynchronous=asynchronous)
            return wrapped

    def psycopg_factory(self, factory, *, asynchronous=False):
        if not callable(factory) or type(asynchronous) is not bool:
            raise ValueError('A local callable and asynchronous boolean are required')
        if asynchronous:
            async def connect(*args, **kwargs):
                raw = await factory(*args, **kwargs)
                try: return self.wrap_async(raw)
                except Exception:
                    self.gap('factory_connection_unobserved', 'Original async connection returned unobserved.')
                    return raw
        else:
            def connect(*args, **kwargs):
                raw = factory(*args, **kwargs)
                try: return self.wrap(raw)
                except Exception:
                    self.gap('factory_connection_unobserved', 'Original connection returned unobserved.')
                    return raw
        return connect

    def attach_engine(self, engine):
        import sqlalchemy
        from sqlalchemy import event
        target = getattr(engine, 'sync_engine', engine)
        dialect = getattr(target, 'dialect', None)
        if sqlalchemy.__version__ != '2.0.55':
            raise ValueError('Engine instrumentation requires SQLAlchemy 2.0.55')
        if getattr(dialect, 'name', None) != 'postgresql' or getattr(dialect, 'driver', None) != 'psycopg':
            raise ValueError('Engine instrumentation requires PostgreSQL/psycopg')
        if not self._enabled or self._listeners:
            raise ValueError('Attach one engine once while observation is open')

        def connection(dbapi, record):
            try:
                if getattr(dialect, 'is_async', False):
                    observed = self.wrap_async(dbapi.driver_connection)
                    if not isinstance(observed, DiagnosticAsyncConnection): return
                    dbapi._connection = observed
                    wrapped = _AdapterConnection(dbapi, observed)
                else: wrapped = self.wrap(dbapi)
                record.dbapi_connection = wrapped
                self.note('pool-connect', connection=_identity(wrapped))
            except Exception:
                self.gap('engine_connection_unobserved', 'Original pooled connection could not be instrumented.')

        def checkout(dbapi, record, proxy):
            key = _identity(dbapi)
            if key is None:
                self.gap('late_engine_attachment', 'An existing pooled connection was not created through this observer.')
                key = 'unobserved'
            with self._lock:
                if len(self._borrowed) < self._max_connections: self._borrowed.add(key)
                else: self.gap('pool_registry_budget', 'Pool ownership registry budget exhausted.')
            self.note('pool-checkout', connection=key)

        def checkin(dbapi, record):
            key = _identity(dbapi)
            if key is not None: self._borrowed.discard(key)
            self.note('pool-checkin', connection=key)

        def reset(dbapi, record, state):
            self.note('pool-reset', connection=_identity(dbapi),
                      transactionWasReset=state.transaction_was_reset,
                      terminateOnly=state.terminate_only, asyncioSafe=state.asyncio_safe)

        def invalidate(dbapi, record, exception):
            observed = _observed(dbapi)
            if observed is not None:
                observed._unknown('pool_connection_invalidated')
                self._borrowed.discard(observed._identity)
            self.note('pool-invalidate', connection=_identity(dbapi),
                      errorClass=type(exception).__name__ if exception is not None else None)

        def soft_invalidate(dbapi, record, exception):
            self.note('pool-soft-invalidate', connection=_identity(dbapi),
                      errorClass=type(exception).__name__ if exception is not None else None)

        def pool_close(dbapi, record):
            self.note('pool-close', connection=_identity(dbapi))

        callbacks = [('connect', connection), ('checkout', checkout), ('checkin', checkin),
                     ('reset', reset), ('invalidate', invalidate), ('soft_invalidate', soft_invalidate), ('close', pool_close)]
        try:
            for name, callback in callbacks:
                event.listen(target, name, callback)
                self._listeners.append((target, name, callback))
        except BaseException:
            self.detach()
            raise
        self.note('engine-attached', asynchronous=bool(getattr(dialect, 'is_async', False)))
        return self

    def detach(self):
        with self._lock:
            if not self._enabled: return
            if self._listeners:
                from sqlalchemy import event
            if self._borrowed:
                self.gap('engine_detached_with_borrowed_connections', 'Later borrowed-connection work is outside this diagnostic window.')
            self.note('instrumentation-detached', borrowedConnections=len(self._borrowed))
            for target, name, callback in reversed(self._listeners):
                event.remove(target, name, callback)
            self._listeners.clear()
            self._enabled = False

    def close(self, *, source_closed=False):
        if not self._closed:
            if self._listeners: self.detach()
            else:
                self.note('instrumentation-detached', borrowedConnections=0)
                self._enabled = False
            try:
                metadata = self.lifecycle.close()
                if not metadata['sealed']:
                    self.gap('instrumentation_metadata_unsealed', 'Metadata did not seal completely.')
            except Exception:
                self.gap('instrumentation_metadata_unsealed', 'Metadata could not be synchronized.')
                metadata = {'sealed': False}
            result = super().close(source_closed=False)
            receipt = {'schema': 1, 'format': 'moontxnwitness-instrumentation/v1',
                       'diagnosticOnly': True, 'completeAnalysisCoverage': False,
                       'actualDatabaseExecution': False, 'lifecycle': metadata, 'journal': result.as_dict()}
            with (self.output / 'instrumentation.json').open('x', encoding='utf8') as file:
                json.dump(receipt, file, ensure_ascii=False, indent=2)
                file.write('\n'); file.flush(); os.fsync(file.fileno())
            return result
        return super().close(source_closed=False)

    def export(self, *args, **kwargs):
        raise ValueError('Diagnostic instrumentation cannot export complete history; use export_diagnostic')


def instrument_engine(engine, path, **options):
    """Attach to one unused engine; no global monkeypatch, SQL rewrite or DDL."""
    observer = Instrumentation(path, **options)
    try: return observer.attach_engine(engine)
    except BaseException:
        observer.close()
        raise


def instrument_psycopg(factory, path, *, asynchronous=False, **options):
    """Return (observer, local_connect); never replace the global driver."""
    observer = Instrumentation(path, **options)
    return observer, observer.psycopg_factory(factory, asynchronous=asynchronous)


def _observed(value):
    if isinstance(value, _AdapterConnection): return value._observed
    return value if isinstance(value, (DiagnosticConnection, DiagnosticAsyncConnection)) else None


def _identity(value):
    observed = _observed(value)
    return observed._identity if observed is not None else None


def _error(cursor, phase, error):
    cursor._session.note('driver-error', connection=cursor._connection._identity,
                         statement=cursor._statement, phase=phase,
                         errorClass=type(error).__name__, sqlstate=getattr(error, 'sqlstate', None))
    completed = getattr(cursor, '_result_complete', getattr(cursor, '_complete', False))
    if cursor._statement is not None and not completed:
        cursor._session.emit('rows', tx=cursor._connection._tx, statement=cursor._statement,
                             rows=[], complete=False,
                             error={'class': type(error).__name__, 'sqlstate': getattr(error, 'sqlstate', None)})
    cursor._pending = False


class _Parameters:
    def __init__(self, cursor, values):
        self.cursor, self.values, self.count = cursor, iter(values), 0
    def __iter__(self): return self
    def __next__(self):
        value = next(self.values)
        self.count += 1
        self.cursor._session.note('executemany-parameters',
            connection=self.cursor._connection._identity, statement=self.cursor._statement,
            ordinal=self.count, parameters=value)
        return value


def _start_call(value, method):
    observer = value._session
    if not observer._enabled: return None
    started = str(time.monotonic_ns())
    connection = getattr(value, '_connection', value)
    if method in ('execute', 'executemany'):
        connection._begin()
    tx = connection._tx
    if tx:
        with observer._lock:
            if tx in observer._active_call_depths or len(observer._active_call_depths) < 512:
                observer._active_call_depths[tx] = observer._active_call_depths.get(tx, 0) + 1
            else:
                observer.gap('call_reference_budget', 'Client-call references exceeded the bounded active-call registry.')
    if method == 'commit': connection._last_native_command_tag = None
    call = {'callId': 'call-' + uuid.uuid4().hex, 'method': method,
            'connection': connection._identity, 'tx': tx}
    observer.note('call-start', **call, monotonicNs=started,
                  statementSeq=None, journalEventSeqs=dict(observer._call_events.get(tx, {})))
    return call


def _end_call(value, call, succeeded):
    if call is None: return
    observer = value._session
    connection = getattr(value, '_connection', value)
    with observer._lock:
        refs = dict(observer._call_events.get(call['tx'], {}))
    fields = {'succeeded': succeeded, 'statementSeq': getattr(value, '_statement', None),
              'journalEventSeqs': refs}
    if call['method'] == 'commit':
        fields['nativeCommandTag'] = getattr(connection, '_last_native_command_tag', None)
    observer.note('call-end', **call, **fields)
    with observer._lock:
        tx = call['tx']
        depth = observer._active_call_depths.get(tx, 0)
        if depth <= 1:
            observer._active_call_depths.pop(tx, None)
            if call['method'] in ('commit', 'rollback') or any(kind in refs for kind in ('commit_ok', 'rollback_ok', 'disconnect')):
                observer._call_events.pop(tx, None)
        else:
            observer._active_call_depths[tx] = depth - 1


def _diagnostic_call(function):
    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def wrapped(self, *args, **kwargs):
            call = _start_call(self, function.__name__)
            try: result = await function(self, *args, **kwargs)
            except BaseException:
                _end_call(self, call, False)
                raise
            _end_call(self, call, True)
            return result
    else:
        @functools.wraps(function)
        def wrapped(self, *args, **kwargs):
            call = _start_call(self, function.__name__)
            try: result = function(self, *args, **kwargs)
            except BaseException:
                _end_call(self, call, False)
                raise
            _end_call(self, call, True)
            return result
    return wrapped


class DiagnosticConnection(CapturedV3Connection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if not self._session._enabled: return raw
        if len(self._session._cursors) >= self._session._max_cursors:
            self._session.gap('cursor_budget', 'Cursor runs without diagnostic observation.')
            return raw
        cursor = DiagnosticCursor(self, raw)
        self._cursors.add(cursor); self._session._cursors.add(cursor)
        if args or kwargs.get('name') or kwargs.get('row_factory') or kwargs.get('withhold'):
            self._session.gap('cursor_mode_unsupported', 'Non-default cursor mode is partially observed.')
        return cursor

    @_diagnostic_call
    def commit(self):
        if not self._session._enabled: return self._raw.commit()
        with self._operation_lock:
            self._incomplete()
            request = self._session.emit('commit_request', tx=self._tx) if self._tx else None
            self._commit_requested = request is not None
            try:
                with self._commit_response_hook() as response:
                    result = self._raw.commit()
            except BaseException as error:
                self._session.note('commit-error', connection=self._identity,
                                   errorClass=type(error).__name__, sqlstate=getattr(error, 'sqlstate', None))
                if self._tx and request is not None and _server_abort(self._raw, error):
                    self._session.emit('rollback_ok', tx=self._tx, commitResponse={'request': request,
                        'sqlstate': error.sqlstate, 'diagnosticSqlstate': error.diag.sqlstate, 'transactionStatus': 'IDLE'})
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                else: self._unknown('commit_unknown')
                raise
            _finish_commit(self, request, response)
            return result

    @_diagnostic_call
    def rollback(self):
        if not self._session._enabled: return self._raw.rollback()
        return super().rollback()

    def close(self):
        if not self._session._enabled: return self._raw.close()
        self._session.note('connection-close', connection=self._identity)
        return super().close()


class DiagnosticCursor(CapturedV3Cursor):
    def __init__(self, connection, raw):
        super().__init__(connection, raw)
        self._many = False

    @_diagnostic_call
    def execute(self, query, params=None, **kwargs):
        if not self._session._enabled:
            result = self._raw.execute(query, params, **kwargs)
            return self if result is self._raw else result
        self._many = False
        try: return super().execute(query, params, **kwargs)
        except BaseException as error:
            self._session.note('driver-error', connection=self._connection._identity,
                               statement=self._statement, phase='execute', errorClass=type(error).__name__,
                               sqlstate=getattr(error, 'sqlstate', None))
            raise

    @_diagnostic_call
    def executemany(self, query, params_seq, **kwargs):
        if not self._session._enabled: return self._raw.executemany(query, params_seq, **kwargs)
        with self._connection._operation_lock:
            if self._pending: self._session.gap('result_replaced', 'Batch replaced an undelivered result.')
            self._connection._begin()
            self._mapping = None; self._result_complete = False; self._many = True
            try: sql = self._sql(query)
            except Exception:
                sql = '<unavailable>'; self._session.gap('sql_encoding_failed', 'Original batch SQL could not be retained.')
            self._statement = self._session.emit('statement', tx=self._connection._tx, sql=sql)
            self._session.note('executemany-begin', connection=self._connection._identity, statement=self._statement)
            parameters = _Parameters(self, params_seq)
            try: result = self._raw.executemany(query, parameters, **kwargs)
            except BaseException as error:
                _error(self, 'executemany', error)
                self._session.note('executemany-end', statement=self._statement,
                                   consumedParameters=parameters.count, successful=False)
                raise
            self._pending = self._raw.description is not None
            if not self._pending:
                self._many = False; self._rows([], True)
            self._session.note('executemany-end', statement=self._statement,
                               consumedParameters=parameters.count, successful=True)
            return self if result is self._raw else result

    def _rows(self, rows, exhausted):
        if self._many:
            self._session.note('executemany-result', statement=self._statement, rows=rows, resultSetExhausted=exhausted)
            exhausted = False
        return super()._rows(rows, exhausted)

    def _fetch(self, method, *args):
        if not self._session._enabled: return getattr(self._raw, method)(*args)
        try: return getattr(super(), method)(*args)
        except BaseException as error:
            _error(self, method, error)
            raise

    def fetchone(self): return self._fetch('fetchone')
    def fetchmany(self, size=None): return self._fetch('fetchmany', size)
    def fetchall(self): return self._fetch('fetchall')

    def nextset(self):
        result = self._raw.nextset()
        if self._session._enabled and self._many:
            self._session.note('executemany-nextset', statement=self._statement, hasNext=bool(result))
            if not result:
                self._many = False; self._rows([], True)
        elif self._session._enabled:
            self._session.gap('nextset_unmapped', 'Non-batch multiple results are outside raw v3 mapping.')
        return result

    def close(self):
        if not self._session._enabled: return self._raw.close()
        return super().close()


def _finish_commit(connection, request, response):
    if not connection._tx: return
    observer = connection._session
    tag = response.get('commandTag')
    connection._last_native_command_tag = tag
    observer.note('commit-response', connection=connection._identity, request=request,
                  commandTag=tag, transactionStatus=_status(connection._raw))
    if request is not None and _status(connection._raw) == 0 and tag == 'ROLLBACK':
        observer.emit('rollback_ok', tx=connection._tx, commitResponse={'request': request, 'commandTag': 'ROLLBACK'})
    elif request is not None and _status(connection._raw) == 0 and tag == 'COMMIT':
        observer.emit('commit_ok', tx=connection._tx)
    else: connection._unknown('commit_ack_not_confirmed')
    connection._tx, connection._savepoints, connection._commit_requested = None, [], False


class DiagnosticAsyncConnection(DraftAsyncConnection):
    def __init__(self, session, raw):
        super().__init__(session, raw)
        self._cursors = weakref.WeakSet()

    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if not self._session._enabled: return raw
        if len(self._session._cursors) >= self._session._max_cursors:
            self._session.gap('cursor_budget', 'Async cursor runs without diagnostic observation.')
            return raw
        cursor = DiagnosticAsyncCursor(self, raw)
        self._cursors.add(cursor); self._session._cursors.add(cursor)
        if args or kwargs.get('name') or kwargs.get('row_factory') or kwargs.get('withhold'):
            self._session.gap('cursor_mode_unsupported', 'Non-default async cursor mode is partially observed.')
        return cursor

    @_diagnostic_call
    async def commit(self):
        if not self._session._enabled: return await self._raw.commit()
        async with self._lock:
            self._unread()
            request = self._session.emit('commit_request', tx=self._tx) if self._tx else None
            self._commit_requested = request is not None
            try:
                with self._response() as response:
                    result = await self._raw.commit()
            except BaseException as error:
                self._session.note('commit-error', connection=self._identity,
                                   errorClass=type(error).__name__, sqlstate=getattr(error, 'sqlstate', None))
                if self._tx and request is not None and _server_abort(self._raw, error):
                    self._session.emit('rollback_ok', tx=self._tx, commitResponse={'request': request,
                        'sqlstate': error.sqlstate, 'diagnosticSqlstate': error.diag.sqlstate, 'transactionStatus': 'IDLE'})
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                else: self._unknown('commit_unknown')
                raise
            _finish_commit(self, request, response)
            return result

    @_diagnostic_call
    async def rollback(self):
        if not self._session._enabled: return await self._raw.rollback()
        return await super().rollback()

    async def close(self):
        if not self._session._enabled: return await self._raw.close()
        self._session.note('connection-close', connection=self._identity)
        return await super().close()

    async def __aenter__(self):
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, kind, value, traceback):
        if self._raw.closed: return False
        if kind is None: await self.commit()
        else:
            try: await self.rollback()
            except Exception: pass
        if not getattr(self._raw, '_pool', None): await self.close()
        return False


class DiagnosticAsyncCursor(DraftAsyncCursor):
    def __init__(self, connection, raw):
        super().__init__(connection, raw)
        self._many = self._adapter_delivery = False

    def _rows(self, rows, complete):
        if self._adapter_delivery and self._raw.description is not None:
            return  # SQLAlchemy prefetch is not DBAPI-consumer delivery.
        if self._many:
            self._session.note('executemany-result', statement=self._statement, rows=rows, resultSetExhausted=complete)
            complete = False
        return super()._rows(rows, complete)

    def delivered(self, rows, complete):
        flag = self._adapter_delivery
        self._adapter_delivery = False
        try: return self._rows(rows, complete)
        finally: self._adapter_delivery = flag

    @_diagnostic_call
    async def execute(self, query, params=None, **kwargs):
        if not self._session._enabled:
            result = await self._raw.execute(query, params, **kwargs)
            return self if result is self._raw else result
        self._many = False
        try: return await super().execute(query, params, **kwargs)
        except BaseException as error:
            self._session.note('driver-error', connection=self._connection._identity,
                               statement=self._statement, phase='execute', errorClass=type(error).__name__,
                               sqlstate=getattr(error, 'sqlstate', None))
            raise

    @_diagnostic_call
    async def executemany(self, query, params_seq, **kwargs):
        if not self._session._enabled: return await self._raw.executemany(query, params_seq, **kwargs)
        async with self._connection._lock:
            if self._pending: self._session.gap('result_replaced', 'Batch replaced an undelivered async result.')
            self._connection._begin()
            self._complete = False; self._many = True
            try: sql = query if isinstance(query, str) else query.as_string(self._connection._raw)
            except Exception:
                sql = '<unavailable>'; self._session.gap('sql_encoding_failed', 'Original async batch SQL could not be retained.')
            self._statement = self._session.emit('statement', tx=self._connection._tx, sql=sql)
            self._session.note('executemany-begin', connection=self._connection._identity, statement=self._statement)
            parameters = _Parameters(self, params_seq)
            try: result = await self._raw.executemany(query, parameters, **kwargs)
            except BaseException as error:
                _error(self, 'executemany', error)
                self._session.note('executemany-end', statement=self._statement, consumedParameters=parameters.count, successful=False)
                raise
            self._pending = self._raw.description is not None
            if not self._pending:
                self._many = False; self._rows([], True)
            self._session.note('executemany-end', statement=self._statement, consumedParameters=parameters.count, successful=True)
            return self if result is self._raw else result

    async def _fetch(self, method, *args):
        if not self._session._enabled: return await getattr(self._raw, method)(*args)
        try: return await getattr(super(), method)(*args)
        except BaseException as error:
            _error(self, method, error)
            raise

    async def fetchone(self): return await self._fetch('fetchone')
    async def fetchmany(self, size=None): return await self._fetch('fetchmany', size)
    async def fetchall(self): return await self._fetch('fetchall')

    def nextset(self):
        result = self._raw.nextset()
        if self._session._enabled and self._many:
            self._session.note('executemany-nextset', statement=self._statement, hasNext=bool(result))
            if not result:
                self._many = False; self.delivered([], True)
        elif self._session._enabled:
            self._session.gap('nextset_unmapped', 'Multiple non-batch async results are partially observed.')
        return result

    async def close(self):
        if not self._session._enabled: return await self._raw.close()
        return await super().close()

    def _close(self):
        if not self._session._enabled: return self._raw._close()
        return super()._close()

    async def __aenter__(self):
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.close()
        return False

    def __aiter__(self): return self
    async def __anext__(self):
        row = await self.fetchone()
        if row is None: raise StopAsyncIteration
        return row


class _AdapterConnection:
    """Keep the native SQLAlchemy async adapter and observe its result boundary."""
    def __init__(self, raw, observed):
        object.__setattr__(self, '_raw', raw)
        object.__setattr__(self, '_observed', observed)
    def cursor(self, *args, **kwargs):
        cursor = self._raw.cursor(*args, **kwargs)
        observed = getattr(cursor, '_cursor', None)
        if not isinstance(observed, DiagnosticAsyncCursor):
            self._observed._session.gap('adapter_cursor_unobserved', 'Unknown SQLAlchemy async cursor adapter.')
            return cursor
        observed._adapter_delivery = True
        return _AdapterCursor(cursor, observed)
    def execute(self, query, params=None, **kwargs):
        cursor = self.cursor()
        cursor.execute(query, params, **kwargs)
        return cursor
    def __getattr__(self, name): return getattr(self._raw, name)
    def __setattr__(self, name, value):
        if name.startswith('_'): object.__setattr__(self, name, value)
        else: setattr(self._raw, name, value)


class _AdapterCursor:
    def __init__(self, raw, observed):
        object.__setattr__(self, '_raw', raw)
        object.__setattr__(self, '_observed', observed)
    def execute(self, *args, **kwargs):
        result = self._raw.execute(*args, **kwargs)
        return self if result is self._raw else result
    def executemany(self, *args, **kwargs): return self._raw.executemany(*args, **kwargs)
    def _fetch(self, method, *args):
        result = getattr(self._raw, method)(*args)
        if self._observed._session._enabled:
            rows = ([] if result is None else [result]) if method == 'fetchone' else result
            remaining = getattr(self._raw, '_rows', None)
            complete = not remaining if remaining is not None else not rows
            self._observed.delivered(rows, complete)
        return result
    def fetchone(self): return self._fetch('fetchone')
    def fetchmany(self, size=None): return self._fetch('fetchmany', size)
    def fetchall(self): return self._fetch('fetchall')
    def __iter__(self): return self
    def __next__(self):
        row = self.fetchone()
        if row is None: raise StopIteration
        return row
    def __getattr__(self, name): return getattr(self._raw, name)
    def __setattr__(self, name, value):
        if name.startswith('_'): object.__setattr__(self, name, value)
        else: setattr(self._raw, name, value)
