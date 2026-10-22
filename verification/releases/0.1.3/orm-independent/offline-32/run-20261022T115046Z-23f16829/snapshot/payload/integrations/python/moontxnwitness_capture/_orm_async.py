"""Same-statement ORM rewrite experiment; source carriers stay outside v3."""
from __future__ import annotations
import uuid
from .orm import VALUES, FIELDS, StructuredSQLCache, CoverageRequired, DEFAULT_CONTEXT
from ._orm_policy import (
    observe_command, observe_get, AsyncCommandCursorView)
from .capture_v3 import CaptureV3Session

from . import _orm_raw_async as raw_module

class SourceResult:
    def __init__(self, result):
        self.result, self.values = result, {}
    def get_value(self, row, column):
        key = (row, column)
        if key not in self.values:
            if len(self.values) >= 8: raise CoverageRequired("Point metadata cell budget")
            value = self.result.get_value(row, column)
            if value is not None and len(value) > 50 * 1024: raise CoverageRequired("SQL-bound source field exceeded size")
            self.values[key] = value
        return self.values[key]
    def snapshot(self):
        return {"status": int(self.result.status), "commandTag": self.result.command_status,
            "commandTuples": self.result.command_tuples, "ntuples": self.result.ntuples,
            "fields": [{"oid": self.result.ftype(i), "format": self.result.fformat(i),
                        "typmod": self.result.fmod(i), "raw": self.values.get((0, i))} for i in range(8)]}
    def __getattr__(self, name): return getattr(self.result, name)


class ReadResultFacade:
    status, binary_tuples, nfields = 2, 0, 6
    def __init__(self, actual, present):
        self._actual, self.ntuples = actual, int(present)
        self.command_status, self.command_tuples = ("SELECT " + str(int(present))).encode(), int(present)
    def get_value(self, row, column):
        return self._actual.get_value(row, column) if 0 <= row < self.ntuples and 0 <= column < 6 else None
    def __getattr__(self, name): return getattr(self._actual, name)


class ProvenanceObserver(CaptureV3Session):
    def __init__(self, path, installation, sink, *, cache_enabled=True, cache_max_entries=128,
                 cache_max_bytes=1024 * 1024, sql_context=DEFAULT_CONTEXT):
        self.installation, self.scope, self.sink = installation, installation.scope, sink
        self.cache, self.plans = StructuredSQLCache(enabled=cache_enabled, max_entries=cache_max_entries,
            max_bytes=cache_max_bytes, context=sql_context), {}
        plans = [self.cache.prepare(self.scope, "get", pk_bind=bind) for bind in ("id_1", "pk_1")]
        plans += [self.cache.prepare(self.scope, "create", pk_bind="id"), self.cache.prepare(self.scope, "delete", pk_bind="id")]
        for mask in range(1, 32):
            fields = tuple(field for i, field in enumerate(VALUES) if mask & (1 << i))
            plans.append(self.cache.prepare(self.scope, "update", fields, self.scope.schema + "_" + self.scope.table + "_id"))
        super().__init__(path, exclusive_writers=True)
        self.plans = {plan.original_sql: plan for plan in plans}
        self.publish_snapshot({key: row["version"] for key, row in installation.initial.items()}, consistent=True)
        self.gap("orm_core_source_proof_unavailable", "Experimental effect/presence carriers are separate from the compatible raw journal; public core does not validate them.")
        sink.append({"kind": "installation", "metadata": installation.metadata,
            "knownIds": self.scope.known_ids, "schema": self.scope.schema, "table": self.scope.table})

    def wrap_async(self, raw):
        self.activity("connect")
        with self._lock:
            if self._closed or len(self._connections) >= 128:
                self.gap("orm_connection_budget", "Connection runs unobserved")
                return raw
            wrapped = Connection(self, raw); self._connections.add(wrapped)
            return wrapped


