"""Fixed-key CRUD/presence capture for the documented PostgreSQL 18 profile.

Every read joins the business row and all-key presence state in one MVCC SQL
statement. Owned BEFORE triggers mint versions, including deletion tombstones.
The RETURNING helpers inspect only the immutable audit row created by that same
statement. Predecessors are facts, never fabricated application read operations.
"""
from __future__ import annotations

import json
import operator
import uuid
from dataclasses import dataclass

from ._column_profile import (ColumnCapture, ProfileConnection, ProfileCursor,
                             _check_business_effects, _function_source,
                             _verify_metadata_constraints)
from .capture import CaptureSession, PointRead, PointWrite, Table
from .capture import _Budget, _error, _measure_json, _status
from ._initialization_guard import begin_initialization, confirm_initial_commit, fail_initialization
from ._provenance import (Installation, Names, ProvenanceError, function_body,
                       identifier, idle_setup, table_catalog_sql)

from ._source_inventory import implementation_bindings

__all__ = ["PresenceCapture", "PresencePointProfile", "PROJECTION", "implementation_bindings"]

PROJECTION = "column-presence-register-v0.1.2-experimental"


@dataclass(frozen=True)
class PresencePointProfile:
    schema: str
    table: str = "items"
    key_column: str = "id"
    value_column: str = "value"

    def __post_init__(self):
        self.names

    @property
    def names(self):
        # Distinct names prevent colliding with another column experiment.
        return Names(self.schema, self.table, "column", self.key_column, self.value_column)

    @property
    def read_sql(self):
        return ("SELECT " + identifier(self.value_column) + " FROM " + self.names.business
                + " WHERE " + identifier(self.key_column) + "=%s")

    @property
    def insert_sql(self):
        return ("INSERT INTO " + self.names.business + " (" + identifier(self.key_column)
                + "," + identifier(self.value_column) + ") VALUES (%s,%s)")

    @property
    def update_sql(self):
        return ("UPDATE " + self.names.business + " SET " + identifier(self.value_column)
                + "=%s WHERE " + identifier(self.key_column) + "=%s")

    @property
    def delete_sql(self):
        return "DELETE FROM " + self.names.business + " WHERE " + identifier(self.key_column) + "=%s"

    @property
    def write_sql(self):
        return self.update_sql

    @property
    def observed_read_sql(self):
        n = self.names
        k, v, token = (identifier(x) for x in (n.key_column, n.value_column, n.version_column))
        # State exists for every frozen key. Checking the business token against
        # it is part of the same snapshot; no later mutable-state source query.
        return ("SELECT b." + k + " IS NOT NULL,b." + v + ",s.token::text,s.present,b."
                + token + "::text FROM (SELECT %s::text AS wanted_key) wanted LEFT JOIN "
                + n.business + " b ON b." + k + "=wanted.wanted_key LEFT JOIN "
                + n.object("state") + " s ON s.key=wanted.wanted_key")

    def observed(self, action):
        n, token = self.names, identifier(self.names.version_column)
        if action == "insert":
            return (self.insert_sql + " RETURNING " + token + "::text,"
                    + n.object("predecessor") + "(" + token + ")::text")
        if action == "update":
            return self.update_sql + " RETURNING OLD." + token + "::text,NEW." + token + "::text"
        if action == "delete":
            return (self.delete_sql + " RETURNING OLD." + token + "::text,"
                    + n.object("delete_token") + "(OLD." + identifier(n.key_column)
                    + ",OLD." + token + ")::text")
        raise ValueError("Unknown generated point action")


