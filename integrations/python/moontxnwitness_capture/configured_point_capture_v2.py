"""Opt-in, connection-local synchronous PostgreSQL point-CRUD projection.

Original inputs, generated SQL, native buffers and business deliveries remain
separate. This producer grants no source closure or model facts. Install and
verify the configured version column separately before enabling projection.
"""
from __future__ import annotations

import base64
import hashlib
import json
import weakref
import uuid
from contextlib import contextmanager
from .capture_v3 import _pinned_connection
from .instrumentation import Instrumentation, DiagnosticConnection, DiagnosticCursor
from .configured_fetch import ConfiguredInstrumentation
from .configured_sql_v2 import SQLCaptureConfigV2, ConfiguredSQLParserV2
from .configured_point_projection_v2 import PointProjectionOptionsV2, build_point_projection
from .configured_factory_v2 import (require_sync_factory_v2, require_sync_result_v2,
    close_rejected_sync_result_v2, record_factory_gap_v2)


def _typed(value):
    kind = type(value).__module__ + '.' + type(value).__qualname__
    if type(value) is int:
        return {'pythonType': kind, 'value': str(value)}
    if type(value) in (str, bool) or value is None:
        return {'pythonType': kind, 'value': value}
    if type(value) is uuid.UUID:
        return {'pythonType': kind, 'value': str(value)}
    raise ValueError('Only default PostgreSQL scalar decoders are observed')


def _tuple_factory(raw):
    factory = raw.row_factory
    return (getattr(factory, '__module__', None), getattr(factory, '__name__', None)) == ('psycopg.rows', 'tuple_row')


def _native(cursor):
    """Inspect the completed libpq buffer without consuming application rows."""
    result = cursor.pgresult
    if result is None:
        raise ValueError('Native result is absent')
    columns, rows = int(result.nfields), int(result.ntuples)
    if not 0 <= columns <= 53 or not 0 <= rows <= 1:
        raise ValueError('Point observation dimensions exceeded')
    b64 = lambda value: None if value is None else base64.b64encode(value).decode('ascii')
    fields = [{'nameBase64': b64(result.fname(i)), 'oid': result.ftype(i),
               'format': result.fformat(i), 'typmod': result.fmod(i),
               'tableOid': result.ftable(i), 'tableColumn': result.ftablecol(i)} for i in range(columns)]
    cells, total = [], 0
    for row in range(rows):
        observed = []
        for column in range(columns):
            value = result.get_value(row, column)
            if value is not None and type(value) is not bytes:
                raise ValueError('Native cells must be original bytes')
            total += len(value) if value is not None else 0
            if total > 32 * 1024:
                raise ValueError('Native observation byte budget exceeded')
            observed.append(b64(value))
        cells.append(observed)
    return {'format': 'moontxnwitness-projected-native-result/v2', 'status': int(result.status),
            'clientEncodingBase64': b64(cursor.connection.pgconn.parameter_status(b'client_encoding')),
            'commandStatusBase64': b64(result.command_status), 'commandTuples': _typed(result.command_tuples),
            'fields': fields, 'rows': cells, 'backendPid': cursor.connection.info.backend_pid,
            'transactionStatus': int(cursor.connection.info.transaction_status)}


