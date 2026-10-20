"""Controlled actual PG18 CRUD/absence fixture; never adopts an existing schema."""
import argparse
import dataclasses
import hashlib
import json
import platform
import threading
import time
import traceback
import uuid
from pathlib import Path
from unittest.mock import patch

from presence_profile import (PROJECTION, PresenceCapture, PresencePointProfile,
                              verify_presence_installation)
from postgres_test import connection_factory
from prototype import ProvenanceError, controlled_schema, identifier, qualified, verify_audit


def prepared(setup, schema, table, *, empty=False):
    p = PresencePointProfile(schema, table)
    setup.execute("CREATE TABLE " + p.names.business + " (id text PRIMARY KEY,value text NOT NULL)")
    if not empty:
        setup.execute("INSERT INTO " + p.names.business + " VALUES('a','same')")
    capture = PresenceCapture(p, keys=("a", "b", "never"), exclusive_writers=True)
    capture.initialize(setup)
    return capture, p


def save(folder, name, session, expected_status, verdict=None, **facts):
    session.close()
    filename = name + ".trace.json"
    (folder / filename).write_text(json.dumps(session.document(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"name": name, "trace": filename, "expectedStatus": expected_status,
            "expectedVerdict": verdict, "facts": facts}


def finish(setup, session, folder, name):
    audit = session.installation.audit(setup)
    verified = verify_audit(audit)
    doc = session.document()
    committed = {e["tx"] for e in doc["events"] if e["kind"] == "end" and e["status"] == "committed"}
    aborted = {e["tx"] for e in doc["events"] if e["kind"] == "end" and e["status"] == "aborted"}
    by_token = {row["token"]: row for row in audit}
    assert {row["token"] for row in audit if row["action"] != "initial"} == {
        fact["version"] for fact in doc["presenceFacts"]["writes"] if fact["tx"] in committed}
    initial = {fact["version"]: fact for fact in doc["presenceFacts"]["initial"]}
    assert set(initial) == {row["token"] for row in audit if row["action"] == "initial"}
    for token, fact in initial.items():
        assert fact["present"] == by_token[token]["present"]
        assert fact["key"] == session._key(session._tables[0], by_token[token]["key"])
    for fact in doc["presenceFacts"]["writes"]:
        if fact["tx"] in committed:
            row = by_token[fact["version"]]
            assert row["predecessor"] == fact["predecessor"]
            assert row["present"] == fact["newPresent"] and row["action"].lower() == fact["action"]
            assert by_token[row["predecessor"]]["present"] == fact["oldPresent"]
        elif fact["tx"] in aborted:
            assert fact["version"] not in by_token
    filename = name + ".audit.json"
    (folder / filename).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = setup.execute("SELECT id,value FROM " + session.profile.names.business + " ORDER BY id").fetchall()
    session.uninstall(setup)
    after = setup.execute("SELECT id,value FROM " + session.profile.names.business + " ORDER BY id").fetchall()
    assert before == after
    return {"audit": filename, "independentAudit": verified, "committedAuditExactlyMatchesCapturedWrites": True,
            "initialPresenceMatchedLockedAudit": True, "uninstallPreservedBusinessRows": True}


def surface(observed, plain, read):
    assert (observed.rowcount, observed.statusmessage, observed.rownumber) == (plain.rowcount, plain.statusmessage, plain.rownumber)
    if read:
        assert [(c.name, c.type_code) for c in observed.description] == [(c.name, c.type_code) for c in plain.description]
    else:
        assert observed.description is plain.description is None
        for method in ("fetchone", "fetchmany", "fetchall"):
            errors = []
            for cursor in (observed, plain):
                try:
                    getattr(cursor, method)()
                except Exception as error:
                    errors.append((type(error).__name__, str(error), error.sqlstate))
                else:
                    raise AssertionError("Original no-RETURNING command unexpectedly produced rows")
            assert len(errors) == 2 and errors[0] == errors[1]


def serial_case(connect, setup, schema, folder):
    capture, p = prepared(setup, schema, "presence_serial")
    mirror = qualified(schema, "plain_serial")
    setup.execute("CREATE TABLE " + mirror + " (id text PRIMARY KEY,value text NOT NULL)")
    setup.execute("INSERT INTO " + mirror + " VALUES('a','same')")
    with connect() as raw, connect() as baseline:
        conn = capture.wrap(raw)

        def read(key, expected):
            one = conn.execute(p.read_sql, (key,))
            two = baseline.execute("SELECT value FROM " + mirror + " WHERE id=%s", (key,))
            surface(one, two, True)
            assert one.fetchone() == two.fetchone() == expected
            assert one.rownumber == two.rownumber
            assert one.fetchall() == two.fetchall() == []

        def write(action, params):
            one = conn.execute(getattr(p, action + "_sql"), params)
            original = getattr(p, action + "_sql").replace(p.names.business, mirror)
            two = baseline.execute(original, params)
            surface(one, two, False)

        read("a", ("same",))
        read("b", None)
        write("update", ("same", "a"))
        read("a", ("same",))
        write("update", ("same", "a"))
        write("delete", ("a",))
        tombstone = capture.document()["presenceFacts"]["writes"][-1]["version"]
        read("a", None)
        assert capture.document()["presenceFacts"]["reads"][-1]["version"] == tombstone
        write("insert", ("a", "same"))
        assert capture.document()["presenceFacts"]["writes"][-1]["predecessor"] == tombstone
        read("a", ("same",))
        write("insert", ("b", "born"))
        read("b", ("born",))
        write("delete", ("b",))
        read("b", None)
        conn.commit()
        baseline.commit()
        initial_state = setup.execute("SELECT key,token::text,present FROM " + p.names.object("state") + " ORDER BY key").fetchall()
        initial_audit = capture.installation.audit(setup)
        write("delete", ("a",))
        read("a", None)
        write("insert", ("a", "rollback"))
        read("a", ("rollback",))
        aborted_tokens = [x["version"] for x in capture.document()["presenceFacts"]["writes"][-2:]]
        conn.rollback()
        baseline.rollback()
        assert setup.execute("SELECT key,token::text,present FROM " + p.names.object("state") + " ORDER BY key").fetchall() == initial_state
        assert capture.installation.audit(setup) == initial_audit
        read("a", ("same",))
        read("b", None)
        conn.commit()
        baseline.commit()
        error_evidence = []
        for action, params, expected in (("update", (None, "a"), "23502"), ("insert", ("a", "duplicate"), "23505")):
            failures = []
            count = len(capture.document()["presenceFacts"]["writes"])
            for connection, query in ((conn, getattr(p, action + "_sql")),
                                      (baseline, getattr(p, action + "_sql").replace(p.names.business, mirror))):
                try:
                    connection.execute(query, params)
                except Exception as error:
                    failures.append((type(error).__name__, error.sqlstate, error.diag.column_name))
                else:
                    raise AssertionError("Business constraint did not reject the original invalid write")
                connection.rollback()
            assert failures[0] == failures[1] and failures[0][1] == expected
            assert len(capture.document()["presenceFacts"]["writes"]) == count
            assert capture.installation.audit(setup) == initial_audit
            error_evidence.append({"action": action, "class": failures[0][0], "sqlstate": expected, "column": failures[0][2]})
    item = save(folder, "crud-absence-reinsert-rollback", capture, "ready", "consistent",
                tombstone=tombstone, abortedTokens=aborted_tokens,
                businessSurfaceCompared=True, originalConstraintErrors=error_evidence,
                ownBeforeTriggerVisibleToVolatileReturningHelpers=True)
    assert setup.execute("SELECT id,value FROM " + p.names.business + " ORDER BY id").fetchall() == setup.execute("SELECT id,value FROM " + mirror + " ORDER BY id").fetchall()
    item.update(finish(setup, capture, folder, item["name"]))
    return item


def skew_case(connect, setup, schema, folder):
    import psycopg
    capture, p = prepared(setup, schema, "presence_skew", empty=True)
    with connect() as raw1, connect() as raw2:
        raw1.isolation_level = raw2.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        one, two = capture.wrap(raw1), capture.wrap(raw2)
        assert one.execute(p.read_sql, ("b",)).fetchone() is None
        assert two.execute(p.read_sql, ("a",)).fetchone() is None
        one.execute(p.insert_sql, ("a", "occupied"))
        two.execute(p.insert_sql, ("b", "occupied"))
        one.commit()
        two.commit()
    item = save(folder, "negative-point-write-skew", capture, "ready", "violation",
                scope="two frozen-key absence reads followed by disjoint inserts, not an arbitrary range/predicate scan")
    item.update(finish(setup, capture, folder, item["name"]))
    return item


def gap_case(connect, setup, schema, folder, kind):
    capture, p = prepared(setup, schema, "presence_gap_" + kind)
    original_error = None
    with connect() as raw:
        conn = capture.wrap(raw)
        if kind == "unread":
            cursor = conn.execute(p.read_sql, ("never",))
            assert cursor.rowcount == 0
            conn.commit()
        elif kind == "unknown":
            assert conn.execute("SELECT 1").fetchone() == (1,)
            conn.execute("SAVEPOINT outside_profile")
            conn.execute("RELEASE SAVEPOINT outside_profile")
            conn.commit()
        else:
            try:
                conn.execute(p.insert_sql, (None, "null-key"))
            except Exception as error:
                assert error.sqlstate == "23502" and error.diag.column_name == "id"
                original_error = {"class": type(error).__name__, "sqlstate": error.sqlstate, "column": error.diag.column_name}
            else:
                raise AssertionError("NULL PK was not rejected by its native constraint")
            conn.rollback()
            for query, params in ((p.update_sql, ("x", "never")), (p.delete_sql, ("never",))):
                cursor = conn.execute(query, params)
                assert cursor.rowcount == 0 and cursor.description is None
            conn.commit()
    item = save(folder, "gap-" + kind, capture, "inconclusive", originalSqlExecuted=True,
                originalNullKeyError=original_error)
    assert not capture.document()["presenceFacts"]["reads"] and not capture.document()["presenceFacts"]["writes"]
    item.update(finish(setup, capture, folder, item["name"]))
    return item


def rc_case(connect, setup, schema, folder):
    """Wait for a real row lock, then prove DELETE helper uses the updated OLD."""
    import psycopg
    capture, p = prepared(setup, schema, "presence_rc")
    raw1, raw2 = connect(), connect()
    raw1.isolation_level = raw2.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
    one, two = capture.wrap(raw1), capture.wrap(raw2)
    pid1, pid2 = raw1.info.backend_pid, raw2.info.backend_pid
    entered, returned, permit, finished = (threading.Event() for _ in range(4))
    worker, decision, polls, cleanup = {}, {"commit": False}, [], []
    failure, thread = None, None

    def second_delete():
        try:
            entered.set()
            two.execute(p.delete_sql, ("a",))
            worker["tx"] = two._tx
            returned.set()
            if not permit.wait(10):
                raise TimeoutError("Controller did not allow the deletion transaction to finish")
            if decision["commit"]:
                two.commit()
                worker["outcome"] = "committed"
            else:
                two.rollback()
                worker["outcome"] = "aborted"
        except BaseException as error:
            worker["errorClass"] = type(error).__name__
            worker["sqlstate"] = getattr(error, "sqlstate", None)
            try:
                two.rollback()
            except BaseException as rollback_error:
                worker["rollbackErrorClass"] = type(rollback_error).__name__
        finally:
            two.close()
            finished.set()

    started = time.monotonic_ns()
    try:
        one.execute(p.update_sql, ("updated-before-delete", "a"))
        first = capture.document()["presenceFacts"]["writes"][-1]
        thread = threading.Thread(target=second_delete, name="presence-rc-delete", daemon=True)
        thread.start()
        assert entered.wait(5)
        deadline, blocked = time.monotonic() + 5, False
        while time.monotonic() < deadline:
            row = setup.execute("SELECT pg_catalog.pg_blocking_pids(pid),wait_event_type,wait_event,state "
                                "FROM pg_catalog.pg_stat_activity WHERE pid=%s", (pid2,)).fetchone()
            polls.append({"elapsedNs": time.monotonic_ns() - started, "blockers": list(row[0]) if row else [],
                          "waitEventType": row[1] if row else None, "waitEvent": row[2] if row else None})
            if row and pid1 in row[0] and row[1] == "Lock":
                blocked = True
                break
            if finished.is_set():
                raise AssertionError("Deletion exited before a real row wait was observed")
            finished.wait(0.02)  # Pacing only; pg_blocking_pids is the proof.
        assert blocked, "Expected PostgreSQL lock wait was not observed"
        one.commit()
        assert returned.wait(10), "DELETE did not return after UPDATE commit"
        assert "errorClass" not in worker
        second = next(f for f in capture.document()["presenceFacts"]["writes"] if f["tx"] == worker["tx"])
        assert second["action"] == "delete" and second["predecessor"] == first["version"]
        assert second["version"] not in (first["predecessor"], first["version"])
        decision["commit"] = True
        permit.set()
        assert finished.wait(10)
        thread.join(1)
        assert not thread.is_alive() and worker.get("outcome") == "committed" and raw2.closed
        assert one.execute(p.read_sql, ("a",)).fetchone() is None
        assert capture.document()["presenceFacts"]["reads"][-1]["version"] == second["version"]
        one.execute(p.insert_sql, ("a", "reinserted-after-wait"))
        third = capture.document()["presenceFacts"]["writes"][-1]
        assert third["predecessor"] == second["version"]
        one.commit()
        facts = {"blockingPidObserved": True, "updatedToken": first["version"], "deleteOldToken": second["predecessor"],
                 "tombstone": second["version"], "reinsertPredecessor": third["predecessor"],
                 "ownBeforeTriggerVisibleToVolatileReturningHelpers": True,
                 "isolation": "READ COMMITTED configured while raw connections were idle"}
    except BaseException as error:
        failure = {"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)}
        raise
    finally:
        if one._tx is not None:
            try:
                one.rollback()
            except BaseException as error:
                cleanup.append({"operation": "first-rollback", "class": type(error).__name__})
        permit.set()
        if thread is not None and thread.is_alive():
            try:
                raw2.cancel()
            except BaseException as error:
                cleanup.append({"operation": "second-cancel", "class": type(error).__name__})
            thread.join(12)
        if thread is None:
            two.close()
        one.close()
        protocol = {"firstBackendPid": pid1, "secondBackendPid": pid2, "polls": polls, "worker": worker,
                    "failure": failure, "cleanupErrors": cleanup, "threadStillAlive": bool(thread and thread.is_alive()),
                    "connectionsClosed": [raw1.closed, raw2.closed]}
        (folder / "rc-delete.protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    item = save(folder, "read-committed-delete-source", capture, "ready", "consistent", **facts)
    item["protocol"] = "rc-delete.protocol.json"
    item.update(finish(setup, capture, folder, item["name"]))
    return item


def tampering(setup, schema):
    capture, p = prepared(setup, schema, "presence_verifier")
    n, results = p.names, []
    for kind in ("nonce", "trigger-disabled", "helper-body", "helper-stable", "unique-predecessor-index", "extra-metadata-index", "metadata-column"):
        setup.execute("BEGIN")
        setup.execute("LOCK TABLE " + n.business + " IN SHARE MODE")
        candidate = capture.installation
        if kind == "nonce":
            candidate = dataclasses.replace(candidate, nonce=str(uuid.uuid4()))
        elif kind == "trigger-disabled":
            setup.execute("ALTER TABLE " + n.business + " DISABLE TRIGGER " + identifier(n.prefix + "_before"))
        elif kind == "helper-body":
            setup.execute("CREATE OR REPLACE FUNCTION " + n.object("delete_token") + "(target_key text,old_token uuid) RETURNS uuid "
                          "LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$BEGIN RETURN NULL; END$$")
        elif kind == "helper-stable":
            setup.execute("ALTER FUNCTION " + n.object("delete_token") + "(text,uuid) STABLE")
        elif kind == "unique-predecessor-index":
            setup.execute("DROP INDEX " + n.object("successor"))
        elif kind == "extra-metadata-index":
            setup.execute("CREATE INDEX " + identifier(n.prefix + "_extra") + " ON " + n.object("state") + "(token)")
        else:
            setup.execute("ALTER TABLE " + n.object("state") + " ADD COLUMN extra text")
        try:
            verify_presence_installation(setup, candidate)
        except ProvenanceError:
            results.append({"alteration": kind, "rejected": True})
        else:
            raise AssertionError("Changed owned presence DDL was not rejected: " + kind)
        finally:
            setup.rollback()
    capture.close()
    capture.uninstall(setup)
    # Force a verifier failure after all new DDL exists. Transaction rollback
    # must remove both the version column and every owned object.
    target = PresencePointProfile(schema, "presence_failed_install")
    setup.execute("CREATE TABLE " + target.names.business + "(id text PRIMARY KEY,value text NOT NULL)")
    setup.execute("INSERT INTO " + target.names.business + " VALUES('a','original')")
    failed = PresenceCapture(target, keys=("a", "b"), exclusive_writers=True)

    def sabotage(connection, installation):
        connection.execute("DROP INDEX " + installation.names.object("successor"))
        verify_presence_installation(connection, installation)

    with patch("presence_profile.verify_presence_installation", side_effect=sabotage):
        try:
            failed.initialize(setup)
        except ProvenanceError:
            pass
        else:
            raise AssertionError("Failed owned DDL validation unexpectedly published initial facts")
    assert not failed._initialized and failed.document()["events"] == []
    assert setup.execute("SELECT id,value FROM " + target.names.business).fetchall() == [("a", "original")]
    assert setup.execute("SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid=%s::regclass AND attname=%s AND NOT attisdropped",
                         (target.names.business, target.names.version_column)).fetchone()[0] == 0
    assert all(setup.execute("SELECT pg_catalog.to_regclass(%s)", (target.names.object(s),)).fetchone()[0] is None
               for s in ("audit", "state", "installation"))
    results.append({"alteration": "failed-initialization", "rejected": True, "noNewObjectsOrColumn": True, "originalRowsPreserved": True})
    for label, declaration in (("deferred-primary-key", "id text PRIMARY KEY DEFERRABLE INITIALLY DEFERRED,value text NOT NULL"),
                               ("business-default", "id text PRIMARY KEY,value text NOT NULL DEFAULT 'default'")):
        target = PresencePointProfile(schema, "reject_" + label.replace("-", "_"))
        setup.execute("CREATE TABLE " + target.names.business + "(" + declaration + ")")
        rejected = PresenceCapture(target, keys=("a",), exclusive_writers=True)
        try:
            rejected.initialize(setup)
        except ProvenanceError:
            pass
        else:
            raise AssertionError("Unsupported INSERT schema was accepted: " + label)
        assert not rejected._initialized and rejected.document()["events"] == []
        assert setup.execute("SELECT count(*) FROM pg_catalog.pg_attribute WHERE attrelid=%s::regclass AND attname=%s AND NOT attisdropped",
                             (target.names.business, target.names.version_column)).fetchone()[0] == 0
        results.append({"alteration": label, "rejected": True, "noNewObjectsOrColumn": True})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-schema", action="store_true")
    args = parser.parse_args()
    controlled_schema(args.schema)
    import psycopg
    connect = connection_factory(psycopg)
    if connect is None:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "no controlled database configured"}))
        return 3
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=False)
    try:
        with connect(autocommit=True) as setup:
            assert 180000 <= setup.info.server_version < 190000
            server = setup.execute("SELECT version()").fetchone()[0]
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            try:
                scenarios = [serial_case(connect, setup, args.schema, folder), skew_case(connect, setup, args.schema, folder),
                             rc_case(connect, setup, args.schema, folder)]
                scenarios.extend(gap_case(connect, setup, args.schema, folder, kind) for kind in ("unread", "unknown", "zero"))
                rejections = tampering(setup, args.schema)
            finally:
                if not args.keep_schema:
                    setup.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt = {"status": "driver-passed-core-pending", "actualDatabaseExecution": True,
            "server": server, "driver": psycopg.__version__, "python": platform.python_version(), "projection": PROJECTION,
            "scope": "controlled generated text-key CRUD fixture; no existing-application or arbitrary-SQL claim",
            "scenarios": scenarios, "rejections": rejections, "schemaRetained": args.keep_schema,
            "notMeasured": ["full capture C/A", "CPU/RSS", "WAL", "contention performance", "application deployment"],
            "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(__file__).with_name("presence_profile.py"))}}
        (folder / "presence-database.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "actualDatabaseExecution": True, "scenarios": len(scenarios)}))
        return 0
    except BaseException as error:
        receipt = {"status": "failed", "actualDatabaseExecution": True, "errorClass": type(error).__name__,
                   "sqlstate": getattr(error, "sqlstate", None), "message": str(error) if isinstance(error, AssertionError) else None,
                   "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name} for f in traceback.extract_tb(error.__traceback__)]}
        (folder / "presence-failure.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