def presence_ddl(n):
    """Fixed SQL; all identifiers quoted and no application values interpolated."""
    audit, state, marker = (n.object(s) for s in ("audit", "state", "installation"))
    key, value, token = (identifier(v) for v in (n.key_column, n.value_column, n.version_column))
    statements = [
        "CREATE TABLE " + marker + " (nonce uuid PRIMARY KEY,mode text NOT NULL,table_oid oid NOT NULL)",
        "CREATE TABLE " + audit + " (token uuid PRIMARY KEY,key text NOT NULL,action text NOT NULL,"
        "present boolean NOT NULL,predecessor uuid REFERENCES " + audit + "(token),old_value jsonb,new_value jsonb)",
        "CREATE UNIQUE INDEX " + identifier(n.prefix + "_successor") + " ON " + audit
        + " (predecessor) WHERE predecessor IS NOT NULL",
        "CREATE TABLE " + state + " (key text PRIMARY KEY,token uuid NOT NULL REFERENCES " + audit
        + "(token),present boolean NOT NULL)",
        "ALTER TABLE " + n.business + " ADD COLUMN " + token + " uuid",
        "UPDATE " + n.business + " SET " + token + "=pg_catalog.gen_random_uuid()",
        "ALTER TABLE " + n.business + " ALTER COLUMN " + token + " SET NOT NULL",
        "INSERT INTO " + audit + " SELECT " + token + "," + key
        + ",'initial',true,NULL,NULL,pg_catalog.to_jsonb(" + value + ") FROM " + n.business,
        "INSERT INTO " + state + " SELECT key,token,present FROM " + audit,
    ]
    body = (
        "DECLARE k text; previous uuid; was_present boolean; next_token uuid; old_payload jsonb; new_payload jsonb;\nBEGIN\n"
        " IF TG_OP<>'DELETE' AND NEW." + key + " IS NULL THEN RETURN NEW; END IF;\n"
        " IF TG_OP='UPDATE' AND NEW." + key + " IS DISTINCT FROM OLD." + key + " THEN\n"
        "  RAISE EXCEPTION 'presence profile requires immutable primary keys';\n END IF;\n"
        " IF TG_OP='DELETE' THEN k:=OLD." + key + "; ELSE k:=NEW." + key + "; END IF;\n"
        " SELECT token,present INTO previous,was_present FROM " + state + " WHERE key=k FOR UPDATE;\n"
        " IF previous IS NULL THEN RAISE EXCEPTION 'key outside initialized presence scope'; END IF;\n"
        " IF TG_OP='INSERT' THEN\n"
        "  IF was_present THEN NEW." + token + ":=pg_catalog.gen_random_uuid(); RETURN NEW; END IF;\n"
        "  old_payload:=NULL;\n ELSE\n"
        "  IF NOT was_present OR previous IS DISTINCT FROM OLD." + token
        + " THEN RAISE EXCEPTION 'presence metadata disagrees with OLD row'; END IF;\n"
        "  old_payload:=pg_catalog.to_jsonb(OLD." + value + ");\n END IF;\n"
        " next_token:=pg_catalog.gen_random_uuid();\n"
        " IF TG_OP='DELETE' THEN new_payload:=NULL; ELSE new_payload:=pg_catalog.to_jsonb(NEW."
        + value + "); NEW." + token + ":=next_token; END IF;\n"
        " INSERT INTO " + audit + " VALUES(next_token,k,TG_OP,TG_OP<>'DELETE',previous,old_payload,new_payload);\n"
        " UPDATE " + state + " SET token=next_token,present=TG_OP<>'DELETE' WHERE key=k;\n"
        " IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;\nEND"
    )
    statements.extend([
        "CREATE FUNCTION " + n.object("before")
        + "() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS " + function_body(body),
        "CREATE TRIGGER " + identifier(n.prefix + "_before") + " BEFORE INSERT OR UPDATE OR DELETE ON "
        + n.business + " FOR EACH ROW EXECUTE FUNCTION " + n.object("before") + "()",
    ])
    delete_body = (
        "DECLARE found_token uuid; found_count integer;\nBEGIN\n"
        " SELECT count(*),min(token::text)::uuid INTO found_count,found_token FROM " + audit
        + " WHERE key=target_key AND predecessor=old_token AND action='DELETE' AND NOT present;\n"
        " IF found_count<>1 THEN RAISE EXCEPTION 'same-statement deletion audit source missing or ambiguous'; END IF;\n"
        " RETURN found_token;\nEND"
    )
    predecessor_body = (
        "DECLARE source uuid; found_count integer;\nBEGIN\n"
        " SELECT count(*),min(predecessor::text)::uuid INTO found_count,source FROM " + audit
        + " WHERE token=new_token AND action='INSERT' AND present AND predecessor IS NOT NULL;\n"
        " IF found_count<>1 OR source IS NULL THEN RAISE EXCEPTION 'same-statement insertion audit source missing'; END IF;\n"
        " RETURN source;\nEND"
    )
    statements.extend([
        "CREATE FUNCTION " + n.object("delete_token") + "(target_key text,old_token uuid) RETURNS uuid "
        "LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS " + function_body(delete_body),
        "CREATE FUNCTION " + n.object("predecessor") + "(new_token uuid) RETURNS uuid "
        "LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS " + function_body(predecessor_body),
    ])
    return statements


