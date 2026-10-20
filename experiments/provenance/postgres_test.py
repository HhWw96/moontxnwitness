"""Run both provenance candidates only inside a new explicit fixture schema."""
import argparse
import dataclasses
import json
import os
import platform
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from prototype import (ProvenanceError, controlled_schema, identifier, install,
                       qualified, uninstall, verify_audit)


def connection_factory(psycopg):
    defaults = {"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"}
    if os.environ.get("MTW_PG_CONNECTION_FILE"):
        parameters = json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
        return lambda **extra: psycopg.connect(**(defaults | parameters | extra))
    if os.environ.get("MTW_PG_DSN"):
        return lambda **extra: psycopg.connect(os.environ["MTW_PG_DSN"], **(defaults | extra))
    return None


def exercise(connect, setup, schema, mode):
    table = "items_" + mode
    target = qualified(schema, table)
    setup.execute("CREATE TABLE " + target + " (id text PRIMARY KEY,value integer NOT NULL)")
    setup.execute("INSERT INTO " + target + " VALUES(%s,%s),(%s,%s)", ("a", 7, "b", 11))
    started = time.perf_counter_ns()
    provenance = install(setup, schema=schema, table=table, mode=mode, missing_keys=("new", "never"))
    installation_ns = time.perf_counter_ns() - started
    observations, tokens = [], set()

    def record(label, observed):
        observations.append({"label": label, **observed.as_dict()})
        return observed

    for key in ("a", "b", "new", "never"):
        observed = record("initial-" + key, provenance.observe(setup, key))
        assert observed.token == provenance.initial[key].token
        tokens.add(observed.token)
    assert len(tokens) == 4

    with connect() as transaction:
        original = record("before-repeated-value", provenance.observe(transaction, "a"))
        transaction.execute("UPDATE " + target + " SET value=%s WHERE id=%s", (7, "a"))
        first = record("same-value-write-1", provenance.observe(transaction, "a"))
        transaction.execute("UPDATE " + target + " SET value=%s WHERE id=%s", (7, "a"))
        second = record("same-value-write-2", provenance.observe(transaction, "a"))
        assert len({original.token, first.token, second.token}) == 3
        transaction.execute("DELETE FROM " + target + " WHERE id=%s", ("a",))
        deleted = record("deleted", provenance.observe(transaction, "a"))
        assert not deleted.exists and deleted.token not in {original.token, first.token, second.token}
        transaction.execute("INSERT INTO " + target + " VALUES(%s,%s)" if mode == "sidecar" else
                            "INSERT INTO " + target + "(id,value) VALUES(%s,%s)", ("a", 7))
        reinserted = record("reinserted", provenance.observe(transaction, "a"))
        assert reinserted.exists and reinserted.value == 7 and reinserted.token != deleted.token
        transaction.execute("SAVEPOINT inner_scope")
        transaction.execute("UPDATE " + target + " SET value=%s WHERE id=%s", (99, "a"))
        rolled_back = record("savepoint-write", provenance.observe(transaction, "a"))
        transaction.execute("ROLLBACK TO SAVEPOINT inner_scope")
        restored = record("savepoint-restored", provenance.observe(transaction, "a"))
        assert restored.token == reinserted.token and restored.value == 7
        transaction.execute("RELEASE SAVEPOINT inner_scope")
    assert rolled_back.token not in {row["token"] for row in provenance.audit(setup)}

    with connect() as transaction:
        transaction.execute("UPDATE " + target + " SET value=%s WHERE id=%s", (22, "b"))
        aborted = record("transaction-write-before-rollback", provenance.observe(transaction, "b"))
        transaction.rollback()
    assert provenance.observe(setup, "b").token == provenance.initial["b"].token
    assert aborted.token not in {row["token"] for row in provenance.audit(setup)}

    with connect() as transaction:
        transaction.execute("INSERT INTO " + target + "(id,value) VALUES(%s,%s)", ("new", 5))
        inserted = record("initially-missing-inserted", provenance.observe(transaction, "new"))
        assert inserted.exists and inserted.token != provenance.initial["new"].token
        transaction.execute("DELETE FROM " + target + " WHERE id=%s", ("new",))
        tombstone = record("initially-missing-deleted", provenance.observe(transaction, "new"))
        assert not tombstone.exists and tombstone.token != inserted.token

    # Two actual connections compete for the same business row; no trigger
    # ordering claim follows from thread return order or UUID sorting.
    barrier = threading.Barrier(2, timeout=10)
    errors = []
    def writer(index):
        try:
            with connect() as transaction:
                barrier.wait()
                transaction.execute("UPDATE " + target + " SET value=%s WHERE id=%s", (7, "a"))
                record("concurrent-writer-" + str(index), provenance.observe(transaction, "a"))
        except BaseException as error:
            errors.append(type(error).__name__)
            barrier.abort()
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors and not any(thread.is_alive() for thread in threads), "Concurrent writer fixture failed"

    audit = provenance.audit(setup)
    verified = verify_audit(audit)
    by_token = {row["token"]: row for row in audit}
    for observed in observations:
        if observed["label"] in ("savepoint-write", "transaction-write-before-rollback"):
            continue
        row = by_token[observed["token"]]
        assert row["present"] == observed["exists"]
        assert row["newValue"] == observed["value"]

    wrong_owner = dataclasses.replace(provenance, nonce=str(uuid.uuid4()))
    try:
        uninstall(setup, wrong_owner)
    except ProvenanceError:
        pass
    else:
        raise AssertionError("Mismatched installation marker must refuse uninstall")
    before_uninstall = setup.execute("SELECT id,value FROM " + target + " ORDER BY id").fetchall()
    uninstall(setup, provenance)
    after_uninstall = setup.execute("SELECT id,value FROM " + target + " ORDER BY id").fetchall()
    assert before_uninstall == after_uninstall
    columns = setup.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table)).fetchall()
    assert columns == [("id",), ("value",)]
    reinstall = install(setup, schema=schema, table=table, mode=mode, missing_keys=("new", "never"))
    assert reinstall.nonce != provenance.nonce
    uninstall(setup, reinstall)
    return {"mode": mode, "actualDatabaseExecution": True, "passed": True,
            "initial": [v.as_dict() for v in provenance.initial.values()],
            "observations": observations, "audit": audit, "independentSourceCheck": verified,
            "uninstallPreservedBusinessRows": True, "reinstallPassed": True,
            "installationSmokeNs": installation_ns,
            "installationTimingClaim": "one smoke run only; not a comparative performance benchmark"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, help="new caller-owned mtw_provenance_* schema")
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-schema", action="store_true")
    args = parser.parse_args()
    controlled_schema(args.schema)
    try:
        import psycopg
    except ModuleNotFoundError:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "optional psycopg is missing"}))
        return 3
    connect = connection_factory(psycopg)
    if connect is None:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "no controlled test database configured"}))
        return 3
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    created = False
    try:
        with connect(autocommit=True) as setup:
            server = setup.execute("SELECT version()").fetchone()[0]
            assert 180000 <= setup.info.server_version < 190000, "This prototype fixture targets PostgreSQL 18"
            # No IF NOT EXISTS: an existing schema is never adopted or cleaned up.
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            created = True
            try:
                results = [exercise(connect, setup, args.schema, mode) for mode in ("column", "sidecar")]
            finally:
                if created and not args.keep_schema:
                    setup.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt = {"status": "passed", "actualDatabaseExecution": True, "server": server,
                   "driver": psycopg.__version__, "python": platform.python_version(),
                   "scope": "controlled provenance prototypes; not production/business adoption",
                   "schemaRetained": args.keep_schema, "results": results,
                   "costStudy": {"status": "not-measured", "metrics": [
                       "application code/config/DDL changes", "install and uninstall lock duration",
                       "TPS and P50/P95/P99 with alternating on/off runs", "CPU and peak RSS",
                       "WAL bytes and storage growth", "lock waits, deadlocks and changed outcomes",
                       "metadata/audit retention and vacuum cost"]}}
        (output / "provenance.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "passed", "actualDatabaseExecution": True, "prototypes": 2}))
        return 0
    except BaseException as error:
        failure = {"status": "failed", "actualDatabaseExecution": True,
                   "errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
                   "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                              for frame in traceback.extract_tb(error.__traceback__)],
                   "scope": "controlled provenance prototypes; no driver message/connection credentials exported"}
        (output / "failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        # Preserve frame locations without driver messages or source-line values.
        print(json.dumps(failure))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
