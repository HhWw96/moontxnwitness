"""Opt-in, synchronous existing-row capture experiment, not a general SQL proxy.

Only the two generated SQL templates are rewritten. This module deliberately
depends on private v0.1.1 recorder hooks so that stable public APIs stay unchanged.
Installation, ownership checks and the actual initial snapshot share one locked
transaction. Do not start business workers before initialize() returns.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from .capture import CaptureSession, PointRead, PointWrite, Table
from .capture import CapturedConnection, CapturedCursor, _Budget, _error, _status
from ._source_inventory import implementation_bindings
from ._initialization_guard import bounded_keys, begin_initialization, confirm_initial_commit, fail_initialization
from ._provenance import (Installation, Names, Observation, ProvenanceError, ddl,
                       identifier, idle_setup, table_catalog_sql)


@dataclass(frozen=True)
class ColumnPointProfile:
    schema: str
    table: str = "items"
    key_column: str = "id"
    value_column: str = "value"

    @property
    def names(self):
        return Names(self.schema, self.table, "column", self.key_column, self.value_column)

    def __post_init__(self):
        self.names  # Validate the explicitly controlled schema and identifiers.

    @property
    def read_sql(self):
        return ("SELECT " + identifier(self.value_column) + " FROM " + self.names.business
                + " WHERE " + identifier(self.key_column) + "=%s")

    @property
    def write_sql(self):
        return ("UPDATE " + self.names.business + " SET " + identifier(self.value_column)
                + "=%s WHERE " + identifier(self.key_column) + "=%s")

    @property
    def observed_read_sql(self):
        return ("SELECT " + identifier(self.value_column) + ","
                + identifier(self.names.version_column) + "::text FROM " + self.names.business
                + " WHERE " + identifier(self.key_column) + "=%s")

    @property
    def observed_write_sql(self):
        return self.write_sql + " RETURNING " + identifier(self.names.version_column) + "::text"


def _function_source(statement):
    # Quoted schema/column identifiers can themselves contain " AS ", dollar
    # delimiters or newlines. The generator's final delimiter is absent from
    # its body, so the LAST complete header marker is unambiguous.
    delimiter = statement.rsplit("\n", 1)[-1]
    marker = " AS " + delimiter + "\n"
    start = statement.rfind(marker)
    if start < 0 or not delimiter.startswith("$mtw") or not delimiter.endswith("$"):
        raise ProvenanceError("Unexpected generated function delimiter")
    return statement[start + len(" AS ") + len(delimiter):-len(delimiter)]


def _check_business_effects(connection, table_oid):
    """Only native scalar point operations without hidden SQL-bearing features."""
    checks = [
        ("table inheritance", "SELECT count(*) FROM pg_catalog.pg_inherits WHERE inhparent=%s OR inhrelid=%s", (table_oid, table_oid)),
        ("foreign keys", "SELECT count(*) FROM pg_catalog.pg_constraint WHERE contype='f' AND (conrelid=%s OR confrelid=%s)", (table_oid, table_oid)),
        ("rewrite rules", "SELECT count(*) FROM pg_catalog.pg_rewrite WHERE ev_class=%s", (table_oid,)),
        ("CHECK/EXCLUDE constraints", "SELECT count(*) FROM pg_catalog.pg_constraint WHERE conrelid=%s AND contype IN ('c','x')", (table_oid,)),
        ("generated/non-native/non-scalar columns", "SELECT count(*) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND (a.attgenerated<>'' OR n.nspname<>'pg_catalog' OR t.typtype<>'b' OR t.typelem<>0)", (table_oid,)),
        ("expression/partial indexes", "SELECT count(*) FROM pg_catalog.pg_index WHERE indrelid=%s AND (indexprs IS NOT NULL OR indpred IS NOT NULL)", (table_oid,)),
    ]
    for label, query, params in checks:
        if connection.execute(query, params).fetchone()[0] != 0:
            raise ProvenanceError("Experimental point profile does not support " + label)


def _verify_metadata_constraints(names, suffix, shape, constraints):
    """Validate the exact fixed PG18 catalog shape, including contype='n'.

    PG18 records one NOT NULL constraint for every non-null column, including
    the columns made non-null by a primary key. Never just ignore these rows.
    See PostgreSQL 18 catalog-pg-constraint and heap.c StoreRelNotNull.
    """
    nonnull = [r for r in constraints if r[0] == "n"]
    expected_columns = {i + 1 for i, column in enumerate(shape) if column[2]}
    actual_columns = []
    for row in nonnull:
        if (len(row) != 17 or not isinstance(row[1], list) or len(row[1]) != 1
                or tuple(row[2:11]) != (False, False, True, None, None, None, " ", " ", " ")
                or tuple(row[11:]) != (True, True, 0, 0, False, False)):
            raise ProvenanceError("Installed metadata NOT NULL definition changed")
        actual_columns.append(row[1][0])
    if len(actual_columns) != len(expected_columns) or set(actual_columns) != expected_columns:
        raise ProvenanceError("Installed metadata NOT NULL column set changed")
    semantic = [r for r in constraints if r[0] != "n"]
    if any(len(row) != 17 or row[11] is not True for row in semantic):
        raise ProvenanceError("Installed metadata key constraints must be enforced")
    primary = [row for row in semantic if row[0] == "p"]
    foreign = [row for row in semantic if row[0] == "f"]
    if len(primary) != 1 or tuple(primary[0][:5]) != ("p", [1], False, False, True):
        raise ProvenanceError("Installed metadata primary key changed")
    fk_column = {"audit": 5, "state": 2}.get(suffix)
    if fk_column is None:
        if len(semantic) != 1:
            raise ProvenanceError("Unexpected installation marker constraint")
    elif (len(semantic) != 2 or len(foreign) != 1
          or tuple(foreign[0][:11]) != ("f", [fk_column], False, False, True, names.schema,
                                      names.prefix + "_audit", [1], "a", "a", "s")):
        raise ProvenanceError("Installed metadata predecessor/source constraint changed")


def verify_installation(connection, installation):
    """Fail closed on changed identities, triggers, functions or metadata shape.

    This runs while the setup SHARE lock is held. A trusted deployment must also
    forbid DDL, trigger disabling and replication-role changes during capture;
    this is not continuous tamper detection against a database administrator.
    """
    n = installation.names
    marker = connection.execute("SELECT nonce::text,mode,table_oid FROM " + n.object("installation")).fetchall()
    if marker != [(installation.nonce, "column", installation.table_oid)]:
        raise ProvenanceError("Installation marker identity changed")
    _check_business_effects(connection, installation.table_oid)
    catalog = connection.execute(table_catalog_sql(), (n.key_column, n.schema, n.table)).fetchone()
    if catalog is None or tuple(catalog) != (installation.table_oid, "r", False, True, True):
        raise ProvenanceError("Business table identity or supported profile changed")
    version = connection.execute(
        "SELECT a.atttypid='pg_catalog.uuid'::pg_catalog.regtype,a.attnotnull,a.attgenerated,a.attidentity "
        "FROM pg_catalog.pg_attribute a WHERE a.attrelid=%s AND a.attname=%s AND NOT a.attisdropped",
        (installation.table_oid, n.version_column)).fetchall()
    if version != [(True, True, "", "")]:
        raise ProvenanceError("Installed version column shape changed")
    expected_sources = [_function_source(s) for s in ddl(n) if s.startswith("CREATE FUNCTION ")]
    triggers = connection.execute(
        "SELECT t.tgname,t.tgtype,t.tgenabled,p.proname,ns.nspname,p.prosrc,p.prosecdef,"
        "p.proconfig,p.pronargs,p.prorettype='pg_catalog.trigger'::pg_catalog.regtype,l.lanname,"
        "t.tgnargs,t.tgargs,t.tgattr::text,t.tgqual IS NULL,t.tgdeferrable,t.tginitdeferred "
        "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
        "JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace "
        "JOIN pg_catalog.pg_language l ON l.oid=p.prolang "
        "WHERE t.tgrelid=%s AND NOT t.tgisinternal ORDER BY t.tgname", (installation.table_oid,)).fetchall()
    expected = {}
    for suffix, bits, source in (("before", 23, expected_sources[0]), ("after", 29, expected_sources[1])):
        expected[n.prefix + "_" + suffix] = (bits, "O", n.prefix + "_" + suffix, n.schema,
            source, False, ["search_path=pg_catalog"], 0, True, "plpgsql", 0, b"", "", True, False, False)
    if len(triggers) != 2:
        raise ProvenanceError("Exactly the two owned user triggers are required")
    for row in triggers:
        actual = list(row[1:])
        actual[11] = bytes(actual[11])  # psycopg may return bytea as memoryview.
        if row[0] not in expected or tuple(actual) != expected[row[0]]:
            raise ProvenanceError("Installed trigger or function definition changed")
    shapes = {
        "installation": [("nonce", "uuid", True), ("mode", "text", True), ("table_oid", "oid", True)],
        "audit": [("token", "uuid", True), ("key", "text", True), ("action", "text", True),
                  ("present", "boolean", True), ("predecessor", "uuid", False),
                  ("old_value", "jsonb", False), ("new_value", "jsonb", False)],
        "state": [("key", "text", True), ("token", "uuid", True), ("present", "boolean", True)]}
    for suffix, shape in shapes.items():
        target = n.object(suffix)
        rows = connection.execute(
            "SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull "
            "FROM pg_catalog.pg_attribute a WHERE a.attrelid=%s::regclass AND a.attnum>0 "
            "AND NOT a.attisdropped ORDER BY a.attnum", (target,)).fetchall()
        if rows != shape:
            raise ProvenanceError("Installed metadata columns changed")
        rel = connection.execute(
            "SELECT relkind,relrowsecurity,relforcerowsecurity,relpersistence "
            "FROM pg_catalog.pg_class WHERE oid=%s::regclass", (target,)).fetchone()
        if rel != ("r", False, False, "p"):
            raise ProvenanceError("Installed metadata relation profile changed")
        constraints = connection.execute(
            "SELECT c.contype,c.conkey::smallint[],c.condeferrable,c.condeferred,c.convalidated,"
            "rn.nspname,r.relname,c.confkey::smallint[],c.confupdtype,c.confdeltype,c.confmatchtype,"
            "c.conenforced,c.conislocal,c.coninhcount,c.conparentid,c.connoinherit,c.conperiod "
            "FROM pg_catalog.pg_constraint c LEFT JOIN pg_catalog.pg_class r ON r.oid=c.confrelid "
            "LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=r.relnamespace "
            "WHERE c.conrelid=%s::regclass ORDER BY c.contype", (target,)).fetchall()
        _verify_metadata_constraints(n, suffix, shape, constraints)
        extras = connection.execute(
            "SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal",
            (target,)).fetchone()[0]
        if extras:
            raise ProvenanceError("Unexpected metadata trigger")


class ColumnCapture(CaptureSession):
    """One generated SELECT/UPDATE profile over explicitly declared existing keys."""

    def __init__(self, profile, *, keys, exclusive_writers=False, **budgets):
        keys = bounded_keys(keys)
        self.profile, self.keys, self.installation = profile, frozenset(keys), None
        n = profile.names
        table = Table(n.schema, n.table, n.key_column, n.version_column)
        super().__init__([PointRead(profile.read_sql, table, version_result=1),
                          PointWrite(profile.write_sql, table, key_parameter=1, version_parameter=0)],
                         exclusive_writers=exclusive_writers, **budgets)

    def _publish_snapshot(self, initial):
        with self._lock:
            ack = getattr(self, "_initialization_ack", None)
            if (not isinstance(ack, dict) or ack.get("actualCommitConfirmed") is not True
                    or self._initialized or self._events or self._closed
                    or self._capture_exhausted or self._log_failed or self._gaps):
                raise ProvenanceError("A confirmed setup and usable recorder are required before publication")
            count = len(self._events)
            try:
                super()._publish_snapshot(initial)
                if (len(self._events) != count + 1 or self._events[-1]["kind"] != "snapshot"
                        or self._closed or self._capture_exhausted or self._log_failed or self._gaps):
                    raise ProvenanceError("The initial snapshot was not completely retained")
            except BaseException:
                self._initialized = False
                raise

    def initialize(self, connection):
        begin_initialization(self, connection)
        try:
            idle_setup(connection)
            from psycopg.rows import tuple_row
            if connection.row_factory is not tuple_row:
                raise ProvenanceError("Setup requires the standard psycopg tuple row factory")
            if not 180000 <= connection.info.server_version < 190000:
                raise ProvenanceError("This experimental catalog contract requires PostgreSQL 18")
            n = self.profile.names
            connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            connection.execute("LOCK TABLE " + n.business + " IN SHARE MODE")
            catalog = connection.execute(table_catalog_sql(), (n.key_column, n.schema, n.table)).fetchone()
            if catalog is None or tuple(catalog[1:]) != ("r", False, False, True):
                raise ProvenanceError("Require an ordinary text-PK table without RLS or user triggers")
            _check_business_effects(connection, catalog[0])
            rows = connection.execute("SELECT " + identifier(n.key_column) + " FROM " + n.business
                                      + " LIMIT 65").fetchall()
            if {row[0] for row in rows} != self.keys or len(rows) != len(self.keys):
                raise ProvenanceError("Declared keys must exactly match the locked existing row set")
            installation = Installation(n, str(uuid.uuid4()), catalog[0], {})
            for statement in ddl(n):
                connection.execute(statement)
            connection.execute("INSERT INTO " + n.object("installation") + " VALUES(%s,%s,%s)",
                               (installation.nonce, "column", installation.table_oid))
            verify_installation(connection, installation)
            initial = {}
            budget = _Budget(65_000, min(self._max_event_bytes - 256, self._max_session_bytes - 1536))
            cursor = connection.execute("SELECT " + identifier(n.key_column) + ","
                + identifier(n.version_column) + "::text FROM " + n.business + " LIMIT 65")
            try:
                while rows := cursor.fetchmany(64):
                    for key, token in rows:
                        if key not in self.keys:
                            raise ProvenanceError("Unexpected initial key")
                        uuid.UUID(token)
                    self._add_snapshot_rows(self._tables[0], rows, initial, budget)
            finally:
                cursor.close()
            if len(initial) != len(self.keys):
                raise ProvenanceError("Initial token snapshot was incomplete")
            # No lock-free gap between installation, verification and snapshot.
            confirm_initial_commit(self, connection)
            self.installation = installation
            self._publish_snapshot(initial)
        except BaseException:
            fail_initialization(self, connection)
            raise

    async def ainitialize(self, connection):
        raise NotImplementedError("This experimental SQL profile is synchronous only")

    def wrap(self, connection):
        if not self._initialized:
            raise ProvenanceError("Initialize and acknowledge the owned installation before wrapping business connections")
        for existing in tuple(self._connections):
            if connection is existing or connection is existing._raw:
                return existing
        captured = ProfileConnection(self, connection)
        self._connections.add(captured)
        return captured

    def connect(self, *args, **kwargs):
        if not self._initialized:
            raise ProvenanceError("Initialize before opening captured business connections")
        return super().connect(*args, **kwargs)

    def awrap(self, connection):
        raise NotImplementedError("This experimental SQL profile is synchronous only")

    async def aconnect(self, *args, **kwargs):
        raise NotImplementedError("This experimental SQL profile is synchronous only")


class ProfileConnection(CapturedConnection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        unsupported = bool(args or kwargs.get("name") or kwargs.get("withhold"))
        if unsupported:
            self._session.gap("server_cursor_unsupported", "Only an unnamed standard tuple cursor belongs to this experiment.")
        cursor = ProfileCursor(self, raw, unsupported=unsupported)
        self._cursors.add(cursor)
        return cursor


class ProfileCursor(CapturedCursor):
    def __init__(self, connection, raw, *, unsupported=False):
        super().__init__(connection, raw)
        self._mode, self._unsupported = None, unsupported

    @property
    def row_factory(self):
        return self._raw.row_factory

    @row_factory.setter
    def row_factory(self, value):
        from psycopg.rows import tuple_row
        if value is not tuple_row:
            self._connection._session.gap("unsupported_row_factory", "Changing to a custom row factory is outside this tuple-only profile.")
        self._raw.row_factory = value

    @property
    def description(self):
        if self._mode == "write":
            return None
        description = self._raw.description
        return description[:-1] if self._mode == "read" and description is not None else description

    @property
    def rownumber(self):
        return None if self._mode == "write" else self._raw.rownumber

    def execute(self, query, params=None, **kwargs):
        with self._connection._operation_lock:
            self._mode = None
            mapping, control, before = self._prepare(query, params)
            effective = query
            session = self._connection._session
            if mapping is not None:
                from psycopg.rows import tuple_row
                if self._unsupported or self._raw.row_factory is not tuple_row:
                    session.gap("unsupported_row_factory", "Only the standard tuple row factory is supported by the experimental projection.")
                    mapping = None
                else:
                    try:
                        key = params[mapping.key_parameter]
                        if not isinstance(key, str) or key not in session.keys:
                            raise ValueError("key outside declared scope")
                    except Exception:
                        session.gap("key_outside_scope", "The point operation did not target one declared existing text key.")
                        mapping = None
            if isinstance(mapping, PointRead):
                effective = session.profile.observed_read_sql
            elif isinstance(mapping, PointWrite):
                effective = session.profile.observed_write_sql
            try:
                self._raw.execute(effective, params, **kwargs)
            except BaseException as error:
                self._connection._sql(phase="execute-error", sql=effective if isinstance(effective, str) and len(effective) <= 65_536 else None,
                                      **_error(error))
                # Reuse the exact outcome handling for transaction controls.
                if control is not None:
                    self._execute_error(control, error)
                raise
            # The request contains original business SQL; this acknowledgement
            # records the actual generated SQL sent in the single driver call.
            if isinstance(mapping, PointWrite):
                self._connection._sql(phase="execute-ack", sql=effective, affectedRows=self._raw.rowcount)
                self._mode = "write"
                self._record_server_write(mapping, params)
            elif isinstance(mapping, PointRead):
                self._connection._sql(phase="execute-ack", sql=effective, affectedRows=self._raw.rowcount)
                self._mode = "read"
                if self._raw.rowcount not in (1, -1):
                    session.gap("point_cardinality", "The generated point SELECT did not return exactly one existing row.")
                else:
                    try:
                        key = session._key(mapping.table, params[mapping.key_parameter])
                        self._pending = (mapping, key, self._connection._tx, 0)
                    except Exception:
                        session.gap("mapping_failed", "The generated SELECT key could not be encoded.")
                if _status(self._connection._raw) == 0:
                    self._connection._finish("unknown")
            else:
                self._executed(mapping, control, before, params)
            return self

    def _record_server_write(self, mapping, params):
        conn, session = self._connection, self._connection._session
        try:
            # RETURNING belongs to this UPDATE. Never query audit/current rows
            # later to manufacture a write's intermediate token.
            rows = self._raw.fetchmany(2)
        except BaseException as error:
            self._fetch_error(error)
            raise
        self._rows(rows, exhausted=True)
        if self._raw.rowcount != 1 or len(rows) != 1 or not isinstance(rows[0], tuple) or len(rows[0]) != 1:
            session.gap("point_cardinality", "The generated point UPDATE did not return exactly one server token.")
        else:
            try:
                version = rows[0][0]
                uuid.UUID(version)
                key = session._key(mapping.table, params[mapping.key_parameter])
                session._event("op", tx=conn._tx, op={"type": "write", "key": key, "version": version})
            except Exception:
                session.gap("mapping_failed", "The actual UPDATE RETURNING result did not contain a UUID token.")
        if _status(conn._raw) == 0:
            conn._finish("unknown")

    def _check_business_fetch(self):
        if self._mode == "write":
            import psycopg
            if self._raw.closed:
                raise psycopg.InterfaceError("the cursor is closed")
            tag = self._raw.statusmessage
            detail = " (command status: " + tag + ")" if tag else ""
            # Match pinned psycopg's no-RETURNING fetch contract without issuing
            # another SQL statement to turn a TUPLES_OK result into COMMAND_OK.
            raise psycopg.ProgrammingError("the last operation didn't produce records" + detail)

    def fetchone(self):
        self._check_business_fetch()
        row = super().fetchone()
        return self._business_row(row)

    def _business_row(self, row):
        if self._mode != "read" or row is None:
            return row
        if not isinstance(row, tuple) or len(row) != 2:
            self._connection._session.gap("unsupported_row_factory", "An active generated result no longer has the supported tuple shape.")
            return row
        return row[:-1]

    def fetchmany(self, size=None):
        self._check_business_fetch()
        rows = super().fetchmany(size)
        return [self._business_row(row) for row in rows] if self._mode == "read" else rows

    def fetchall(self):
        self._check_business_fetch()
        rows = super().fetchall()
        return [self._business_row(row) for row in rows] if self._mode == "read" else rows
