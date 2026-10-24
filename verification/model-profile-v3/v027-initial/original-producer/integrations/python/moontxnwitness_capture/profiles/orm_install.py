"""Explicit controlled migration; fixed UUID domain; unique versions, no ordering."""
from __future__ import annotations
import hashlib
import json
import uuid
from copy import deepcopy
from psycopg import sql
from psycopg.types.json import Jsonb
from ..orm import FIELDS, VERSION
from . import orm_relation as relation_contract


def qualified(schema, name):
    return sql.Identifier(schema, name).as_string(None)


def payload(alias):
    return "jsonb_build_object(" + ",".join("'" + field + "'," + alias + '."' + field + '"' + ("::text" if field == "id" else "") for field in FIELDS) + ")"


def sources(scope):
    s = {name: qualified(scope.schema, "_mtw_orm_" + name) for name in ("state", "candidates", "effects", "predecessor", "deleted_version")}
    old, new = payload("OLD"), payload("NEW")
    before = f"""
DECLARE k text; previous uuid; was_present boolean; v uuid; old_data jsonb; new_data jsonb;
BEGIN
 IF TG_OP<>'DELETE' THEN
  IF NEW.id IS NULL OR NEW.email IS NULL OR NEW.hashed_password IS NULL OR NEW.is_active IS NULL OR NEW.is_superuser IS NULL OR NEW.is_verified IS NULL THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'ORM fixed UUID mutation unsupported'; END IF;
  k:=NEW.id::text;
 ELSE k:=OLD.id::text; END IF;
 SELECT token,present INTO previous,was_present FROM {s['state']} WHERE key=k FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'ORM key outside controlled fixed domain'; END IF;
 IF TG_OP<>'INSERT' AND (NOT was_present OR previous IS DISTINCT FROM OLD."{VERSION}") THEN RAISE EXCEPTION 'ORM source chain mismatch'; END IF;
 v:=gen_random_uuid();
 old_data:=CASE WHEN TG_OP='INSERT' THEN NULL ELSE {old} END;
 new_data:=CASE WHEN TG_OP='DELETE' THEN NULL ELSE {new} END;
 INSERT INTO {s['candidates']}(token,key,predecessor,action,old_present,new_present,old_image,new_image)
 VALUES(v,k,previous,TG_OP,was_present,TG_OP<>'DELETE',old_data,new_data);
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE NEW."{VERSION}":=v; RETURN NEW; END IF;
END
"""
    predecessor = f"""
DECLARE v uuid; n integer;
BEGIN
 SELECT count(*),min(predecessor::text)::uuid INTO n,v FROM {s['candidates']} WHERE token=token_text::uuid;
 IF n<>1 THEN RAISE EXCEPTION 'ORM candidate predecessor not unique'; END IF;
 RETURN v;
END
"""
    deleted = f"""
DECLARE v uuid; n integer;
BEGIN
 SELECT count(*),min(token::text)::uuid INTO n,v FROM {s['candidates']}
 WHERE key=key_text AND predecessor=predecessor_text::uuid AND action='DELETE';
 IF n<>1 THEN RAISE EXCEPTION 'ORM delete candidate not unique'; END IF;
 RETURN v;
END
"""
    after = f"""
DECLARE k text; v uuid; candidate record; n integer; actual_image jsonb;
BEGIN
 IF TG_OP='DELETE' THEN k:=OLD.id::text; v:={s['deleted_version']}(k,OLD."{VERSION}"::text); actual_image:=NULL;
 ELSE k:=NEW.id::text; v:=NEW."{VERSION}"; actual_image:={new}; END IF;
 SELECT * INTO candidate FROM {s['candidates']} WHERE token=v;
 IF NOT FOUND OR candidate.key IS DISTINCT FROM k OR candidate.action IS DISTINCT FROM TG_OP OR candidate.new_image IS DISTINCT FROM actual_image THEN RAISE EXCEPTION 'ORM actual effect candidate mismatch'; END IF;
 IF TG_OP='INSERT' AND candidate.old_present THEN RAISE EXCEPTION 'ORM insert source presence drift'; END IF;
 UPDATE {s['state']} SET token=v,present=(TG_OP<>'DELETE'),image=actual_image
 WHERE key=k AND token=candidate.predecessor AND present=candidate.old_present;
 GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'ORM actual effect chain mismatch'; END IF;
 INSERT INTO {s['effects']} SELECT * FROM {s['candidates']} WHERE token=v;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END
"""
    return {"before": before, "after": after, "predecessor": predecessor, "deleted_version": deleted}


