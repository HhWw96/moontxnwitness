"""Opt-in, fixed-key dislock provenance migration for a fresh controlled schema.

BEFORE candidates are not actual effects: INSERT ... ON CONFLICT can execute its
BEFORE INSERT trigger without inserting a row. Only AFTER actual I/U advances
state and adds an effect ledger row. No commit order is inferred from UUIDs.
"""
from __future__ import annotations

import hashlib
import copy
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/provenance"))
from prototype import ProvenanceError, controlled_schema, function_body, idle_setup
from capture_profile import _check_business_effects
from v3_registry import PROFILE, identifier, registry


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Installation:
    def __init__(self, schema, table, keys, nonce):
        self.schema, self.table, self.keys, self.nonce = schema, table, tuple(keys), nonce
        self.version_column = "_mtw_v3_version"
        self.table_sql = self.object(table)
        self.sources = self._sources()
        self.metadata = self.initial = self.initial_state = self.table_oid = self.ddl_sha256 = None
        self.catalog, self.window = {"business": None, "owned": {}}, []
        self.function_catalog = {}

    def object(self, name):
        return identifier(self.schema) + "." + identifier(name)

    def _sources(self):
        state, candidates, effects = (self.object("_mtw_v3_" + n) for n in ("state", "candidates", "effects"))
        token = identifier(self.version_column)
        before = f"""
DECLARE previous uuid; was_present boolean;
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'dislock v3 profile does not support DELETE'; END IF;
  IF NEW.key IS NULL OR NEW.value IS NULL OR NEW.expire_at IS NULL THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND NEW.key IS DISTINCT FROM OLD.key THEN RAISE EXCEPTION 'dislock v3 key mutation unsupported'; END IF;
  SELECT token,present INTO previous,was_present FROM {state} WHERE key=NEW.key FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'dislock v3 key outside declared domain'; END IF;
  IF TG_OP='UPDATE' AND (NOT was_present OR previous IS DISTINCT FROM OLD.{token}) THEN
    RAISE EXCEPTION 'dislock v3 predecessor state mismatch';
  END IF;
  NEW.{token}:=pg_catalog.gen_random_uuid();
  INSERT INTO {candidates}(token,key,predecessor,action,owner,expire_at)
    VALUES(NEW.{token},NEW.key,previous,TG_OP,NEW.value,NEW.expire_at);
  RETURN NEW;
END
"""
        after = f"""
DECLARE previous uuid; candidate_key text; candidate_action text; changed integer;
BEGIN
  SELECT predecessor,key,action INTO STRICT previous,candidate_key,candidate_action
    FROM {candidates} WHERE token=NEW.{token};
  IF candidate_key IS DISTINCT FROM NEW.key OR candidate_action<>TG_OP THEN
    RAISE EXCEPTION 'dislock v3 candidate does not match actual effect';
  END IF;
  UPDATE {state} SET token=NEW.{token},present=true WHERE key=NEW.key AND token=previous;
  GET DIAGNOSTICS changed=ROW_COUNT;
  IF changed<>1 THEN RAISE EXCEPTION 'dislock v3 actual effect source mismatch'; END IF;
  INSERT INTO {effects}(token,key,predecessor,action,owner,expire_at)
    VALUES(NEW.{token},NEW.key,previous,TG_OP,NEW.value,NEW.expire_at);
  RETURN NEW;
END
"""
        predecessor = f"""
DECLARE previous text; matches integer;
BEGIN
  SELECT pg_catalog.count(*)::integer,pg_catalog.min(predecessor::text)
    INTO matches,previous FROM {candidates} WHERE token=p_token::uuid;
  IF matches<>1 THEN RAISE EXCEPTION 'dislock v3 unique immutable candidate missing'; END IF;
  RETURN previous;
END
"""
        return {"before": before, "after": after, "predecessor": predecessor}

    def ddl(self):
        statements = []
        for name in ("before", "after", "predecessor"):
            signature = "p_token text" if name == "predecessor" else ""
            returns = "text" if name == "predecessor" else "trigger"
            statements.append("CREATE FUNCTION " + self.object("_mtw_v3_" + name) + "(" + signature + ") RETURNS "
                + returns + " LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS " + function_body(self.sources[name]))
        statements += ["CREATE TRIGGER " + identifier("_mtw_v3_before") + " BEFORE INSERT OR UPDATE OR DELETE ON "
            + self.table_sql + " FOR EACH ROW EXECUTE FUNCTION " + self.object("_mtw_v3_before") + "()",
            "CREATE TRIGGER " + identifier("_mtw_v3_after") + " AFTER INSERT OR UPDATE ON "
            + self.table_sql + " FOR EACH ROW EXECUTE FUNCTION " + self.object("_mtw_v3_after") + "()"]
        return statements

    def _business(self, connection, *, installed):
        row = connection.execute("SELECT c.oid,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.relpersistence "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relname=%s", (self.schema, self.table)).fetchone()
        if row is None or tuple(row[1:]) != ("r", False, False, "p"):
            raise ProvenanceError("A permanent ordinary business table without RLS is required")
        if self.table_oid is not None and row[0] != self.table_oid:
            raise ProvenanceError("Business relation OID changed")
        self.table_oid = row[0]
        relation = row
        _check_business_effects(connection, self.table_oid)
        columns = connection.execute("SELECT a.attname,a.atttypid::pg_catalog.regtype::text,a.attnotnull,a.attgenerated,a.attidentity "
            "FROM pg_catalog.pg_attribute a WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum", (self.table_oid,)).fetchall()
        expected = [("key", "text", True, "", ""), ("value", "text", True, "", ""),
                    ("expire_at", "timestamp with time zone", True, "", "")]
        if installed:
            expected.append((self.version_column, "uuid", True, "", ""))
        if columns != expected:
            raise ProvenanceError("Exact upstream three-column timestamptz table shape is required")
        constraints = connection.execute("SELECT contype,conkey::smallint[],convalidated,conenforced,condeferrable,condeferred "
            "FROM pg_catalog.pg_constraint WHERE conrelid=%s ORDER BY contype,conkey", (self.table_oid,)).fetchall()
        expected_n = 4 if installed else 3
        semantic = [r for r in constraints if r[0] != "n"]
        notnull = [r for r in constraints if r[0] == "n"]
        if semantic != [("p", [1], True, True, False, False)] or len(notnull) != expected_n or {tuple(r[1]) for r in notnull} != {(n,) for n in range(1, expected_n + 1)} or any(tuple(r[2:]) != (True, True, False, False) for r in notnull):
            raise ProvenanceError("Only the original primary key and exact NOT NULL constraints are supported")
        bad_collation = connection.execute("SELECT count(*) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_collation c ON c.oid=a.attcollation "
            "WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND NOT c.collisdeterministic", (self.table_oid,)).fetchone()[0]
        if bad_collation:
            raise ProvenanceError("Nondeterministic text collation is unsupported")
        self.catalog["business"] = self._catalog_entry(connection, self.table_oid, relation, columns, constraints)

    def _catalog_entry(self, connection, oid, relation, columns, constraints):
        checks = {
            "foreignKeys": ("SELECT count(*) FROM pg_catalog.pg_constraint WHERE contype='f' AND (conrelid=%s OR confrelid=%s)", (oid, oid)),
            "rewriteRules": ("SELECT count(*) FROM pg_catalog.pg_rewrite WHERE ev_class=%s", (oid,)),
            "checkConstraints": ("SELECT count(*) FROM pg_catalog.pg_constraint WHERE conrelid=%s AND contype='c'", (oid,)),
            "exclusionConstraints": ("SELECT count(*) FROM pg_catalog.pg_constraint WHERE conrelid=%s AND contype='x'", (oid,)),
            "generatedColumns": ("SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped AND attgenerated<>''", (oid,)),
            "expressionIndexes": ("SELECT count(*) FROM pg_catalog.pg_index WHERE indrelid=%s AND indexprs IS NOT NULL", (oid,)),
            "partialIndexes": ("SELECT count(*) FROM pg_catalog.pg_index WHERE indrelid=%s AND indpred IS NOT NULL", (oid,)),
            "customTypes": ("SELECT count(*) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND (n.nspname<>'pg_catalog' OR t.typtype<>'b' OR t.typelem<>0)", (oid,)),
            "inheritance": ("SELECT count(*) FROM pg_catalog.pg_inherits WHERE inhparent=%s OR inhrelid=%s", (oid, oid)),
            "nondeterministicCollations": ("SELECT count(*) FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_collation c ON c.oid=a.attcollation WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND NOT c.collisdeterministic", (oid,)),
            "customIndexOperators": ("SELECT count(*) FROM pg_catalog.pg_index i CROSS JOIN LATERAL pg_catalog.unnest(i.indclass::oid[]) cl(oid) JOIN pg_catalog.pg_opclass o ON o.oid=cl.oid JOIN pg_catalog.pg_namespace n ON n.oid=o.opcnamespace WHERE i.indrelid=%s AND n.nspname<>'pg_catalog'", (oid,)),
            "nonBtreeIndexes": ("SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid JOIN pg_catalog.pg_am a ON a.oid=c.relam WHERE i.indrelid=%s AND a.amname<>'btree'", (oid,)),
            "nondeterministicIndexCollations": ("SELECT count(*) FROM pg_catalog.pg_index i CROSS JOIN LATERAL pg_catalog.unnest(i.indcollation::oid[]) cl(oid) JOIN pg_catalog.pg_collation c ON c.oid=cl.oid WHERE i.indrelid=%s AND NOT c.collisdeterministic", (oid,)),
        }
        counts = {name: connection.execute(sql, args).fetchone()[0] for name, (sql, args) in checks.items()}
        if any(counts.values()):
            raise ProvenanceError("A catalog feature can execute unobserved SQL or change the fixed profile")
        triggers = connection.execute("SELECT oid FROM pg_catalog.pg_trigger WHERE tgrelid=%s AND NOT tgisinternal ORDER BY oid", (oid,)).fetchall()
        index_count = connection.execute("SELECT count(*) FROM pg_catalog.pg_index WHERE indrelid=%s", (oid,)).fetchone()[0]
        expected_indexes = sum(row[0] in ("p", "u") for row in constraints)
        if index_count != expected_indexes:
            raise ProvenanceError("Unregistered indexes are outside the controlled profile")
        return {"relation": list(relation), "columns": [list(r) for r in columns], "constraints": [list(r) for r in constraints],
                "userTriggerOids": [row[0] for row in triggers], "unsafeEffects": counts, "indexCount": index_count}

    def verify(self, connection):
        """Call while the setup lock is held; runtime no-DDL is a deployment premise."""
        self._business(connection, installed=True)
        marker = connection.execute("SELECT nonce::text,table_oid FROM " + self.object("_mtw_v3_installation")).fetchall()
        if marker != [(self.nonce, self.table_oid)]:
            raise ProvenanceError("Installation nonce/relation binding changed")
        expected_shapes = {
            "installation": [("nonce", "uuid", True), ("table_oid", "oid", True)],
            "state": [("key", "text", True), ("token", "uuid", True), ("present", "boolean", True)],
            "candidates": [("token", "uuid", True), ("key", "text", True), ("predecessor", "uuid", True), ("action", "text", True),
                           ("owner", "text", True), ("expire_at", "timestamp with time zone", True)],
            "effects": [("token", "uuid", True), ("key", "text", True), ("predecessor", "uuid", True), ("action", "text", True),
                        ("owner", "text", True), ("expire_at", "timestamp with time zone", True)]}
        for suffix, shape in expected_shapes.items():
            target = self.object("_mtw_v3_" + suffix)
            relation = connection.execute("SELECT oid,relkind,relrowsecurity,relforcerowsecurity,relpersistence FROM pg_catalog.pg_class WHERE oid=%s::regclass", (target,)).fetchone()
            if relation is None or tuple(relation[1:]) != ("r", False, False, "p"):
                raise ProvenanceError("Metadata relation profile changed")
            _check_business_effects(connection, relation[0])
            actual = connection.execute("SELECT attname,atttypid::pg_catalog.regtype::text,attnotnull FROM pg_catalog.pg_attribute "
                "WHERE attrelid=%s AND attnum>0 AND NOT attisdropped ORDER BY attnum", (relation[0],)).fetchall()
            if actual != shape:
                raise ProvenanceError("Owned metadata columns changed")
            if connection.execute("SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgrelid=%s AND NOT tgisinternal", (relation[0],)).fetchone()[0]:
                raise ProvenanceError("Unexpected metadata trigger")
            constraints = connection.execute("SELECT contype,conkey::smallint[],convalidated,conenforced,condeferrable,condeferred FROM pg_catalog.pg_constraint WHERE conrelid=%s ORDER BY contype,conkey", (relation[0],)).fetchall()
            nn = [r for r in constraints if r[0] == "n"]
            keys = [r for r in constraints if r[0] != "n"]
            expected_keys = [("p", [1], True, True, False, False)]
            if suffix in ("state", "effects"):
                expected_keys.append(("u", [2 if suffix == "state" else 3], True, True, False, False))
            if keys != expected_keys or len(nn) != len(shape) or {tuple(r[1]) for r in nn} != {(n,) for n in range(1, len(shape) + 1)} or any(tuple(r[2:]) != (True, True, False, False) for r in nn):
                raise ProvenanceError("Owned metadata constraints changed")
            self.catalog["owned"][suffix] = self._catalog_entry(connection, relation[0], relation, actual, constraints)
        metadata = {"versionColumn": self.version_column, "installationNonce": self.nonce,
                    "serverVersion": connection.info.server_version, "tableOid": self.table_oid,
                    "marker": {"nonce": marker[0][0], "tableOid": marker[0][1]}}
        triggers = connection.execute("SELECT t.oid,t.tgname,t.tgtype,t.tgenabled,t.tgnargs,t.tgargs,t.tgattr::text,t.tgqual IS NULL,"
            "t.tgdeferrable,t.tginitdeferred,t.tgfoid,pg_catalog.pg_get_triggerdef(t.oid,true) FROM pg_catalog.pg_trigger t "
            "WHERE t.tgrelid=%s AND NOT t.tgisinternal ORDER BY t.tgname", (self.table_oid,)).fetchall()
        if len(triggers) != 2:
            raise ProvenanceError("Exactly two owned business triggers required")
        for short, bits in (("before", 31), ("after", 21)):
            row = next((r for r in triggers if r[1] == "_mtw_v3_" + short), None)
            if row is None or tuple(row[2:5]) != (bits, "O", 0) or bytes(row[5]) != b"" or tuple(row[6:10]) != ("", True, False, False):
                raise ProvenanceError("Owned trigger type/enabled/parameters changed")
            metadata[short] = {"triggerOid": row[0], "functionOid": row[10], "sourceSha256": self._verify_function(connection, short, row[10]),
                               "triggerDefinition": row[11], "triggerType": row[2], "enabled": row[3], "argumentsHex": bytes(row[5]).hex(),
                               "source": "\n" + self.sources[short] + "\n",
                               "functionCatalog": copy.deepcopy(list(self.function_catalog[short]))}
        helper = connection.execute("SELECT %s::regprocedure::oid", (self.object("_mtw_v3_predecessor") + "(text)",)).fetchone()[0]
        metadata["predecessor"] = {"functionOid": helper, "sourceSha256": self._verify_function(connection, "predecessor", helper),
                                   "source": "\n" + self.sources["predecessor"] + "\n",
                                   "functionCatalog": copy.deepcopy(list(self.function_catalog["predecessor"]))}
        metadata["installationDdlSha256"] = self.ddl_sha256
        metadata["catalog"] = copy.deepcopy(self.catalog)
        metadata["initializationWindow"] = copy.deepcopy(self.window)
        if self.metadata is not None and metadata != self.metadata:
            raise ProvenanceError("Installed object identity or definition changed since initialization")
        return metadata

    def _verify_function(self, connection, name, oid):
        row = connection.execute("SELECT n.nspname,p.proname,p.prosrc,p.prosecdef,p.provolatile,p.proconfig,p.pronargs,"
            "p.prorettype::pg_catalog.regtype::text,l.lanname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
            "JOIN pg_catalog.pg_language l ON l.oid=p.prolang WHERE p.oid=%s", (oid,)).fetchone()
        expected = (self.schema, "_mtw_v3_" + name, "\n" + self.sources[name] + "\n", False, "v", ["search_path=pg_catalog"],
                    1 if name == "predecessor" else 0, "text" if name == "predecessor" else "trigger", "plpgsql")
        if row != expected:
            raise ProvenanceError("Owned function source/type/security/search_path changed")
        self.function_catalog[name] = row
        return _hash(row[2])

    def profile(self, connection, encode):
        ledger = connection.execute("SELECT key,token::text,predecessor::text,action,owner,expire_at FROM "
            + self.object("_mtw_v3_effects") + " ORDER BY key,token LIMIT 10001").fetchall()
        if len(ledger) > 10_000:
            raise ProvenanceError("Effect ledger exceeds this analysis window budget")
        return {"profile": PROFILE, "schema": self.schema, "table": self.table,
            "knownKeys": list(self.keys), "metadata": encode(self.metadata),
            "initialState": [{"key": r[0], "version": r[1], "present": r[2], "owner": r[3], "expireAt": encode(r[4])}
                             for r in self.initial_state],
            "effectLedger": [{"key": r[0], "version": r[1], "predecessor": r[2], "action": r[3],
                              "owner": r[4], "expireAt": encode(r[5])} for r in ledger]}


def install(setup, *, schema, table="key_value", keys):
    idle_setup(setup)
    controlled_schema(schema)
    identifier(table)
    keys = tuple(keys)
    if not keys or len(keys) > 128 or len(set(keys)) != len(keys) or any(not isinstance(k, str) or not k or len(k.encode("utf-8")) > 512 for k in keys):
        raise ValueError("Declare 1..128 distinct bounded text keys")
    if not 180000 <= setup.info.server_version < 190000:
        raise ProvenanceError("This migration is pinned to PostgreSQL 18")
    installation = Installation(schema, table, keys, str(uuid.uuid4()))
    begin = setup.execute("BEGIN")
    installation.window.append({"kind": "begin", "commandTag": begin.statusmessage})
    try:
        locked = setup.execute("LOCK TABLE " + installation.table_sql + " IN ACCESS EXCLUSIVE MODE")
        installation._business(setup, installed=False)
        installation.window.append({"kind": "lock", "tableOid": installation.table_oid,
                                    "mode": "ACCESS EXCLUSIVE", "commandTag": locked.statusmessage})
        if setup.execute("SELECT count(*) FROM pg_catalog.pg_trigger WHERE tgrelid=%s AND NOT tgisinternal", (installation.table_oid,)).fetchone()[0]:
            raise ProvenanceError("Existing business user triggers are unsupported")
        existing = setup.execute("SELECT key FROM " + installation.table_sql).fetchall()
        if any(row[0] not in keys for row in existing):
            raise ProvenanceError("Every existing business key must be in the frozen capture domain")
        reserved = setup.execute("SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname LIKE '_mtw_v3_%%'", (schema,)).fetchone()[0]
        if reserved:
            raise ProvenanceError("Reserved v3 metadata objects already exist")
        statements = ["CREATE TABLE " + installation.object("_mtw_v3_installation") + "(nonce uuid PRIMARY KEY,table_oid oid NOT NULL)",
            "CREATE TABLE " + installation.object("_mtw_v3_state") + "(key text PRIMARY KEY,token uuid NOT NULL UNIQUE,present boolean NOT NULL)",
            "CREATE TABLE " + installation.object("_mtw_v3_candidates") + "(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL,action text NOT NULL,owner text NOT NULL,expire_at timestamptz NOT NULL)",
            "CREATE TABLE " + installation.object("_mtw_v3_effects") + "(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL UNIQUE,action text NOT NULL,owner text NOT NULL,expire_at timestamptz NOT NULL)",
            "ALTER TABLE " + installation.table_sql + " ADD COLUMN " + identifier(installation.version_column) + " uuid",
            "UPDATE " + installation.table_sql + " SET " + identifier(installation.version_column) + "=pg_catalog.gen_random_uuid()",
            "ALTER TABLE " + installation.table_sql + " ALTER COLUMN " + identifier(installation.version_column) + " SET NOT NULL"]
        installation.ddl_sha256 = _hash(json.dumps(statements + installation.ddl(), ensure_ascii=False, separators=(",", ":")))
        for sql in statements:
            setup.execute(sql)
        setup.execute("INSERT INTO " + installation.object("_mtw_v3_installation") + " VALUES(%s,%s)", (installation.nonce, installation.table_oid))
        for key in keys:
            setup.execute("INSERT INTO " + installation.object("_mtw_v3_state") + " SELECT %s,COALESCE((SELECT "
                + identifier(installation.version_column) + " FROM " + installation.table_sql + " WHERE key=%s),pg_catalog.gen_random_uuid()),EXISTS(SELECT 1 FROM "
                + installation.table_sql + " WHERE key=%s)", (key, key, key))
        for sql in installation.ddl():
            setup.execute(sql)
        installation.metadata = installation.verify(setup)
        installation.window.append({"kind": "catalog", "tableOid": installation.table_oid})
        rows = setup.execute("SELECT s.key,s.token::text,s.present,b.value,b.expire_at FROM "
            + installation.object("_mtw_v3_state") + " s LEFT JOIN " + installation.table_sql
            + " b ON b.key=s.key ORDER BY s.key").fetchall()
        if len(rows) != len(keys):
            raise ProvenanceError("Initial fixed-key state is incomplete")
        installation.initial_state = rows
        installation.initial = {row[0]: row[1] for row in rows}
        installation.window.append({"kind": "snapshot", "rows": [{"key": r[0], "version": r[1], "present": r[2],
            "owner": r[3], "expireAt": r[4]} for r in rows]})
        committed = setup.execute("COMMIT")
        if committed.statusmessage != "COMMIT":
            raise ProvenanceError("Initialization did not return COMMIT")
        installation.window.append({"kind": "commit", "commandTag": committed.statusmessage})
        installation.metadata["initializationWindow"] = copy.deepcopy(installation.window)
        return installation
    except BaseException:
        setup.rollback()
        raise
