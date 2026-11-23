"""Explicit synchronous PostgreSQL transactions with source-bound range reads."""

from pathlib import Path
import threading

from . import configured_source_v2 as source
from .capture_v3 import _pinned_connection
from .configured_effects import PEER_SQL
from .configured_session import read_text
from .configured_source import VERSION_COLUMN, canonical
from .configured_sql_v2 import _input_value
from .configured_window_v2 import (
    SourceInputsV2, _snapshot_profile, _write_window_bundle, observe_source_snapshot_v2,
)


INPUT_FORMAT = "moontxnwitness-configured-predicate-window-input/v1"
LOG_FORMAT = "moontxnwitness-configured-predicate-transaction-log/v1"
CONTRACT = "postgres18-int64-range-insert/v1"
ISOLATIONS = ("repeatable read", "serializable")
MAX_ROWS = 128
MAX_OPERATIONS = 128
MODE_SQL = (
    "SELECT pg_catalog.jsonb_build_object('isolation',pg_catalog.current_setting('transaction_isolation'),"
    "'snapshot',pg_catalog.pg_current_snapshot()::text,'xid',pg_catalog.pg_current_xact_id_if_assigned()::text,"
    "'login',SESSION_USER,'pid',pg_catalog.pg_backend_pid(),'peer'," + PEER_SQL + ")::text"
)


def range_sql(table):
    key = "t." + source._qi(table.key.name)
    return (
        f"SELECT pg_catalog.to_jsonb(t)::text FROM {source._qt(table)} t "
        f"WHERE {key}>=%s::bigint AND {key}<%s::bigint ORDER BY {key}"
    )


def insert_sql(table):
    names = ",".join(source._qi(column.name) for column in table.columns)
    types = {"int64": "bigint", "bool": "boolean", "text": "text"}
    values = ",".join("%s::" + types[column.type] for column in table.columns)
    return (
        f"WITH mtw_inserted AS (INSERT INTO {source._qt(table)} ({names}) VALUES ({values}) RETURNING *) "
        "SELECT pg_catalog.to_jsonb(mtw_inserted)::text FROM mtw_inserted"
    )


class ConfiguredPredicateWindow:
    """Own a bounded capture scope and seal the original PostgreSQL observations."""

    def __init__(self, output, config, control, policy, installation, *, opt_in=False):
        if opt_in is not True or type(installation) is not SourceInputsV2 or config.table.key.type != "int64":
            raise ValueError("Explicit opt-in, installed V2 sources and an int64 primary key required")
        installation.validate(config, policy)
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.config, self.control, self.policy, self.installation = config, control, policy, installation
        self._lock = threading.Lock()
        self._transactions = []
        self._sequence = 0
        self._operations = 0
        self._sealed = False
        self._start = self._snapshot("start")

    def _snapshot(self, side):
        directory = self.output / side
        profile = "paged-v1"
        observe_source_snapshot_v2(self.control, directory, self.config, self.policy,
                                   self.installation, opt_in=True, snapshot_profile=profile)
        return canonical({
            "format": _snapshot_profile(profile)[0],
            "logText": read_text(directory / "snapshot.jsonl", 64 * 1024 * 1024),
            "receiptText": read_text(directory / "snapshot-receipt.json", 2 * 1024 * 1024),
        }) + "\n"

    def _event(self, *, business=False):
        with self._lock:
            if business:
                if self._operations >= MAX_OPERATIONS:
                    raise ValueError("Range-window business operation budget exhausted")
                self._operations += 1
            self._sequence += 1
            return self._sequence

    def begin(self, connection, *, isolation="repeatable read"):
        if isolation not in ISOLATIONS:
            raise ValueError("The range session requires Repeatable Read or Serializable")
        if (connection is self.control or not _pinned_connection(connection)
                or connection.autocommit is not True or int(connection.info.transaction_status) != 0):
            raise ValueError("An idle, dedicated, pinned synchronous autocommit connection is required")
        with self._lock:
            if (self._sealed or len(self._transactions) >= 32
                    or any(transaction.connection is connection for transaction in self._transactions)):
                raise ValueError("Range window is closed, full or already owns this connection")
            transaction = _RangeTransaction(self, connection, len(self._transactions) + 1, isolation)
            self._transactions.append(transaction)
        transaction._begin()
        return transaction

    def seal(self):
        with self._lock:
            if self._sealed or not self._transactions or any(not tx.closed for tx in self._transactions):
                raise ValueError("Seal requires completed, closed range transactions")
            self._sealed = True
        end = self._snapshot("end")
        result = self.output / "predicate-window.json"
        _write_window_bundle(result, {
            "format": INPUT_FORMAT, "contract": CONTRACT,
            "configSha256": self.config.sha256,
            "installationLogText": self.installation.installation_log_text,
            "installationReceiptText": self.installation.installation_receipt_text,
            "startInputText": self._start, "endInputText": end,
            "transactions": [tx._original() for tx in self._transactions],
        })
        return result


