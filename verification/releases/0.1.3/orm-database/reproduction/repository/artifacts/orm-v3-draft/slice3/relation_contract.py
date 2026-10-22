"""Strict PG18 base-user catalog evidence, collected only under an owned lock.

This is a read-only contract checker, not a provenance migration installer. It
does not assert initial versions, source closure or completed core proof.
"""
from provenance_policy import CoverageRequired, FIELDS, VERSION


RELATION = """SELECT c.oid,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.relpersistence
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relname=%s LIMIT 2"""
LOCKS = "SELECT mode,granted FROM pg_locks WHERE pid=pg_backend_pid() AND relation=%s AND mode='AccessExclusiveLock' LIMIT 2"
COLUMNS = """SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
a.attgenerated,a.attidentity,(d.oid IS NOT NULL)
FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum LIMIT 9"""
CONSTRAINTS = """SELECT contype,conkey,convalidated,conenforced,condeferrable,condeferred,connoinherit
FROM pg_constraint WHERE conrelid=%s ORDER BY contype,oid LIMIT 16"""
TRIGGERS = "SELECT oid FROM pg_trigger WHERE tgrelid=%s AND NOT tgisinternal ORDER BY oid LIMIT 4"
INDEXES = """SELECT i.indisprimary,i.indisunique,i.indisvalid,i.indisready,i.indimmediate,
i.indnkeyatts,i.indnatts,(i.indexprs IS NULL),(i.indpred IS NULL),am.amname,
ARRAY(SELECT a.attname FROM unnest(i.indkey::smallint[]) WITH ORDINALITY k(attnum,n)
 JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum ORDER BY k.n),
ARRAY(SELECT ns.nspname FROM unnest(i.indclass::oid[]) WITH ORDINALITY k(opclass,n)
 JOIN pg_opclass oc ON oc.oid=k.opclass JOIN pg_namespace ns ON ns.oid=oc.opcnamespace ORDER BY k.n),
ARRAY(SELECT COALESCE(c.collisdeterministic,true) FROM unnest(i.indcollation::oid[]) WITH ORDINALITY k(coll,n)
 LEFT JOIN pg_collation c ON c.oid=k.coll ORDER BY k.n)
FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam
WHERE i.indrelid=%s ORDER BY i.indexrelid LIMIT 4"""
UNSAFE = """SELECT
(SELECT count(*) FROM pg_constraint WHERE contype='f' AND (conrelid=%s OR confrelid=%s)),
(SELECT count(*) FROM pg_rewrite WHERE ev_class=%s),
(SELECT count(*) FROM pg_inherits WHERE inhrelid=%s OR inhparent=%s),
(SELECT count(*) FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid JOIN pg_namespace n ON n.oid=t.typnamespace
 WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND (n.nspname<>'pg_catalog' OR t.typtype='d'))"""
LOCALE = "SELECT datcollate,datctype FROM pg_database WHERE datname=current_database()"