class Installation:
    def __init__(self, scope, nonce, source, oids, initial, metadata):
        self.scope, self.nonce, self.source, self.oids = scope, nonce, source, oids
        self.initial, self.metadata = initial, metadata

    def verify(self, connection):
        facts = relation_contract.collect_sync(connection, self.scope)
        self.last_catalog_refs = deepcopy(connection.last_catalog_refs)
        relation_contract.validate(self.scope, facts, versioned=True,
            owned_trigger_oids=tuple(self.oids[name]["triggerOid"] for name in ("before", "after")))
        if facts["relation"][0] != self.metadata["tableOid"]:
            raise ValueError("Business relation identity changed")
        for name, expected in self.oids.items():
            cursor = connection.execute("""SELECT n.nspname,p.proname,p.prosrc,p.prosecdef,p.provolatile,p.proconfig,p.pronargs,
p.prorettype::regtype::text,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=%s""", (expected["functionOid"],))
            row = cursor.fetchone()
            expected["functionQuerySeq"] = cursor.control_query_seq
            target_name = "_mtw_orm_" + (name + "_fn" if name in ("before", "after") else name)
            args = 0 if name in ("before", "after") else 1 if name == "predecessor" else 2
            expected_row = (self.scope.schema, target_name, self.source[name], False, "v", ["search_path=pg_catalog"], args,
                "trigger" if args == 0 else "uuid", "plpgsql")
            if row != expected_row:
                raise ValueError("Owned function identity/source/config changed")
            expected["functionCatalog"] = list(row)
            if name in ("before", "after"):
                cursor = connection.execute("SELECT tgfoid,tgtype,tgenabled,tgnargs,encode(tgargs,'hex'),tgisinternal,tgqual IS NULL FROM pg_trigger WHERE oid=%s AND tgrelid=%s", (expected["triggerOid"], facts["relation"][0]))
                trigger = cursor.fetchone()
                expected["triggerQuerySeq"] = cursor.control_query_seq
                if trigger != (expected["functionOid"], 31 if name == "before" else 29, "O", 0, "", False, True):
                    raise ValueError("Owned trigger definition changed")
                expected["triggerCatalog"] = list(trigger)
        cursor = connection.execute("SELECT nonce::text,table_oid FROM " + qualified(self.scope.schema, "_mtw_orm_installation"))
        marker = cursor.fetchall()
        self.last_marker_rows, self.last_marker_query_seq = deepcopy(marker), cursor.control_query_seq
        if marker != [(self.nonce, self.metadata["tableOid"])]:
            raise ValueError("Owned installation marker changed")
        owned, owned_refs = {}, {}
        specs = {
            "installation": (["nonce", "table_oid"], ["uuid", "oid"], {1, 2}, []),
            "state": (["key", "token", "present", "image"], ["text", "uuid", "boolean", "jsonb"], {1, 2, 3}, [("token",)]),
            "candidates": (["token", "key", "predecessor", "action", "old_present", "new_present", "old_image", "new_image"], ["uuid", "text", "uuid", "text", "boolean", "boolean", "jsonb", "jsonb"], set(range(1, 7)), []),
            "effects": (["token", "key", "predecessor", "action", "old_present", "new_present", "old_image", "new_image"], ["uuid", "text", "uuid", "text", "boolean", "boolean", "jsonb", "jsonb"], set(range(1, 7)), [("predecessor",)])}
        for name, (names, types, not_null, extra_unique) in specs.items():
            cursor = connection.execute(relation_contract.RELATION, (self.scope.schema, "_mtw_orm_" + name))
            relation = cursor.fetchall()
            refs = {"relation": cursor.control_query_seq}
            if len(relation) != 1 or relation[0][1:] != ("r", False, False, "p"):
                raise ValueError("Owned metadata relation shape changed")
            oid = relation[0][0]
            cursor = connection.execute(relation_contract.COLUMNS, (oid,))
            columns = cursor.fetchall(); refs["columns"] = cursor.control_query_seq
            expected_columns = [(n, t, i + 1 in not_null, "", "", False) for i, (n, t) in enumerate(zip(names, types))]
            if columns != expected_columns:
                raise ValueError("Owned metadata columns/defaults changed")
            cursor = connection.execute(relation_contract.CONSTRAINTS, (oid,))
            constraints = cursor.fetchall(); refs["constraints"] = cursor.control_query_seq
            nulls, primary, unique = set(), 0, []
            for kind, keys, validated, enforced, deferrable, deferred, noinherit in constraints:
                if (validated, enforced, deferrable, deferred, noinherit) != (True, True, False, False, kind in ("p", "u")):
                    raise ValueError("Owned constraint flags changed")
                if kind == "p" and keys == [1]: primary += 1
                elif kind == "n" and len(keys) == 1 and keys[0] not in nulls: nulls.add(keys[0])
                elif kind == "u": unique.append(tuple(names[k-1] for k in keys))
                else: raise ValueError("Unknown owned constraint")
            if primary != 1 or nulls != not_null or unique != ([("token",)] if name == "state" else []):
                raise ValueError("Owned NOT NULL/primary/unique contract changed")
            cursor = connection.execute(relation_contract.TRIGGERS, (oid,))
            user_triggers = cursor.fetchall(); refs["userTriggers"] = cursor.control_query_seq
            cursor = connection.execute(relation_contract.UNSAFE, (oid,) * 6)
            unsafe = cursor.fetchone(); refs["unsafeEffects"] = cursor.control_query_seq
            if user_triggers or unsafe != (0, 0, 0, 0):
                raise ValueError("Owned metadata has unsafe side effects")
            cursor = connection.execute(relation_contract.INDEXES, (oid,))
            indexes = cursor.fetchall(); refs["indexes"] = cursor.control_query_seq
            expected_indexes = {(names[0],), *extra_unique}
            if len(indexes) != len(expected_indexes): raise ValueError("Owned index count changed")
            actual = set()
            for row in indexes:
                p, u, valid, ready, immediate, nk, na, noexpr, nopred, method, fields, ns, deterministic = row
                field = tuple(fields)
                if (u, valid, ready, immediate, nk, na, noexpr, nopred, method) != (True, True, True, True, 1, 1, True, True, "btree") or ns != ["pg_catalog"] or deterministic != [True] or p != (field == (names[0],)):
                    raise ValueError("Owned index semantics changed")
                actual.add(field)
            if actual != expected_indexes: raise ValueError("Owned index columns changed")
            owned[name] = {"relation": list(relation[0]), "columns": columns, "constraints": constraints, "indexes": indexes,
                "userTriggers": deepcopy(user_triggers), "unsafeEffects": list(unsafe)}
            owned_refs[name] = refs
        previous = self.metadata.get("ownedCatalog")
        if previous is not None and previous != owned:
            raise ValueError("Owned metadata identities/catalog changed since installation")
        self.metadata["ownedCatalog"] = owned
        self.last_owned_refs = owned_refs
        return facts

    def ledger(self, connection):
        cursor = connection.execute("SELECT token::text,key,predecessor::text,action,old_present,new_present,old_image,new_image FROM " + qualified(self.scope.schema, "_mtw_orm_effects") + " ORDER BY token LIMIT 513")
        rows = cursor.fetchall(); self.last_ledger_query_seq = cursor.control_query_seq
        if len(rows) > 512:
            raise ValueError("Functional-slice effect ledger budget exceeded")
        return [dict(zip(("version", "key", "predecessor", "action", "oldPresent", "newPresent", "oldImage", "newImage"), row)) for row in rows]

    def snapshot(self, connection):
        target = qualified(self.scope.schema, self.scope.table)
        state = qualified(self.scope.schema, "_mtw_orm_state")
        cursor = connection.execute("SELECT s.key,s.token::text,s.present,s.image,t.id::text,t." + '"' + VERSION + '"::text,' + payload("t")
            + " FROM " + state + " s LEFT JOIN " + target + " t ON t.id=s.key::uuid ORDER BY s.key LIMIT 129")
        rows = cursor.fetchall()
        self.last_snapshot_rows, self.last_snapshot_query_seq = deepcopy(rows), cursor.control_query_seq
        if {row[0] for row in rows} != set(self.scope.known_ids) or len(rows) != len(self.scope.known_ids):
            raise ValueError("State domain is missing/extra")
        result = {}
        for key, version, present, image, business_id, business_version, business_image in rows:
            if present != (business_id is not None) or present and (business_id != key or business_version != version or business_image != image) or not present and image is not None:
                raise ValueError("Actual same-snapshot business/state presence, version or image differs")
            result[key] = {"version": version, "present": present, "image": image}
        return result