def _business_columns(connection, n, table_oid, installed=False):
    rows = connection.execute(
        "SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.atthasdef,a.attidentity,a.attgenerated "
        "FROM pg_catalog.pg_attribute a WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
        (table_oid,)).fetchall()
    wanted = [(n.key_column, "text", False, "", ""), (n.value_column, "text", False, "", "")]
    if installed:
        wanted.append((n.version_column, "uuid", False, "", ""))
    if rows != wanted:
        raise ProvenanceError("Presence experiment requires exactly text PK and text value columns without defaults or identities")
    deferred = connection.execute(
        "SELECT count(*) FROM pg_catalog.pg_constraint WHERE conrelid=%s AND contype IN ('p','u') AND condeferrable",
        (table_oid,)).fetchone()[0]
    if deferred:
        # A BEFORE helper must not turn a deferred duplicate-key failure into
        # an earlier missing-audit exception in an added RETURNING expression.
        raise ProvenanceError("Presence experiment requires immediate nondeferrable primary/unique constraints")
    _native_indexes(connection, table_oid)


def _native_indexes(connection, relation):
    target = "%s" if isinstance(relation, int) else "%s::regclass"
    count = connection.execute(
        "SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class ci ON ci.oid=i.indexrelid "
        "JOIN pg_catalog.pg_am am ON am.oid=ci.relam WHERE i.indrelid=" + target + " AND "
        "(am.amname<>'btree' OR EXISTS (SELECT 1 FROM pg_catalog.pg_opclass oc JOIN pg_catalog.pg_namespace ns "
        "ON ns.oid=oc.opcnamespace WHERE oc.oid=ANY(i.indclass::oid[]) AND ns.nspname<>'pg_catalog'))",
        (relation,)).fetchone()[0]
    if count:
        raise ProvenanceError("Presence experiment requires native btree operator classes")


