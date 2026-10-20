"""Experimental exact SQL declarations with existing business RETURNING columns.

The caller supplies a reviewed, fixed SQL profile, not arbitrary SQL inference.
Only successful existing-row conditional updates are projected as OLD-version
reads followed by NEW-version writes. A zero-row result is a coverage gap.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from capture_profile import ColumnCapture, ProfileConnection, ProfileCursor
from moontxnwitness_capture import PointRead, PointWrite, Table
from moontxnwitness_capture.capture import _status
from prototype import Names, ProvenanceError


@dataclass(frozen=True)
class ReturningPointProfile:
    schema: str
    table: str
    key_column: str
    value_column: str
    read_sql: str
    write_sql: str
    observed_read_sql: str
    observed_write_sql: str
    read_columns: int = 2
    returning_columns: int = 1
    write_key_parameter: int = 1

    @property
    def names(self):
        return Names(self.schema, self.table, "column", self.key_column, self.value_column)

    def __post_init__(self):
        self.names
        for text in (self.read_sql, self.write_sql, self.observed_read_sql, self.observed_write_sql):
            if not isinstance(text, str) or not text or len(text) > 65_536:
                raise ValueError("Declare reviewed nonempty SQL strings within the SQL budget")
        if self.read_sql == self.write_sql:
            raise ValueError("Read and update templates must differ")
        for value in (self.read_columns, self.returning_columns):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 64:
                raise ValueError("Declare 1..64 original business result columns")
        if (isinstance(self.write_key_parameter, bool)
                or not isinstance(self.write_key_parameter, int) or self.write_key_parameter < 0):
            raise ValueError("Declare a nonnegative update key parameter index")


class ReturningColumnCapture(ColumnCapture):
    """Reuse the locked installation, initialization and outcome contracts."""

    def __init__(self, profile, *, keys, exclusive_writers=False, **budgets):
        if not isinstance(profile, ReturningPointProfile):
            raise TypeError("Use an explicit reviewed ReturningPointProfile")
        super().__init__(profile, keys=keys, exclusive_writers=exclusive_writers, **budgets)
        n = profile.names
        table = Table(n.schema, n.table, n.key_column, n.version_column)
        # The same table/namespace and all recorder budgets stay unchanged. Only
        # the exact SQL selectors differ from the original one-column profile.
        self._mappings = {
            profile.read_sql: PointRead(profile.read_sql, table, version_result=profile.read_columns),
            profile.write_sql: PointWrite(profile.write_sql, table,
                                         key_parameter=profile.write_key_parameter, version_parameter=0),
        }

    def wrap(self, connection):
        if not self._initialized:
            raise ProvenanceError("Initialize and acknowledge installation before wrapping connections")
        for existing in tuple(self._connections):
            if connection is existing or connection is existing._raw:
                return existing
        captured = ReturningConnection(self, connection)
        self._connections.add(captured)
        return captured


class ReturningConnection(ProfileConnection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        unsupported = bool(args or kwargs.get("name") or kwargs.get("withhold"))
        if unsupported:
            self._session.gap("server_cursor_unsupported", "This exact profile supports unnamed tuple cursors only.")
        cursor = ReturningCursor(self, raw, unsupported=unsupported)
        self._cursors.add(cursor)
        return cursor


class ReturningCursor(ProfileCursor):
    def __init__(self, connection, raw, *, unsupported=False):
        super().__init__(connection, raw, unsupported=unsupported)
        self._business_rows = []
        self._business_position = 0
        self._business_pending = False

    @property
    def description(self):
        raw = self._raw.description
        if raw is None:
            return None
        profile = self._connection._session.profile
        if self._mode == "returning":
            return raw[:profile.returning_columns]
        if self._mode == "read":
            return raw[:profile.read_columns]
        return super().description

    @property
    def rownumber(self):
        if self._raw.closed:
            return None
        return self._business_position if self._mode == "returning" else super().rownumber

    def _unfinished(self):
        if self._business_pending:
            self._connection._session.gap("unconsumed_result", "Business RETURNING rows were not consumed before another operation or transaction end.")
            self._business_pending = False
        super()._unfinished()

    def _business_row(self, row):
        if self._mode != "read" or row is None:
            return row
        width = self._connection._session.profile.read_columns
        if not isinstance(row, tuple) or len(row) != width + 1:
            self._connection._session.gap("unsupported_row_factory", "The active result no longer has the reviewed tuple shape.")
            return row
        return row[:width]

    def _record_server_write(self, mapping, params):
        conn, session = self._connection, self._connection._session
        width = session.profile.returning_columns
        self._mode = "returning"
        self._business_rows, self._business_position = [], 0
        try:
            rows = self._raw.fetchmany(2)
        except BaseException as error:
            self._fetch_error(error)
            raise
        # This is the actual server RETURNING result, before metadata projection.
        self._rows(rows, exhausted=True)
        self._business_rows = [row[:width] if isinstance(row, tuple) else row for row in rows]
        self._business_pending = bool(rows)
        if self._raw.rowcount != 1 or len(rows) != 1:
            session.gap("conditional_update_cardinality", "A conditional update did not return exactly one existing row; failed predicates are not inferred as reads.")
        else:
            try:
                row = rows[0]
                if not isinstance(row, tuple) or len(row) != width + 2:
                    raise ValueError("RETURNING shape changed")
                old, new = row[-2:]
                old_id, new_id = uuid.UUID(old), uuid.UUID(new)
                if str(old_id) != old or str(new_id) != new or old_id == new_id:
                    raise ValueError("update did not create a distinct version")
                key = session._key(mapping.table, params[mapping.key_parameter])
                session._event("op", tx=conn._tx, op={"type": "read", "key": key, "version": old})
                session._event("op", tx=conn._tx, op={"type": "write", "key": key, "version": new})
            except Exception:
                session.gap("mapping_failed", "The same-statement OLD/NEW RETURNING metadata was not two distinct UUID versions.")
        if _status(conn._raw) == 0:
            conn._finish("unknown")

    def _returning_rows(self, size):
        from psycopg import InterfaceError
        with self._connection._operation_lock:
            if self._raw.closed:
                raise InterfaceError("the cursor is closed")
            if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
                self._connection._session.gap("unsupported_fetch_size", "Only nonnegative integer fetch sizes belong to this buffered RETURNING profile.")
                return self._raw.fetchmany(size)
            size = len(self._business_rows) if size is None else size or self._raw.arraysize
            end = min(self._business_position + size, len(self._business_rows))
            rows = self._business_rows[self._business_position:end]
            self._business_position = end
            if end == len(self._business_rows):
                self._business_pending = False
            return rows

    def fetchone(self):
        if self._mode != "returning":
            return super().fetchone()
        rows = self._returning_rows(1)
        return rows[0] if rows else None

    def fetchmany(self, size=None):
        if self._mode != "returning":
            return super().fetchmany(size)
        return self._returning_rows(0 if size is None else size)

    def fetchall(self):
        if self._mode != "returning":
            return super().fetchall()
        return self._returning_rows(None)