class Connection(raw_module.DraftAsyncConnection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if len(self._cursors) >= 128:
            self._session.gap("orm_cursor_budget", "Cursor runs unobserved"); return raw
        if args or kwargs.get("name") or kwargs.get("row_factory") or kwargs.get("withhold"):
            self._session.gap("orm_cursor_mode_unsupported", "Unsupported cursor runs without semantic rewrite")
            cursor = raw_module.DraftAsyncCursor(self, raw)
        else:
            cursor = Cursor(self, raw)
        self._cursors.add(cursor)
        return cursor


class Cursor(raw_module.DraftAsyncCursor):
    def __init__(self, connection, raw):
        super().__init__(connection, raw)
        self._plan = self._command = self._read = self._source_result = None
        self._business_position, self._present_hint, self._params = 0, None, None

    @property
    def pgresult(self):
        if self._command: return self._command.pgresult
        if self._present_hint is not None: return ReadResultFacade(self._raw.pgresult, self._present_hint)
        return self._raw.pgresult
    @property
    def description(self):
        if self._command: return None
        value = self._raw.description
        return value[:6] if value is not None and self._present_hint is not None else value
    @property
    def rowcount(self):
        return int(self._present_hint) if self._present_hint is not None else self._raw.rowcount
    @property
    def rownumber(self):
        return None if self._command else self._business_position if self._present_hint is not None else self._raw.rownumber
    @property
    def statusmessage(self):
        return "SELECT " + str(int(self._present_hint)) if self._present_hint is not None else self._raw.statusmessage

    async def execute(self, query, params=None, **kwargs):
        self._plan = self._command = self._read = self._source_result = None
        self._present_hint = None
        candidate = self._session.plans.get(query) if isinstance(query, str) else None
        if candidate is None:
            return await super().execute(query, params, **kwargs)
        try:
            if not isinstance(params, dict): raise CoverageRequired("Pinned named parameters required")
            self._session.scope.key(params[candidate.key.pk_bind])
            plan = self._session.cache.match(self._session.scope, query, candidate.key.operation,
                candidate.key.fields, candidate.key.pk_bind)
            required = set(FIELDS) if plan.key.operation == "create" else set(plan.key.fields) | {plan.key.pk_bind}
            if set(params) != required: raise CoverageRequired("Exact original parameter layout required")
            encoded_params = self._session.encode(params)
        except Exception:
            self._session.gap("orm_parameters_unmapped", "Original parameters are outside fixed profile; original SQL still runs")
            return await super().execute(query, params, **kwargs)
        async with self._connection._lock:
            self._session.activity("execute")
            if self._pending: self._session.gap("orm_result_replaced", "Unconsumed result replaced")
            self._connection._begin()
            self._plan, self._complete, self._business_position = plan, False, 0
            self._params = encoded_params
            self._statement = self._session.emit("statement", tx=self._connection._tx, sql=query,
                executedSql=plan.observed_sql, mappingId=plan.mapping_id, parameters=encoded_params)
            try:
                await self._raw.execute(plan.observed_sql, params, **kwargs)
            except BaseException as error:
                self._connection._last_error = error; self._pending = False
                self._session.emit("rows", tx=self._connection._tx, statement=self._statement, rows=[], complete=False,
                    error={"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)})
                self._session.gap("orm_statement_failed", "Original database exception re-raised")
                raise
            self._source_result = SourceResult(self._raw.pgresult)
            try:
                if plan.result_mode == "command":
                    self._command = AsyncCommandCursorView(self._raw)
                    self._pending, self._complete = False, True
                    rows_event = self._session.emit("rows", tx=self._connection._tx, statement=self._statement, rows=[], complete=True)
                    observed = observe_command(self._session.scope, plan, self._source_result)
                    self._retain(observed, rows_event, query, params)
                else:
                    self._present_hint = self._raw.pgresult.ntuples > 0 and self._raw.pgresult.get_value(0, 0) is not None
                    self._read = observe_get(self._session.scope, plan, self._source_result, params[plan.key.pk_bind])
                    self._pending = True
            except Exception as error:
                self._session.gap("orm_source_observation_missing", "No source fact accepted; business result restoration remains active where possible")
                try:
                    self._session.sink.append({"kind": "source-gap", "statement": self._statement,
                        "tx": self._connection._tx, "errorClass": type(error).__name__, "operation": plan.key.operation,
                        "actualPGresult": self._source_result.snapshot(), "businessCommand": {
                            "tag": self.statusmessage, "rowcount": self.rowcount,
                            "description": None if self.description is None else "six-business-columns", "rownumber": self.rownumber}})
                except Exception:
                    self._session.gap("orm_source_sink_failed", "Bounded sidecar failed; business result retained")
            return self

    def _retain(self, observation, rows_event, original_sql=None, parameters=None):
        try:
            self._session.sink.append({"kind": "source-batch", "statement": self._statement,
                "businessRowsEvent": rows_event, "tx": self._connection._tx,
                "mappingId": self._plan.mapping_id, "operation": self._plan.key.operation,
                "originalSql": self._plan.original_sql, "executedSql": self._plan.observed_sql,
                "parameters": self._params, "businessCommand": {"tag": self.statusmessage,
                    "rowcount": self.rowcount, "rownumber": self.rownumber,
                    "description": None if self.description is None else [{"name": col.name, "typeCode": col.type_code} for col in self.description]},
                "actualPGresult": self._source_result.snapshot(), "observation": observation})
        except Exception:
            self._session.gap("orm_source_sink_failed", "Bounded sidecar failed; business behavior retained")

    async def _fetch(self, method, *args):
        async with self._connection._lock:
            self._session.activity(method)
            if self._command:
                return await getattr(self._command, method)(*args)
            if self._present_hint is None:
                # Unmapped results still use the original raw protocol layer.
                result = await getattr(self._raw, method)(*args)
                rows = ([] if result is None else [result]) if method == "fetchone" else result
                self._rows(rows, method == "fetchall" or not rows)
                return result
            actual = await getattr(self._raw, method)(*args)
            source_rows = ([] if actual is None else [actual]) if method == "fetchone" else actual
            business = [row[:6] for row in source_rows if row[0] is not None]
            complete = (method == "fetchall" or not source_rows or self._raw.rownumber >= self._raw.rowcount)
            self._business_position += len(business)
            if not self._complete:
                fields = {"tx": self._connection._tx, "statement": self._statement,
                    "rows": self._session.encode(business), "complete": complete,
                    "columns": [{"name": col.name, "typeCode": col.type_code} for col in self.description]}
                if business: fields["serverRows"] = self._session.encode(source_rows)
                rows_event = self._session.emit("rows", **fields)
                try:
                    observed = self._read.deliver(business, eof=complete) if self._read is not None else None
                    if observed is not None: self._retain(observed, rows_event)
                except Exception:
                    self._session.gap("orm_read_source_delivery_missing", "Actual read/EOF delivery could not be source-bound")
            self._pending, self._complete = not complete, complete
            return (business[0] if business else None) if method == "fetchone" else business

    async def fetchone(self): return await self._fetch("fetchone")
    async def fetchmany(self, *args): return await self._fetch("fetchmany", *args)
    async def fetchall(self): return await self._fetch("fetchall")
