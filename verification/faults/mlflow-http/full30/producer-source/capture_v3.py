"""Experimental synchronous psycopg protocol capture backed by the v3 journal.

Raw statements are observations, not SQL semantic proofs. Optional fixed SQL
mappings must be independently verified by the model consumer. No event-history
list is retained here. The original driver exceptions and business row shapes
are preserved; observer failures become bounded coverage gaps.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
import weakref

from .capture import CaptureSession, _Budget, _CaptureBudgetError, _status
from .journal_v3 import (SegmentedJournal, JournalReader, JournalError, SAFE_INTEGER,
                         _bounded_copy, _json, _sync_directory)


def _pinned_connection(raw):
    try:
        import psycopg
        return psycopg.__version__ == "3.3.6" and isinstance(raw, psycopg.Connection)
    except ImportError:
        return False


def _server_abort(raw, error):
    try:
        import psycopg
        state = error.sqlstate
        return (isinstance(error, psycopg.Error) and error.pgresult is not None
                and state in ("40001", "40P01") and error.diag.sqlstate == state
                and _status(raw) == 0)
    except Exception:
        return False


_IDENT = r'(?:"(?:[^"\x00]|"")+"|[A-Za-z_][A-Za-z_0-9$]*)'
_SAVEPOINT = re.compile(r'^\s*(SAVEPOINT|RELEASE(?:\s+SAVEPOINT)?|ROLLBACK\s+TO(?:\s+SAVEPOINT)?)\s+('
                        + _IDENT + r')\s*;?\s*$', re.IGNORECASE)


def _control(sql):
    match = _SAVEPOINT.fullmatch(sql)
    if not match:
        return None
    command, name = match.groups()
    name = name[1:-1].replace('""', '"') if name.startswith('"') else name.lower()
    return ("savepoint" if command.upper() == "SAVEPOINT" else
            "release" if command.upper().startswith("RELEASE") else "rollback_to", name)


@dataclass(frozen=True)
class SQLMapping:
    """Exact frozen SQL registration, never a general SQL parser.

    on_rows(cursor, server_rows, exhausted) may publish source facts. It must
    use actual same-statement evidence; callbacks are not themselves proofs.
    """
    sql: str
    mapping_id: str
    executed_sql: str | None = None
    business_columns: int | None = None
    on_rows: object | None = None
    bind_parameters: object | None = None

    def __post_init__(self):
        if (not isinstance(self.sql, str) or not self.sql or len(self.sql) > 65_536
                or not isinstance(self.mapping_id, str) or not self.mapping_id or len(self.mapping_id) > 256
                or self.executed_sql is not None and (not isinstance(self.executed_sql, str) or len(self.executed_sql) > 131_072)):
            raise ValueError("Exact SQL and bounded mapping identity are required")
        if self.business_columns is not None and (type(self.business_columns) is not int or not 1 <= self.business_columns <= 64):
            raise ValueError("business_columns must be 1..64")


from ._experimental_budget import profile


class CaptureV3Session:
    _value = CaptureSession._value  # Only bounded typed encoding is reused.

    def __init__(self, path, *, mappings=(), exclusive_writers=False, journal_options=None,
                 max_connections=128, max_cursors=512, max_value_bytes=256 * 1024,
                 max_value_nodes=16_384, experimental_budget=None):
        self.experimental_budget=profile(experimental_budget)
        if type(exclusive_writers) is not bool:
            raise ValueError("exclusive_writers must be explicit boolean")
        if (type(max_connections) is not int or not 1 <= max_connections <= 128
                or type(max_cursors) is not int or not 1 <= max_cursors <= 512
                or type(max_value_bytes) is not int or not 128 <= max_value_bytes <= 256 * 1024
                or type(max_value_nodes) is not int or not 16 <= max_value_nodes <= 65_536):
            raise ValueError("Observer resource settings exceed their bounded range")
        self.clock_domain = "mtw-v3-" + uuid.uuid4().hex
        self.exclusive_writers = exclusive_writers
        self._origin, self._seq = time.monotonic_ns(), 0
        self._lock, self._connections, self._cursors = threading.RLock(), weakref.WeakSet(), weakref.WeakSet()
        self._gaps, self._initialized, self._closed = [], False, False
        self._close_lock, self._close_error = threading.RLock(), None
        self._invalidated, self._invalidation_attempted, self._invalidation_persisted = False, False, False
        self._max_connections, self._max_cursors = max_connections, max_cursors
        self._max_value_bytes, self._max_value_nodes = max_value_bytes, max_value_nodes
        self._mappings = {}
        for mapping in mappings:
            if not isinstance(mapping, SQLMapping) or mapping.sql in self._mappings or len(self._mappings) >= 256:
                raise ValueError("Mappings must have distinct exact SQL")
            self._mappings[mapping.sql] = mapping
        options=dict(journal_options or {})
        if "experimental_budget" in options and options["experimental_budget"]!=self.experimental_budget:
            raise ValueError("Journal experiment must match explicit session budget")
        options["experimental_budget"]=self.experimental_budget
        self.journal = SegmentedJournal(path, **options)

    def gap(self, code, message):
        with self._lock:
            item = {"code": code, "message": message}
            if item not in self._gaps:
                if len(self._gaps) >= 64:
                    item = {"code": "gap_budget_exhausted", "message": "Further capture gaps omitted."}
                if item not in self._gaps:
                    self._gaps.append(item)
            self.journal._gap(item["code"], item["message"])

    @property
    def gaps(self):
        with self._lock:
            return tuple(dict(item) for item in self._gaps)

    def encode(self, value):
        return self._value(value, _Budget(self._max_value_nodes, self._max_value_bytes))

    def emit(self, kind, **fields):
        with self._lock:
            if self._closed:
                self.activity("event")
                return None
            self._seq += 1
            seq = self._seq
            try:
                result = self.journal.append({"seq": seq, "time": min(SAFE_INTEGER, time.monotonic_ns() - self._origin),
                                              "kind": kind, **fields})
                if not result.accepted:
                    self.gap("capture_event_not_retained", "An observed event could not be retained by the bounded journal.")
                    return None
                return seq
            except Exception:
                self.gap("capture_observer_failed", "A recording operation failed; business execution was preserved.")
                return None

    def activity(self, operation):
        with self._lock:
            if not self._closed:
                return
            self._invalidated = True
            self.gap("capture_activity_after_close", "A wrapped database operation occurred after the declared capture window ended.")
            if not self._invalidation_attempted:
                self._invalidation_attempted = True
                self._invalidation_persisted = self.journal.invalidate(
                    code="capture_activity_after_close", message="A wrapped database operation occurred after the declared capture window ended.")
                if not self._invalidation_persisted:
                    self.gap("invalidation_marker_io_failed", "Post-close invalidation is retained in memory; its separate disk marker could not be synchronized.")

    def publish_snapshot(self, initial, *, consistent):
        """Publish only a separately established initialization fact.

        This generic protocol layer does not create/verify table provenance.
        An application profile must lock, install, verify and read its actual
        initialization before calling this method, and prevent worker startup.
        """
        with self._lock:
            if self._initialized or self._seq:
                raise JournalError("Publish exactly one initialization before captured activity")
            if type(consistent) is not bool:
                raise ValueError("consistent must be explicit boolean")
            encoded = self.encode(initial)
            if not isinstance(encoded, dict) or any(not isinstance(v, str) or not v for v in encoded.values()):
                raise ValueError("initial requires nonempty unique-version strings")
            if not consistent:
                self.gap("initialization_unproven", "The initial database snapshot has not been established as consistent.")
            self._initialized = self.emit("snapshot", initial=encoded, consistent=consistent) is not None

    def wrap(self, raw, *, role=None):
        if not self._initialized or self._closed:
            raise JournalError("Initialize capture before wrapping business connections")
        with self._lock:
            if len(self._connections) >= self._max_connections:
                self.gap("connection_budget", "A connection exceeded the bounded observer registry; it runs unwrapped.")
                return raw
            connection = CapturedV3Connection(self, raw)
            self._connections.add(connection)
            return connection

    def driver(self, driver):
        session = self
        class Driver:
            def connect(self, *args, **kwargs):
                session.activity("connect")
                raw = driver.connect(*args, **kwargs)
                try:
                    return session.wrap(raw)
                except Exception:
                    session.gap("connection_not_wrapped", "A newly opened business connection could not be observed.")
                    return raw
            def __getattr__(self, name):
                return getattr(driver, name)
        return Driver()

    def flush(self):
        return self.journal.flush()

    def close(self, *, source_closed=False):
        # Never close a business connection or terminate its worker here.
        with self._close_lock:
            with self._lock:
                if self._closed:
                    if self._close_error is not None:
                        raise self._close_error
                    return self._apply_invalidation(JournalReader(self.journal.path, experimental_budget=self.experimental_budget).verify())
                active, unread = [], []
                for connection in self._connections:
                    if connection._tx:
                        active.append(connection._tx)
                    for cursor in connection._cursors:
                        if cursor._pending:
                            if len(unread) < 4096:
                                unread.append(cursor._identity)
                            else:
                                self.gap("unread_reference_budget", "Unread cursor references exceeded the bounded closure tracker.")
                self.journal.set_references(active_transactions=active, unread_results=unread)
                self._closed = True
            try:
                return self._apply_invalidation(self.journal.close(source_closed=source_closed))
            except BaseException as error:
                self._close_error = error
                raise

    def _apply_invalidation(self, status):
        with self._lock:
            if not self._invalidated:
                return status
            gaps = list(status.gaps)
            for item in self.gaps:
                if item not in gaps:
                    gaps.append(item)
            return replace(status, complete=False, gaps=tuple(gaps))

    def export(self, destination, *, sql_profiles=None, max_bytes=8 * 1024 * 1024):
        with self._lock:
            if self._invalidated:
                raise JournalError("This capture session observed post-close activity and can never export a complete window")
            return JournalReader(self.journal.path, experimental_budget=self.experimental_budget).export(destination, clock_domain=self.clock_domain,
                exclusive_writers=self.exclusive_writers, max_bytes=max_bytes, sql_profiles=sql_profiles)

    def export_diagnostic(self, destination, *, sql_profiles=None, max_bytes=8 * 1024 * 1024):
        with self._lock:
            return self._export_diagnostic(destination, sql_profiles=sql_profiles, max_bytes=max_bytes)

    def _export_diagnostic(self, destination, *, sql_profiles=None, max_bytes=8 * 1024 * 1024):
        """Export valid partial evidence with mandatory gaps; never a ready trace.

        Unlike strict journal.export this preserves diagnostic observations
        after an unknown outcome. The output receipt is always complete:false.
        """
        reader = JournalReader(self.journal.path, experimental_budget=self.experimental_budget)
        if self._invalidated:
            raise JournalError("Post-close activity was not recorded; diagnostic re-export from this reused observer is refused")
        if not self._closed:
            raise JournalError("Close the observer before diagnostic export; active storage is not a stable diagnostic snapshot")
        status = reader.verify()
        if not status.valid:
            raise JournalError("Corrupt storage cannot be exported as diagnostic evidence")
        if type(max_bytes) is not int or not 128 <= max_bytes <= 8 * 1024 * 1024:
            raise ValueError("Diagnostic output bound must be 128 bytes..8 MiB")
        profiles = [] if sql_profiles is None else _bounded_copy(sql_profiles, max_bytes, node_limit=200_000)
        if not isinstance(profiles, list) or len(profiles) > 16:
            raise ValueError("At most16 diagnostic SQL profiles")
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.journal.path) or destination.exists():
            raise JournalError("Diagnostic destination must be a new file outside the journal")
        temporary = destination.parent / ("." + destination.name + ".diagnostic-" + uuid.uuid4().hex + ".tmp")
        size, digest = 0, hashlib.sha256()
        gaps = list(status.gaps)
        for item in self.gaps:
            if item not in gaps:
                gaps.append(item)
        gaps.append({"code": "diagnostic_only", "message": "This export is incomplete diagnostic evidence, not a complete analysis input."})
        try:
            with temporary.open("xb") as target:
                def write(value):
                    nonlocal size
                    if size + len(value) > max_bytes:
                        raise JournalError("Diagnostic export exceeded its byte budget; no events were silently truncated")
                    target.write(value)
                    digest.update(value)
                    size += len(value)
                write(b'{"traceSchema":3,"clockDomain":' + _json(self.clock_domain)
                    + b',"scope":{"exclusiveWriters":' + (b'true' if self.exclusive_writers else b'false')
                    + b'},"sqlProfiles":' + _json(profiles) + b',"gaps":' + _json(gaps) + b',"events":[')
                comma = b""
                for item in reader.iter_events(require_complete=False):
                    write(comma + _json(item)); comma = b","
                write(b"]}\n")
                target.flush(); os.fsync(target.fileno())
            if reader.verify().index_sha256 != status.index_sha256:
                raise JournalError("Diagnostic source changed during export")
            os.link(temporary, destination)
            _sync_directory(destination.parent)
            return {"complete": False, "diagnostic": True, "bytes": size, "sha256": digest.hexdigest(),
                    "actualDatabaseExecution": False, "gapCount": len(gaps)}
        except Exception as error:
            reason = destination.parent / (destination.name + ".refused-" + uuid.uuid4().hex + ".json")
            with reason.open("x", encoding="utf-8") as file:
                json.dump({"complete": False, "errorClass": type(error).__name__,
                    "reason": str(error), "sourceIndexSha256": status.index_sha256}, file)
            raise
        finally:
            if temporary.exists():
                temporary.unlink()


class CapturedV3Connection:
    def __init__(self, session, raw):
        self._session, self._raw = session, raw
        self._identity, self._tx = "connection-" + uuid.uuid4().hex, None
        self._operation_lock, self._cursors = threading.RLock(), weakref.WeakSet()
        self._savepoints, self._commit_requested = [], False
        if _status(raw) != 0:
            session.gap("preexisting_transaction", "A wrapped connection already had an unobserved transaction.")
        if getattr(raw, "autocommit", False):
            session.gap("autocommit_unsupported", "This protocol slice requires explicit transaction boundaries.")

    def _begin(self):
        if self._tx is None:
            if _status(self._raw) != 0:
                self._session.gap("transaction_start_unproven", "A new identity began on a connection whose transaction was already active/unknown.")
            self._tx = "transaction-" + uuid.uuid4().hex
            self._savepoints, self._commit_requested = [], False
            self._session.emit("begin", tx=self._tx, connection=self._identity)
        return self._tx

    def _incomplete(self):
        for cursor in self._cursors:
            if cursor._pending:
                self._session.gap("unconsumed_result", "A statement result was not fully delivered before transaction/connection end.")

    def _unknown(self, code):
        if self._tx:
            self._session.gap(code, "A transaction outcome is unresolved; a later idle rollback cannot prove it aborted.")
            self._session.emit("disconnect", tx=self._tx)
            self._tx = None
            self._savepoints, self._commit_requested = [], False

    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if len(self._session._cursors) >= self._session._max_cursors:
            self._session.gap("cursor_budget", "A cursor exceeded the bounded observer registry; it runs unwrapped.")
            return raw
        if args or kwargs.get("name") or kwargs.get("withhold") or kwargs.get("row_factory"):
            self._session.gap("cursor_mode_unsupported", "Named/custom/withhold cursors are outside this protocol slice.")
        cursor = CapturedV3Cursor(self, raw)
        self._cursors.add(cursor)
        self._session._cursors.add(cursor)
        return cursor

    def execute(self, query, params=None, **kwargs):
        return self.cursor().execute(query, params, **kwargs)

    def commit(self):
        with self._operation_lock:
            self._session.activity("commit")
            self._incomplete()
            before = _status(self._raw)
            request = None
            if self._tx:
                request = self._session.emit("commit_request", tx=self._tx)
                self._commit_requested = True
            try:
                with self._commit_response_hook() as response:
                    result = self._raw.commit()
            except BaseException as error:
                if self._tx and request is not None and _server_abort(self._raw, error):
                    self._session.emit("rollback_ok", tx=self._tx, commitResponse={"request": request,
                        "sqlstate": error.sqlstate, "diagnosticSqlstate": error.diag.sqlstate,
                        "transactionStatus": "IDLE"})
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                else:
                    self._unknown("commit_unknown")
                raise
            if self._tx:
                if response.get("commandTag") == "ROLLBACK" and request is not None and _status(self._raw) == 0:
                    self._session.emit("rollback_ok", tx=self._tx, commitResponse={"request": request, "commandTag": "ROLLBACK"})
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                elif before != 3 and _status(self._raw) == 0:
                    self._session.emit("commit_ok", tx=self._tx)
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                else:
                    self._unknown("commit_ack_not_confirmed")
            return result

    @contextmanager
    def _commit_response_hook(self):
        response = {}
        raw = self._raw
        if not _pinned_connection(raw):
            yield response
            return
        if getattr(raw, "_pipeline", None) or getattr(raw, "_tpc", None):
            self._session.gap("commit_mode_unsupported", "Pipeline/two-phase commit response capture is unsupported.")
            yield response
            return
        original = raw._exec_command
        dictionary = getattr(raw, "__dict__", {})
        existed, previous = "_exec_command" in dictionary, dictionary.get("_exec_command")
        owner, calls = threading.get_ident(), 0
        def observe(command, *args, **kwargs):
            nonlocal calls
            result = yield from original(command, *args, **kwargs)
            if command == b"COMMIT":
                if threading.get_ident() != owner or calls:
                    self._session.gap("commit_hook_concurrency", "An unexpected concurrent/repeated COMMIT used the scoped response hook.")
                else:
                    calls += 1
                    try:
                        tag = result.command_status if result is not None else None
                        if tag in (b"COMMIT", b"ROLLBACK"):
                            response["commandTag"] = tag.decode("ascii")
                    except Exception:
                        self._session.gap("commit_response_unavailable", "The pinned driver response could not be observed.")
            return result
        try:
            raw._exec_command = observe
        except Exception:
            self._session.gap("commit_hook_unavailable", "The pinned driver could not install its instance-local response observer.")
            yield response
            return
        try:
            yield response
        finally:
            try:
                if existed:
                    raw._exec_command = previous
                else:
                    del raw._exec_command
            except Exception:
                self._session.gap("commit_hook_restore_failed", "The instance-local response observer could not be restored.")

    def rollback(self):
        with self._operation_lock:
            self._session.activity("rollback")
            self._incomplete()
            try:
                result = self._raw.rollback()
            except BaseException:
                self._unknown("rollback_unknown")
                raise
            if self._tx:
                if not self._commit_requested and _status(self._raw) == 0:
                    self._session.emit("rollback_ok", tx=self._tx)
                    self._tx, self._savepoints = None, []
                else:
                    self._unknown("rollback_not_confirmed")
            return result

    def close(self):
        with self._operation_lock:
            self._incomplete()
            try:
                return self._raw.close()
            finally:
                self._unknown("closed_without_outcome")

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, exc_type, value, traceback):
        if self._raw.closed:
            self._unknown("closed_outside_wrapper")
            return None
        if exc_type:
            try:
                self.rollback()
            except Exception:
                pass  # Preserve the original business exception, as psycopg.
        else:
            self.commit()
        if not getattr(self._raw, "_pool", None):
            self.close()
        return None

    def __getattr__(self, name):
        if name in ("transaction", "pipeline", "tpc_begin", "tpc_prepare", "tpc_commit", "tpc_rollback"):
            self._session.gap("connection_api_unsupported", "An unobserved connection lifecycle API was used.")
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._raw, name, value)
        if name in ("autocommit", "row_factory"):
            self._session.gap("connection_configuration_changed", "Transaction/row factory configuration changed during capture.")


class CapturedV3Cursor:
    def __init__(self, connection, raw):
        self._connection, self._raw, self._session = connection, raw, connection._session
        self._identity = "cursor-" + uuid.uuid4().hex
        self._pending, self._statement, self._mapping = False, None, None
        self._result_complete = False
        self._bound = {}
        self._server_rows_seen, self._batch_start = 0, 0

    @property
    def description(self):
        description = self._raw.description
        n = self._mapping.business_columns if self._mapping else None
        return description[:n] if description is not None and n is not None else description

    def _sql(self, query):
        if isinstance(query, str):
            return query
        if isinstance(query, bytes):
            return query.decode(getattr(getattr(self._connection._raw, "info", None), "encoding", "utf-8"))
        if callable(getattr(query, "as_string", None)):
            return query.as_string(self._connection._raw)
        raise ValueError("SQL cannot be represented without guessing")

    def execute(self, query, params=None, **kwargs):
        with self._connection._operation_lock:
            self._session.activity("execute")
            if self._pending:
                self._session.gap("result_replaced", "A new statement replaced an undelivered result.")
            self._connection._begin()
            try:
                sql = self._sql(query)
            except Exception:
                self._session.gap("sql_encoding_failed", "SQL text could not be retained; the original query still executes.")
                sql = "<unavailable>"
            self._mapping = self._session._mappings.get(sql)
            factory = getattr(self._raw, "row_factory", None)
            if factory is not None and (getattr(factory, "__module__", None), getattr(factory, "__name__", None)) != ("psycopg.rows", "tuple_row"):
                self._session.gap("row_factory_unsupported", "Only the driver's default tuple factory can hide mapped metadata.")
                self._mapping = None
            mapping = self._mapping
            self._result_complete = False
            self._bound = {}
            self._server_rows_seen, self._batch_start = 0, 0
            if mapping and callable(mapping.bind_parameters):
                try:
                    bound = mapping.bind_parameters(params)
                    self._bound = self._session._value(bound, _Budget(256, 4096))
                except Exception:
                    self._session.gap("mapping_parameter_binding_failed", "Fixed statement parameters could not be bound within the 4 KiB provenance context.")
            fields = {"tx": self._connection._tx, "sql": sql}
            if mapping:
                fields.update(mappingId=mapping.mapping_id, executedSql=mapping.executed_sql or sql)
            try:
                fields["parameters"] = self._session.encode(params)
            except Exception:
                self._session.gap("parameter_encoding_failed", "Parameters exceeded the bounded raw encoding profile.")
            self._statement = self._session.emit("statement", **fields)
            actual = mapping.executed_sql if mapping and mapping.executed_sql else query
            try:
                self._raw.execute(actual, params, **kwargs)
            except BaseException as error:
                self._pending = False
                if self._statement is not None:
                    self._session.emit("rows", tx=self._connection._tx, statement=self._statement,
                        rows=[], complete=False, error={"class": type(error).__name__,
                        "sqlstate": getattr(error, "sqlstate", None)})
                self._session.gap("statement_failed", "A business statement raised its original driver exception.")
                raise
            self._pending = self._raw.description is not None
            if not self._pending:
                self._rows([], True)
            command = _control(sql)
            if command:
                kind, name = command
                if len(name.encode("utf-8")) > 63 or mapping and mapping.executed_sql and mapping.executed_sql != sql:
                    self._session.gap("savepoint_name_or_mapping_unsupported", "Savepoint identity was truncated or its control SQL was rewritten.")
                    return self
                stack = self._connection._savepoints
                if kind == "savepoint":
                    if len(stack) >= 64:
                        self._session.gap("savepoint_depth_budget", "Savepoint observer depth exceeds 64; the SQL still executed unchanged.")
                    else:
                        instance = "savepoint-" + uuid.uuid4().hex
                        stack.append((name, instance))
                        self._session.emit(kind, tx=self._connection._tx, name=name, instance=instance)
                else:
                    found = next((n for n in range(len(stack) - 1, -1, -1) if stack[n][0] == name), None)
                    if found is None:
                        self._session.gap("savepoint_source_missing", "A savepoint acknowledgement lacked a recorded target instance.")
                    else:
                        self._session.emit(kind, tx=self._connection._tx, instance=stack[found][1])
                        del stack[found if kind == "release" else found + 1:]
            elif sql.strip().upper().rstrip(";").strip() in ("COMMIT", "ROLLBACK", "BEGIN", "START TRANSACTION"):
                self._session.gap("raw_transaction_control", "Use connection commit/rollback; raw transaction SQL is not yet mapped.")
            return self

    def _rows(self, rows, exhausted):
        if self._result_complete:
            if rows:
                self._session.gap("rows_after_eof", "The driver returned rows after its previously confirmed result exhaustion.")
            return
        mapping = self._mapping
        n = mapping.business_columns if mapping else None
        self._batch_start = self._server_rows_seen
        self._server_rows_seen += len(rows)
        try:
            # Encode the original complete batch under one budget before making
            # any projected per-row containers. Large business fetchall() results
            # are returned unchanged; the observer does not clone them first.
            encoded = self._session.encode(rows)
            if not isinstance(encoded, list):
                raise ValueError("A result batch must encode as an array")
            if n is not None and any(not isinstance(row, tuple) or len(row) < n for row in rows):
                raise ValueError("Default tuple server rows required for hidden metadata")
            fields = {"tx": self._connection._tx, "statement": self._statement,
                      "rows": [row[:n] for row in encoded] if n is not None else encoded,
                      "complete": exhausted}
            if mapping:
                fields["serverRows"] = encoded
                description = self.description
                if description is not None and all(hasattr(c, "name") and hasattr(c, "type_code") for c in description):
                    fields["columns"] = [{"name": c.name, "typeCode": c.type_code} for c in description]
            if self._statement is not None:
                self._session.emit("rows", **fields)
            if mapping and callable(mapping.on_rows):
                mapping.on_rows(self, rows, exhausted)
        except Exception:
            self._session.gap("result_observation_failed", "Returned rows or their provenance could not be retained/verified; original business rows were preserved.")
        self._pending = not exhausted
        self._result_complete = exhausted
        if exhausted:
            self._bound = {}

    def fact(self, kind, **fields):
        if kind not in ("read", "write", "condition") or self._mapping is None or self._statement is None:
            raise ValueError("A fact requires a registered statement and supported fact kind")
        return self._session.emit(kind, tx=self._connection._tx, statement=self._statement,
            mappingId=self._mapping.mapping_id, **self._session.encode(fields))

    def _project_batch(self, rows):
        n = self._mapping.business_columns if self._mapping else None
        if n is not None:
            for index, row in enumerate(rows):
                if isinstance(row, tuple):
                    rows[index] = row[:n]
        return rows

    def _exhausted(self, rows, eof=False):
        if eof:
            return True
        count, position = getattr(self._raw, "rowcount", -1), getattr(self._raw, "rownumber", None)
        return type(count) is int and count >= 0 and type(position) is int and position >= count

    def fetchone(self):
        with self._connection._operation_lock:
            self._session.activity("fetchone")
            row = self._raw.fetchone()  # Exceptions are never replaced by observer exceptions.
            self._rows([] if row is None else [row], self._exhausted([], eof=row is None))
            n = self._mapping.business_columns if self._mapping else None
            return row[:n] if row is not None and n is not None and isinstance(row, tuple) else row

    def fetchmany(self, size=None):
        with self._connection._operation_lock:
            self._session.activity("fetchmany")
            rows = self._raw.fetchmany() if size is None else self._raw.fetchmany(size)
            self._rows(rows, self._exhausted(rows, eof=not rows))
            return self._project_batch(rows)

    def fetchall(self):
        with self._connection._operation_lock:
            self._session.activity("fetchall")
            rows = self._raw.fetchall()
            self._rows(rows, True)
            return self._project_batch(rows)

    def close(self):
        if self._pending:
            self._session.gap("unconsumed_result", "A cursor closed before its business result was exhausted.")
        try:
            return self._raw.close()
        finally:
            self._pending = False

    def __iter__(self):
        return self

    def __next__(self):
        value = self.fetchone()
        if value is None:
            raise StopIteration
        return value

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *args):
        self.close()
        return None

    def __getattr__(self, name):
        if name in ("executemany", "copy", "stream", "nextset"):
            self._session.gap("cursor_api_unsupported", "An unobserved cursor execution API was used.")
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._raw, name, value)
        if name == "row_factory":
            self._session.gap("cursor_configuration_changed", "The cursor row factory changed during capture.")