class PointCaptureV2(Instrumentation):
    """Opt-in producer; synchronous default tuple cursors on pinned psycopg.

    No connection is opened, database schema changed or business row fetched at
    construction. Call close only after stopping/closing enrolled connections.
    """
    frame = ConfiguredInstrumentation.frame

    def __init__(self, path, config, *, projection_options=None, opt_in=False,
                 automatic_writer_checkpoints=True, **options):
        if opt_in is not True or type(config) is not SQLCaptureConfigV2:
            raise ValueError('Explicit projection opt-in and immutable V2 config required')
        if type(automatic_writer_checkpoints) is not bool:
            raise ValueError('Checkpoint option must be boolean')
        if projection_options is None:
            projection_options = PointProjectionOptionsV2(config)
        if (type(projection_options) is not PointProjectionOptionsV2
                or projection_options.config.to_dict() != config.to_dict()):
            raise ValueError('Independent projection options must match config')
        self.config, self.options = config, projection_options
        self.parser = ConfiguredSQLParserV2(config)
        self._registry = {}
        self._automatic_writer_checkpoints = automatic_writer_checkpoints
        super().__init__(path, **options)
        self.frame('configured-point-producer', {
            'format': 'moontxnwitness-point-producer/v2', 'config': config.to_dict(),
            'projectionOptions': projection_options.to_dict(),
            'sourceFactsProduced': False, 'completeWindow': False, 'modelCoverageAccepted': False})
        self.gap('point_source_window_unverified', 'Projection observations require independent installation, writer and window verification.')

    def _wrap(self, raw, *, asynchronous):
        if not self._enabled:
            return raw
        if isinstance(raw, PointConnectionV2):
            if raw._session is not self:
                raise ValueError('Connection already enrolled with a different producer')
            return raw
        with self._lock:
            entry = self._registry.get(id(raw))
            if entry is not None and entry[0]() is raw:
                existing = entry[1]()
                if existing is not None:
                    return existing
        if (asynchronous or not _pinned_connection(raw) or raw.autocommit
                or raw.closed or int(raw.info.transaction_status) != 0
                or raw._pipeline or raw._tpc or not _tuple_factory(raw)):
            raise ValueError('New idle synchronous psycopg 3.3.6 tuple connection required')
        with self._lock:
            key = id(raw)
            entry = self._registry.get(key)
            if entry is not None and entry[0]() is raw:
                existing = entry[1]()
                if existing is not None:
                    return existing
            if len(self._connections) >= self._max_connections:
                raise ValueError('Connection observation budget exceeded')
            connection = PointConnectionV2(self, raw)
            def remove(reference):
                with self._lock:
                    current = self._registry.get(key)
                    if current and any(item is reference for item in current):
                        self._registry.pop(key, None)
            self._registry[key] = weakref.ref(raw, remove), weakref.ref(connection, remove)
            self._connections.add(connection)
            self.note('connect', connection=connection._identity, asynchronous=False)
            return connection

    def attach_engine(self, engine):
        raise ValueError('V2 point projection currently requires a synchronous local connection factory')

    def psycopg_factory(self, factory, *, asynchronous=False):
        require_sync_factory_v2(factory, asynchronous=asynchronous)
        def connect(*args, **kwargs):
            raw = None
            try:
                raw = factory(*args, **kwargs)
                require_sync_result_v2(raw)
                return self.wrap(raw)
            except BaseException:
                # A foreign diagnostic wrapper is not a new owned connection.
                protected = (raw,) if isinstance(raw, DiagnosticConnection) else ()
                close_rejected_sync_result_v2(raw, protected=protected)
                record_factory_gap_v2(self)
                raise
        return connect