def all_tables(scope):
    return [qualified(scope.schema, scope.table)] + [qualified(scope.schema, "_mtw_orm_" + name) for name in ("installation", "state", "candidates", "effects")]


def relation_identities(scope, table_oid, owned):
    return [{"schema": scope.schema, "table": scope.table, "oid": table_oid}] + [
        {"schema": scope.schema, "table": "_mtw_orm_" + name, "oid": owned[name]["relation"][0]} for name in ("installation", "state", "candidates", "effects")]


def install(connection, scope, *, diagnostic_path=None):
    if not connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ValueError("Fresh idle autocommit setup connection required")
    if not 180000 <= connection.info.server_version < 190000:
        raise ValueError("PostgreSQL18 required")
    table, nonce = qualified(scope.schema, scope.table), str(uuid.uuid4())
    source, oids = sources(scope), {}
    begin_cursor = connection.execute("BEGIN")
    begin_tag, begin_seq = begin_cursor.statusmessage, begin_cursor.control_query_seq
    try:
        lock_cursor = connection.execute("LOCK TABLE " + table + " IN ACCESS EXCLUSIVE MODE")
        lock_tag, first_lock_seq = lock_cursor.statusmessage, lock_cursor.control_query_seq
        before = relation_contract.collect_sync(connection, scope)
        if diagnostic_path is not None:
            from pathlib import Path
            Path(diagnostic_path).write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
        relation_contract.validate(scope, before)
        existing = connection.execute("SELECT id::text FROM " + table + " LIMIT 129").fetchall()
        if len(existing) > 128 or any(row[0] not in scope.known_ids for row in existing):
            raise ValueError("Existing rows outside declared fixed UUID domain")
        connection.execute("ALTER TABLE " + table + ' ADD COLUMN "' + VERSION + '" uuid NOT NULL DEFAULT gen_random_uuid()')
        connection.execute("ALTER TABLE " + table + ' ALTER COLUMN "' + VERSION + '" DROP DEFAULT')
        connection.execute("CREATE TABLE " + qualified(scope.schema, "_mtw_orm_installation") + "(nonce uuid PRIMARY KEY,table_oid oid NOT NULL)")
        connection.execute("INSERT INTO " + qualified(scope.schema, "_mtw_orm_installation") + " VALUES(%s,%s)", (nonce, before["relation"][0]))
        connection.execute("CREATE TABLE " + qualified(scope.schema, "_mtw_orm_state") + "(key text PRIMARY KEY,token uuid NOT NULL UNIQUE,present boolean NOT NULL,image jsonb)")
        definitions = "(token uuid PRIMARY KEY,key text NOT NULL,predecessor uuid NOT NULL,action text NOT NULL,old_present boolean NOT NULL,new_present boolean NOT NULL,old_image jsonb,new_image jsonb)"
        for name in ("candidates", "effects"):
            connection.execute("CREATE TABLE " + qualified(scope.schema, "_mtw_orm_" + name) + definitions)
        connection.execute("CREATE UNIQUE INDEX _mtw_orm_effect_predecessor ON " + qualified(scope.schema, "_mtw_orm_effects") + "(predecessor)")
        rows = connection.execute("SELECT id::text," + '"' + VERSION + '"::text,' + payload(table) + " FROM " + table).fetchall()
        original = {row[0]: (row[1], row[2]) for row in rows}
        for key in scope.known_ids:
            version, image = original.get(key, (str(uuid.uuid4()), None))
            connection.execute("INSERT INTO " + qualified(scope.schema, "_mtw_orm_state") + " VALUES(%s,%s,%s,%s)",
                (key, version, key in original, Jsonb(image, dumps=json.dumps) if image is not None else None))
        for name in ("predecessor", "deleted_version", "before", "after"):
            function = qualified(scope.schema, "_mtw_orm_" + (name + "_fn" if name in ("before", "after") else name))
            args = "" if name in ("before", "after") else "token_text text" if name == "predecessor" else "key_text text,predecessor_text text"
            returns = "trigger" if not args else "uuid"
            connection.execute("CREATE FUNCTION " + function + "(" + args + ") RETURNS " + returns + " LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$" + source[name] + "$$")
            oid = connection.execute("SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s", (scope.schema, "_mtw_orm_" + (name + "_fn" if not args else name))).fetchone()[0]
            oids[name] = {"functionOid": oid, "sourceSha256": hashlib.sha256(source[name].encode()).hexdigest(), "source": source[name]}
            if name in ("before", "after"):
                trigger_name = "_mtw_orm_" + name
                connection.execute('CREATE TRIGGER "' + trigger_name + '" ' + name.upper() + " INSERT OR UPDATE OR DELETE ON " + table + " FOR EACH ROW EXECUTE FUNCTION " + function + "()")
                oids[name]["triggerOid"] = connection.execute("SELECT oid FROM pg_trigger WHERE tgrelid=%s AND tgname=%s", (before["relation"][0], trigger_name)).fetchone()[0]
        metadata = {"tableOid": before["relation"][0], "nonce": nonce, "serverVersion": connection.info.server_version,
            "versionColumn": VERSION, "functions": oids, "coreProofAccepted": False}
        installed = Installation(scope, nonce, source, oids, {}, metadata)
        all_lock = connection.execute("LOCK TABLE " + ",".join(all_tables(scope)) + " IN ACCESS EXCLUSIVE MODE")
        all_lock_tag, all_lock_seq = all_lock.statusmessage, all_lock.control_query_seq
        catalog_start = len(connection.query_sequences)
        metadata["catalog"] = installed.verify(connection)
        metadata["catalogQueryRefs"] = deepcopy(installed.last_catalog_refs)
        metadata["ownedCatalogQueryRefs"] = deepcopy(installed.last_owned_refs)
        metadata["initialMarkerRows"] = deepcopy(installed.last_marker_rows)
        metadata["initialMarkerQuerySeq"] = installed.last_marker_query_seq
        catalog_queries = connection.references_since(catalog_start)
        installed.initial = installed.snapshot(connection)
        metadata["initialState"] = installed.initial
        metadata["initialSnapshotRows"] = deepcopy(installed.last_snapshot_rows)
        metadata["initialSnapshotQuerySeq"] = installed.last_snapshot_query_seq
        commit_cursor = connection.execute("COMMIT")
        commit_tag, commit_seq = commit_cursor.statusmessage, commit_cursor.control_query_seq
        if (begin_tag, lock_tag, all_lock_tag, commit_tag) != ("BEGIN", "LOCK TABLE", "LOCK TABLE", "COMMIT"):
            raise ValueError("Initialization acknowledgement not confirmed")
        metadata["initializationWindow"] = [{"kind": "begin", "commandTag": begin_tag, "querySeq": begin_seq},
            {"kind": "lock", "commandTag": all_lock_tag, "querySeqs": [first_lock_seq, all_lock_seq], "tableOid": before["relation"][0], "mode": "ACCESS EXCLUSIVE",
                "relations": relation_identities(scope, before["relation"][0], metadata["ownedCatalog"])},
            {"kind": "catalog", "tableOid": before["relation"][0], "querySeqs": catalog_queries},
            {"kind": "snapshot", "rows": deepcopy(metadata["initialSnapshotRows"]), "querySeq": metadata["initialSnapshotQuerySeq"]},
            {"kind": "commit", "commandTag": commit_tag, "querySeq": commit_seq}]
        metadata["functions"] = deepcopy(oids)
        return installed
    except BaseException:
        try: connection.execute("ROLLBACK")
        except BaseException:
            try: connection.raw.execute("ROLLBACK")
            except BaseException: pass
        raise


