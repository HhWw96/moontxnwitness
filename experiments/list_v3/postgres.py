"""Six controlled PostgreSQL append-list scenarios; optional psycopg driver.

The semantic mapping below is specific to this fresh fixture's literal SQL.
SQL/results are retained separately; this is not arbitrary SQL instrumentation.
No database starts here. Use an explicitly provided dedicated test database.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("duplicate-business-values", "repeatable-read-cycle", "serializable-retry",
             "own-read-then-rollback", "same-name-scope", "injected-commit-ack-loss")


def write_new(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {"file": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def connection_factory(psycopg):
    defaults = {"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"}
    configured = os.environ.get("MTW_PG_CONNECTION_FILE")
    if configured:
        path = Path(configured)
        if not path.is_file() or path.stat().st_size > 16384:
            raise ValueError("Controlled connection file is unavailable or over budget")
        parameters = json.loads(path.read_bytes())
        if type(parameters) is not dict:
            raise ValueError("Controlled connection file must be an object")
        return lambda **extra: psycopg.connect(**(defaults | parameters | extra))
    if os.environ.get("MTW_PG_DSN"):
        return lambda **extra: psycopg.connect(os.environ["MTW_PG_DSN"], **(defaults | extra))
    return None


class Observation:
    def __init__(self, directory, initial):
        self.events, self.sql_records, self.lock = [], [], threading.RLock()
        self.events_path, self.sql_path = directory / "events.jsonl", directory / "sql-results.jsonl"
        self.events_path.open("xb").close()
        self.sql_path.open("xb").close()
        self.add("snapshot", initial=initial, consistent=True)

    def persist(self, path, value):
        with path.open("ab") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def add(self, kind, **fields):
        with self.lock:
            event = {"seq": len(self.events) + 1, "time": len(self.events), "kind": kind, **fields}
            self.persist(self.events_path, event)
            self.events.append(event)
            return event["seq"]

    def sql(self, connection, tx, text, parameters=None):
        record = {"tx": tx, "sql": text, "parameters": parameters}
        try:
            cursor = connection.execute(text, parameters)
            rows = [list(row) for row in cursor.fetchall()] if cursor.description else []
            record.update(rows=rows, rowcount=cursor.rowcount, commandTag=cursor.statusmessage, sqlstate=None)
        except Exception as error:
            record.update(errorClass=type(error).__name__, sqlstate=getattr(error, "sqlstate", None),
                          diagnosticSqlstate=getattr(getattr(error, "diag", None), "sqlstate", None),
                          transactionStatus=connection.info.transaction_status.name)
            with self.lock:
                record["ordinal"] = len(self.sql_records) + 1
                self.persist(self.sql_path, record)
                self.sql_records.append(record)
            raise
        with self.lock:
            record["ordinal"] = len(self.sql_records) + 1
            self.persist(self.sql_path, record)
            self.sql_records.append(record)
        return rows, record

    def trace(self):
        return {"traceSchema": 3, "dataModel": "append-list-v1", "clockDomain": "owned-postgres-list-log-order",
                "scope": {"exclusiveWriters": True}, "events": self.events, "gaps": []}


class Actor:
    def __init__(self, connect, observed, table, tx, isolation="REPEATABLE READ"):
        self.connection, self.observed, self.table, self.tx = connect(), observed, table, tx
        self.active, self.outcome, self.error_state = True, None, None
        observed.add("begin", tx=tx, connection="connection-" + tx)
        observed.sql(self.connection, tx, "BEGIN ISOLATION LEVEL " + isolation)

    def read(self, key):
        rows, _ = self.observed.sql(self.connection, self.tx, "SELECT items FROM " + self.table + " WHERE key=%s", (key,))
        assert len(rows) == 1 and type(rows[0][0]) is list
        items = rows[0][0]
        self.observed.add("list_read", tx=self.tx, key=key, items=items)
        return items

    def append(self, key, identity, value="same"):
        items = [{"id": identity, "value": value}]
        rows, _ = self.observed.sql(self.connection, self.tx,
            "UPDATE " + self.table + " SET items=items || %s::jsonb WHERE key=%s RETURNING items",
            (json.dumps(items, ensure_ascii=False), key))
        assert len(rows) == 1 and rows[0][0][-1] == items[0]
        self.observed.add("append", tx=self.tx, key=key, **rows[0][0][-1])

    def mark(self, name, instance):
        assert re.fullmatch("[a-z_]+", name)
        self.observed.sql(self.connection, self.tx, 'SAVEPOINT "' + name + '"')
        self.observed.add("savepoint", tx=self.tx, name=name, instance=instance)

    def undo(self, name, instance):
        self.observed.sql(self.connection, self.tx, 'ROLLBACK TO SAVEPOINT "' + name + '"')
        self.observed.add("rollback_to", tx=self.tx, instance=instance)

    def release(self, name, instance):
        self.observed.sql(self.connection, self.tx, 'RELEASE SAVEPOINT "' + name + '"')
        self.observed.add("release", tx=self.tx, instance=instance)

    def rollback(self, sqlstate=None):
        self.observed.sql(self.connection, self.tx, "ROLLBACK")
        self.observed.add("rollback_ok", tx=self.tx)
        self.outcome, self.active, self.error_state = "aborted", False, sqlstate

    def commit(self, drop_ack=False):
        request = self.observed.add("commit_request", tx=self.tx)
        try:
            _, result = self.observed.sql(self.connection, self.tx, "COMMIT")
        except Exception as error:
            state, diagnostic = getattr(error, "sqlstate", None), getattr(getattr(error, "diag", None), "sqlstate", None)
            status = self.connection.info.transaction_status.name
            if state in ("40001", "40P01") and diagnostic == state and status == "IDLE":
                self.observed.add("rollback_ok", tx=self.tx, commitResponse={"request": request, "sqlstate": state,
                    "diagnosticSqlstate": diagnostic, "transactionStatus": status})
                self.outcome, self.active, self.error_state = "aborted", False, state
                return
            self.observed.add("disconnect", tx=self.tx)
            self.outcome, self.active = "unknown", False
            raise
        if result["commandTag"] == "ROLLBACK":
            self.observed.add("rollback_ok", tx=self.tx, commitResponse={"request": request, "commandTag": "ROLLBACK"})
            self.outcome = "aborted"
        else:
            assert result["commandTag"] == "COMMIT"
            self.observed.add("disconnect" if drop_ack else "commit_ok", tx=self.tx)
            self.outcome = "unknown" if drop_ack else "committed"
        self.active = False

    def close(self):
        self.connection.close()


def run_case(connect, admin, schema, directory, name, round_number):
    directory.mkdir(parents=True, exist_ok=False)
    table = '"' + schema + '"."c' + str(SCENARIOS.index(name)) + "_r" + str(round_number) + '"'
    admin.execute("CREATE TABLE " + table + " (key text PRIMARY KEY,items jsonb NOT NULL)")
    admin.execute("INSERT INTO " + table + " VALUES ('x','[]'),('y','[]')")
    initial = dict(admin.execute("SELECT key,items FROM " + table + " ORDER BY key").fetchall())
    observed, actors, retries = Observation(directory, initial), [], []
    failures = []

    def actor(tx="T", isolation="REPEATABLE READ"):
        result = Actor(connect, observed, table, tx, isolation)
        actors.append(result)
        return result

    try:
        if name in ("repeatable-read-cycle", "serializable-retry"):
            isolation = "SERIALIZABLE" if name == "serializable-retry" else "REPEATABLE READ"
            read_barrier, commit_barrier = threading.Barrier(2), threading.Barrier(2)
            workers = [actor("T1", isolation), actor("T2", isolation)]

            def concurrent(worker, read_key, write_key):
                try:
                    values = worker.read(read_key)
                    read_barrier.wait(15)
                    try:
                        if not values:
                            worker.append(write_key, worker.tx + "-append")
                    except Exception as error:
                        state = getattr(error, "sqlstate", None)
                        if state not in ("40001", "40P01"):
                            raise
                        worker.rollback(state)
                    finally:
                        commit_barrier.wait(15)
                    if worker.active:
                        worker.commit()
                except Exception as error:
                    failures.append({"tx": worker.tx, "errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)})

            threads = [threading.Thread(target=concurrent, args=(workers[0], "x", "y"), daemon=True),
                       threading.Thread(target=concurrent, args=(workers[1], "y", "x"), daemon=True)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(40)
            assert not any(thread.is_alive() for thread in threads), "Bounded concurrent workers timed out"
            assert not failures, failures
            initial_outcomes = [{"tx": worker.tx, "outcome": worker.outcome, "sqlstate": worker.error_state} for worker in workers]
            if name == "repeatable-read-cycle":
                assert [worker.outcome for worker in workers] == ["committed", "committed"]
            else:
                assert any(worker.outcome == "aborted" for worker in workers)
                for index, worker in enumerate(workers):
                    if worker.outcome == "aborted":
                        retry = actor(worker.tx + "_retry", "SERIALIZABLE")
                        read_key, write_key = (("x", "y"), ("y", "x"))[index]
                        if not retry.read(read_key):
                            retry.append(write_key, retry.tx + "-append")
                        retry.commit()
                        assert retry.outcome == "committed"
                        retries.append(retry.tx)
        else:
            worker = actor()
            initial_outcomes = []
            if name == "duplicate-business-values":
                worker.append("x", "a1", "重复业务值")
                worker.append("x", "a2", "重复业务值")
                assert worker.read("x") == [{"id": "a1", "value": "重复业务值"}, {"id": "a2", "value": "重复业务值"}]
                worker.commit()
            elif name == "own-read-then-rollback":
                worker.mark("scope", "s1")
                worker.append("x", "a1")
                assert len(worker.read("x")) == 1
                worker.undo("scope", "s1")
                assert worker.read("x") == []
                worker.commit()
            elif name == "same-name-scope":
                worker.mark("repeat", "old")
                worker.append("x", "a1")
                worker.mark("repeat", "new")
                worker.append("x", "a2")
                worker.undo("repeat", "new")
                assert [entry["id"] for entry in worker.read("x")] == ["a1"]
                worker.release("repeat", "new")
                worker.undo("repeat", "old")
                assert worker.read("x") == []
                worker.commit()
            elif name == "injected-commit-ack-loss":
                worker.append("x", "a1")
                worker.commit(drop_ack=True)
                assert worker.outcome == "unknown"
            else:
                raise AssertionError("Unknown scenario")
        final = dict(admin.execute("SELECT key,items FROM " + table + " ORDER BY key").fetchall())
        trace_binding = write_new(directory / "trace.json", observed.trace())
        files = [trace_binding]
        for path in (observed.events_path, observed.sql_path):
            raw = path.read_bytes()
            files.append({"file": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        expected = "violation" if name == "repeatable-read-cycle" else "inconclusive" if name == "injected-commit-ack-loss" else "consistent"
        return {"name": name, "round": round_number, "expectedModelStatus": expected, "passed": True,
                "directory": directory.name, "initialOutcomes": initial_outcomes, "retries": retries, "serverFinalLists": final,
                "faultInjection": "The real COMMIT response is retained in the SQL log but deliberately omitted from the semantic trace" if name == "injected-commit-ack-loss" else None,
                "files": files}
    finally:
        for worker in actors:
            worker.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema", default="mtw_list_v3")
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()
    assert re.fullmatch("[a-z][a-z0-9_]{0,30}", args.schema) and 1 <= args.rounds <= 20
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "passed": False, "status": "not-executed", "actualDatabaseExecution": False,
               "roundsPerScenario": args.rounds, "smokeOnly": args.rounds != 20,
               "mappingScope": "Only the literal fresh-schema SQL in this fixture; not arbitrary SQL, automatic application capture, or production adoption",
               "serverAckOrderUsedAsCommitOrder": False, "cases": [], "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        import psycopg
        connect = connection_factory(psycopg)
        if connect is None:
            raise ImportError("Explicit database configuration is required")
    except (ImportError, OSError, ValueError, TypeError):
        receipt["reason"] = "Optional psycopg driver or explicitly provided PostgreSQL test database is unavailable"
        write_new(args.output / "database-receipt.json", receipt)
        print(json.dumps({"status": receipt["status"], "actualDatabaseExecution": False}))
        return 3
    schema = args.schema + "_" + uuid.uuid4().hex[:12]
    admin, schema_created = None, False
    try:
        admin = connect(autocommit=True)
        receipt.update(actualDatabaseExecution=True, status="running", server=admin.execute("SELECT version()").fetchone()[0], driver=psycopg.__version__)
        admin.execute('CREATE SCHEMA "' + schema + '"')
        schema_created = True
        for name in SCENARIOS:
            for number in range(args.rounds):
                case = run_case(lambda: connect(autocommit=True), admin, schema,
                                args.output / (name + "-" + str(number).zfill(2)), name, number)
                receipt["cases"].append(case)
            print(json.dumps({"progress": name, "roundsCompleted": args.rounds}), flush=True)
        receipt.update(passed=True, status="passed")
    except Exception as error:
        receipt.update(status="failed", errorClass=type(error).__name__, sqlstate=getattr(error, "sqlstate", None))
    finally:
        if schema_created:
            try:
                admin.execute('DROP SCHEMA "' + schema + '" CASCADE')
                receipt["ownedSchemaCleanup"] = True
            except Exception:
                receipt["ownedSchemaCleanup"] = False
        if admin is not None:
            admin.close()
        receipt["finishedAt"] = datetime.now(timezone.utc).isoformat()
        write_new(args.output / "database-receipt.json", receipt)
    print(json.dumps({"passed": receipt["passed"], "actualDatabaseExecution": receipt["actualDatabaseExecution"],
                      "roundsPerScenario": args.rounds, "cases": len(receipt["cases"]), "smokeOnly": receipt["smokeOnly"]}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
