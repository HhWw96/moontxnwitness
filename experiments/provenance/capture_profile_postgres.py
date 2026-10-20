"""Actual PostgreSQL fixture for the opt-in existing-row capture profile.

Creates a NEW caller-specified controlled schema only. No external application
or production data is installed, read or modified. Core normalization runs in
the companion capture_profile_e2e.mjs, not in this Python driver fixture.
"""
import argparse
import dataclasses
import hashlib
import json
import platform
import traceback
import uuid
from pathlib import Path
from unittest.mock import patch

from capture_profile import ColumnCapture, ColumnPointProfile, verify_installation
from postgres_test import connection_factory
from prototype import ProvenanceError, controlled_schema, identifier, qualified, uninstall, verify_audit
from moontxnwitness_capture import CaptureSession, CaptureSetupError, Table, PointRead


def evidence(session, kind, op_type=None):
    return [e for e in session.document()["events"] if e["kind"] == kind
            and (op_type is None or e["op"]["type"] == op_type)]


def prepared(connect, setup, schema, table, values=(7, 11)):
    profile = ColumnPointProfile(schema, table)
    setup.execute("CREATE TABLE " + profile.names.business
                  + " (id text PRIMARY KEY,value integer NOT NULL)")
    setup.execute("INSERT INTO " + profile.names.business + " VALUES(%s,%s),(%s,%s)", ("a", values[0], "b", values[1]))
    session = ColumnCapture(profile, keys=("a", "b"), exclusive_writers=True)
    session.initialize(setup)
    return session, profile