def finalize(connection, installed):
    """Actual final raw state is one locked transaction, not checker booleans."""
    scope = installed.scope
    begin = connection.execute("BEGIN")
    begin_tag, begin_seq = begin.statusmessage, begin.control_query_seq
    try:
        lock = connection.execute("LOCK TABLE " + ",".join(all_tables(scope)) + " IN ACCESS EXCLUSIVE MODE")
        lock_tag, lock_seq = lock.statusmessage, lock.control_query_seq
        start = len(connection.query_sequences)
        catalog = installed.verify(connection)
        catalog_sequences = connection.references_since(start)
        ledger = installed.ledger(connection)
        ledger_seq = installed.last_ledger_query_seq
        state = installed.snapshot(connection)
        joined, snapshot_seq = deepcopy(installed.last_snapshot_rows), installed.last_snapshot_query_seq
        record = {"kind": "final-effect-ledger", "ledger": deepcopy(ledger), "ledgerQuerySeq": ledger_seq, "state": deepcopy(state),
            "finalCatalog": deepcopy(catalog), "finalCatalogQueryRefs": deepcopy(installed.last_catalog_refs),
            "finalOwnedCatalog": deepcopy(installed.metadata["ownedCatalog"]), "finalOwnedCatalogQueryRefs": deepcopy(installed.last_owned_refs),
            "finalFunctions": deepcopy(installed.oids), "finalMarkerRows": deepcopy(installed.last_marker_rows), "finalMarkerQuerySeq": installed.last_marker_query_seq,
            "finalSnapshotRows": joined, "finalSnapshotQuerySeq": snapshot_seq}
        commit = connection.execute("COMMIT")
        commit_tag, commit_seq = commit.statusmessage, commit.control_query_seq
        if (begin_tag, lock_tag, commit_tag) != ("BEGIN", "LOCK TABLE", "COMMIT"): raise ValueError("Finalization ACK not confirmed")
        record["finalizationWindow"] = [{"kind": "begin", "commandTag": begin_tag, "querySeq": begin_seq},
            {"kind": "lock", "commandTag": lock_tag, "querySeq": lock_seq, "tableOid": installed.metadata["tableOid"], "mode": "ACCESS EXCLUSIVE",
                "relations": relation_identities(scope, installed.metadata["tableOid"], record["finalOwnedCatalog"])},
            {"kind": "catalog", "tableOid": installed.metadata["tableOid"], "querySeqs": catalog_sequences},
            {"kind": "snapshot_and_ledger", "rows": deepcopy(joined), "effectLedger": deepcopy(ledger), "snapshotQuerySeq": snapshot_seq, "ledgerQuerySeq": ledger_seq},
            {"kind": "commit", "commandTag": commit_tag, "querySeq": commit_seq}]
        return record
    except BaseException:
        try: connection.execute("ROLLBACK")
        except BaseException:
            try: connection.raw.execute("ROLLBACK")
            except BaseException: pass
        raise
