"""Eight preregistered relational PG fixtures; not an arbitrary SQL mapper."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
DRAFT = Path(__file__).resolve().parent
SCHEMA = {"accounts": {"primaryKey": "id", "columns": {"id": "int64", "balance": "int64", "active": "bool", "region": "text"}}}
FIELDS = ("id", "balance", "active", "region", "version")
KINDS = ("insert", "update", "delete")


def encoded(value):
    if isinstance(value, uuid.UUID): return str(value)
    if isinstance(value, bytes): return {"captureType": "bytes", "hex": value.hex()}
    if isinstance(value, int) and not isinstance(value, bool): return str(value)
    if isinstance(value, (tuple, list)): return [encoded(x) for x in value]
    if isinstance(value, dict): return {k: encoded(v) for k, v in value.items()}
    return value


def dump(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as stream: stream.write(raw)
    return {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def binding(path):
    raw = path.read_bytes()
    return {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def quoted(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", name): raise ValueError("Unsafe fixture identifier")
    return '"' + name + '"'


def row(values):
    key, balance, active, region, version = values
    assert isinstance(key, int) and isinstance(balance, int) and isinstance(active, bool)
    assert isinstance(region, str) and "\x00" not in region and version is not None
    return {"key": str(key), "version": str(version), "values": {"balance": str(balance), "active": active, "region": region}}


class RawLog:
    def __init__(self, path):
        self.path, self.count, self.total = path, 0, 0
        self.stream = path.open("xb")
    def add(self, **item):
        self.count += 1
        item = {"rawSeq": self.count, "timeNs": time.monotonic_ns(), **item}
        raw = (json.dumps(encoded(item), ensure_ascii=False) + "\n").encode()
        if len(raw) > 262144 or self.total + len(raw) > 4194304: raise ValueError("Fixture raw evidence budget exceeded")
        self.total += len(raw)
        self.stream.write(raw); self.stream.flush()
        return self.count
    def sql(self, connection, tx, sql, params=None):
        request = self.add(kind="request", tx=tx, sql=sql, parameters=params)
        try:
            cursor = connection.execute(sql, params)
            columns = None if cursor.description is None else [{"name": c.name, "typeCode": c.type_code} for c in cursor.description]
            result = [] if cursor.description is None else cursor.fetchall()
            response = self.add(kind="response", request=request, tx=tx, rows=result,
                columns=columns, rowcount=cursor.rowcount, commandTag=cursor.statusmessage,
                transactionStatus=connection.info.transaction_status.name)
            return result, {"request": request, "response": response, "commandTag": cursor.statusmessage}
        except Exception as error:
            self.add(kind="error", request=request, tx=tx, errorClass=type(error).__name__,
                sqlstate=getattr(error, "sqlstate", None), diagnosticSqlstate=getattr(getattr(error, "diag", None), "sqlstate", None),
                hasServerResult=getattr(error, "pgresult", None) is not None,
                transactionStatus=connection.info.transaction_status.name)
            raise
    def close(self):
        if not self.stream.closed:
            self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()


def install(setup, schema, initial, log):
    q = quoted(schema)
    target, state, candidates, effects = [q + "." + quoted(n) for n in ("accounts", "state", "candidates", "effects")]
    pred, deleted = q + '."predecessor"', q + '."delete_token"'
    ddl = ["CREATE SCHEMA " + q,
        "CREATE TABLE " + target + " (id bigint PRIMARY KEY,balance bigint NOT NULL,active boolean NOT NULL,region text COLLATE \"C\" NOT NULL,version uuid NOT NULL)",
        "CREATE TABLE " + state + " (key bigint PRIMARY KEY,version uuid,present boolean NOT NULL)",
        "CREATE TABLE " + candidates + " (version uuid PRIMARY KEY,key bigint NOT NULL,predecessor uuid,action text NOT NULL,old_present boolean NOT NULL,new_present boolean NOT NULL,image jsonb)",
        "CREATE TABLE " + effects + " (LIKE " + candidates + " INCLUDING ALL)",
        "CREATE UNIQUE INDEX ON " + effects + "(predecessor) WHERE predecessor IS NOT NULL"]
    image = lambda a: "jsonb_build_object('balance'," + a + ".balance::text,'active'," + a + ".active,'region'," + a + ".region)"
    before = f"""DECLARE k bigint; p uuid; live boolean; v uuid; BEGIN