def verify_presence_installation(connection, installation):
    """Exact owned PG18 DDL verification; not protection against a trusted DBA."""
    n = installation.names
    marker = connection.execute("SELECT nonce::text,mode,table_oid FROM " + n.object("installation")).fetchall()
    if marker != [(installation.nonce, "presence", installation.table_oid)]:
        raise ProvenanceError("Presence installation identity changed")
    _check_business_effects(connection, installation.table_oid)
    catalog = connection.execute(table_catalog_sql(), (n.key_column, n.schema, n.table)).fetchone()
    if catalog != (installation.table_oid, "r", False, True, True):
        raise ProvenanceError("Presence business relation identity changed")
    _business_columns(connection, n, installation.table_oid, installed=True)
    version = connection.execute(
        "SELECT a.attnotnull FROM pg_catalog.pg_attribute a WHERE a.attrelid=%s AND a.attname=%s AND NOT a.attisdropped",
        (installation.table_oid, n.version_column)).fetchall()
    if version != [(True,)]:
        raise ProvenanceError("Presence version column must be NOT NULL")
    statements = presence_ddl(n)
    sources = [_function_source(s) for s in statements if s.startswith("CREATE FUNCTION ")]
    triggers = connection.execute(
        "SELECT t.tgname,t.tgtype,t.tgenabled,p.proname,ns.nspname,p.prosrc,p.prosecdef,p.proconfig,"
        "p.pronargs,p.prorettype='pg_catalog.trigger'::pg_catalog.regtype,l.lanname,t.tgnargs,t.tgargs,"
        "t.tgattr::text,t.tgqual IS NULL,t.tgdeferrable,t.tginitdeferred,p.provolatile "
        "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
        "JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace JOIN pg_catalog.pg_language l ON l.oid=p.prolang "
        "WHERE t.tgrelid=%s AND NOT t.tgisinternal ORDER BY t.tgname", (installation.table_oid,)).fetchall()
    if len(triggers) != 1:
        raise ProvenanceError("Exactly one owned BEFORE presence trigger is required")
    actual = list(triggers[0])
    actual[12] = bytes(actual[12])
    expected = (n.prefix + "_before", 31, "O", n.prefix + "_before", n.schema, sources[0], False,
                ["search_path=pg_catalog"], 0, True, "plpgsql", 0, b"", "", True, False, False, "v")
    if tuple(actual) != expected:
        raise ProvenanceError("Presence trigger or owned function changed")
    for suffix, args, source in (("delete_token", "text, uuid", sources[1]), ("predecessor", "uuid", sources[2])):
        functions = connection.execute(
            "SELECT p.prosrc,p.prosecdef,p.proconfig,p.provolatile,p.prorettype='pg_catalog.uuid'::pg_catalog.regtype,"
            "l.lanname,p.prokind,p.proisstrict,p.proretset,p.proparallel,p.proargnames,"
            "p.proargmodes IS NULL,p.proallargtypes IS NULL,p.pronargdefaults,p.provariadic "
            "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace "
            "JOIN pg_catalog.pg_language l ON l.oid=p.prolang WHERE ns.nspname=%s AND p.proname=%s "
            "AND pg_catalog.oidvectortypes(p.proargtypes)=%s", (n.schema, n.prefix + "_" + suffix, args)).fetchall()
        argnames = ["target_key", "old_token"] if suffix == "delete_token" else ["new_token"]
        if functions != [(source, False, ["search_path=pg_catalog"], "v", True, "plpgsql", "f", False, False, "u",
                          argnames, True, True, 0, 0)]:
            raise ProvenanceError("Presence same-statement helper changed")
    shapes = {
        "installation": [("nonce", "uuid", True), ("mode", "text", True), ("table_oid", "oid", True)],
        "audit": [("token", "uuid", True), ("key", "text", True), ("action", "text", True),
                  ("present", "boolean", True), ("predecessor", "uuid", False), ("old_value", "jsonb", False), ("new_value", "jsonb", False)],
        "state": [("key", "text", True), ("token", "uuid", True), ("present", "boolean", True)]}
    for suffix, shape in shapes.items():
        target = n.object(suffix)
        rows = connection.execute(
            "SELECT a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull FROM pg_catalog.pg_attribute a "
            "WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum", (target,)).fetchall()
        if rows != shape:
            raise ProvenanceError("Presence metadata columns changed")
        rel = connection.execute(
            "SELECT relkind,relrowsecurity,relforcerowsecurity,relpersistence FROM pg_catalog.pg_class WHERE oid=%s::regclass",
            (target,)).fetchone()
        if rel != ("r", False, False, "p"):
            raise ProvenanceError("Presence metadata relation changed")
        constraints = connection.execute(
            "SELECT c.contype,c.conkey::smallint[],c.condeferrable,c.condeferred,c.convalidated,"
            "rn.nspname,r.relname,c.confkey::smallint[],c.confupdtype,c.confdeltype,c.confmatchtype,"
            "c.conenforced,c.conislocal,c.coninhcount,c.conparentid,c.connoinherit,c.conperiod "
            "FROM pg_catalog.pg_constraint c LEFT JOIN pg_catalog.pg_class r ON r.oid=c.confrelid "
            "LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid=r.relnamespace WHERE c.conrelid=%s::regclass ORDER BY c.contype",
            (target,)).fetchall()
        _verify_metadata_constraints(n, suffix, shape, constraints)
        extras = connection.execute(
            "SELECT (SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal),"
            "(SELECT count(*) FROM pg_catalog.pg_rewrite WHERE ev_class=%s::regclass),"
            "(SELECT count(*) FROM pg_catalog.pg_inherits WHERE inhparent=%s::regclass OR inhrelid=%s::regclass)",
            (target, target, target, target)).fetchone()
        if extras != (0, 0, 0):
            raise ProvenanceError("Unexpected presence metadata trigger, rule or inheritance")
        _native_indexes(connection, target)
        indexes = connection.execute(
            "SELECT ci.relname,i.indisprimary,i.indisunique,i.indisvalid,i.indisready,i.indnkeyatts,i.indnatts,"
            "i.indkey::text,pg_catalog.pg_get_expr(i.indpred,i.indrelid),i.indexprs IS NULL "
            "FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class ci ON ci.oid=i.indexrelid "
            "WHERE i.indrelid=%s::regclass ORDER BY i.indisprimary DESC,ci.relname", (target,)).fetchall()
        expected_count = 2 if suffix == "audit" else 1
        if len(indexes) != expected_count or tuple(indexes[0][1:]) != (True, True, True, True, 1, 1, "1", None, True):
            raise ProvenanceError("Presence metadata primary index changed")
        if suffix == "audit" and tuple(indexes[1]) != (n.prefix + "_successor", False, True, True, True, 1, 1, "5", "(predecessor IS NOT NULL)", True):
            raise ProvenanceError("Unique immutable predecessor index changed")


