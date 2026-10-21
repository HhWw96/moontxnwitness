"""Targeted real PG18 commit-time serialization abort through capture_v3.

This is a protocol fixture, not a discovered dislock defect or SQL-mapping proof.
The original exception object is observed around the driver's own command
generator and compared with the object re-raised by the public capture wrapper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "integrations/python"))
sys.path.insert(0, str(ROOT / "experiments/provenance"))
from moontxnwitness_capture.capture_v3 import CaptureV3Session
from moontxnwitness_capture.journal_v3 import JournalReader
from postgres_test import connection_factory
from prototype import controlled_schema, identifier


def bindings():
    files = [Path(__file__).resolve(), ROOT / "experiments/provenance/postgres_test.py",
             ROOT / "experiments/provenance/prototype.py"]
    files += [ROOT / "integrations/python/moontxnwitness_capture" / name for name in
              ("capture_v3.py", "capture.py", "journal_v3.py", "__init__.py")]
    return {path.relative_to(ROOT).as_posix(): {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size} for path in files}


def run(connect, psycopg, schema, output, receipt):
    controlled_schema(schema)
    table = identifier(schema) + '."ssi_commit"'
    with connect(autocommit=True) as setup:
        assert 180000 <= setup.info.server_version < 190000
        setup.execute("CREATE SCHEMA " + identifier(schema))
        setup.execute("CREATE TABLE " + table + "(key text PRIMARY KEY,n integer NOT NULL)")
        setup.execute("INSERT INTO " + table + " VALUES('x',0),('y',0)")
        receipt.update(actualDatabaseExecution=True, serverVersion=setup.info.server_version,
                       driverVersion=psycopg.__version__)
    session = CaptureV3Session(output / "journal", exclusive_writers=True)
    # No register SQL mapping is declared by this protocol-only fixture.
    session.publish_snapshot({}, consistent=True)
    connections = []
    try:
        for _ in range(2):
            raw = connect()
            raw.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
            connections.append(session.wrap(raw))
        first, second = connections
        assert first.execute("SELECT n FROM " + table + " WHERE key='x'").fetchone() == (0,)
        assert second.execute("SELECT n FROM " + table + " WHERE key='y'").fetchone() == (0,)
        first.execute("UPDATE " + table + " SET n=n+1 WHERE key='y'")
        second.execute("UPDATE " + table + " SET n=n+1 WHERE key='x'")
        outcomes = []
        for connection in connections:
            raw, original = connection._raw, connection._raw._exec_command
            dictionary = raw.__dict__
            existed, previous = "_exec_command" in dictionary, dictionary.get("_exec_command")
            original_errors = []
            def observe_original(command, *args, _original=original, **kwargs):
                try:
                    return (yield from _original(command, *args, **kwargs))
                except BaseException as error:
                    original_errors.append(error)
                    raise
            tx = connection._tx
            raw._exec_command = observe_original
            try:
                result = connection.commit()
                assert result is None
                assert raw.__dict__.get("_exec_command") is observe_original
                outcomes.append({"tx": tx, "outcome": "committed", "originalReturnPreserved": True})
            except psycopg.Error as error:
                assert error.sqlstate == "40001"
                assert error.pgresult is not None
                assert error.diag.sqlstate == error.sqlstate
                assert int(raw.info.transaction_status) == 0
                assert original_errors and original_errors[-1] is error
                assert raw.__dict__.get("_exec_command") is observe_original
                session.flush()
                before = session.journal.stats["lastAcceptedSeq"]
                assert connection.rollback() is None  # This is a later idle rollback, not new evidence.
                session.flush()
                after = session.journal.stats["lastAcceptedSeq"]
                assert before == after
                outcomes.append({"tx": tx, "outcome": "server-confirmed-aborted", "sqlstate": error.sqlstate,
                    "diagnosticSqlstate": error.diag.sqlstate, "pgresultPresent": True,
                    "transactionStatus": "IDLE", "originalExceptionIdentityPreserved": True,
                    "idleRollbackAddedEvents": after - before})
            finally:
                if existed:
                    raw._exec_command = previous
                else:
                    del raw._exec_command
        assert len([row for row in outcomes if row["outcome"] == "server-confirmed-aborted"]) == 1
        assert len([row for row in outcomes if row["outcome"] == "committed"]) == 1
        for connection in connections:
            connection.close()
        status = session.close(source_closed=True)
        assert status.complete
        exported = session.export(output / "capture.json")
        confirmed = []
        for event in JournalReader(session.journal.path).iter_events():
            if event["kind"] == "rollback_ok" and "commitResponse" in event:
                confirmed.append(event)
        assert len(confirmed) == 1
        proof = confirmed[0]["commitResponse"]
        assert set(proof) == {"request", "sqlstate", "diagnosticSqlstate", "transactionStatus"}
        assert proof["sqlstate"] == proof["diagnosticSqlstate"] == "40001"
        assert proof["transactionStatus"] == "IDLE"
        receipt.update(passed=True, outcomes=outcomes, rollbackProof=confirmed[0], journal=status.as_dict(),
                       export=exported, trace="capture.json", expectedAnalysis="inconclusive: protocol fixture does not map its SQL")
    finally:
        for connection in connections:
            if not connection._raw.closed:
                connection.close()
        if not session._closed:
            session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema", default="mtw_provenance_dislock_commit_" + uuid.uuid4().hex[:12])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "passed": False, "actualDatabaseExecution": False,
               "sourceBindings": bindings(), "scope": "Owned PG18 commit protocol; not production or full SQL proof"}
    try:
        import psycopg
        connect = connection_factory(psycopg)
        if connect is None:
            receipt["notExecuted"] = "No explicit owned PostgreSQL configuration"
            return 3
        run(connect, psycopg, args.schema, args.output, receipt)
    except BaseException as error:
        receipt.update(errorClass=type(error).__name__, sqlstate=getattr(error, "sqlstate", None))
        raise
    finally:
        receipt["sourceBindingsAfter"] = bindings()
        receipt["sourceBindingsUnchanged"] = receipt["sourceBindingsAfter"] == receipt["sourceBindings"]
        if not receipt["sourceBindingsUnchanged"]:
            receipt["passed"] = False
        (args.output / "commit-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": receipt["passed"], "actualDatabaseExecution": receipt["actualDatabaseExecution"]}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
