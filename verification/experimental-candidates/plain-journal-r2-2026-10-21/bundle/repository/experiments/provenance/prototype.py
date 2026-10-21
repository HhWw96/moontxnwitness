"""Two opt-in PostgreSQL provenance experiments, not a production capture API.

All created objects are confined to an explicitly named mtw_provenance_* schema.
Only controlled text-primary-key tables and a frozen initialized key scope are
supported. Tokens identify versions; no integer or timestamp orders commits.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass


class ProvenanceError(RuntimeError):
    pass


def identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > 63:
        raise ValueError("Use a nonempty PostgreSQL identifier of at most 63 UTF-8 bytes, without NUL")
    return '"' + value.replace('"', '""') + '"'


def controlled_schema(value):
    identifier(value)
    if not value.startswith("mtw_provenance_"):
        raise ValueError("This experiment only installs inside explicit mtw_provenance_* schemas")
    return value


def qualified(schema, name):
    return identifier(schema) + "." + identifier(name)


def function_body(value):
    # Quoted identifiers may themselves contain dollar delimiters. Select a
    # delimiter absent from the entire body instead of interpolating into $$.
    number = 0
    delimiter = "$mtw$"
    while delimiter in value:
        number += 1
        delimiter = "$mtw" + str(number) + "$"
    return delimiter + "\n" + value + "\n" + delimiter


def idle_setup(connection):
    if not connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ProvenanceError("Use a dedicated idle autocommit setup connection")


@dataclass(frozen=True)
class Names:
    schema: str
    table: str
    mode: str
    key_column: str = "id"
    value_column: str = "value"

    def __post_init__(self):
        controlled_schema(self.schema)
        if self.mode not in ("column", "sidecar"):
            raise ValueError("mode must be column or sidecar")
        for value in (self.table, self.key_column, self.value_column):
            identifier(value)
        if self.key_column == self.value_column:
            raise ValueError("key and value columns must differ")

    @property
    def prefix(self):
        digest = hashlib.sha256((self.table + "\0" + self.mode).encode("utf-8")).hexdigest()[:16]
        return "mtwp_" + digest

    @property
    def business(self):
        return qualified(self.schema, self.table)

    def object(self, suffix):
        return qualified(self.schema, self.prefix + "_" + suffix)

    @property
    def version_column(self):
        return self.prefix + "_version"


@dataclass(frozen=True)
class Observation:
    key: str
    exists: bool
    value: object
    token: str

    def as_dict(self):
        return {"key": self.key, "exists": self.exists, "value": self.value, "token": self.token}


@dataclass
class Installation:
    names: Names
    nonce: str
    table_oid: int
    initial: dict[str, Observation]

    def observe(self, connection, key):
        if key not in self.initial:
            raise ProvenanceError("Key is outside the frozen initialized scope; no initial absence is invented")
        row = connection.execute(read_sql(self.names), (key,)).fetchone()
        if row is None or row[2] is None:
            raise ProvenanceError("Business row/version provenance is missing")
        exists, value, token, metadata_present = row
        if self.names.mode == "sidecar":
            if metadata_present is None or bool(metadata_present) != bool(exists):
                raise ProvenanceError("Sidecar and business visibility disagree in the same statement snapshot")
        elif exists and metadata_present is not None:
            raise ProvenanceError("A visible row also has visible absence metadata")
        elif not exists and metadata_present is not False:
            raise ProvenanceError("Absent key has no visible absence metadata")
        return Observation(key, bool(exists), value, str(token))

    def audit(self, connection):
        rows = connection.execute(
            "SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM "
            + self.names.object("audit") + " ORDER BY token"
        ).fetchall()
        columns = ("token", "key", "action", "present", "predecessor", "oldValue", "newValue")
        return [dict(zip(columns, row)) for row in rows]


def table_catalog_sql():
    return ("SELECT c.oid,c.relkind,c.relrowsecurity,"
            "EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgrelid=c.oid "
            "AND NOT t.tgisinternal AND t.tgenabled <> 'D'),"
            "EXISTS (SELECT 1 FROM pg_catalog.pg_index i JOIN pg_catalog.pg_attribute a "
            "ON a.attrelid=i.indrelid AND a.attnum=i.indkey[0] "
            "WHERE i.indrelid=c.oid AND i.indisprimary AND i.indnkeyatts=1 "
            "AND a.attname=%s AND a.atttypid='pg_catalog.text'::pg_catalog.regtype) "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relname=%s")


def read_sql(names):
    """One MVCC statement for both positive and negative observations."""
    key, value = identifier(names.key_column), identifier(names.value_column)
    token = "b." + identifier(names.version_column) if names.mode == "column" else "s.token"
    if names.mode == "column":
        token = "CASE WHEN b." + key + " IS NULL THEN s.token ELSE " + token + " END"
    return ("SELECT b." + key + " IS NOT NULL,b." + value + ",(" + token + ")::text,s.present "
            "FROM (SELECT %s::text AS wanted_key) wanted "
            "LEFT JOIN " + names.business + " b ON b." + key + "=wanted.wanted_key "
            "LEFT JOIN " + names.object("state") + " s ON s.key=wanted.wanted_key")


def ddl(names):
    """Return fully qualified, identifier-quoted DDL, with no business values."""
    audit, state, marker = (names.object(s) for s in ("audit", "state", "installation"))
    key, value, version = (identifier(v) for v in (names.key_column, names.value_column, names.version_column))
    before_fn, after_fn = names.object("before"), names.object("after")
    statements = [
        "CREATE TABLE " + marker + " (nonce uuid PRIMARY KEY,mode text NOT NULL,table_oid oid NOT NULL)",
        "CREATE TABLE " + audit + " (token uuid PRIMARY KEY,key text NOT NULL,action text NOT NULL,"
        "present boolean NOT NULL,predecessor uuid REFERENCES " + audit + "(token),"
        "old_value jsonb,new_value jsonb)",
        "CREATE TABLE " + state + " (key text PRIMARY KEY,token uuid NOT NULL REFERENCES " + audit
        + "(token),present boolean NOT NULL)",
    ]
    if names.mode == "column":
        statements.append("ALTER TABLE " + names.business + " ADD COLUMN " + version + " uuid")
        statements.append("UPDATE " + names.business + " SET " + version + "=pg_catalog.gen_random_uuid()")
        statements.append("ALTER TABLE " + names.business + " ALTER COLUMN " + version + " SET NOT NULL")
        statements.append(
            "INSERT INTO " + audit + "(token,key,action,present,predecessor,old_value,new_value) "
            "SELECT " + version + "," + key + ",'initial',true,NULL,NULL,pg_catalog.to_jsonb(" + value
            + ") FROM " + names.business
        )
    else:
        statements.append(
            "INSERT INTO " + audit + "(token,key,action,present,predecessor,old_value,new_value) "
            "SELECT pg_catalog.gen_random_uuid()," + key + ",'initial',true,NULL,NULL,pg_catalog.to_jsonb(" + value
            + ") FROM " + names.business
        )
        statements.append("INSERT INTO " + state + "(key,token,present) SELECT key,token,true FROM " + audit)

    if names.mode == "column":
        statements.append(
            "CREATE FUNCTION " + before_fn + "() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS "
            + function_body("BEGIN\n NEW." + version + " := pg_catalog.gen_random_uuid();\n RETURN NEW;\nEND")
        )
        statements.append(
            "CREATE TRIGGER " + identifier(names.prefix + "_before") + " BEFORE INSERT OR UPDATE ON "
            + names.business + " FOR EACH ROW EXECUTE FUNCTION " + before_fn + "()"
        )

    # Metadata is updated inside the business transaction. Row/state locks are
    # intentional prototype costs; they must be measured, not called transparent.
    common_start = (
        "DECLARE k text; previous uuid; previous_present boolean; next_token uuid; "
        "old_payload jsonb; new_payload jsonb; next_present boolean;\nBEGIN\n"
        " IF TG_OP='UPDATE' AND NEW." + key + " IS DISTINCT FROM OLD." + key + " THEN\n"
        "  RAISE EXCEPTION 'prototype requires immutable primary keys';\n END IF;\n"
        " IF TG_OP='DELETE' THEN k:=OLD." + key + "; ELSE k:=NEW." + key + "; END IF;\n"
        " IF TG_OP='INSERT' THEN old_payload:=NULL; ELSE old_payload:=pg_catalog.to_jsonb(OLD." + value + "); END IF;\n"
        " IF TG_OP='DELETE' THEN new_payload:=NULL; next_present:=false; "
        "ELSE new_payload:=pg_catalog.to_jsonb(NEW." + value + "); next_present:=true; END IF;\n"
    )
    if names.mode == "column":
        body = (
            " IF TG_OP='INSERT' THEN\n"
            "  SELECT token,present INTO previous,previous_present FROM " + state + " WHERE key=k FOR UPDATE;\n"
            "  IF previous IS NULL OR previous_present THEN RAISE EXCEPTION 'key not initialized absent'; END IF;\n"
            " ELSE previous:=OLD." + version + "; END IF;\n"
            " IF TG_OP='DELETE' THEN next_token:=pg_catalog.gen_random_uuid(); ELSE next_token:=NEW." + version + "; END IF;\n"
            " INSERT INTO " + audit + " VALUES(next_token,k,TG_OP,next_present,previous,old_payload,new_payload);\n"
            " IF TG_OP='DELETE' THEN\n"
            "  INSERT INTO " + state + " VALUES(k,next_token,false) ON CONFLICT(key) "
            "DO UPDATE SET token=EXCLUDED.token,present=false;\n"
            " ELSE DELETE FROM " + state + " WHERE key=k; END IF;\n"
        )
    else:
        body = (
            " SELECT token,present INTO previous,previous_present FROM " + state + " WHERE key=k FOR UPDATE;\n"
            " IF previous IS NULL THEN RAISE EXCEPTION 'key outside initialized scope'; END IF;\n"
            " IF (TG_OP='INSERT' AND previous_present) OR (TG_OP<>'INSERT' AND NOT previous_present) "
            "THEN RAISE EXCEPTION 'sidecar prior presence disagrees'; END IF;\n"
            " next_token:=pg_catalog.gen_random_uuid();\n"
            " INSERT INTO " + audit + " VALUES(next_token,k,TG_OP,next_present,previous,old_payload,new_payload);\n"
            " UPDATE " + state + " SET token=next_token,present=next_present WHERE key=k;\n"
        )
    statements.append(
        "CREATE FUNCTION " + after_fn + "() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS "
        + function_body(common_start + body + " RETURN NULL;\nEND")
    )
    statements.append(
        "CREATE TRIGGER " + identifier(names.prefix + "_after") + " AFTER INSERT OR UPDATE OR DELETE ON "
        + names.business + " FOR EACH ROW EXECUTE FUNCTION " + after_fn + "()"
    )
    return statements


def install(connection, *, schema, table, mode, missing_keys=(), key_column="id", value_column="value"):
    """Install only in a caller-owned fixture schema and return the initial facts.

    missing_keys declares initially absent keys that may later be inserted. The
    prototype's frozen scope includes these keys and every existing row. There
    is no transparent dynamically growing key-universe claim.
    """
    names = Names(schema, table, mode, key_column, value_column)
    idle_setup(connection)
    missing_keys = tuple(missing_keys)
    if not all(isinstance(key, str) for key in missing_keys) or len(set(missing_keys)) != len(missing_keys):
        raise ValueError("missing_keys must be distinct strings")
    nonce = str(uuid.uuid4())
    try:
        connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
        connection.execute("LOCK TABLE " + names.business + " IN SHARE MODE")
        catalog = connection.execute(table_catalog_sql(), (key_column, schema, table)).fetchone()
        if catalog is None or tuple(catalog[1:]) != ("r", False, False, True):
            raise ProvenanceError("Require an ordinary table, single text primary key, no RLS/user triggers")
        table_oid = catalog[0]
        existing = connection.execute("SELECT " + identifier(key_column) + " FROM " + names.business + " LIMIT 10001").fetchall()
        if len(existing) + len(missing_keys) > 10_000:
            raise ProvenanceError("Prototype initialization is limited to 10,000 declared keys")
        existing_keys = {row[0] for row in existing}
        if existing_keys.intersection(missing_keys):
            raise ProvenanceError("A declared missing key exists in the locked initial state")
        for statement in ddl(names):
            connection.execute(statement)
        connection.execute("INSERT INTO " + names.object("installation") + " VALUES(%s,%s,%s)", (nonce, mode, table_oid))
        for key in missing_keys:
            token = str(uuid.uuid4())
            connection.execute("INSERT INTO " + names.object("audit") + " VALUES(%s,%s,'initial',false,NULL,NULL,NULL)", (token, key))
            connection.execute("INSERT INTO " + names.object("state") + " VALUES(%s,%s,false)", (key, token))
        installation = Installation(names, nonce, table_oid, {})
        # Known keys are introduced from the locked snapshot facts, never from
        # a later first read. The temporary values merely allow observe's guard.
        installation.initial = {key: None for key in existing_keys.union(missing_keys)}
        initial = {key: installation.observe(connection, key) for key in sorted(installation.initial)}
        installation.initial = initial
        connection.commit()
        return installation
    except BaseException:
        try:
            connection.rollback()
        except Exception:
            pass
        raise


def uninstall(connection, installation):
    """Remove only the objects matched by this installation's nonce/OID."""
    idle_setup(connection)
    names = installation.names
    controlled_schema(names.schema)
    try:
        connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
        connection.execute("LOCK TABLE " + names.business + " IN SHARE MODE")
        marker = connection.execute("SELECT mode,table_oid FROM " + names.object("installation") + " WHERE nonce=%s", (installation.nonce,)).fetchone()
        current = connection.execute(
            "SELECT c.oid FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relname=%s", (names.schema, names.table)
        ).fetchone()
        if marker is None or tuple(marker) != (names.mode, installation.table_oid) or current != (installation.table_oid,):
            raise ProvenanceError("Installation ownership marker or business table identity does not match")
        connection.execute("DROP TRIGGER " + identifier(names.prefix + "_after") + " ON " + names.business)
        connection.execute("DROP FUNCTION " + names.object("after") + "()")
        if names.mode == "column":
            connection.execute("DROP TRIGGER " + identifier(names.prefix + "_before") + " ON " + names.business)
            connection.execute("DROP FUNCTION " + names.object("before") + "()")
            connection.execute("ALTER TABLE " + names.business + " DROP COLUMN " + identifier(names.version_column))
        for suffix in ("state", "audit", "installation"):
            connection.execute("DROP TABLE " + names.object(suffix))
        connection.commit()
    except BaseException:
        try:
            connection.rollback()
        except Exception:
            pass
        raise