class PresenceCapture(ColumnCapture):
    """Explicit generated templates over a frozen present-or-absent text-key set."""

    def __init__(self, profile, *, keys, exclusive_writers=False, **budgets):
        if not isinstance(profile, PresencePointProfile):
            raise TypeError("Use a generated PresencePointProfile")
        if budgets.get("jsonl_path") is not None:
            raise ValueError("traceSchema:2 uses complete document snapshots; jsonl_path requires the v1 profile")
        super().__init__(profile, keys=keys, exclusive_writers=exclusive_writers, **budgets)
        table = self._tables[0]
        self._mappings = {profile.read_sql: PointRead(profile.read_sql, table),
                          profile.insert_sql: PointWrite(profile.insert_sql, table, key_parameter=0),
                          profile.update_sql: PointWrite(profile.update_sql, table, key_parameter=1),
                          profile.delete_sql: PointWrite(profile.delete_sql, table, key_parameter=0)}
        self._presence_initial, self._presence_reads, self._presence_writes = [], [], []

    def initialize(self, connection):
        begin_initialization(self, connection)
        try:
            idle_setup(connection)
            from psycopg.rows import tuple_row
            if connection.row_factory is not tuple_row or not 180000 <= connection.info.server_version < 190000:
                raise ProvenanceError("Presence capture requires PostgreSQL 18 and standard tuple rows")
            n = self.profile.names
            connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            connection.execute("LOCK TABLE " + n.business + " IN SHARE MODE")
            catalog = connection.execute(table_catalog_sql(), (n.key_column, n.schema, n.table)).fetchone()
            if catalog is None or tuple(catalog[1:]) != ("r", False, False, True):
                raise ProvenanceError("Require an ordinary text-PK table without RLS/user triggers")
            _check_business_effects(connection, catalog[0])
            _business_columns(connection, n, catalog[0])
            rows = connection.execute("SELECT " + identifier(n.key_column) + " FROM " + n.business + " LIMIT 65").fetchall()
            existing = {row[0] for row in rows}
            if len(existing) != len(rows) or not existing.issubset(self.keys):
                raise ProvenanceError("Declared presence scope must contain every locked existing key")
            installation = Installation(n, str(uuid.uuid4()), catalog[0], {})
            for statement in presence_ddl(n):
                connection.execute(statement)
            connection.execute("INSERT INTO " + n.object("installation") + " VALUES(%s,%s,%s)",
                               (installation.nonce, "presence", installation.table_oid))
            for key in sorted(self.keys - existing):
                absent = str(uuid.uuid4())
                connection.execute("INSERT INTO " + n.object("audit") + " VALUES(%s,%s,'initial',false,NULL,NULL,NULL)", (absent, key))
                connection.execute("INSERT INTO " + n.object("state") + " VALUES(%s,%s,false)", (key, absent))
            verify_presence_installation(connection, installation)
            initial, facts = {}, []
            budget = _Budget(65_000, min(self._max_event_bytes - 512, self._max_session_bytes - 1536))
            for key in sorted(self.keys):
                row = connection.execute(self.profile.observed_read_sql, (key,)).fetchone()
                present, token = _observation(row)
                self._add_snapshot_rows(self._tables[0], [(key, token)], initial, budget)
                facts.append({"key": self._key(self._tables[0], key), "version": token, "present": present})
            fact_budget = _Budget(65_536, self._max_session_bytes - 1536)
            _measure_json(facts, fact_budget)
            if (self._retained_bytes + fact_budget.used_bytes + budget.used_bytes + 1024 > self._max_session_bytes
                    or self._retained_nodes + fact_budget.used_nodes + budget.used_nodes + 32 > self._max_session_nodes):
                raise ProvenanceError("Presence initial facts exceed the retained evidence budget")
            confirm_initial_commit(self, connection)
            self.installation = installation
            with self._lock:
                self._retained_bytes += fact_budget.used_bytes
                self._retained_nodes += fact_budget.used_nodes
                self._presence_initial = facts
                self._publish_snapshot(initial)
        except BaseException:
            fail_initialization(self, connection)
            self._presence_initial = []
            raise

    def wrap(self, connection):
        if not self._initialized:
            raise ProvenanceError("Initialize and acknowledge presence installation before wrapping connections")
        for existing in tuple(self._connections):
            if connection is existing or connection is existing._raw:
                return existing
        captured = PresenceConnection(self, connection)
        self._connections.add(captured)
        return captured

    def _fact_event(self, op_type, *, tx, key, token, **metadata):
        with self._lock:
            fact = {"seq": len(self._events) + 1, "tx": tx, "key": key, "version": token,
                    **metadata}
            budget = _Budget(32, 2048 + len(key) * 6)
            try:
                _measure_json(fact, budget)
                if (len(self._presence_writes) + len(self._presence_reads) >= 10_000
                        or self._retained_bytes + budget.used_bytes > self._max_session_bytes - 1024
                        or self._retained_nodes + budget.used_nodes > self._max_session_nodes - 32):
                    raise ValueError("presence fact budget")
            except Exception:
                self.gap("presence_fact_budget", "Presence predecessor facts exceeded the retained evidence budget.")
                return
            self._retained_bytes += budget.used_bytes
            self._retained_nodes += budget.used_nodes
            count = len(self._events)
            self._event("op", tx=tx, op={"type": op_type, "key": key, "version": token})
            if len(self._events) == count + 1:
                (self._presence_writes if op_type == "write" else self._presence_reads).append(fact)
            else:
                self._retained_bytes -= budget.used_bytes
                self._retained_nodes -= budget.used_nodes

    def document(self):
        with self._lock:
            result = super().document()
            result["traceSchema"] = 2
            result["presenceFacts"] = json.loads(json.dumps({"schema": 1, "projection": PROJECTION,
                "initial": self._presence_initial, "reads": self._presence_reads,
                "writes": self._presence_writes}, ensure_ascii=False))
            return result

    def uninstall(self, connection):
        if self.installation is None:
            raise ProvenanceError("No acknowledged presence installation")
        idle_setup(connection)
        n = self.profile.names
        try:
            connection.execute("BEGIN")
            connection.execute("LOCK TABLE " + n.business + " IN ACCESS EXCLUSIVE MODE")
            verify_presence_installation(connection, self.installation)
            connection.execute("DROP TRIGGER " + identifier(n.prefix + "_before") + " ON " + n.business)
            for suffix, args in (("before", ""), ("delete_token", "text,uuid"), ("predecessor", "uuid")):
                connection.execute("DROP FUNCTION " + n.object(suffix) + "(" + args + ")")
            connection.execute("ALTER TABLE " + n.business + " DROP COLUMN " + identifier(n.version_column))
            for suffix in ("state", "audit", "installation"):
                connection.execute("DROP TABLE " + n.object(suffix))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Not a canonical UUID")
    return value