class _RangeTransaction:
    def __init__(self, window, connection, number, isolation):
        self.window, self.connection, self.isolation = window, connection, isolation
        self.id = f"range-{number}"
        self.path = window.output / f"{self.id}.jsonl"
        self.log = source._LogV2(self.path, min(window.policy.max_log_bytes, 4 * 1024 * 1024),
                                 log_format=LOG_FORMAT, contract=CONTRACT)
        self.control = source._ControlV2(connection, self.log, terminal_queries=("commit", "rollback"))
        self.opening = self.ending = 0
        self.calls = []
        self.closed = self.failed = False
        self.outcome, self.sqlstate = "unknown", None
        self.receipt = None
        self._lock = threading.RLock()

    def _begin(self):
        try:
            self.opening = self.window._event()
            source._ack(self.control, "begin", "BEGIN ISOLATION LEVEL " + self.isolation.upper(), "BEGIN")
            source._ack(self.control, "safe-path", "SET LOCAL search_path TO pg_catalog,pg_temp", "SET")
        except BaseException as error:
            self.failed = True
            self.sqlstate = getattr(error, "sqlstate", None)
            self._finish()
            raise

    def _execute(self, kind, sql, parameters, limit):
        if self.closed or self.failed:
            raise ValueError("The range transaction is closed or incomplete")
        try:
            sequence = self.window._event(business=True)
            rows, _ = self.control.command(kind, sql, parameters, max_rows=limit)
            # The explicit supported isolation keeps the snapshot used by the
            # original statement available after that statement, even on an empty read.
            source._one(self.control, "transaction-mode", MODE_SQL)
            delivery = [{key: value for key, value in row.items() if key != VERSION_COLUMN} for row in rows]
            self.calls.append({"kind": kind, "parameters": list(parameters), "sequence": sequence,
                               "delivered": delivery})
            # The caller can mutate returned dicts without changing retained evidence.
            return [dict(row) for row in delivery]
        except BaseException as error:
            self.failed = True
            self.sqlstate = getattr(error, "sqlstate", None)
            raise

    def select_range(self, lower, upper):
        config = self.window.config
        lower = _input_value(lower, "int64", config.max_text_bytes)
        upper = _input_value(upper, "int64", config.max_text_bytes)
        if lower >= upper:
            raise ValueError("A half-open range requires lower < upper")
        with self._lock:
            return self._execute("range", range_sql(config.table), (str(lower), str(upper)), MAX_ROWS)

    def insert(self, values):
        config = self.window.config
        columns = config.table.columns
        if type(values) is not dict or set(values) != {column.name for column in columns}:
            raise ValueError("One complete configured insert row required")
        params = [_input_value(values[column.name], column.type, config.max_text_bytes) for column in columns]
        params = [str(value) if column.type == "int64" else value for column, value in zip(columns, params, strict=True)]
        with self._lock:
            rows = self._execute("insert", insert_sql(config.table), params, 1)
            if len(rows) != 1:
                self.failed = True
                raise ValueError("The original insert did not return one row")
            return rows[0]

    def _finish(self):
        try:
            self.ending = self.window._event()
            self.receipt = self.log.close()
        finally:
            try:
                self.connection.close()
            finally:
                self.closed = True

    def _end(self, commit):
        with self._lock:
            if self.closed:
                raise ValueError("The range transaction is already closed")
            if commit and self.failed:
                self._end(False)
                raise ValueError("The range transaction has incomplete evidence")
            try:
                tag = "COMMIT" if commit else "ROLLBACK"
                source._ack(self.control, tag.lower(), tag, tag, state=0)
                self.outcome = "committed" if commit else "rolled-back"
            except BaseException as error:
                self.sqlstate = getattr(error, "sqlstate", None)
                if self.sqlstate == "40001" and int(self.connection.info.transaction_status) == 0:
                    self.outcome = "rolled-back"
                raise
            finally:
                self._finish()

    def commit(self):
        self._end(True)

    def rollback(self):
        self._end(False)

    def _original(self):
        return {"id": self.id, "isolation": self.isolation, "begin": self.opening, "end": self.ending,
                "outcome": self.outcome, "sqlstate": self.sqlstate, "calls": self.calls,
                "logReceipt": self.receipt, "logText": read_text(self.path, 4 * 1024 * 1024)}
