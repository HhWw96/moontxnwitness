"""Real PostgreSQL savepoint observations; not a claim of mapped arbitrary SQL.

Runs only in a fresh owned schema. SQL/results and protocol observations remain
separate from model facts. Until the SQL mapping verifier is implemented, these
raw traces deliberately retain unmapped_statement coverage gaps.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/provenance"))
from postgres_test import connection_factory
from prototype import controlled_schema, identifier, qualified


class Observation:
    def __init__(self, raw, table, log):
        self.raw, self.table, self.events, self.results = raw, table, [], []
        self.log = log
        self.log.open("xb").close()
        self.add("snapshot", consistent=True, initial={"x": "x0"})
        self.add("begin", tx="T", connection="C")

    def add(self, kind, **fields):
        item = {"seq": len(self.events) + 1, "time": len(self.events), "kind": kind, **fields}
        self.events.append(item)
        with self.log.open("ab") as stream:
            stream.write(json.dumps(item).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return item["seq"]

    def sql(self, sql, parameters=None):
        statement = self.add("statement", tx="T", sql=sql, parameters=parameters)
        try:
            cursor = self.raw.execute(sql, parameters)
        except Exception as error:
            self.log.with_suffix(".failure.json").write_bytes(json.dumps({
                "statement": statement, "errorClass": type(error).__name__,
                "sqlstate": getattr(error, "sqlstate", None)}).encode() + b"\n")
            raise
        rows = cursor.fetchall() if cursor.description else []
        self.add("rows", tx="T", statement=statement, rows=[list(row) for row in rows], complete=True)
        self.results.append({"statement": statement, "rows": [list(row) for row in rows],
                             "rowcount": cursor.rowcount, "status": cursor.statusmessage})
        return rows

    def mark(self, name, identity):
        self.sql('SAVEPOINT "' + name + '"')
        self.add("savepoint", tx="T", name=name, instance=identity)

    def release(self, name, identity):
        self.sql('RELEASE SAVEPOINT "' + name + '"')
        self.add("release", tx="T", instance=identity)

    def undo(self, name, identity):
        self.sql('ROLLBACK TO SAVEPOINT "' + name + '"')
        self.add("rollback_to", tx="T", instance=identity)

    def write(self, version):
        rows = self.sql("UPDATE " + self.table + " SET version=%s WHERE id='x' "
                        "RETURNING WITH (OLD AS o, NEW AS n) o.version,n.version", (version,))
        assert len(rows) == 1 and rows[0][1] == version
        self.add("write", tx="T", key="x", version=rows[0][1], predecessor=rows[0][0])

    def read(self, expected):
        rows = self.sql("SELECT version FROM " + self.table + " WHERE id='x'")
        assert rows == [(expected,)]
        self.add("read", tx="T", key="x", version=rows[0][0])

    def commit(self):
        self.add("commit_request", tx="T")
        self.raw.commit()
        self.add("commit_ok", tx="T")

    def trace(self):
        return {"traceSchema": 3, "clockDomain": "owned-postgres-fixture-clock",
                "scope": {"exclusiveWriters": True}, "gaps": [], "events": self.events}


def run(connect, setup, schema, output):
    cases = []
    for name in ("read-before-rollback", "read-after-rollback", "released-child-parent-rollback",
                 "duplicate-name-reveal", "repeated-rollback-target", "cursor-position-survives"):
        table = qualified(schema, "case_" + name.replace("-", "_"))
        setup.execute("CREATE TABLE " + table + " (id text PRIMARY KEY,version text NOT NULL)")
        setup.execute("INSERT INTO " + table + " VALUES('x','x0')")
        with connect() as raw:
            observed = Observation(raw, table, output / (name + ".events.jsonl"))
            if name == "read-before-rollback":
                observed.mark("work", "S1"); observed.write("x1"); observed.read("x1")
                observed.undo("work", "S1"); expected = "x0"
            elif name == "read-after-rollback":
                observed.mark("work", "S1"); observed.write("x1"); observed.undo("work", "S1")
                observed.read("x0"); expected = "x0"
            elif name == "released-child-parent-rollback":
                observed.mark("parent", "S1"); observed.mark("child", "S2")
                observed.write("x1"); observed.release("child", "S2"); observed.read("x1")
                observed.undo("parent", "S1"); observed.read("x0"); expected = "x0"
            elif name == "duplicate-name-reveal":
                observed.mark("same", "S1"); observed.write("x1"); observed.mark("same", "S2")
                observed.write("x2"); observed.undo("same", "S2"); observed.read("x1")
                observed.release("same", "S2"); observed.undo("same", "S1"); observed.read("x0"); expected = "x0"
            elif name == "repeated-rollback-target":
                observed.mark("work", "S1"); observed.write("x1"); observed.undo("work", "S1")
                observed.write("x2"); observed.undo("work", "S1"); observed.read("x0"); expected = "x0"
            else:
                observed.sql("DECLARE c CURSOR FOR SELECT n FROM generate_series(1,3) AS n")
                observed.mark("work", "S1")
                assert observed.sql("FETCH 1 FROM c") == [(1,)]
                observed.undo("work", "S1")
                assert observed.sql("FETCH 1 FROM c") == [(2,)]
                observed.sql("CLOSE c"); expected = "x0"
            observed.commit()
        assert setup.execute("SELECT version FROM " + table + " WHERE id='x'").fetchall() == [(expected,)]
        content = json.dumps(observed.trace(), ensure_ascii=False, indent=2).encode() + b"\n"
        trace = name + ".trace.json"
        (output / trace).write_bytes(content)
        cases.append({"name": name, "trace": trace, "sha256": hashlib.sha256(content).hexdigest(),
                      "serverFinalVersion": expected, "delivered": observed.results,
                      "expectedCoverage": "inconclusive: SQL mapping proof is not implemented"})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="mtw_provenance_lifecycle_v3_" + uuid.uuid4().hex[:12])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "actualDatabaseExecution": False, "passed": False,
               "scope": "PostgreSQL lifecycle/cursor semantics; not full SQL capture or business acceptance"}
    try:
        import psycopg
        connect = connection_factory(psycopg)
        if connect is None:
            receipt["notExecuted"] = "No explicit PostgreSQL connection was configured"
            return 3
        with connect(autocommit=True) as setup:
            controlled_schema(args.schema)
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            receipt["actualDatabaseExecution"] = True
            receipt["server"] = setup.execute("SHOW server_version").fetchone()[0]
            receipt["cases"] = run(connect, setup, args.schema, args.output)
        receipt["passed"] = True
    except Exception as error:
        receipt["errorClass"] = type(error).__name__
        raise
    finally:
        receipt["sourceSha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (args.output / "database-receipt.json").write_bytes(json.dumps(receipt, indent=2).encode() + b"\n")
    print(json.dumps({"passed": True, "cases": len(receipt["cases"]), "actualDatabaseExecution": True}))


if __name__ == "__main__":
    raise SystemExit(main())