def validate(scope, facts, *, versioned=False, owned_trigger_oids=()):
    expected_fields = list(FIELDS) + ([VERSION] if versioned else [])
    expected_types = ["uuid", "character varying(320)", "character varying(1024)", "boolean", "boolean", "boolean"] + (["uuid"] if versioned else [])
    relation = facts.get("relation")
    if not isinstance(relation, (tuple, list)) or len(relation) != 5 or type(relation[0]) is not int or relation[0] <= 0 or any(type(value) is not bool for value in relation[2:4]) or list(relation[1:]) != ["r", False, False, "p"]:
        raise CoverageRequired("Ordinary permanent non-RLS relation required")
    if type(facts.get("serverVersion")) is not int or not 180000 <= facts["serverVersion"] < 190000:
        raise CoverageRequired("This relation contract is pinned to PostgreSQL18")
    if list(facts.get("databaseLocale", ())) != ["C", "C"]:
        raise CoverageRequired("Controlled C/C database locale required for the first email-uniqueness contract")
    if list(map(list, facts.get("locks", ()))) != [["AccessExclusiveLock", True]]:
        raise CoverageRequired("Actual granted own-table ACCESS EXCLUSIVE lock is required")
    columns = list(map(list, facts.get("columns", ())))
    expected = [[name, kind, True, "", "", False] for name, kind in zip(expected_fields, expected_types)]
    if columns != expected:
        raise CoverageRequired("Strict six native base-user columns/defaults/generated/identity changed")
    unsafe = facts.get("unsafeEffects", ())
    if len(unsafe) != 4 or any(type(value) is not int for value in unsafe) or list(unsafe) != [0, 0, 0, 0]:
        raise CoverageRequired("Foreign keys, rewrite rules, inheritance or custom types are unsupported")
    actual_triggers = tuple(row[0] for row in facts.get("userTriggers", ()))
    if versioned and (len(owned_trigger_oids) != 2 or len(set(owned_trigger_oids)) != 2):
        raise CoverageRequired("After migration exactly two independently checked owned trigger identities are required")
    if actual_triggers != tuple(sorted(owned_trigger_oids)):
        raise CoverageRequired("Unknown/missing user trigger identity")
    not_null, primary = set(), 0
    for row in facts.get("constraints", ()):
        kind, keys, validated, enforced, deferrable, deferred, noinherit = row
        expected_noinherit = kind == "p"
        if any(type(value) is not bool for value in (validated, enforced, deferrable, deferred, noinherit)) or any(type(value) is not int for value in keys) or (validated, enforced, deferrable, deferred, noinherit) != (True, True, False, False, expected_noinherit):
            raise CoverageRequired("Unexpected constraint enforcement/timing/inheritance")
        if kind == "n" and len(keys) == 1 and keys[0] not in not_null:
            not_null.add(keys[0])
        elif kind == "p" and list(keys) == [1]:
            primary += 1
        else:
            raise CoverageRequired("Unexpected, repeated or unsafe table constraint")
    if primary != 1 or not_null != set(range(1, len(expected_fields) + 1)):
        raise CoverageRequired("Missing or duplicate primary/NOT NULL constraints")
    indexes = facts.get("indexes", ())
    if len(indexes) != 2:
        raise CoverageRequired("Exactly native UUID primary index and unique-email index required")
    found = set()
    for row in indexes:
        primary, unique, valid, ready, immediate, nkeys, natts, noexpr, nopredicate, method, fields, namespaces, deterministic = row
        if any(type(value) is not bool for value in (primary, unique, valid, ready, immediate, noexpr, nopredicate)) or type(nkeys) is not int or type(natts) is not int or (unique, valid, ready, immediate, nkeys, natts, noexpr, nopredicate, method) != (True, True, True, True, 1, 1, True, True, "btree"):
            raise CoverageRequired("Unexpected index semantics, INCLUDE, expression or partial predicate")
        field = tuple(fields)
        if field not in (("id",), ("email",)) or primary != (field == ("id",)) or field in found or list(namespaces) != ["pg_catalog"] or list(deterministic) != [True]:
            raise CoverageRequired("Unexpected index field/uniqueness/operator/collation")
        found.add(field)
    return {"profile": "base-user-native-six-column-relation/2", "schema": scope.schema,
        "table": scope.table, "tableOid": relation[0], "facts": facts,
        "migrationInstalled": False, "sourceProofAccepted": False}


def _requests(oid):
    return (("locks", LOCKS, (oid,)), ("columns", COLUMNS, (oid,)),
        ("constraints", CONSTRAINTS, (oid,)), ("userTriggers", TRIGGERS, (oid,)),
        ("indexes", INDEXES, (oid,)), ("unsafeEffects", UNSAFE, (oid,) * 6),
        ("databaseLocale", LOCALE, None))


def collect_sync(connection, scope):
    if int(connection.info.transaction_status) != 2:
        raise CoverageRequired("Begin and lock the target explicitly before read-only collection")
    cursor = connection.execute(RELATION, (scope.schema, scope.table))
    rows = cursor.fetchall()
    query_refs = {"relation": getattr(cursor, "control_query_seq", None)}
    if len(rows) != 1:
        raise CoverageRequired("Exact target relation is missing/ambiguous")
    facts = {"serverVersion": connection.info.server_version, "relation": list(rows[0])}
    for key, query, parameters in _requests(rows[0][0]):
        cursor = connection.execute(query, parameters)
        values = cursor.fetchall()
        query_refs[key] = getattr(cursor, "control_query_seq", None)
        facts[key] = list(values[0]) if key in ("unsafeEffects", "databaseLocale") and len(values) == 1 else values
        if key == "locks" and list(map(list, values)) != [["AccessExclusiveLock", True]]:
            raise CoverageRequired("No verified target lock; stop before collecting business shape")
    connection.last_catalog_refs = query_refs
    return facts


async def collect_async(connection, scope):
    if int(connection.info.transaction_status) != 2:
        raise CoverageRequired("Begin and lock the target explicitly before read-only collection")
    cursor = await connection.execute(RELATION, (scope.schema, scope.table))
    rows = await cursor.fetchall()
    if len(rows) != 1:
        raise CoverageRequired("Exact target relation is missing/ambiguous")
    facts = {"serverVersion": connection.info.server_version, "relation": list(rows[0])}
    for key, query, parameters in _requests(rows[0][0]):
        cursor = await connection.execute(query, parameters)
        values = await cursor.fetchall()
        facts[key] = list(values[0]) if key in ("unsafeEffects", "databaseLocale") and len(values) == 1 else values
        if key == "locks" and list(map(list, values)) != [["AccessExclusiveLock", True]]:
            raise CoverageRequired("No verified target lock; stop before collecting business shape")
    return facts