class PointConnectionV2(DiagnosticConnection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if not self._session._enabled:
            return raw
        if len(self._session._cursors) >= self._session._max_cursors:
            self._session.gap('cursor_budget', 'Cursor runs unchanged without projection.')
            return raw
        cursor = PointCursorV2(self, raw)
        cursor._mode_supported = not args and not any(kwargs.get(name) for name in (
            'name', 'row_factory', 'withhold', 'binary', 'scrollable'))
        self._cursors.add(cursor)
        self._session._cursors.add(cursor)
        return cursor

    def commit(self):
        with self._operation_lock:
            if (self._session._enabled and self._session._automatic_writer_checkpoints
                    and self._tx and int(self._raw.info.transaction_status) == 2):
                try:
                    self._checkpoint()
                except Exception:
                    self._session.gap('point_writer_checkpoint_missing', 'COMMIT is still observed; writer identity is incomplete.')
                    if int(self._raw.info.transaction_status) != 2:
                        # SAVEPOINT creation/recovery or the connection itself
                        # failed. Do not silently acknowledge an aborted commit.
                        raise
            return super().commit()

    def _checkpoint(self):
        from .configured_effects import WRITER_PROBE_SQL
        from psycopg.rows import tuple_row
        raw = self._raw
        if not _pinned_connection(raw) or raw.autocommit or raw._pipeline or raw._tpc:
            raise ValueError('Writer checkpoint mode unsupported')
        pid = raw.info.backend_pid
        savepoint = '__mtw_probe_' + uuid.uuid4().hex
        with raw.cursor(row_factory=tuple_row) as cursor:
            cursor.execute('SAVEPOINT "' + savepoint + '"', prepare=False)
            try:
                cursor.execute(WRITER_PROBE_SQL, prepare=False)
                native = _native(cursor)
                rows = cursor.fetchall()  # Only the explicitly owned checkpoint, never business SQL.
            except BaseException:
                # A failed observer query must not turn a later COMMIT into a
                # successful-looking ROLLBACK of the application's writes.
                cursor.execute('ROLLBACK TO SAVEPOINT "' + savepoint + '"', prepare=False)
                cursor.execute('RELEASE SAVEPOINT "' + savepoint + '"', prepare=False)
                raise
            else:
                cursor.execute('RELEASE SAVEPOINT "' + savepoint + '"', prepare=False)
        if (native['status'] != 2 or native['commandStatusBase64'] != 'U0VMRUNUIDE='
                or len(rows) != 1 or type(rows[0]) is not tuple or len(rows[0]) != 1
                or type(rows[0][0]) is not str or len(rows[0][0].encode('utf8')) > 4096
                or native['rows'] != [[base64.b64encode(rows[0][0].encode('utf8')).decode('ascii')]]
                or raw.info.backend_pid != pid or int(raw.info.transaction_status) != 2):
            raise ValueError('Writer checkpoint native/result mismatch')
        if self._session.frame('configured-point-writer', {
                'format': 'moontxnwitness-point-writer-checkpoint/v2',
                'connection': self._identity, 'tx': self._tx, 'sql': WRITER_PROBE_SQL,
                'native': native, 'deliveredText': rows[0][0], 'sourceFactsProduced': False}) is None:
            raise ValueError('Writer checkpoint not retained')


class PointCursorV2(DiagnosticCursor):
    def __init__(self, connection, raw):
        super().__init__(connection, raw)
        self._projection = None
        self._result_id = None
        self._delivery_position = 0
        self._mode_supported = True
        self._point_statement, self._point_tx = None, None

    def _forget_projection(self):
        self._projection, self._result_id, self._delivery_position = None, None, 0
        self._point_statement, self._point_tx = None, None

    @contextmanager
    def _replacement(self):
        previous = self._raw.pgresult
        names = ('_projection', '_result_id', '_delivery_position', '_point_statement', '_point_tx',
                 '_pending', '_statement', '_mapping', '_result_complete', '_server_rows_seen', '_batch_start')
        saved = {name: getattr(self, name) for name in names}
        try:
            yield
        except BaseException:
            if self._raw.pgresult is previous:
                for name, value in saved.items():
                    setattr(self, name, value)
            else:
                self._forget_projection()
            raise

    @property
    def connection(self):
        return self._connection

    @property
    def description(self):
        actual = self._raw.description
        if self._projection is None or actual is None:
            return actual
        business = self._projection['businessResult']
        return None if business['mode'] == 'no-result' else actual[:len(business['columns'])]

    def execute(self, query, params=None, **kwargs):
        with self._connection._operation_lock:
            projected = None
            if self._session._enabled:
                try:
                    if (not self._mode_supported or not _tuple_factory(self._raw)
                            or self._connection._raw.autocommit or self._connection._raw._pipeline
                            or self._connection._raw._tpc or kwargs.get('binary')
                            or not set(kwargs).issubset({'prepare', 'binary'})):
                        raise ValueError('Unsupported cursor/execute mode')
                    projected = build_point_projection(self._session.parser.recognize(query), params, self._session.options)
                except Exception:
                    self._session.gap('point_projection_unrecognized', 'Original SQL executes unchanged and supplies no projection fact.')
            if projected is None:
                with self._replacement():
                    result = super().execute(query, params, **kwargs)
                self._forget_projection()
                return result
            descriptor = projected.to_dict()
            note = self._session.frame('configured-point-projection', {
                'format': 'moontxnwitness-projected-execution/v2',
                'connection': self._connection._identity, 'cursor': self._identity,
                'descriptor': descriptor, 'sourceFactsProduced': False})
            # Retain construction before execution. Journal failure must not
            # silently turn an executed rewrite into complete captured coverage.
            with self._replacement():
                result = super().execute(projected.sql, projected.parameters, **kwargs)
            self._projection = descriptor
            self._result_id = 'point-result-' + uuid.uuid4().hex
            self._delivery_position = 0
            self._point_statement, self._point_tx = self._statement, self._connection._tx
            try:
                native = _native(self._raw)
                self._session.frame('configured-point-native', {
                    'resultId': self._result_id, 'projectionNoteSeq': note,
                    'connection': self._connection._identity, 'cursor': self._identity,
                    'tx': self._connection._tx, 'statementSeq': self._statement,
                    'native': native, 'sourceFactsProduced': False})
            except Exception:
                self._session.gap('point_native_observation_missing', 'Original native buffer could not be retained within bounds.')
            if descriptor['businessResult']['mode'] == 'no-result':
                # Hidden RETURNING is inspected as an immutable native buffer;
                # it is never claimed as a fetched business result.
                self._pending = False
            return result

    def _fetch(self, method, *args):
        if self._projection is None:
            return super()._fetch(method, *args)
        from psycopg import ProgrammingError
        with self._connection._operation_lock:
            if self._raw.closed:
                # Delegate the native closed-cursor error before synthesizing a
                # no-result error; the failed fetch consumes no records.
                return getattr(self._raw, method)(*args) if args and args[0] is not None else getattr(self._raw, method)()
            business = self._projection['businessResult']
            if business['mode'] == 'no-result':
                raise ProgrammingError("the last operation didn't produce records (command status: " + self._raw.statusmessage + ')')
            if not _tuple_factory(self._raw):
                self._session.gap('point_decoder_changed', 'Changing a projected result row factory is unsupported.')
                raise ProgrammingError('Projected point results require the original tuple row factory')
            effective = (self._raw.arraysize if not args or not args[0] else args[0]) if method == 'fetchmany' else None
            actual_start = self._raw.rownumber
            if type(actual_start) is not int or actual_start < 0:
                actual_start = self._delivery_position
            raw = getattr(self._raw, method)(*args) if args and args[0] is not None else getattr(self._raw, method)()
            rows = [] if raw is None else [raw] if method == 'fetchone' else raw
            width = len(business['columns'])
            result = None if raw is None else rows[0][:width] if method == 'fetchone' else [row[:width] for row in rows]
            # Preserve original business delivery separately from hidden values.
            delivered = [] if result is None else [result] if method == 'fetchone' else result
            try:
                self._session.frame('configured-point-delivery', {
                    'format': 'moontxnwitness-projected-delivery/v2', 'resultId': self._result_id,
                    'connection': self._connection._identity, 'cursor': self._identity,
                    'tx': self._point_tx, 'statementSeq': self._point_statement,
                    'method': method, 'resultPythonType': type(result).__module__ + '.' + type(result).__qualname__,
                    'requestedSize': args[0] if method == 'fetchmany' and args else None,
                    'effectiveSize': effective, 'start': actual_start,
                    'rows': [{'pythonType': type(row).__module__ + '.' + type(row).__qualname__,
                              'cells': [_typed(cell) for cell in row]} for row in delivered],
                    'exhaustedObserved': method == 'fetchall' or (method == 'fetchone' and raw is None),
                    'sourceFactsProduced': False})
            except Exception:
                self._session.gap('point_delivery_missing', 'Business result returned unchanged; delivery evidence is incomplete.')
            self._delivery_position = actual_start + len(rows)
            self._rows(rows, self._exhausted(rows, eof=method == 'fetchall' or method == 'fetchone' and raw is None))
            return result

    def fetchone(self): return self._fetch('fetchone')
    def fetchmany(self, size=None): return self._fetch('fetchmany', size)
    def fetchall(self): return self._fetch('fetchall')

    def executemany(self, query, params_seq, **kwargs):
        with self._connection._operation_lock:
            self._session.gap('point_executemany_unmapped', 'Batch executes unchanged without point projection.')
            with self._replacement():
                result = super().executemany(query, params_seq, **kwargs)
            self._forget_projection()
            return result

    def nextset(self):
        self._session.gap('point_nextset_unmapped', 'Multiple results do not grant point coverage.')
        with self._connection._operation_lock:
            result = super().nextset()
            # psycopg leaves the current result buffer active when no next set
            # exists. Keep hiding metadata until a new buffer actually replaces it.
            if result:
                self._forget_projection()
            return result

    def set_result(self, index):
        with self._connection._operation_lock:
            previous = self._raw.pgresult
            self._raw.set_result(index)
            if self._raw.pgresult is not previous:
                self._session.gap('point_result_switched', 'Result switching does not grant point coverage.')
                self._forget_projection()
            return self

    def results(self):
        if self._raw.pgresult is not None:
            while True:
                yield self
                if not self.nextset():
                    break

    def scroll(self, value, mode='relative'):
        with self._connection._operation_lock:
            result = self._raw.scroll(value, mode=mode)
            self._session.gap('point_result_scrolled', 'Scrolled deliveries require an independent position-aware check.')
            return result