def write_trace(folder, name, session, expected_status, expected_verdict=None, **facts):
    session.close()
    path = name + ".trace.json"
    (folder / path).write_text(json.dumps(session.document(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"name": name, "trace": path, "expectedStatus": expected_status,
            "expectedVerdict": expected_verdict, "facts": facts}


def compare_surface(profile_cursor, plain_cursor, is_read):
    assert profile_cursor.rowcount == plain_cursor.rowcount
    assert profile_cursor.statusmessage == plain_cursor.statusmessage
    assert profile_cursor.rownumber == plain_cursor.rownumber
    if is_read:
        a = [(c.name, c.type_code) for c in profile_cursor.description]
        b = [(c.name, c.type_code) for c in plain_cursor.description]
        assert a == b and len(a) == 1
    else:
        assert profile_cursor.description is plain_cursor.description is None
        for method in ("fetchone", "fetchmany", "fetchall"):
            failures = []
            for cursor in (profile_cursor, plain_cursor):
                try:
                    getattr(cursor, method)()
                except Exception as error:
                    failures.append((type(error).__name__, str(error), error.sqlstate))
                else:
                    raise AssertionError("No-RETURNING UPDATE fetch unexpectedly produced a result")
            assert failures[0] == failures[1]


def serial_case(connect, setup, schema, folder):
    session, p = prepared(connect, setup, schema, "items_serial")
    plain = qualified(schema, "plain_serial")
    setup.execute("CREATE TABLE " + plain + " (id text PRIMARY KEY,value integer NOT NULL)")
    setup.execute("INSERT INTO " + plain + " VALUES('a',7),('b',11)")
    with connect() as raw, connect() as baseline:
        conn = session.wrap(raw)
        first = conn.execute(p.read_sql, ("a",))
        plain_read = baseline.execute("SELECT value FROM " + plain + " WHERE id=%s", ("a",))
        compare_surface(first, plain_read, True)
        assert first.fetchone() == plain_read.fetchone() == (7,)
        versions = []
        for _ in range(2):
            write = conn.execute(p.write_sql, (7, "a"))
            original = baseline.execute("UPDATE " + plain + " SET value=%s WHERE id=%s", (7, "a"))
            compare_surface(write, original, False)
            write.close()
            original.close()
            closed = []
            for cursor in (write, original):
                try:
                    cursor.fetchone()
                except Exception as error:
                    closed.append((type(error).__name__, str(error), error.sqlstate))
                else:
                    raise AssertionError("Closed cursor fetch unexpectedly succeeded")
            assert closed[0] == closed[1] and closed[0][0] == "InterfaceError"
            version = evidence(session, "op", "write")[-1]["op"]["version"]
            versions.append(version)
            assert conn.execute(p.read_sql, ("a",)).fetchmany(1) == [(7,)]
            assert evidence(session, "op", "read")[-1]["op"]["version"] == version
        assert len(set(versions)) == 2
        conn.commit()
        baseline.commit()
        initial = session.document()["events"][0]["initial"]
        assert not set(versions).intersection(initial.values())

        conn.execute(p.write_sql, (99, "b"))
        aborted_token = evidence(session, "op", "write")[-1]["op"]["version"]
        assert conn.execute(p.read_sql, ("b",)).fetchall() == [(99,)]
        conn.rollback()
        known_writes = len(evidence(session, "op", "write"))
        for connection, sql in ((conn, p.write_sql), (baseline, "UPDATE " + plain + " SET value=%s WHERE id=%s")):
            try:
                connection.execute(sql, (None, "a"))
            except Exception as error:
                assert error.sqlstate == "23502"
            else:
                raise AssertionError("Original NOT NULL constraint did not reject the business update")
            connection.rollback()
        assert len(evidence(session, "op", "write")) == known_writes
        assert conn.execute(p.read_sql, ("a",)).fetchone() == (7,)
        assert conn.execute(p.read_sql, ("b",)).fetchone() == (11,)
        conn.commit()
        baseline.commit()
    result = write_trace(folder, "same-value-intermediate-rollback", session, "ready", "consistent",
                         intermediateWriteTokens=versions, abortedToken=aborted_token,
                         businessSurfaceCompared=True, originalConstraintError="23502")
    actual = setup.execute("SELECT id,value FROM " + p.names.business + " ORDER BY id").fetchall()
    expected = setup.execute("SELECT id,value FROM " + plain + " ORDER BY id").fetchall()
    assert actual == expected == [("a", 7), ("b", 11)]
    audit = session.installation.audit(setup)
    result["independentAudit"] = verify_audit(audit)
    assert all(token in {r["token"] for r in audit} for token in versions)
    assert aborted_token not in {r["token"] for r in audit}
    result["ddlTamperingRejected"] = check_tampering(setup, session.installation)
    uninstall(setup, session.installation)
    assert setup.execute("SELECT id,value FROM " + p.names.business + " ORDER BY id").fetchall() == expected
    result["uninstallPreservedBusinessRows"] = True
    return result


def check_tampering(setup, installation):
    n = installation.names
    tested = []
    for kind in ("nonce", "disabled-trigger", "function-body"):
        setup.execute("BEGIN")
        setup.execute("LOCK TABLE " + n.business + " IN SHARE MODE")
        candidate = installation
        if kind == "nonce":
            candidate = dataclasses.replace(installation, nonce=str(uuid.uuid4()))
        elif kind == "disabled-trigger":
            setup.execute("ALTER TABLE " + n.business + " DISABLE TRIGGER " + identifier(n.prefix + "_before"))
        else:
            setup.execute("CREATE OR REPLACE FUNCTION " + n.object("before")
                          + "() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN RETURN NEW; END $$")
        try:
            verify_installation(setup, candidate)
        except ProvenanceError:
            tested.append(kind)
        else:
            raise AssertionError("Altered owned installation passed verification")
        finally:
            setup.rollback()
    return tested


def skew_case(connect, setup, schema, folder):
    session, p = prepared(connect, setup, schema, "items_skew", values=(1, 1))
    with connect() as raw1, connect() as raw2:
        one, two = session.wrap(raw1), session.wrap(raw2)
        one.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
        two.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
        assert one.execute(p.read_sql, ("b",)).fetchone() == (1,)
        assert two.execute(p.read_sql, ("a",)).fetchone() == (1,)
        one.execute(p.write_sql, (0, "a"))
        two.execute(p.write_sql, (0, "b"))
        one.commit()
        two.commit()
    result = write_trace(folder, "repeatable-read-write-skew", session, "ready", "violation",
                         schedule="both point reads before disjoint point updates; acknowledged commits")
    uninstall(setup, session.installation)
    return result


def gap_case(connect, setup, schema, folder, unconsumed=False):
    name = "unconsumed" if unconsumed else "unsupported-sql"
    session, p = prepared(connect, setup, schema, "items_" + name.replace("-", "_"))
    with connect() as raw:
        conn = session.wrap(raw)
        if unconsumed:
            cursor = conn.execute(p.read_sql, ("a",))
            conn.commit()
        else:
            assert conn.execute("SELECT 1").fetchone() == (1,)
            conn.execute("SAVEPOINT outside_profile")
            conn.execute("RELEASE SAVEPOINT outside_profile")
            conn.commit()
    result = write_trace(folder, name, session, "inconclusive", originalSqlExecuted=True)
    uninstall(setup, session.installation)
    return result


def assert_uninstalled(setup, session):
    n = session.profile.names
    assert not session._initialized and session.document()["events"] == []
    assert setup.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s",
                         (n.schema, n.table, n.version_column)).fetchone()[0] == 0
    for suffix in ("installation", "audit", "state"):
        assert setup.execute("SELECT pg_catalog.to_regclass(%s)", (n.object(suffix),)).fetchone()[0] is None
    assert setup.execute("SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname IN (%s,%s)",
                         (n.schema, n.prefix + "_before", n.prefix + "_after")).fetchone()[0] == 0


def rejection_cases(setup, schema):
    results = []
    for index, kind in enumerate(("outgoing-fk", "incoming-fk", "rewrite-rule", "check", "generated", "expression-index", "partial-index", "domain", "inherited-parent", "inherited-child", "failure-after-ddl")):
        p = ColumnPointProfile(schema, "reject_" + str(index))
        target = p.names.business
        value_type = "integer"
        if kind == "domain":
            value_type = qualified(schema, "payload_domain")
            setup.execute("CREATE DOMAIN " + value_type + " AS integer")
        setup.execute("CREATE TABLE " + target + " (id text PRIMARY KEY,value " + value_type + " NOT NULL,version text NOT NULL)")
        setup.execute("INSERT INTO " + target + " VALUES('a',7,'original-a'),('b',11,'original-b')")
        if kind == "outgoing-fk":
            parent = qualified(schema, "fk_parent")
            setup.execute("CREATE TABLE " + parent + " (value integer PRIMARY KEY)")
            setup.execute("INSERT INTO " + parent + " VALUES(7),(11)")
            setup.execute("ALTER TABLE " + target + " ADD FOREIGN KEY(value) REFERENCES " + parent + "(value) ON UPDATE CASCADE")
        elif kind == "incoming-fk":
            setup.execute("CREATE TABLE " + qualified(schema, "fk_child") + " (id text REFERENCES " + target + "(id) ON UPDATE CASCADE)")
        elif kind == "rewrite-rule":
            shadow = qualified(schema, "rule_shadow")
            setup.execute("CREATE TABLE " + shadow + " (id text PRIMARY KEY,value integer)")
            setup.execute("CREATE RULE hidden_write AS ON UPDATE TO " + target + " DO ALSO UPDATE " + shadow + " SET value=NEW.value WHERE id=NEW.id")
        elif kind == "check":
            setup.execute("ALTER TABLE " + target + " ADD CHECK(value>=0)")
        elif kind == "generated":
            setup.execute("ALTER TABLE " + target + " ADD COLUMN computed integer GENERATED ALWAYS AS(value+1) STORED")
        elif kind == "expression-index":
            setup.execute("CREATE INDEX " + identifier("expr_idx") + " ON " + target + " ((value+1))")
        elif kind == "partial-index":
            setup.execute("CREATE INDEX " + identifier("partial_idx") + " ON " + target + " (value) WHERE value>0")
        elif kind == "inherited-parent":
            setup.execute("CREATE TABLE " + qualified(schema, "legacy_child") + " () INHERITS (" + target + ")")
        elif kind == "inherited-child":
            parent = qualified(schema, "legacy_parent")
            setup.execute("CREATE TABLE " + parent + " (id text NOT NULL,value integer NOT NULL,version text NOT NULL)")
            setup.execute("ALTER TABLE " + target + " INHERIT " + parent)
        session = ColumnCapture(p, keys=("a", "b"), exclusive_writers=True)
        if kind == "failure-after-ddl":
            def sabotage(connection, installation):
                connection.execute("ALTER TABLE " + target + " DISABLE TRIGGER " + identifier(p.names.prefix + "_before"))
                verify_installation(connection, installation)
            context = patch("capture_profile.verify_installation", side_effect=sabotage)
        else:
            from contextlib import nullcontext
            context = nullcontext()
        with context:
            try:
                session.initialize(setup)
            except ProvenanceError:
                pass
            else:
                raise AssertionError("Unsupported SQL-bearing schema feature was accepted: " + kind)
        assert_uninstalled(setup, session)
        assert setup.execute("SELECT id,value,version FROM " + target + " ORDER BY id").fetchall() == [
            ("a", 7, "original-a"), ("b", 11, "original-b")]
        stable_rejected = None
        if kind in ("outgoing-fk", "incoming-fk", "rewrite-rule", "inherited-parent", "inherited-child"):
            table = Table(schema, p.table, "id", "version")
            stable = CaptureSession([PointRead.for_table(table)], exclusive_writers=True)
            try:
                stable.initialize(setup)
            except CaptureSetupError:
                stable_rejected = True
            else:
                raise AssertionError("Stable capture did not reject FK/rule side effects")
            assert stable.document()["events"] == []
        results.append({"feature": kind, "rejected": True, "stableRejected": stable_rejected,
                        "noNewInstallationObjects": True, "originalBusinessRowsPreserved": True})
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
    created = False
    try:
        with connect(autocommit=True) as setup:
            assert 180000 <= setup.info.server_version < 190000, "Fixture targets PostgreSQL 18"
            server = setup.execute("SELECT version()").fetchone()[0]
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            created = True
            try:
                scenarios = [serial_case(connect, setup, args.schema, folder),
                             skew_case(connect, setup, args.schema, folder),
                             gap_case(connect, setup, args.schema, folder),
                             gap_case(connect, setup, args.schema, folder, unconsumed=True)]
                rejections = rejection_cases(setup, args.schema)
            finally:
                if created and not args.keep_schema:
                    setup.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt = {"status": "driver-passed-core-pending", "actualDatabaseExecution": True,
            "scope": "controlled synthetic SQL profile; not existing external application adoption",
            "server": server, "driver": psycopg.__version__, "python": platform.python_version(),
            "scenarios": scenarios, "rejections": rejections, "schemaRetained": args.keep_schema,
            "notMeasured": ["full capture C/A performance", "multi-client contention cost", "CPU", "RSS", "lock waits"],
            "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__), Path(__file__).with_name("capture_profile.py"), Path(__file__).with_name("prototype.py"))}}
        (folder / "profile-database.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "actualDatabaseExecution": True, "scenarios": len(scenarios)}))
        return 0
    except BaseException as error:
        receipt = {"status": "failed", "actualDatabaseExecution": True,
            "errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
            "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                       for f in traceback.extract_tb(error.__traceback__)]}
        (folder / "profile-failure.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
