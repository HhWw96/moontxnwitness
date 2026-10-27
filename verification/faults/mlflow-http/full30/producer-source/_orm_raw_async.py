"""Unreleased raw-protocol experiment; no ORM SQL/provenance proof is claimed.

This file intentionally lives outside the frozen release source. It uses the
existing bounded encoder/journal, never an in-memory event history. SQLAlchemy
receives the original DBAPI rows; no ORM SQL or return shape is rewritten.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import uuid

from .capture_v3 import CaptureV3Session, _control, _server_abort
from .capture import _status


class DraftAsyncObserver(CaptureV3Session):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        self.publish_snapshot({}, consistent=False)
        self.gap("orm_provenance_not_implemented", "Draft records actual DBAPI observations only; no initial/version/predicate proof is implemented.")

    def wrap_async(self, raw):
        self.activity("connect")
        with self._lock:
            if self._closed or len(self._connections) >= self._max_connections:
                self.gap("orm_connection_not_observed", "A draft connection could not be observed within the active registry.")
                return raw
            wrapped = DraftAsyncConnection(self, raw)
            self._connections.add(wrapped)
            return wrapped


class DraftAsyncConnection:
    def __init__(self, session, raw):
        self._session, self._raw = session, raw
        self._identity, self._tx = "orm-connection-" + uuid.uuid4().hex, None
        self._lock, self._cursors = asyncio.Lock(), set()
        self._last_error = None  # One bounded reference for draft exception-identity checks.
        self._savepoints, self._commit_requested = [], False
        if _status(raw) != 0:
            session.gap("orm_preexisting_transaction", "Connection already had an unobserved transaction.")
        if getattr(raw, "autocommit", False):
            session.gap("orm_autocommit_unproven", "Autocommit transitions are not supported by this draft.")

    def _begin(self):
        if self._tx is None:
            self._tx = "orm-tx-" + uuid.uuid4().hex
            self._savepoints, self._commit_requested = [], False
            self._session.emit("begin", tx=self._tx, connection=self._identity)

    def _unread(self):
        if any(cursor._pending for cursor in self._cursors):
            self._session.gap("orm_unconsumed_result", "An async DBAPI result was not fully delivered before transaction/connection end.")

    def _unknown(self, code):
        if self._tx:
            self._session.gap(code, "An async transaction outcome is unresolved; later idle rollback does not resolve it.")
            self._session.emit("disconnect", tx=self._tx)
            self._tx, self._savepoints, self._commit_requested = None, [], False

    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        if len(self._cursors) >= 128:
            self._session.gap("orm_cursor_budget", "Draft async cursor registry is bounded at 128; the new cursor runs unobserved.")
            return raw
        if args or kwargs.get("name") or kwargs.get("row_factory") or kwargs.get("withhold"):
            self._session.gap("orm_cursor_mode_unproven", "Named/custom/withhold async cursors are not supported.")
        cursor = DraftAsyncCursor(self, raw)
        self._cursors.add(cursor)
        return cursor

    async def execute(self, query, params=None, **kwargs):
        return await self.cursor().execute(query, params, **kwargs)

    @contextmanager
    def _response(self):
        response = {}
        try:
            import psycopg
            pinned = psycopg.__version__ == "3.3.6" and isinstance(self._raw, psycopg.AsyncConnection)
        except ImportError:
            pinned = False
        if not pinned or getattr(self._raw, "_pipeline", None) or getattr(self._raw, "_tpc", None):
            self._session.gap("orm_commit_response_not_observed", "Actual pinned async COMMIT result tag was not available.")
            yield response
            return
        original = self._raw._exec_command
        dictionary = getattr(self._raw, "__dict__", {})
        existed, previous = "_exec_command" in dictionary, dictionary.get("_exec_command")
        owner, seen = asyncio.current_task(), False

        def observe(command, *args, **kwargs):
            nonlocal seen
            result = yield from original(command, *args, **kwargs)
            if command == b"COMMIT":
                if asyncio.current_task() is not owner or seen:
                    self._session.gap("orm_commit_hook_concurrency", "Unexpected async COMMIT used the scoped hook.")
                else:
                    seen = True
                    tag = result.command_status if result is not None else None
                    if tag in (b"COMMIT", b"ROLLBACK"):
                        response["commandTag"] = tag.decode("ascii")
            return result

        try:
            self._raw._exec_command = observe
        except Exception:
            self._session.gap("orm_commit_hook_unavailable", "The original async commit still executes without response-tag observation.")
            yield response
            return
        try:
            yield response
        finally:
            try:
                if existed:
                    self._raw._exec_command = previous
                else:
                    del self._raw._exec_command
            except Exception:
                self._session.gap("orm_commit_hook_restore_failed", "Scoped async response observer could not restore the instance method.")

    async def commit(self):
        async with self._lock:
            self._session.activity("commit")
            self._unread()
            before, request = _status(self._raw), None
            if self._tx:
                request = self._session.emit("commit_request", tx=self._tx)
                self._commit_requested = True
            try:
                with self._response() as response:
                    result = await self._raw.commit()
            except BaseException as error:
                if self._tx and request is not None and _server_abort(self._raw, error):
                    self._session.emit("rollback_ok", tx=self._tx, commitResponse={"request": request,
                        "sqlstate": error.sqlstate, "diagnosticSqlstate": error.diag.sqlstate, "transactionStatus": "IDLE"})
                    self._tx, self._savepoints, self._commit_requested = None, [], False
                else:
                    self._unknown("orm_commit_unknown")
                raise
            if self._tx:
                if response.get("commandTag") == "ROLLBACK" and request is not None and _status(self._raw) == 0:
                    self._session.emit("rollback_ok", tx=self._tx, commitResponse={"request": request, "commandTag": "ROLLBACK"})
                elif before != 3 and _status(self._raw) == 0:
                    self._session.emit("commit_ok", tx=self._tx)
                else:
                    self._unknown("orm_commit_ack_unproven")
                self._tx, self._savepoints, self._commit_requested = None, [], False
            return result

    async def rollback(self):
        async with self._lock:
            self._session.activity("rollback")
            self._unread()
            try:
                result = await self._raw.rollback()
            except BaseException:
                self._unknown("orm_rollback_unknown")
                raise
            if self._tx:
                if not self._commit_requested and _status(self._raw) == 0:
                    self._session.emit("rollback_ok", tx=self._tx)
                    self._tx, self._savepoints = None, []
                else:
                    self._unknown("orm_rollback_unproven")
            return result

    async def close(self):
        self._unread()
        try:
            return await self._raw.close()
        finally:
            self._unknown("orm_connection_closed_unknown")

    def __getattr__(self, name):
        if name in ("transaction", "pipeline", "tpc_begin", "tpc_prepare", "tpc_commit", "tpc_rollback"):
            self._session.gap("orm_async_api_unproven", "Async lifecycle API bypasses this draft's observations.")
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._raw, name, value)
            if name in ("autocommit", "row_factory"):
                self._session.gap("orm_configuration_transition", "SQLAlchemy/driver configuration changed; no complete capture is claimed.")


class DraftAsyncCursor:
    def __init__(self, connection, raw):
        self._connection, self._session, self._raw = connection, connection._session, raw
        self._identity = "orm-cursor-" + uuid.uuid4().hex
        self._pending, self._statement, self._complete = False, None, False

    async def execute(self, query, params=None, **kwargs):
        async with self._connection._lock:
            self._session.activity("execute")
            if self._pending:
                self._session.gap("orm_result_replaced", "A new statement replaced an unconsumed result.")
            self._connection._begin()
            try:
                sql = query if isinstance(query, str) else query.as_string(self._connection._raw)
            except Exception:
                sql = "<unavailable>"
                self._session.gap("orm_sql_encoding_failed", "SQL text could not be recorded; the original object still executes.")
            fields = {"tx": self._connection._tx, "sql": sql}
            try:
                fields["parameters"] = self._session.encode(params)
            except Exception:
                self._session.gap("orm_parameter_budget", "Parameters exceeded the bounded raw encoding profile.")
            self._statement = self._session.emit("statement", **fields)
            self._session.gap("orm_sql_unmapped", "Actual ORM DBAPI SQL has no independently validated fixed provenance profile.")
            self._complete = False
            try:
                await self._raw.execute(query, params, **kwargs)
            except BaseException as error:
                self._connection._last_error = error
                self._pending = False
                self._session.emit("rows", tx=self._connection._tx, statement=self._statement,
                    rows=[], complete=False, error={"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)})
                self._session.gap("orm_statement_failed", "The original asynchronous DBAPI exception was re-raised.")
                raise
            self._pending = self._raw.description is not None
            if not self._pending:
                self._rows([], True)
            control = _control(sql)
            if control:
                kind, name = control
                stack = self._connection._savepoints
                if kind == "savepoint":
                    if len(stack) >= 64 or len(name.encode("utf-8")) > 63:
                        self._session.gap("orm_savepoint_budget", "Savepoint tracking exceeded its bounded domain.")
                    else:
                        instance = "orm-savepoint-" + uuid.uuid4().hex
                        stack.append((name, instance))
                        self._session.emit(kind, tx=self._connection._tx, name=name, instance=instance)
                else:
                    found = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][0] == name), None)
                    if found is None:
                        self._session.gap("orm_savepoint_missing", "Acknowledged savepoint target was not observed.")
                    else:
                        self._session.emit(kind, tx=self._connection._tx, instance=stack[found][1])
                        del stack[found if kind == "release" else found + 1:]
            return self

    def _rows(self, rows, complete):
        if self._complete:
            return
        try:
            encoded = self._session.encode(rows)
            self._session.emit("rows", tx=self._connection._tx, statement=self._statement, rows=encoded, complete=complete)
        except Exception:
            self._session.gap("orm_result_budget", "Actual returned rows could not be retained within the bounded encoder.")
        self._pending, self._complete = not complete, complete

    async def fetchone(self):
        async with self._connection._lock:
            self._session.activity("fetchone")
            result = await self._raw.fetchone()
            self._rows([] if result is None else [result], result is None or self._exhausted())
            return result

    async def fetchmany(self, size=None):
        async with self._connection._lock:
            self._session.activity("fetchmany")
            result = await self._raw.fetchmany() if size is None else await self._raw.fetchmany(size)
            self._rows(result, not result or self._exhausted())
            return result

    async def fetchall(self):
        async with self._connection._lock:
            self._session.activity("fetchall")
            result = await self._raw.fetchall()
            self._rows(result, True)
            return result

    def _exhausted(self):
        count, number = getattr(self._raw, "rowcount", -1), getattr(self._raw, "rownumber", None)
        return type(count) is int and count >= 0 and type(number) is int and number >= count

    async def close(self):
        if self._pending:
            self._session.gap("orm_unconsumed_result", "An async cursor closed with undelivered rows.")
        try:
            return await self._raw.close()
        finally:
            self._pending = False
            self._connection._cursors.discard(self)

    def _close(self):
        """SQLAlchemy 2.0.55's regular psycopg adapter closes this way."""
        if self._pending:
            self._session.gap("orm_unconsumed_result", "SQLAlchemy closed an async cursor with undelivered DBAPI rows.")
        try:
            return self._raw._close()
        finally:
            self._pending = False
            self._connection._cursors.discard(self)

    def __getattr__(self, name):
        if name in ("executemany", "stream", "copy"):
            self._session.gap("orm_cursor_api_unproven", "This async cursor API bypasses draft statement/result capture.")
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._raw, name, value)