IF TG_OP<>'DELETE' AND (NEW.id IS NULL OR NEW.balance IS NULL OR NEW.active IS NULL OR NEW.region IS NULL) THEN RETURN NEW; END IF;
IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'fixture primary key mutation'; END IF;
k:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
SELECT version,present INTO p,live FROM {state} WHERE key=k FOR UPDATE;
IF NOT FOUND THEN RAISE EXCEPTION 'fixture key outside preregistered domain'; END IF;
IF TG_OP<>'INSERT' AND (NOT live OR p IS DISTINCT FROM OLD.version) THEN RAISE EXCEPTION 'fixture source mismatch'; END IF;
v:=gen_random_uuid();
INSERT INTO {candidates} VALUES(v,k,p,TG_OP,live,TG_OP<>'DELETE',CASE WHEN TG_OP='DELETE' THEN NULL ELSE {image('NEW')} END);
IF TG_OP='DELETE' THEN RETURN OLD; ELSE NEW.version:=v; RETURN NEW; END IF;
END"""
    predecessor = f"""DECLARE n integer; p uuid; BEGIN SELECT count(*),min(predecessor::text)::uuid INTO n,p FROM {candidates} WHERE version=v; IF n<>1 THEN RAISE EXCEPTION 'fixture predecessor not unique'; END IF; RETURN p; END"""
    delete_token = f"""DECLARE n integer; v uuid; BEGIN SELECT count(*),min(version::text)::uuid INTO n,v FROM {candidates} WHERE key=k AND predecessor=p AND action='DELETE'; IF n<>1 THEN RAISE EXCEPTION 'fixture delete not unique'; END IF; RETURN v; END"""
    after = f"""DECLARE v uuid; c record; n integer; BEGIN