def verify_audit(rows):
    """Independent graph-of-version-facts check; no order from UUID/SQL row order."""
    tokens = {row["token"]: row for row in rows}
    if len(tokens) != len(rows):
        raise ProvenanceError("Duplicate version identity")
    initial_keys, successors = set(), {}
    for row in rows:
        uuid.UUID(row["token"])
        if not isinstance(row["key"], str) or not isinstance(row["present"], bool):
            raise ProvenanceError("Invalid key or presence fact")
        if row["action"] == "initial":
            if row["predecessor"] is not None or row["oldValue"] is not None or (not row["present"] and row["newValue"] is not None):
                raise ProvenanceError("Initial version has a predecessor")
            if row["key"] in initial_keys:
                raise ProvenanceError("Key has multiple initial versions")
            initial_keys.add(row["key"])
            continue
        previous = tokens.get(row["predecessor"])
        if previous is None or previous["key"] != row["key"]:
            raise ProvenanceError("Missing or cross-key version source")
        if row["predecessor"] in successors:
            raise ProvenanceError("A single-key committed version chain forks")
        successors[row["predecessor"]] = row["token"]
        expected = {"INSERT": (False, True), "UPDATE": (True, True), "DELETE": (True, False)}.get(row["action"])
        if expected is None or (previous["present"], row["present"]) != expected:
            raise ProvenanceError("Invalid presence transition")
        if row["action"] != "INSERT" and row["oldValue"] != previous["newValue"]:
            raise ProvenanceError("Old payload does not match its declared predecessor")
        if row["action"] == "DELETE" and row["newValue"] is not None:
            raise ProvenanceError("Deletion version contains a live payload")
        if row["action"] == "INSERT" and row["oldValue"] is not None:
            raise ProvenanceError("Insertion claims an old live payload")
    finished = set()
    for token in tokens:
        path, visiting = [], set()
        while token is not None and token not in finished:
            if token in visiting:
                raise ProvenanceError("Cyclic predecessor facts")
            visiting.add(token)
            path.append(token)
            token = tokens[token]["predecessor"]
        finished.update(path)
    return {"versions": len(rows), "writes": sum(row["action"] != "initial" for row in rows),
            "ordering": "predecessor links only; UUID/row order is not commit order"}