def _observation(row):
    if not isinstance(row, tuple) or len(row) != 5:
        raise ProvenanceError("Presence observation must have the generated five-column tuple shape")
    exists, value, token, present, business_token = row
    if not isinstance(exists, bool) or not isinstance(present, bool) or exists != present:
        raise ProvenanceError("Business and presence visibility disagree in one SQL snapshot")
    _uuid(token)
    if (exists and business_token != token) or (not exists and (business_token is not None or value is not None)):
        raise ProvenanceError("Live row token and same-snapshot presence token disagree")
    return exists, token


class PresenceConnection(ProfileConnection):
    def cursor(self, *args, **kwargs):
        raw = self._raw.cursor(*args, **kwargs)
        unsupported = bool(args or kwargs.get("name") or kwargs.get("withhold"))
        if unsupported:
            self._session.gap("server_cursor_unsupported", "Presence experiment supports unnamed tuple cursors only.")
        cursor = PresenceCursor(self, raw, unsupported=unsupported)
        self._cursors.add(cursor)
        return cursor


class PresenceCursor(ProfileCursor):
    def __init__(self, connection, raw, *, unsupported=False):
        super().__init__(connection, raw, unsupported=unsupported)
        self._business_rows, self._position, self._read_token, self._read_key = [], 0, None, None
        self._read_tx, self._read_present = None, None

    @property
    def description(self):
        if self._mode == "presence_read":
            raw = self._raw.description
            return None if raw is None else raw[1:2]
        return super().description

    @property
    def rowcount(self):
        return len(self._business_rows) if self._mode == "presence_read" and not self._raw.closed else self._raw.rowcount

    @property
    def rownumber(self):
        if self._raw.closed:
            return None
        return self._position if self._mode == "presence_read" else super().rownumber

    @property
    def statusmessage(self):
        return "SELECT " + str(len(self._business_rows)) if self._mode == "presence_read" and not self._raw.closed else self._raw.statusmessage

    def execute(self, query, params=None, **kwargs):
        with self._connection._operation_lock:
            self._mode = None
            mapping, control, before = self._prepare(query, params)
            session, effective, action = self._connection._session, query, None
            self._business_rows, self._position, self._read_token = [], 0, None
            if mapping is not None:
                from psycopg.rows import tuple_row
                try:
                    if self._unsupported or self._raw.row_factory is not tuple_row:
                        raise ValueError("Unsupported cursor")
                    key = params[mapping.key_parameter]
                    if not isinstance(key, str) or key not in session.keys:
                        raise ValueError("Key outside scope")
                except Exception:
                    session.gap("presence_scope_unsupported", "Only declared fixed text keys and ordinary tuple cursors can be rewritten.")
                    mapping = None
            if isinstance(mapping, PointRead):
                effective = session.profile.observed_read_sql
            elif mapping is not None:
                action = {session.profile.insert_sql: "insert", session.profile.update_sql: "update", session.profile.delete_sql: "delete"}[mapping.sql]
                effective = session.profile.observed(action)
            try:
                self._raw.execute(effective, params, **kwargs)
            except BaseException as error:
                self._connection._sql(phase="execute-error", sql=effective if isinstance(effective, str) and len(effective) <= 65_536 else None, **_error(error))
                if control is not None:
                    self._execute_error(control, error)
                raise
            if mapping is None:
                self._executed(mapping, control, before, params)
                return self
            self._connection._sql(phase="execute-ack", sql=effective, affectedRows=self._raw.rowcount)
            try:
                rows = self._raw.fetchmany(2)
            except BaseException as error:
                self._fetch_error(error)
                raise
            self._rows(rows, exhausted=True)  # Original server evidence, not delivered business rows.
            try:
                logical = session._key(mapping.table, key)
            except Exception:
                session.gap("mapping_budget_exhausted", "The logical presence key exceeded the recorder budget.")
                logical = None
            if isinstance(mapping, PointRead):
                self._mode = "presence_read"
                if len(rows) == 1 and isinstance(rows[0], tuple) and len(rows[0]) == 5 and isinstance(rows[0][0], bool):
                    self._business_rows = [(rows[0][1],)] if rows[0][0] else []
                try:
                    if len(rows) != 1 or self._raw.rowcount != 1:
                        raise ProvenanceError("Missing or duplicate fixed-key presence observation")
                    exists, token = _observation(rows[0])
                    if logical is None:
                        raise ProvenanceError("Logical key unavailable")
                    self._read_token, self._read_key, self._read_tx = token, logical, self._connection._tx
                    self._read_present = exists
                    self._pending = (mapping, logical, self._read_tx, 0)
                except Exception:
                    session.gap("presence_observation_invalid", "The same-statement business/state tuple did not prove presence or absence.")
            else:
                self._mode = "write"  # Preserve original no-RETURNING fetch behavior.
                try:
                    if len(rows) != 1 or self._raw.rowcount != 1 or not isinstance(rows[0], tuple) or len(rows[0]) != 2:
                        raise ValueError("Point DML did not affect one row")
                    first, second = (_uuid(value) for value in rows[0])
                    token, predecessor = (first, second) if action == "insert" else (second, first)
                    if token == predecessor or logical is None:
                        raise ValueError("No new version")
                    old_present, new_present = {"insert": (False, True), "update": (True, True), "delete": (True, False)}[action]
                    session._fact_event("write", tx=self._connection._tx, key=logical, token=token,
                        predecessor=predecessor, oldPresent=old_present, newPresent=new_present, action=action)
                except Exception:
                    session.gap("presence_write_unproven", "The point DML did not return exactly one distinct write and immutable predecessor token.")
            if _status(self._connection._raw) == 0:
                self._connection._finish("unknown")
            return self

    def _presence_fetch(self, size):
        from psycopg import InterfaceError
        with self._connection._operation_lock:
            if self._raw.closed:
                raise InterfaceError("the cursor is closed")
            all_rows = size is None
            if all_rows:
                size = len(self._business_rows)
            else:
                try:
                    size = operator.index(size or self._raw.arraysize)
                except TypeError:
                    # Keep the driver's actual invalid-size error identity/type.
                    return self._raw.fetchmany(size)
                if size < 0:
                    self._connection._session.gap("unsupported_fetch_size", "Negative fetch sizes are outside the presence observer contract.")
                    return []
                if size == 0:
                    return []  # arraysize=0 does not inspect EOF or consume a row.
            end = min(len(self._business_rows), self._position + size)
            rows = self._business_rows[self._position:end]
            self._position = end
            if self._pending is not None:
                conn, session = self._connection, self._connection._session
                if conn._tx != self._read_tx or self._read_tx is None:
                    session.gap("fetch_outside_transaction", "A positive row or negative EOF was fetched after its transaction ended.")
                elif rows or not self._business_rows:
                    session._fact_event("read", tx=self._read_tx, key=self._read_key, token=self._read_token, present=self._read_present)
                self._pending = None
            return rows

    def fetchone(self):
        if self._mode != "presence_read":
            return super().fetchone()
        rows = self._presence_fetch(1)
        return rows[0] if rows else None

    def fetchmany(self, size=None):
        if self._mode != "presence_read":
            return super().fetchmany(size)
        return self._presence_fetch(0 if size is None else size)

    def fetchall(self):
        if self._mode != "presence_read":
            return super().fetchall()
        return self._presence_fetch(None)
