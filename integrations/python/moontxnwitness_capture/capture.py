"""Conservative synchronous/asynchronous psycopg 3 wrappers.

SQL matching is exact and opt-in: a mapping is a trusted declaration of SQL
semantics, not a general SQL parser. An unregistered statement is still executed
unchanged, but makes the trace incomplete. No optional driver is imported until
connect()/aconnect() is called.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import decimal
import hashlib
import json
import math
import threading
import time
import uuid
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CaptureSetupError(RuntimeError):
    """Capture initialization failed; business connections have not been changed."""


class _CaptureBudgetError(ValueError):
    pass


class _Budget:
    """Charge JSON nodes/UTF-8 bytes before retaining or copying a subtree."""

    def __init__(self, nodes, size):
        self.nodes, self.size = nodes, size
        self.used_nodes, self.used_bytes = 0, 0

    def charge(self, size=0, nodes=0):
        if size > self.size - self.used_bytes or nodes > self.nodes - self.used_nodes:
            raise _CaptureBudgetError("aggregate capture budget exhausted")
        self.used_nodes += nodes
        self.used_bytes += size

    def text(self, value):
        # Each character needs at least one JSON byte. Reject long strings before
        # iteration or encode()/json.dumps() can allocate another large object.
        if len(value) + 2 > self.size - self.used_bytes:
            raise _CaptureBudgetError("aggregate string bytes exhausted")
        self.charge(2)
        for character in value:
            code = ord(character)
            if character in ('"', "\\", "\b", "\f", "\n", "\r", "\t"):
                size = 2
            elif code < 32:
                size = 6
            elif code < 128:
                size = 1
            elif code < 2048:
                size = 2
            elif 0xD800 <= code <= 0xDFFF:
                raise ValueError("unpaired surrogate cannot be persisted as UTF-8")
            else:
                size = 3 if code <= 0xFFFF else 4
            self.charge(size)


def _measure_json(value, budget):
    """Measure already encoded JSON without constructing a serialized copy."""
    budget.charge(nodes=1)
    if value is None:
        budget.charge(4)
    elif isinstance(value, bool):
        budget.charge(4 if value else 5)
    elif isinstance(value, str):
        budget.text(value)
    elif isinstance(value, int):
        if int.bit_length(value) * 30103 // 100000 + 2 > budget.size - budget.used_bytes:
            raise _CaptureBudgetError("integer encoding exceeds remaining budget")
        budget.charge(len(int.__repr__(value)))
    elif isinstance(value, float) and math.isfinite(value):
        budget.charge(len(repr(value)))
    elif isinstance(value, list):
        budget.charge(2 + max(0, len(value) - 1))
        for item in value:
            _measure_json(item, budget)
    elif isinstance(value, dict):
        budget.charge(2 + max(0, len(value) - 1))
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            budget.charge(1, nodes=1)
            budget.text(key)
            _measure_json(item, budget)
    else:
        raise ValueError("unsupported retained JSON value")


def _identifier(value):
    if (not isinstance(value, str) or not value or len(value) > 63 or "\x00" in value
            or len(value.encode("utf-8")) > 63):
        raise ValueError("SQL identifiers must be nonempty strings of at most 63 UTF-8 bytes without NUL")
    return '"' + value.replace('"', '""') + '"'


def _parameter(params, selector):
    if isinstance(selector, bool) or not isinstance(selector, (int, str)):
        raise ValueError("parameter selector must be an integer or string")
    return params[selector]


def _status(connection):
    """libpq status: IDLE=0, ACTIVE=1, INTRANS=2, INERROR=3, UNKNOWN=4."""
    try:
        return int(connection.info.transaction_status)
    except (AttributeError, TypeError, ValueError):
        return 4


def _error(error):
    # Driver messages can contain data and credentials. Preserve type/SQLSTATE.
    return {"errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)}


def _commit_error_status(connection, error):
    """Only classify an acknowledged server rollback with an idle connection.

    A SQLSTATE attribute alone can also be attached to a locally constructed
    exception. Matching server diagnostics plus libpq IDLE provide the evidence
    required for these documented rollback errors. Lost replies stay unknown.
    """
    state = getattr(error, "sqlstate", None)
    diagnostic = getattr(error, "diag", None)
    if (state in ("40001", "40P01") and getattr(diagnostic, "sqlstate", None) == state
            and _status(connection) == 0):
        return "aborted"
    return "unknown"


@dataclass(frozen=True)
class Table:
    schema: str
    name: str
    key_column: str
    version_column: str
    namespace: str | None = None

    def __post_init__(self):
        for field in (self.schema, self.name, self.key_column, self.version_column):
            _identifier(field)
        if self.namespace is not None and (not isinstance(self.namespace, str) or not self.namespace):
            raise ValueError("namespace must be a nonempty string")

    @property
    def qualified(self):
        return _identifier(self.schema) + "." + _identifier(self.name)

    def key(self, value):
        if isinstance(value, bool):
            kind = "bool"
        elif isinstance(value, int):
            kind = "int"
        elif isinstance(value, str):
            kind = "text"
        else:
            raise ValueError("v0.1.1 keys must be text, integer, or boolean")
        # Typed JSON avoids collisions between 1, true, and "1".
        return json.dumps([self.namespace or self.schema + "." + self.name, kind, value],
                          ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class PointRead:
    """An exact primary-key SELECT returning its existing version column.

    version_result indexes an actual returned row (tuple index or dict key).
    The registered SQL must have no other database reads or side effects.
    """
    sql: str
    table: Table
    key_parameter: int | str = 0
    version_result: int | str = 1

    @classmethod
    def for_table(cls, table, *, value_columns=("value",)):
        """Generate the supported single-table primary-key SELECT shape."""
        columns = _value_columns(table, value_columns)
        query = ("SELECT " + ",".join(_identifier(c) for c in (*columns, table.version_column))
                 + " FROM " + table.qualified + " WHERE " + _identifier(table.key_column) + "=%s")
        return cls(query, table, 0, len(columns))


@dataclass(frozen=True)
class PointWrite:
    """An exact primary-key UPDATE assigning an existing unique version column.

    version_parameter is the actual assigned version, not the business value.
    Database-generated/trigger-rewritten versions need a later capture profile.
    """
    sql: str
    table: Table
    key_parameter: int | str = 2
    version_parameter: int | str = 1

    @classmethod
    def for_table(cls, table, *, value_columns=("value",)):
        """Generate UPDATE parameters: values..., unique version, primary key."""
        columns = _value_columns(table, value_columns)
        query = ("UPDATE " + table.qualified + " SET "
                 + ",".join(_identifier(c) + "=%s" for c in (*columns, table.version_column))
                 + " WHERE " + _identifier(table.key_column) + "=%s")
        return cls(query, table, len(columns) + 1, len(columns))


def _value_columns(table, columns):
    columns = tuple(columns)
    if len(columns) != len(set(columns)) or table.key_column in columns or table.version_column in columns:
        raise ValueError("value columns must be distinct and exclude primary key and version")
    for column in columns:
        _identifier(column)
    return columns


_BEGIN = {"BEGIN", "BEGIN TRANSACTION", "START TRANSACTION"}
for _prefix in ("BEGIN", "BEGIN TRANSACTION", "START TRANSACTION"):
    for _level in ("READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE", "READ UNCOMMITTED"):
        _BEGIN.add(_prefix + " ISOLATION LEVEL " + _level)
_COMMIT = {"COMMIT", "COMMIT TRANSACTION", "END", "END TRANSACTION"}
_ROLLBACK = {"ROLLBACK", "ROLLBACK TRANSACTION", "ABORT", "ABORT TRANSACTION"}


def _control(text):
    normalized = " ".join(text.strip().removesuffix(";").split()).upper()
    if normalized in _BEGIN:
        return "begin"
    if normalized in _COMMIT:
        return "commit"
    if normalized in _ROLLBACK:
        return "rollback"
    return None


class CaptureSession:
    """One process clock domain, explicit writer-scope assumption, and trace.

    initialize() must finish before any captured business transaction starts.
    exclusive_writers=True is the caller's deployment assertion; the wrapper
    cannot discover arbitrary uninstrumented clients elsewhere in the database.

    Raw encoding defaults: 16,384 visited nodes and 256 KiB compact JSON bytes
    per parameters/results tree; 512 KiB per event; 8 MiB and 262,144 nodes of
    retained events/gaps; 64 distinct gaps plus one exhaustion marker. Bounds
    reserve room for the document envelope and a terminal gap. These limit the
    observer's retained/copied evidence, not original driver buffers, application
    objects, configured mappings, concurrent callers or the process's total RSS.
    """

    def __init__(self, mappings, *, jsonl_path=None, exclusive_writers=False, max_events=65_536,
                 max_value_nodes=16_384, max_value_bytes=256 * 1024,
                 max_event_bytes=512 * 1024, max_session_bytes=8 * 1024 * 1024,
                 max_session_nodes=262_144, max_gaps=64):
        if not isinstance(exclusive_writers, bool):
            raise ValueError("exclusive_writers must be a boolean")
        if not isinstance(max_events, int) or isinstance(max_events, bool) or max_events < 1:
            raise ValueError("max_events must be positive")
        for limit in (max_value_nodes, max_value_bytes, max_event_bytes, max_session_bytes, max_session_nodes, max_gaps):
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                raise ValueError("capture resource budgets must be positive integers")
        if max_session_bytes < 2048 or max_session_nodes < 128:
            raise ValueError("session budgets must reserve at least 2048 bytes and 128 nodes")
        self._mappings = {}
        for mapping in mappings:
            if not isinstance(mapping, (PointRead, PointWrite)) or not isinstance(mapping.sql, str) or not mapping.sql or len(mapping.sql) > 65_536:
                raise ValueError("use explicit PointRead/PointWrite mappings")
            if _control(mapping.sql) or mapping.sql in self._mappings:
                raise ValueError("duplicate mapping or transaction-control SQL mapping")
            for selector in (mapping.key_parameter,
                             mapping.version_result if isinstance(mapping, PointRead) else mapping.version_parameter):
                if isinstance(selector, bool) or not isinstance(selector, (int, str)) or (isinstance(selector, int) and selector < 0):
                    raise ValueError("mapping selectors must be nonnegative indexes or names")
            self._mappings[mapping.sql] = mapping
        if not self._mappings:
            raise ValueError("at least one SQL mapping is required")
        self._tables = sorted(set(m.table for m in self._mappings.values()), key=lambda t: (t.schema, t.name))
        identities = [(t.schema, t.name) for t in self._tables]
        if len(identities) != len(set(identities)):
            raise ValueError("one consistent Table declaration is required per database table")
        namespaces = [t.namespace or t.schema + "." + t.name for t in self._tables]
        if len(namespaces) != len(set(namespaces)):
            raise ValueError("table namespaces must be distinct")
        self._lock = threading.RLock()
        self._clock_start = time.monotonic_ns()
        self._domain = "python-monotonic-" + uuid.uuid4().hex
        self._exclusive = exclusive_writers
        self._events = []
        self._gaps = []
        self._connections = weakref.WeakSet()
        self._next_tx = 0
        self._max_events = max_events
        self._max_value_nodes, self._max_value_bytes = max_value_nodes, max_value_bytes
        self._max_event_bytes = max_event_bytes
        self._max_session_bytes, self._max_session_nodes = max_session_bytes, max_session_nodes
        self._max_gaps = max_gaps
        self._retained_bytes = self._retained_nodes = 0
        self._capture_exhausted = False
        self._gap_limit_reached = False
        self._initialized = False
        self._closed = False
        self._stream = None
        self._digest = hashlib.sha256()
        self._log_failed = False
        if jsonl_path is not None:
            # Never overwrite a previous capture or silently append a new session.
            self._stream = Path(jsonl_path).open("x", encoding="utf-8", newline="\n")
            self._write({"record": "header", "traceSchema": 1, "clockDomain": self._domain,
                         "scope": {"exclusiveWriters": self._exclusive}})

    def _write(self, record, *, footer=False):
        if self._stream is None or self._log_failed:
            return
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            self._stream.write(line)
            self._stream.flush()
            if not footer:
                self._digest.update(line.encode("utf-8"))
        except Exception:
            self._log_failed = True
            self.gap("log_write_failed", "Raw event persistence failed; memory observations are incomplete evidence.")

    def gap(self, code, message):
        with self._lock:
            if self._gap_limit_reached:
                return
            item = {"code": code[:128] if isinstance(code, str) and code else "capture_gap",
                    "message": message[:512] if isinstance(message, str) and message else "Capture evidence is incomplete."}
            if item not in self._gaps:
                budget = _Budget(32, 4096)
                try:
                    _measure_json(item, budget)
                except Exception:
                    item = {"code": "gap_value_unsupported", "message": "A coverage gap could not be represented faithfully."}
                    budget = _Budget(32, 4096)
                    _measure_json(item, budget)
                if (len(self._gaps) >= self._max_gaps
                        or self._retained_bytes + budget.used_bytes + 1 > self._max_session_bytes - 1024
                        or self._retained_nodes + budget.used_nodes > self._max_session_nodes - 32):
                    # One reserved terminal marker preserves the resource cause
                    # without allowing later unique gaps to grow memory again.
                    terminal_code = item["code"] if item["code"] in {
                        "session_budget_exhausted", "event_budget_exhausted", "event_value_budget",
                        "snapshot_budget_exhausted", "raw_value_budget"
                    } else "gap_budget_exhausted"
                    item = {"code": terminal_code, "message": "Retained evidence budget exhausted; additional observations or gaps may be omitted."}
                    self._gap_limit_reached = True
                    budget = _Budget(32, 4096)
                    _measure_json(item, budget)
                self._retained_bytes += budget.used_bytes + 1
                self._retained_nodes += budget.used_nodes
                self._gaps.append(item)
                self._write({"record": "gap", "gap": item})

    def _event(self, kind, **payload):
        with self._lock:
            if self._closed:
                self.gap("capture_closed", "A business operation occurred after the capture was closed.")
                return
            if self._capture_exhausted:
                return
            if len(self._events) >= self._max_events:
                self._capture_exhausted = True
                self.gap("event_budget_exhausted", "Raw event budget exhausted; this capture cannot provide a complete conclusion.")
                return
            item = {"seq": len(self._events) + 1, "kind": kind,
                    "time": (time.monotonic_ns() - self._clock_start) // 1000, **payload}
            budget = _Budget(65_536, self._max_event_bytes)
            try:
                _measure_json(item, budget)
            except _CaptureBudgetError:
                self._capture_exhausted = True
                self.gap("event_value_budget", "One event exceeded its aggregate byte or node budget; only the preceding evidence was retained.")
                return
            except Exception:
                self._capture_exhausted = True
                self.gap("event_value_unsupported", "One event could not be represented as bounded JSON evidence.")
                return
            if (self._retained_bytes + budget.used_bytes + 1 > self._max_session_bytes - 1024
                    or self._retained_nodes + budget.used_nodes > self._max_session_nodes - 32):
                self._capture_exhausted = True
                self.gap("session_budget_exhausted", "Session retained bytes or nodes were exhausted; further business operations continue without complete evidence.")
                return
            self._retained_bytes += budget.used_bytes + 1
            self._retained_nodes += budget.used_nodes
            self._events.append(item)
            self._write({"record": "event", "event": item})

    def _new_tx(self):
        with self._lock:
            self._next_tx += 1
            return "tx-" + str(self._next_tx)

    def _value(self, value, budget, depth=0):
        """One shared budget applies to the complete parameters/result tree."""
        budget.charge(nodes=1)
        if depth > 8:
            raise _CaptureBudgetError("raw nesting limit")
        if value is None:
            budget.charge(4)
            return value
        if isinstance(value, bool):
            budget.charge(4 if value else 5)
            return value
        if isinstance(value, int):
            if int.bit_length(value) * 30103 // 100000 + 2 > budget.size - budget.used_bytes:
                raise _CaptureBudgetError("raw integer limit")
            if abs(value) <= 9_007_199_254_740_991:
                budget.charge(len(int.__repr__(value)))
                return value
            return self._value({"captureType": "int", "value": int.__repr__(value)}, budget, depth + 1)
        if isinstance(value, str):
            if len(value) > 65_536:
                raise _CaptureBudgetError("raw string limit")
            budget.text(value)
            return value
        if isinstance(value, float):
            if math.isfinite(value):
                budget.charge(len(repr(value)))
                return value
            return self._value({"captureType": "float", "value": str(value)}, budget, depth + 1)
        if isinstance(value, (decimal.Decimal, datetime.date, datetime.time, uuid.UUID)):
            if isinstance(value, decimal.Decimal) and value.__sizeof__() > 16_384:
                raise _CaptureBudgetError("raw Decimal representation limit")
            return self._value({"captureType": type(value).__name__, "value": str(value)}, budget, depth + 1)
        if isinstance(value, (bytes, bytearray, memoryview)):
            # len(memoryview) counts elements (or the first dimension), not
            # bytes. Check the actual buffer size before base64 allocates.
            if isinstance(value, memoryview) and not value.c_contiguous:
                raise ValueError("non-contiguous raw memoryview is not supported")
            raw_size = value.nbytes if isinstance(value, memoryview) else len(value)
            if raw_size > 65_536:
                raise _CaptureBudgetError("raw binary limit")
            encoded_size = 4 * ((raw_size + 2) // 3)
            # Charge the complete tagged JSON representation before encoding,
            # including the expansion beyond the raw 64 KiB binary boundary.
            _measure_json({"captureType": "bytes", "base64": ""}, budget)
            budget.charge(encoded_size)
            return {"captureType": "bytes", "base64": base64.b64encode(value).decode("ascii")}
        if isinstance(value, (list, tuple)) and len(value) <= 10_000:
            budget.charge(2 + max(0, len(value) - 1))
            return [self._value(item, budget, depth + 1) for item in value]
        if isinstance(value, dict) and len(value) <= 10_000:
            budget.charge(2 + max(0, len(value) - 1))
            result = {}
            for key, item in value.items():
                if not isinstance(key, str) or len(key) > 65_536:
                    raise ValueError("raw dictionary key is not supported")
                budget.charge(1, nodes=1)
                budget.text(key)
                result[key] = self._value(item, budget, depth + 1)
            return result
        raise ValueError("unsupported raw value type")

    def _safe_value(self, value):
        if self._capture_exhausted or self._closed:
            return {"captureType": "capture-stopped"}
        try:
            return self._value(value, _Budget(self._max_value_nodes, self._max_value_bytes))
        except _CaptureBudgetError:
            self.gap("raw_value_budget", "Parameters or returned rows exceeded the shared aggregate nesting, node, or JSON byte budget.")
            return {"captureType": "budget-exhausted"}
        except Exception:
            self.gap("raw_value_unsupported", "A parameter/result could not be encoded as raw evidence.")
            return {"captureType": "encoding-failed"}

    def _add_snapshot_rows(self, table, rows, initial, budget):
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise CaptureSetupError("Snapshot requires the setup connection's default tuple row factory")
            try:
                key, version = self._key(table, row[0]), row[1]
                if key in initial or not isinstance(version, str) or not version:
                    raise CaptureSetupError("Snapshot keys must be unique and versions nonempty strings")
                if len(initial) >= 10_000:
                    raise _CaptureBudgetError("snapshot row limit")
                budget.charge(2, nodes=2)
                budget.text(key)
                budget.text(version)
            except _CaptureBudgetError as error:
                self.gap("snapshot_budget_exhausted", "The initial snapshot exceeded its retained row, byte, or node budget.")
                raise CaptureSetupError("Initial snapshot resource budget exhausted") from error
            initial[key] = version

    def _publish_snapshot(self, initial):
        self._event("snapshot", initial=initial, consistent=True)
        self._initialized = True

    def _key(self, table, value):
        namespace = table.namespace or table.schema + "." + table.name
        if len(namespace) > 65_536 or (isinstance(value, str) and len(value) > 65_536):
            raise _CaptureBudgetError("logical key representation too large")
        if isinstance(value, int) and int.bit_length(value) > 4096:
            raise _CaptureBudgetError("logical integer key representation too large")
        kind = "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "text"
        _measure_json([namespace, kind, value],
                      _Budget(8, min(self._max_event_bytes - 320, self._max_session_bytes - 1536)))
        return table.key(value)

    def _check_initialization(self, connection):
        if self._initialized or self._events:
            raise CaptureSetupError("Initialize once, before captured business activity")
        if _status(connection) != 0 or not getattr(connection, "autocommit", False):
            raise CaptureSetupError("Use a dedicated idle autocommit setup connection")

    @staticmethod
    def _catalog_sql():
        return ("SELECT c.relkind,c.relrowsecurity,EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t "
                "WHERE t.tgrelid=c.oid AND NOT t.tgisinternal AND t.tgenabled <> 'D'),"
                "EXISTS (SELECT 1 FROM pg_catalog.pg_index i JOIN pg_catalog.pg_attribute a "
                "ON a.attrelid=i.indrelid AND a.attnum=i.indkey[0] "
                "WHERE i.indrelid=c.oid AND i.indisprimary AND i.indnkeyatts=1 AND a.attname=%s) "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relname=%s "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint fk "
                "WHERE fk.contype='f' AND (fk.conrelid=c.oid OR fk.confrelid=c.oid)) "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_rewrite rw WHERE rw.ev_class=c.oid) "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits ih "
                "WHERE ih.inhparent=c.oid OR ih.inhrelid=c.oid)")

    @staticmethod
    def _validate_catalog(row):
        if row is None or tuple(row) != ("r", False, False, True):
            raise CaptureSetupError("v0.1.1 requires ordinary tables with the declared single-column primary key, without RLS, enabled user triggers, foreign keys, rewrite rules or inheritance")

    def initialize(self, connection):
        """Take one locked initial state, without deriving initial from first reads.

        Locks are setup-only SHARE locks, acquired before all table reads in a
        READ COMMITTED transaction. They prevent concurrent writes while the
        initial state is collected. Start application workers after this returns.
        """
        self._check_initialization(connection)
        try:
            connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            connection.execute("LOCK TABLE " + ",".join(t.qualified for t in self._tables) + " IN SHARE MODE")
            initial = {}
            budget = _Budget(65_000, min(self._max_event_bytes - 256, self._max_session_bytes - 1536))
            for table in self._tables:
                self._validate_catalog(connection.execute(self._catalog_sql(), (table.key_column, table.schema, table.name)).fetchone())
                query = ("SELECT " + _identifier(table.key_column) + "," + _identifier(table.version_column)
                         + " FROM " + table.qualified + " LIMIT " + str(10_001 - len(initial)))
                cursor = connection.execute(query)
                try:
                    while True:
                        rows = cursor.fetchmany(64)
                        if not rows:
                            break
                        self._add_snapshot_rows(table, rows, initial, budget)
                finally:
                    cursor.close()
            connection.commit()
            self._publish_snapshot(initial)
        except BaseException:
            self.gap("initialization_failed", "An initial state could not be established reliably.")
            try:
                connection.rollback()
            except Exception:
                self.gap("initialization_rollback_unknown", "Setup rollback was not acknowledged.")
            raise

    async def ainitialize(self, connection):
        self._check_initialization(connection)
        try:
            await connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            await connection.execute("LOCK TABLE " + ",".join(t.qualified for t in self._tables) + " IN SHARE MODE")
            initial = {}
            budget = _Budget(65_000, min(self._max_event_bytes - 256, self._max_session_bytes - 1536))
            for table in self._tables:
                cursor = await connection.execute(self._catalog_sql(), (table.key_column, table.schema, table.name))
                self._validate_catalog(await cursor.fetchone())
                query = ("SELECT " + _identifier(table.key_column) + "," + _identifier(table.version_column)
                         + " FROM " + table.qualified + " LIMIT " + str(10_001 - len(initial)))
                cursor = await connection.execute(query)
                try:
                    while True:
                        rows = await cursor.fetchmany(64)
                        if not rows:
                            break
                        self._add_snapshot_rows(table, rows, initial, budget)
                finally:
                    await cursor.close()
            await connection.commit()
            self._publish_snapshot(initial)
        except BaseException:
            self.gap("initialization_failed", "An initial state could not be established reliably.")
            try:
                await connection.rollback()
            except Exception:
                self.gap("initialization_rollback_unknown", "Setup rollback was not acknowledged.")
            raise

    def wrap(self, connection):
        for existing in tuple(self._connections):
            if connection is existing or connection is existing._raw:
                return existing
        captured = CapturedConnection(self, connection)
        self._connections.add(captured)
        return captured

    def awrap(self, connection):
        for existing in tuple(self._connections):
            if connection is existing or connection is existing._raw:
                return existing
        captured = AsyncCapturedConnection(self, connection)
        self._connections.add(captured)
        return captured

    def connect(self, *args, **kwargs):
        import psycopg
        return self.wrap(psycopg.connect(*args, **kwargs))

    async def aconnect(self, *args, **kwargs):
        import psycopg
        return self.awrap(await psycopg.AsyncConnection.connect(*args, **kwargs))

    def document(self):
        # A copy prevents a caller accidentally changing retained observations.
        with self._lock:
            return json.loads(json.dumps({"traceSchema": 1, "clockDomain": self._domain,
                "scope": {"exclusiveWriters": self._exclusive}, "events": self._events,
                "gaps": self._gaps}, ensure_ascii=False, separators=(",", ":")))

    def close(self):
        """Finish evidence only; never commit/rollback/close business connections."""
        with self._lock:
            if self._closed:
                return
            for connection in tuple(self._connections):
                connection._incomplete_reads()
                if connection._tx is not None:
                    self.gap("transaction_outstanding", "Capture ended without an acknowledged transaction outcome.")
            self._closed = True
            self._write({"record": "footer", "eventCount": len(self._events),
                         "gapCount": len(self._gaps), "sha256": self._digest.hexdigest()}, footer=True)
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    self._log_failed = True
                    self.gap("log_close_failed", "Raw event stream close failed.")


class _ConnectionState:
    def __setattr__(self, name, value):
        raw = self.__dict__.get("_raw")
        if name.startswith("_") or raw is None or isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
        elif hasattr(raw, name):
            setattr(raw, name, value)
        else:
            object.__setattr__(self, name, value)

    def _initialize(self, session, raw):
        self._session, self._raw, self._tx = session, raw, None
        self._cursors = weakref.WeakSet()
        if _status(raw) != 0:
            session.gap("inflight_transaction", "Connection was already in a transaction when wrapped.")

    def _ensure_tx(self):
        if self._tx is None:
            if not self._session._initialized:
                self._session.gap("missing_initialization", "Business activity preceded a consistent initial snapshot.")
            if _status(self._raw) not in (0, 4):
                self._session.gap("inflight_transaction", "Transaction started through an unobserved path.")
            self._tx = self._session._new_tx()
            self._session._event("begin", tx=self._tx)
        return self._tx

    def _incomplete_reads(self, except_cursor=None):
        for cursor in tuple(self._cursors):
            if cursor is not except_cursor:
                cursor._unfinished()

    def __del__(self):
        if self.__dict__.get("_tx") is not None:
            try:
                self._session.gap("connection_discarded", "A connection was discarded without an acknowledged transaction outcome.")
            except Exception:
                pass

    def _end(self, status):
        if self._tx is not None:
            self._session._event("end", tx=self._tx, status=status)
            self._tx = None

    def _sql(self, **fields):
        if self._tx is not None:
            fields["tx"] = self._tx
        self._session._event("sql", **fields)

    def _finish(self, status):
        self._incomplete_reads()
        self._end(status)

    def __getattr__(self, name):
        value = getattr(self._raw, name)
        if callable(value):
            def unsupported(*args, **kwargs):
                self._session.gap("unsupported_connection_method", "A connection method outside the capture profile was used: " + name[:128])
                return value(*args, **kwargs)
            return unsupported
        if name in ("pgconn",):
            self._session.gap("raw_connection_access", "Low-level connection access can bypass capture.")
        return value

    @property
    def autocommit(self):
        return self._raw.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._raw.autocommit = value


class CapturedConnection(_ConnectionState):
    def __init__(self, session, raw):
        self._initialize(session, raw)
        self._operation_lock = threading.RLock()

    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if args or kwargs.get("name") or kwargs.get("withhold"):
            self._session.gap("server_cursor_unsupported", "Named/withhold cursors are outside the initial capture profile.")
        cursor = CapturedCursor(self, raw)
        self._cursors.add(cursor)
        return cursor

    def execute(self, query, params=None, **kwargs):
        cursor = self.cursor()
        return cursor.execute(query, params, **kwargs)

    def commit(self):
        with self._operation_lock:
            self._incomplete_reads()
            before = _status(self._raw)
            try:
                result = self._raw.commit()
            except BaseException as error:
                self._sql(phase="commit-error", **_error(error))
                outcome = _commit_error_status(self._raw, error)
                if outcome == "unknown":
                    self._session.gap("commit_unknown", "COMMIT did not return an acknowledged outcome.")
                self._end(outcome)
                raise
            self._sql(phase="commit-ack")
            self._end("aborted" if before == 3 else "committed" if _status(self._raw) == 0 else "unknown")
            return result

    def rollback(self):
        with self._operation_lock:
            self._incomplete_reads()
            try:
                result = self._raw.rollback()
            except BaseException as error:
                self._sql(phase="rollback-error", **_error(error))
                self._session.gap("rollback_unknown", "ROLLBACK did not return an acknowledged outcome.")
                self._end("unknown")
                raise
            self._sql(phase="rollback-ack")
            self._end("aborted" if _status(self._raw) == 0 else "unknown")
            return result

    def close(self):
        with self._operation_lock:
            self._incomplete_reads()
            try:
                return self._raw.close()
            finally:
                if self._tx is not None:
                    self._session.gap("closed_without_outcome", "Connection closed without an acknowledged transaction outcome.")
                    self._end("unknown")

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._raw.closed:
            if self._tx is not None:
                self._session.gap("closed_without_outcome", "Connection was closed outside the wrapper.")
                self._finish("unknown")
            return None
        if exc_type:
            try:
                self.rollback()
            except Exception:
                # Preserve the business exception, matching psycopg's context.
                pass
        else:
            self.commit()
        if not getattr(self._raw, "_pool", None):
            self.close()
        return None


class AsyncCapturedConnection(_ConnectionState):
    def __init__(self, session, raw):
        self._initialize(session, raw)
        self._operation_lock = asyncio.Lock()

    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if args or kwargs.get("name") or kwargs.get("withhold"):
            self._session.gap("server_cursor_unsupported", "Named/withhold cursors are outside the initial capture profile.")
        cursor = AsyncCapturedCursor(self, raw)
        self._cursors.add(cursor)
        return cursor

    async def execute(self, query, params=None, **kwargs):
        cursor = self.cursor()
        return await cursor.execute(query, params, **kwargs)

    async def commit(self):
        async with self._operation_lock:
            self._incomplete_reads()
            before = _status(self._raw)
            try:
                result = await self._raw.commit()
            except BaseException as error:
                self._sql(phase="commit-error", **_error(error))
                outcome = _commit_error_status(self._raw, error)
                if outcome == "unknown":
                    self._session.gap("commit_unknown", "COMMIT did not return an acknowledged outcome.")
                self._end(outcome)
                raise
            self._sql(phase="commit-ack")
            self._end("aborted" if before == 3 else "committed" if _status(self._raw) == 0 else "unknown")
            return result

    async def rollback(self):
        async with self._operation_lock:
            self._incomplete_reads()
            try:
                result = await self._raw.rollback()
            except BaseException as error:
                self._sql(phase="rollback-error", **_error(error))
                self._session.gap("rollback_unknown", "ROLLBACK did not return an acknowledged outcome.")
                self._end("unknown")
                raise
            self._sql(phase="rollback-ack")
            self._end("aborted" if _status(self._raw) == 0 else "unknown")
            return result

    async def close(self):
        async with self._operation_lock:
            self._incomplete_reads()
            try:
                return await self._raw.close()
            finally:
                if self._tx is not None:
                    self._session.gap("closed_without_outcome", "Connection closed without an acknowledged transaction outcome.")
                    self._end("unknown")

    async def __aenter__(self):
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._raw.closed:
            if self._tx is not None:
                self._session.gap("closed_without_outcome", "Connection was closed outside the wrapper.")
                self._finish("unknown")
            return None
        if exc_type:
            try:
                await self.rollback()
            except Exception:
                pass
        else:
            await self.commit()
        if not getattr(self._raw, "_pool", None):
            await self.close()
        return None


class _CursorState:
    def __setattr__(self, name, value):
        raw = self.__dict__.get("_raw")
        if name.startswith("_") or raw is None or isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
        elif hasattr(raw, name):
            setattr(raw, name, value)
        else:
            object.__setattr__(self, name, value)

    def _initialize(self, connection, raw):
        self._connection, self._raw = connection, raw
        self._pending = None

    @property
    def connection(self):
        return self._connection

    def _unfinished(self):
        if self._pending is not None:
            self._connection._session.gap("unconsumed_result", "A mapped point-read result was not fully fetched before another operation or transaction end.")
            self._pending = None

    def __del__(self):
        if self.__dict__.get("_pending") is not None:
            try:
                self._unfinished()
            except Exception:
                pass

    def _prepare(self, query, params):
        conn, session = self._connection, self._connection._session
        conn._incomplete_reads()
        try:
            if isinstance(query, (str, bytes)) and len(query) > 65_536:
                raise _CaptureBudgetError("SQL text limit")
            text = query if isinstance(query, str) else query.decode("utf-8") if isinstance(query, bytes) else query.as_string(conn._raw)
            if len(text) > 65_536:
                raise _CaptureBudgetError("SQL text limit")
        except _CaptureBudgetError:
            session.gap("sql_value_budget", "SQL text exceeded the supported observation budget; the original query still goes to the driver.")
            text = None
        except Exception:
            text = None
        control = _control(text) if text is not None else None
        mapping = session._mappings.get(text)
        if control == "begin":
            if conn._tx is not None:
                session.gap("nested_begin", "BEGIN occurred inside an already observed transaction.")
            else:
                conn._ensure_tx()
        elif control in ("commit", "rollback"):
            pass
        else:
            conn._ensure_tx()
        if control is None and mapping is None:
            session.gap("unsupported_sql", "An SQL statement has no explicit point-read/write mapping.")
        if mapping is not None and getattr(conn._raw, "autocommit", False) and _status(conn._raw) == 0:
            session.gap("autocommit_unsupported", "A mapped statement ran outside an explicit transaction in autocommit mode.")
        conn._sql(phase="execute-request", sql=text, parameters=session._safe_value(params),
                  mapped=mapping is not None or control is not None)
        return mapping, control, _status(conn._raw)

    def _executed(self, mapping, control, before, params):
        conn, session = self._connection, self._connection._session
        conn._sql(phase="execute-ack", affectedRows=self._raw.rowcount)
        if control in ("commit", "rollback"):
            conn._end("aborted" if control == "rollback" or before == 3 else "committed" if _status(conn._raw) == 0 else "unknown")
            return
        if mapping is not None:
            try:
                key = session._key(mapping.table, _parameter(params, mapping.key_parameter))
                if self._raw.rowcount not in (1, -1):
                    session.gap("point_cardinality", "A mapped point statement did not affect/return exactly one row.")
                    return
                if isinstance(mapping, PointRead):
                    self._pending = (mapping, key, conn._tx, 0)
                else:
                    if self._raw.rowcount != 1:
                        session.gap("unknown_write_count", "Write row count was not confirmed.")
                        return
                    version = _parameter(params, mapping.version_parameter)
                    if not isinstance(version, str) or not version:
                        raise ValueError("version must be a nonempty string")
                    session._event("op", tx=conn._tx, op={"type": "write", "key": key, "version": version})
            except _CaptureBudgetError:
                session.gap("mapping_budget_exhausted", "The mapped logical key exceeded its observation budget.")
            except Exception:
                session.gap("mapping_failed", "The declared SQL mapping could not identify a key and unique version.")
        if control is None and _status(conn._raw) == 0 and conn._tx is not None:
            conn._finish("unknown")

    def _execute_error(self, control, error):
        conn = self._connection
        conn._sql(phase="execute-error", **_error(error))
        if control in ("commit", "rollback"):
            outcome = _commit_error_status(conn._raw, error) if control == "commit" else "unknown"
            if outcome == "unknown":
                conn._session.gap("transaction_outcome_unknown", "A transaction control command did not return acknowledgement.")
            conn._end(outcome)

    def _fetch_error(self, error):
        self._connection._sql(phase="fetch-error", **_error(error))
        self._connection._session.gap("fetch_failed", "A cursor fetch failed; returned observations may be incomplete.")

    def _rows(self, rows, exhausted=False):
        conn, session = self._connection, self._connection._session
        fields = {"phase": "fetch", "returnedRows": len(rows), "exhausted": exhausted}
        encoded_rows = session._safe_value(rows)
        # The trace contract requires rows:Array. If the outer result cannot be
        # encoded, its existing explicit gap replaces that optional field.
        if isinstance(encoded_rows, list):
            fields["rows"] = encoded_rows
        conn._sql(**fields)
        if self._pending is None:
            return
        mapping, key, tx, count = self._pending
        if conn._tx != tx or tx is None:
            session.gap("fetch_outside_transaction", "A mapped read was fetched after its transaction ended.")
            self._pending = None
            return
        for row in rows:
            count += 1
            try:
                version = _parameter(row, mapping.version_result)
                if count > 1 or not isinstance(version, str) or not version:
                    raise ValueError("point read version/cardinality invalid")
                session._event("op", tx=tx, op={"type": "read", "key": key, "version": version})
            except Exception:
                session.gap("mapping_failed", "A fetched point result did not contain the declared unique version.")
        total = self._raw.rowcount
        if exhausted or (total >= 0 and count >= total):
            if count != 1:
                session.gap("point_cardinality", "A mapped point read did not return exactly one row.")
            self._pending = None
        else:
            self._pending = (mapping, key, tx, count)

    def __getattr__(self, name):
        value = getattr(self._raw, name)
        if callable(value):
            def unsupported(*args, **kwargs):
                self._connection._session.gap("unsupported_cursor_method", "A cursor method outside the capture profile was used: " + name[:128])
                return value(*args, **kwargs)
            return unsupported
        if name == "pgresult":
            self._connection._session.gap("raw_result_access", "Low-level cursor access can bypass fetch capture.")
        return value


class CapturedCursor(_CursorState):
    def __init__(self, connection, raw):
        self._initialize(connection, raw)

    def execute(self, query, params=None, **kwargs):
        with self._connection._operation_lock:
            mapping, control, before = self._prepare(query, params)
            try:
                self._raw.execute(query, params, **kwargs)
            except BaseException as error:
                self._execute_error(control, error)
                raise
            self._executed(mapping, control, before, params)
            return self

    def fetchone(self):
        with self._connection._operation_lock:
            try:
                row = self._raw.fetchone()
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows([] if row is None else [row], exhausted=row is None)
            return row

    def fetchmany(self, size=None):
        with self._connection._operation_lock:
            try:
                rows = self._raw.fetchmany() if size is None else self._raw.fetchmany(size)
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows(rows, exhausted=not rows)
            return rows

    def fetchall(self):
        with self._connection._operation_lock:
            try:
                rows = self._raw.fetchall()
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows(rows, exhausted=True)
            return rows

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        self._unfinished()
        return self._raw.close()

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *args):
        self._unfinished()
        return self._raw.__exit__(*args)


class AsyncCapturedCursor(_CursorState):
    def __init__(self, connection, raw):
        self._initialize(connection, raw)

    async def execute(self, query, params=None, **kwargs):
        async with self._connection._operation_lock:
            mapping, control, before = self._prepare(query, params)
            try:
                await self._raw.execute(query, params, **kwargs)
            except BaseException as error:
                self._execute_error(control, error)
                raise
            self._executed(mapping, control, before, params)
            return self

    async def fetchone(self):
        async with self._connection._operation_lock:
            try:
                row = await self._raw.fetchone()
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows([] if row is None else [row], exhausted=row is None)
            return row

    async def fetchmany(self, size=None):
        async with self._connection._operation_lock:
            try:
                rows = await self._raw.fetchmany() if size is None else await self._raw.fetchmany(size)
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows(rows, exhausted=not rows)
            return rows

    async def fetchall(self):
        async with self._connection._operation_lock:
            try:
                rows = await self._raw.fetchall()
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows(rows, exhausted=True)
            return rows

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row

    async def close(self):
        self._unfinished()
        return await self._raw.close()

    async def __aenter__(self):
        await self._raw.__aenter__()
        return self

    async def __aexit__(self, *args):
        self._unfinished()
        return await self._raw.__aexit__(*args)


class _LogBudgetError(ValueError):
    pass


def load_jsonl(path, *, max_bytes=32 * 1024 * 1024, max_line_bytes=1024 * 1024,
               max_events=65_536):
    """Recover valid prefixes, marking truncated/corrupt/unclosed logs incomplete.

    The checksum detects changes, not a malicious or dishonest event producer.
    Raw framing has a separate 32 MiB budget, 1 MiB per line, and 65,536 events.
    Core normalized-document and history input budgets still apply independently.
    """
    trace = {"traceSchema": 1, "clockDomain": "unreadable-log", "scope": {"exclusiveWriters": False}, "events": [], "gaps": []}
    digest = hashlib.sha256()
    footer = None
    for limit in (max_bytes, max_line_bytes, max_events):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("raw log budgets must be positive integers")
    try:
        with Path(path).open("rb") as stream:
            number, total = 0, 0
            while True:
                # Bounded readline also bounds allocation before JSON decoding.
                raw = stream.readline(min(max_line_bytes + 1, max_bytes - total + 1))
                if not raw:
                    break
                number, total = number + 1, total + len(raw)
                if total > max_bytes or len(raw) > max_line_bytes or number > 2 * max_events + 2:
                    raise _LogBudgetError("raw log resource limit")
                if not raw.endswith(b"\n"):
                    raise ValueError("incomplete line")
                item = json.loads(raw)
                if not isinstance(item, dict):
                    raise ValueError("record must be an object")
                record = item.get("record")
                if footer is not None:
                    raise ValueError("content after footer")
                if number == 1:
                    scope = item.get("scope")
                    if (record != "header" or type(item.get("traceSchema")) is not int or item.get("traceSchema") != 1
                            or not isinstance(item.get("clockDomain"), str) or not item["clockDomain"]
                            or not isinstance(scope, dict) or set(scope) != {"exclusiveWriters"}
                            or not isinstance(scope["exclusiveWriters"], bool)):
                        raise ValueError("missing header")
                    trace["clockDomain"], trace["scope"] = item["clockDomain"], item["scope"]
                elif record == "event":
                    if len(trace["events"]) >= max_events:
                        raise _LogBudgetError("raw event limit")
                    if not isinstance(item.get("event"), dict):
                        raise ValueError("event must be an object")
                    trace["events"].append(item["event"])
                elif record == "gap":
                    if len(trace["gaps"]) >= max_events:
                        raise _LogBudgetError("raw gap limit")
                    gap = item.get("gap")
                    if (not isinstance(gap, dict) or set(gap) != {"code", "message"}
                            or not all(isinstance(gap.get(key), str) and gap[key] for key in ("code", "message"))):
                        raise ValueError("gap must contain code and message strings")
                    trace["gaps"].append(item["gap"])
                elif record == "footer":
                    footer = item
                    if (type(item.get("eventCount")) is not int or type(item.get("gapCount")) is not int
                            or item.get("eventCount") != len(trace["events"]) or item.get("gapCount") != len(trace["gaps"])
                            or item.get("sha256") != digest.hexdigest()):
                        raise ValueError("footer mismatch")
                    continue
                else:
                    raise ValueError("unrecognized record")
                digest.update(raw)
        if footer is None:
            trace["gaps"].append({"code": "log_unclosed", "message": "Capture footer is absent; the event stream may be truncated."})
    except _LogBudgetError:
        trace["gaps"].append({"code": "log_budget_exhausted", "message": "Raw log size, line, or record budget was exceeded; only a valid prefix was retained."})
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        trace["gaps"].append({"code": "log_corrupt", "message": "Raw event stream integrity could not be verified."})
    return trace