v:=CASE WHEN TG_OP='DELETE' THEN {deleted}(OLD.id,OLD.version) ELSE NEW.version END;
SELECT * INTO c FROM {candidates} WHERE version=v;
IF NOT FOUND OR c.action<>TG_OP OR c.key IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END) OR c.image IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN NULL ELSE {image('NEW')} END) THEN RAISE EXCEPTION 'fixture actual effect mismatch'; END IF;
IF TG_OP='INSERT' AND c.old_present THEN RAISE EXCEPTION 'fixture insert presence mismatch'; END IF;
UPDATE {state} SET version=v,present=(TG_OP<>'DELETE') WHERE key=c.key AND version IS NOT DISTINCT FROM c.predecessor AND present=c.old_present;
GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'fixture effect state mismatch'; END IF;
INSERT INTO {effects} SELECT * FROM {candidates} WHERE version=v;
IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END"""
    sources = {"before": before, "after": after, "predecessor": predecessor, "delete_token": delete_token}
    for name, args, result in (("before", "", "trigger"), ("after", "", "trigger"), ("predecessor", "v uuid", "uuid"), ("delete_token", "k bigint,p uuid", "uuid")):
        ddl.append("CREATE FUNCTION " + q + "." + quoted(name) + "(" + args + ") RETURNS " + result + " LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $fixture$" + sources[name] + "$fixture$")
    ddl += ["CREATE TRIGGER fixture_before BEFORE INSERT OR UPDATE OR DELETE ON " + target + " FOR EACH ROW EXECUTE FUNCTION " + q + '."before"()',
        "CREATE TRIGGER fixture_after AFTER INSERT OR UPDATE OR DELETE ON " + target + " FOR EACH ROW EXECUTE FUNCTION " + q + '."after"()']
    # Seed the original rows and absent scope before enabling worker transactions.
    log.sql(setup, None, "BEGIN")
    try:
        for statement in ddl[:6]: log.sql(setup, None, statement)
        for item in initial:
            log.sql(setup, None, "INSERT INTO " + target + " VALUES(%s,%s,%s,%s,gen_random_uuid())", (int(item["id"]), int(item["balance"]), item["active"], item["region"]))
        keys = sorted({-9223372036854775808, 1, 2, 3, 9223372036854775807})
        for key in keys:
            log.sql(setup, None, "INSERT INTO " + state + " SELECT %s,version,true FROM " + target + " WHERE id=%s", (key, key))
            log.sql(setup, None, "INSERT INTO " + state + " VALUES(%s,NULL,false) ON CONFLICT DO NOTHING", (key,))
        for statement in ddl[6:]: log.sql(setup, None, statement)
        log.sql(setup, None, "LOCK TABLE " + target + " IN ACCESS EXCLUSIVE MODE")
        actual, snapshot_binding = log.sql(setup, None, "SELECT id,balance,active,region,version FROM " + target)
        catalog, _ = log.sql(setup, None, "SELECT p.oid,p.proname,p.prosrc,p.prosecdef,p.provolatile,p.proconfig,p.pronargs,p.prorettype::regtype::text,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=%s ORDER BY p.proname", (schema,))
        triggers, _ = log.sql(setup, None, "SELECT t.oid,t.tgfoid,t.tgtype,t.tgenabled,t.tgnargs,encode(t.tgargs,'hex'),t.tgisinternal FROM pg_trigger t WHERE t.tgrelid=%s::regclass ORDER BY t.tgname", (target,))
        collation, _ = log.sql(setup, None, "SELECT collname,collprovider,collisdeterministic FROM pg_collation WHERE oid='pg_catalog.\"C\"'::regcollation")
        assert collation == [("C", "c", True)]
        assert len(catalog) == 4 and len(triggers) == 2
        for function in catalog:
            assert function[2] == sources[function[1]] and function[3:6] == (False, "v", ["search_path=pg_catalog"])
        log.sql(setup, None, "COMMIT")
        metadata = {"controlledSchema": schema, "ddl": ddl, "ddlSha256": hashlib.sha256("\n".join(ddl).encode()).hexdigest(),
            "functionCatalog": encoded(catalog), "triggerCatalog": encoded(triggers), "collation": encoded(collation),
            "snapshotBinding": snapshot_binding, "initial": [row(r) for r in actual],
            "workerWindow": "no worker connections opened until the installation transaction COMMIT acknowledgment; all writes controlled for this fresh schema"}
        return metadata
    except BaseException:
        setup.execute("ROLLBACK")
        raise


class Observation:
    def __init__(self, connect, schema, log, metadata, scenario, round_number):
        self.connect, self.schema, self.log = connect, schema, log
        self.target = quoted(schema) + '."accounts"'
        self.events, self.bindings, self.connections, self.outcomes, self.savepoints = [], [], {}, {}, {}
        self.lock, self.origin = threading.Lock(), time.monotonic_ns()
        self.scenario, self.round_number = scenario, round_number
        self.add("snapshot", initial={"accounts": metadata["initial"]}, consistent=True)
    def add(self, kind, **fields):
        with self.lock:
            item = {"seq": len(self.events) + 1, "time": (time.monotonic_ns() - self.origin) // 1000, "kind": kind, **fields}
            if len(self.events) >= 1000: raise ValueError("Fixture event budget exceeded")
            self.events.append(item)
            return item["seq"]
    def begin(self, name, isolation="REPEATABLE READ"):
        raw = self.connect(autocommit=True)
        self.connections[name] = raw
        _, source = self.log.sql(raw, name, "BEGIN ISOLATION LEVEL " + isolation)
        seq = self.add("begin", tx=name, connection="C-" + name)
        self.bindings.append({"event": seq, "source": source, "fact": "actual BEGIN acknowledgement"})
        assert raw.info.transaction_status.name == "INTRANS"
    def read(self, tx, predicate):
        fields = SCHEMA["accounts"]["columns"]
        operators = {"eq": "=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
        clauses, params = [], []
        assert len(predicate) <= 8
        for part in predicate:
            name, op, value = part["column"], part["op"], part["value"]
            assert name in fields and op in operators
            assert fields[name] != "bool" or op == "eq"
            if fields[name] == "text": assert "\x00" not in value
            clauses.append(quoted(name) + (' COLLATE "C"' if fields[name] == "text" else "") + operators[op] + "%s")
            params.append(int(value) if fields[name] == "int64" else value)
        sql = "SELECT id,balance,active,region,version FROM " + self.target + (" WHERE " + " AND ".join(clauses) if clauses else "")
        actual, source = self.log.sql(self.connections[tx], tx, sql, params or None)
        rows = [row(r) for r in actual]
        seq = self.add("row_read", tx=tx, relation="accounts", predicate=predicate, rows=rows, complete=True)
        self.bindings.append({"event": seq, "source": source, "fact": "all rows delivered using fetchall on this SELECT; no LIMIT or write-result projection"})
        return rows
    def write(self, tx, action, key, values=None):
        key = str(key)
        fn = quoted(self.schema)
        if action == "insert":
            sql = "INSERT INTO " + self.target + "(id,balance,active,region) VALUES(%s,%s,%s,%s) RETURNING id,balance,active,region,version," + fn + '."predecessor"(version)'
            params = (int(key), int(values["balance"]), values["active"], values["region"])
        elif action == "update":
            sql = "UPDATE " + self.target + " SET balance=%s,active=%s,region=%s WHERE id=%s RETURNING WITH (OLD AS o,NEW AS n) n.id,n.balance,n.active,n.region,n.version,o.version"
            params = (int(values["balance"]), values["active"], values["region"], int(key))
        else:
            sql = "DELETE FROM " + self.target + " WHERE id=%s RETURNING WITH (OLD AS o,NEW AS n) o.id," + fn + '."delete_token"(o.id,o.version),o.version'
            params = (int(key),)
        actual, source = self.log.sql(self.connections[tx], tx, sql, params)
        assert len(actual) == 1
        r = actual[0]
        if action == "delete":
            actual_key, version, predecessor = r
            data = None
        else:
            actual_key, balance, active, region, version, predecessor = r
            data = {"balance": str(balance), "active": active, "region": region}
        assert str(actual_key) == key and version is not None and version != predecessor
        seq = self.add("row_write", tx=tx, relation="accounts", key=key, action=action,
            version=str(version), predecessor=None if predecessor is None else str(predecessor), values=data)
        self.bindings.append({"event": seq, "source": source, "fact": "actual affected row; predecessor metadata is not a SELECT read"})
        return str(version)
    def save(self, tx, name, instance):
        _, source = self.log.sql(self.connections[tx], tx, "SAVEPOINT " + quoted(name))
        seq = self.add("savepoint", tx=tx, name=name, instance=instance)
        self.bindings.append({"event": seq, "source": source})
    def undo(self, tx, name, instance):
        _, source = self.log.sql(self.connections[tx], tx, "ROLLBACK TO SAVEPOINT " + quoted(name))
        seq = self.add("rollback_to", tx=tx, instance=instance)
        self.bindings.append({"event": seq, "source": source})
    def release(self, tx, name, instance):
        _, source = self.log.sql(self.connections[tx], tx, "RELEASE SAVEPOINT " + quoted(name))
        seq = self.add("release", tx=tx, instance=instance)
        self.bindings.append({"event": seq, "source": source})
    def rollback(self, tx):
        _, source = self.log.sql(self.connections[tx], tx, "ROLLBACK")
        seq = self.add("rollback_ok", tx=tx)
        self.bindings.append({"event": seq, "source": source})
        self.outcomes[tx] = {"status": "aborted", "source": source}
    def commit(self, tx):
        request = self.add("commit_request", tx=tx)
        raw = self.connections[tx]
        try:
            _, source = self.log.sql(raw, tx, "COMMIT")
            if source["commandTag"] == "ROLLBACK":
                seq = self.add("rollback_ok", tx=tx, commitResponse={"request": request, "commandTag": "ROLLBACK"})
                self.outcomes[tx] = {"status": "aborted", "source": source}
            else:
                assert source["commandTag"] == "COMMIT"
                seq = self.add("commit_ok", tx=tx)
                self.outcomes[tx] = {"status": "committed", "source": source}
            self.bindings.append({"event": seq, "source": source})
            return self.outcomes[tx]["status"]
        except Exception as error:
            code = getattr(error, "sqlstate", None)
            diag = getattr(getattr(error, "diag", None), "sqlstate", None)
            if code in ("40001", "40P01") and diag == code and getattr(error, "pgresult", None) is not None and raw.info.transaction_status.name == "IDLE":
                self.add("rollback_ok", tx=tx, commitResponse={"request": request, "sqlstate": code, "diagnosticSqlstate": diag, "transactionStatus": "IDLE"})
                self.outcomes[tx] = {"status": "aborted", "sqlstate": code, "serverResponse": True}
            else:
                self.add("disconnect", tx=tx)
                self.outcomes[tx] = {"status": "unknown", "errorClass": type(error).__name__}
            raise
    def close(self):
        for raw in self.connections.values(): raw.close()
    def trace(self):
        return {"traceSchema": 3, "dataModel": "relation-set-v1", "relationSchema": SCHEMA,
            "clockDomain": "relation-fixture-" + self.schema,
            "scope": {"exclusiveWriters": True, "completeSnapshotTables": ["accounts"]},
            "events": self.events, "gaps": []}


def p(column, op, value): return {"column": column, "op": op, "value": value}
def v(balance="10", active=True, region="east"): return {"balance": balance, "active": active, "region": region}


def scenario(observed, name):
    active, east, west = [p("active", "eq", True)], [p("region", "eq", "east")], [p("region", "eq", "west")]
    if name == "empty-result":
        observed.begin("A")
        assert observed.read("A", [p("balance", "gt", "0"), p("balance", "lt", "0")]) == []
        assert len(observed.read("A", [p("region", "lt", "\U00010000")])) == 1
        assert len(observed.read("A", [p("id", "ge", "-9223372036854775808"), p("id", "le", "9223372036854775807")])) == 2
        observed.commit("A")
    elif name == "delete-reinsert":
        observed.begin("A"); observed.read("A", [])
        tombstone = observed.write("A", "delete", "1")
        assert observed.read("A", []) == []
        new = observed.write("A", "insert", "1", v("11", False, "west"))
        assert observed.events[-1]["predecessor"] == tombstone and tombstone != new
        observed.read("A", []); observed.commit("A")
    elif name == "same-value-new-version":
        observed.begin("A"); observed.read("A", [])
        a = observed.write("A", "update", "1", v()); observed.read("A", [])
        b = observed.write("A", "update", "1", v()); observed.read("A", [])
        assert a != b
        observed.commit("A"); observed.begin("B"); observed.read("B", []); observed.commit("B")
    elif name == "savepoint-complete-query":
        observed.begin("A"); observed.read("A", [])
        observed.save("A", "same", "S1"); observed.write("A", "update", "1", v("11"))
        observed.save("A", "same", "S2"); observed.write("A", "delete", "1")
        assert observed.read("A", [p("id", "eq", "1")]) == []
        observed.undo("A", "same", "S2"); observed.read("A", [])
        observed.release("A", "same", "S2"); observed.undo("A", "same", "S1")
        observed.read("A", []); observed.release("A", "same", "S1"); observed.commit("A")
    else:
        isolation = "SERIALIZABLE" if name == "serializable-abort-retry" else "REPEATABLE READ"
        observed.begin("A", isolation); observed.begin("B", isolation)
        observed.read("A", east if name == "cross-predicate-update" else active)
        observed.read("B", west if name == "cross-predicate-update" else active)
        if name == "insert-phantom":
            observed.write("A", "insert", "1", v()); observed.write("B", "insert", "2", v("20", True, "west"))
        elif name == "cross-predicate-update":
            observed.write("A", "update", "1", v("10", True, "west")); observed.write("B", "update", "2", v("20", True, "east"))
        else:
            observed.write("A", "update", "1", v("10", False))
            try: observed.write("B", "update", "2", v("20", False, "west"))
            except Exception as error:
                if name != "serializable-abort-retry" or getattr(error, "sqlstate", None) not in ("40001", "40P01"): raise
                observed.rollback("B")
        if name != "serializable-abort-retry":
            assert observed.commit("A") == observed.commit("B") == "committed"
        else:
            for tx in ("A", "B"):
                if tx in observed.outcomes: continue
                try: observed.commit(tx)
                except Exception as error:
                    if getattr(error, "sqlstate", None) not in ("40001", "40P01"): raise
            aborted = [tx for tx in ("A", "B") if observed.outcomes[tx]["status"] == "aborted"]
            assert len(aborted) == 1
            assert sum(o["status"] == "committed" for o in observed.outcomes.values()) == 1
            retry = aborted[0] + "-retry-1"
            observed.begin(retry, "SERIALIZABLE")
            assert len(observed.read(retry, active)) == 1
            observed.commit(retry)


def surviving_writes(events):
    effects, stacks, committed = {}, {}, set()
    for event in events:
        tx, kind = event.get("tx"), event["kind"]
        if kind == "begin": effects[tx], stacks[tx] = [], []
        elif kind == "row_write": effects[tx].append(event)
        elif kind == "savepoint": stacks[tx].append((event["instance"], len(effects[tx])))
        elif kind == "rollback_to":
            at = next(i for i, s in enumerate(stacks[tx]) if s[0] == event["instance"])
            effects[tx] = effects[tx][:stacks[tx][at][1]]; stacks[tx] = stacks[tx][:at+1]
        elif kind == "release":
            at = next(i for i, s in enumerate(stacks[tx]) if s[0] == event["instance"])
            stacks[tx] = stacks[tx][:at]
        elif kind == "commit_ok": committed.add(tx)
    return [e for tx in committed for e in effects[tx]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="mtw_relation_v3_" + uuid.uuid4().hex[:12])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert re.fullmatch(r"mtw_relation_v3_[a-f0-9]{12}", args.schema)
    args.output.mkdir(parents=True, exist_ok=False)
    plan_raw = (DRAFT / "plan.json").read_bytes()
    plan = json.loads(plan_raw)
    assert plan["roundsPerScenario"] == 20 and len(plan["scenarios"]) == 8
    sources = {p.name: binding(p) for p in DRAFT.glob("*.py")}
    prereg = {"schema": 1, "plan": binding(DRAFT / "plan.json"), "sourceBindings": sources,
        "expectedFrozenBeforeDatabaseExecution": True, "scenarios": plan["scenarios"],
        "formalPerformanceMeasurement": False}
    dump(args.output / "frozen-plan.json", prereg)
    receipt = {"schema": 1, "actualPostgresExecution": False, "actualDatabaseExecution": False, "passed": False,
        "completeAutomaticSqlCapture": False, "productionCoreValidation": "pending separate offline execution",
        "formalPerformanceMeasurement": False, "plan": prereg["plan"], "scenarios": [],
        "roundsPerScenario": 20, "scenarioCount": 8}
    try:
        import psycopg
    except ImportError:
        receipt["notExecuted"] = "Optional psycopg driver is unavailable"
        dump(args.output / "database-receipt.json", receipt)
        return 3
    connection_file, dsn = os.environ.get("MTW_PG_CONNECTION_FILE"), os.environ.get("MTW_PG_DSN")
    if connection_file:
        options = json.loads(Path(connection_file).read_text(encoding="utf-8"))
        connect = lambda **kw: psycopg.connect(**options, **kw)
    elif dsn:
        connect = lambda **kw: psycopg.connect(dsn, **kw)
    else:
        receipt["notExecuted"] = "No explicit PostgreSQL connection file or DSN was configured"
        dump(args.output / "database-receipt.json", receipt)
        return 3
    try:
        with connect(autocommit=True) as setup:
            assert setup.info.server_version == 180006
            receipt.update(actualPostgresExecution=True, actualDatabaseExecution=True, serverVersion=setup.info.server_version,
                psycopgVersion=psycopg.__version__)
            for index, spec in enumerate(plan["scenarios"]):
                for round_number in range(plan["roundsPerScenario"]):
                    stem = spec["name"] + "-" + str(round_number + 1).zfill(2)
                    directory = args.output / stem
                    directory.mkdir()
                    schema = args.schema + "_" + str(index) + "_" + str(round_number)
                    raw = RawLog(directory / "raw-sql.jsonl")
                    observed = None
                    try:
                        metadata = install(setup, schema, plan["initialSets"][spec["initial"]], raw)
                        dump(directory / "installation.json", metadata)
                        observed = Observation(connect, schema, raw, metadata, spec["name"], round_number)
                        scenario(observed, spec["name"])
                        target = quoted(schema)
                        effects, effects_source = raw.sql(setup, None, "SELECT version::text,key,predecessor::text,action,old_present,new_present,image FROM " + target + '."effects"')
                        final, final_source = raw.sql(setup, None, "SELECT id,balance,active,region,version FROM " + target + '."accounts"')
                        state, state_source = raw.sql(setup, None, "SELECT key,version::text,present FROM " + target + '."state"')
                        effective = surviving_writes(observed.events)
                        actual = {e[0]: {"key": str(e[1]), "predecessor": e[2], "action": e[3].lower(), "values": e[6]} for e in effects}
                        expected = {e["version"]: {k: e[k] for k in ("key", "predecessor", "action", "values")} for e in effective}
                        assert actual == expected
                        live = {str(r[0]): str(r[4]) for r in final}
                        assert {str(r[0]): r[1] for r in state if r[2]} == live
                        facts = {"effectLedger": encoded(effects), "finalRows": [row(r) for r in final],
                            "state": encoded(state), "sources": {"effects": effects_source, "final": final_source, "state": state_source},
                            "survivingWriteEvents": [e["seq"] for e in effective], "outcomes": observed.outcomes,
                            "actualLedgerEqualsAllCommittedUnrevertedEffects": True,
                            "versionOrderInferredFromAckUuidOrTransactionIds": False}
                        dump(directory / "trace.json", observed.trace())
                        dump(directory / "semantic-bindings.json", {"controlledFixtureOnly": True, "bindings": observed.bindings})
                        dump(directory / "actual-effects.json", facts)
                    except BaseException as error:
                        dump(directory / "failure.json", {"errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None), "scenario": spec["name"], "round": round_number+1})
                        raise
                    finally:
                        if observed is not None: observed.close()
                        raw.close()
                    artifacts = [binding(path) for path in sorted(directory.iterdir()) if path.is_file()]
                    receipt["scenarios"].append({"name": spec["name"], "round": round_number+1,
                        "expectedVerdict": spec["expected"], "path": stem,
                        "artifacts": artifacts, "actualCommittedUnrevertedEffectsVerified": True})
        receipt["passed"] = len(receipt["scenarios"]) == 160
    except BaseException as error:
        receipt["failureClass"] = type(error).__name__
        raise
    finally:
        receipt["sourceBindings"] = sources
        receipt["sourceBindingsAfter"] = {p.name: binding(p) for p in DRAFT.glob("*.py")}
        receipt["sourceBindingsUnchanged"] = receipt["sourceBindingsAfter"] == sources
        receipt["passed"] = receipt["passed"] and receipt["sourceBindingsUnchanged"]
        dump(args.output / "database-receipt.json", receipt)
    print(json.dumps({"passed": receipt["passed"], "actualPostgresExecution": True, "scenarios": len(receipt["scenarios"]), "formalPerformanceMeasurement": False}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
