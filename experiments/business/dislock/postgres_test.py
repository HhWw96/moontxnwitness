"""Run genuine frozen dislock helpers against a new controlled PostgreSQL schema.

This is a bounded pre-existing component integration, not an upstream defect,
production deployment, full CLI/heartbeat test or full roadmap acceptance.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path

from business import HERE, REPO_ROOT, LeaseClient, make_capture, verify_sources

PROVENANCE = REPO_ROOT / "experiments" / "provenance"
if str(PROVENANCE) not in sys.path:
    sys.path.insert(0, str(PROVENANCE))
from prototype import controlled_schema, identifier, qualified, uninstall, verify_audit

KEYS = ("cronjob-lock:lease:importer", "cronjob-lock:lease:synchronizer")
OWNERS = ("mtw-dislock:1001", "mtw-dislock:1002")


def connection_factory(psycopg):
    defaults = {"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"}
    if os.environ.get("MTW_PG_CONNECTION_FILE"):
        parameters = json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
        return lambda **extra: psycopg.connect(**(defaults | parameters | extra))
    if os.environ.get("MTW_PG_DSN"):
        return lambda **extra: psycopg.connect(os.environ["MTW_PG_DSN"], **(defaults | extra))
    return None


def ops(capture, kind=None):
    return [e["op"] for e in capture.document()["events"] if e["kind"] == "op"
            and (kind is None or e["op"]["type"] == kind)]


def prepared(connect, setup, schema, table):
    client = LeaseClient(schema, table)
    target = qualified(schema, table)
    # Same business schema as the fixed upstream README, only qualified into a
    # new caller-owned test schema. No application version column is invented.
    setup.execute("CREATE TABLE " + target
                  + " (key text PRIMARY KEY,value text NOT NULL,expire_at timestamptz NOT NULL)")
    with connect() as seed:
        for key, owner in zip(KEYS, OWNERS):
            success, expiry = client.acquire_before_capture(seed, key, 600, owner)
            assert success and isinstance(expiry, datetime.datetime)
        seed.commit()
    capture, client = make_capture(setup, schema, table=table, keys=KEYS, exclusive_writers=True)
    capture.initialize(setup)
    return capture, client


def trace(folder, name, capture, status, verdict=None, **facts):
    capture.close()
    filename = name + ".trace.json"
    (folder / filename).write_text(json.dumps(capture.document(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"name": name, "trace": filename, "expectedStatus": status,
            "expectedVerdict": verdict, "facts": facts}


def finish(setup, capture, client):
    target = qualified(*client.table_parts)
    before = setup.execute("SELECT key,value,expire_at FROM " + target + " ORDER BY key").fetchall()
    audit = verify_audit(capture.installation.audit(setup))
    uninstall(setup, capture.installation)
    after = setup.execute("SELECT key,value,expire_at FROM " + target + " ORDER BY key").fetchall()
    assert before == after
    return {"audit": audit, "uninstallPreservedBusinessRows": True}


def success_case(connect, setup, schema, folder):
    capture, client = prepared(connect, setup, schema, "renew_success")
    with connect() as raw:
        conn = capture.wrap(raw)
        initial = client.read_current(conn, KEYS[0])
        assert initial[1] == OWNERS[0]
        assert client.renew(conn, KEYS[0], 120.5, OWNERS[0]) is True
        first = client.read_current(conn, KEYS[0])
        first_token = ops(capture, "write")[-1]["version"]
        assert client.renew(conn, KEYS[0], 120.5, OWNERS[0]) is True
        second = client.read_current(conn, KEYS[0])
        second_token = ops(capture, "write")[-1]["version"]
        # NOW is transaction-stable: identical expiry data is a real repeated
        # business value, while BEFORE triggers create distinct write tokens.
        assert first == second and first[1] == OWNERS[0]
        assert first_token != second_token
        assert len(ops(capture, "write")) == 2
        conn.commit()
    item = trace(folder, "real-renew-same-expiry", capture, "ready", "consistent",
                 actualUpstreamFunction="core.renew_lease", renewals=2,
                 repeatedExpiry=first[0].isoformat(), ownerUnchanged=True,
                 intermediateWriteTokens=[first_token, second_token],
                 timeClaim="same transaction's NOW with unchanged TTL; no cross-transaction absolute comparison")
    item.update(finish(setup, capture, client))
    return item


def rollback_case(connect, setup, schema, folder):
    capture, client = prepared(connect, setup, schema, "renew_rollback")
    with connect() as raw:
        conn = capture.wrap(raw)
        before = client.read_current(conn, KEYS[0])
        assert client.renew(conn, KEYS[0], 300, OWNERS[0]) is True
        aborted_token = ops(capture, "write")[-1]["version"]
        during = client.read_current(conn, KEYS[0])
        assert during[1] == before[1]
        conn.rollback()
        assert client.read_current(conn, KEYS[0]) == before
        conn.commit()
    item = trace(folder, "real-renew-rollback", capture, "ready", "consistent",
                 abortedToken=aborted_token, originalRowRestored=True)
    assert aborted_token not in {r["token"] for r in capture.installation.audit(setup)}
    item.update(finish(setup, capture, client))
    return item


def owner_case(connect, setup, schema, folder):
    capture, client = prepared(connect, setup, schema, "wrong_owner")
    with connect() as raw:
        conn = capture.wrap(raw)
        before = client.read_current(conn, KEYS[0])
        assert client.renew(conn, KEYS[0], 60, "different-owner:9999") is False
        assert client.read_current(conn, KEYS[0]) == before
        assert ops(capture, "write") == []
        conn.commit()
    item = trace(folder, "real-owner-guard-false", capture, "inconclusive",
                 upstreamReturnedFalse=True, noInventedWrite=True, originalRowUnchanged=True)
    item.update(finish(setup, capture, client))
    return item


def columns(cursor):
    return [(c.name, c.type_code) for c in cursor.description] if cursor.description is not None else None


def surface_case(connect, setup, schema, folder):
    capture, observed = prepared(connect, setup, schema, "surface_observed")
    plain = LeaseClient(schema, "surface_plain")
    observed_table, plain_table = (qualified(*c.table_parts) for c in (observed, plain))
    setup.execute("CREATE TABLE " + plain_table
                  + " (key text PRIMARY KEY,value text NOT NULL,expire_at timestamptz NOT NULL)")
    setup.execute("INSERT INTO " + plain_table + " SELECT key,value,expire_at FROM " + observed_table)
    with connect() as raw:
        conn = capture.wrap(raw)
        with conn.cursor() as a, conn.cursor() as b:
            a.execute(observed.read_query(), (KEYS[0],))
            # Fetch before another statement, as required by the point profile.
            ca, ra, sa = columns(a), a.rowcount, a.statusmessage
            row_a = a.fetchone()
            b.execute(plain.read_query(), (KEYS[0],))
            assert columns(b) == ca and b.rowcount == ra and b.statusmessage == sa
            assert row_a == b.fetchone()
        with conn.cursor() as a, conn.cursor() as b:
            a.execute(observed.renew_query(), (120.5, KEYS[0], OWNERS[0]))
            ca, ra, sa, pa = columns(a), a.rowcount, a.statusmessage, a.rownumber
            expiry_a = a.fetchone()
            assert a.fetchmany(1) == [] and a.fetchall() == []
            b.execute(plain.renew_query(), (120.5, KEYS[0], OWNERS[0]))
            assert (columns(b), b.rowcount, b.statusmessage, b.rownumber) == (ca, ra, sa, pa)
            expiry_b = b.fetchone()
            assert expiry_a == expiry_b  # Same server transaction, same NOW.
            assert b.fetchmany(1) == [] and b.fetchall() == []
            closed_a, closed_b = a, b
        errors = []
        for cursor in (closed_a, closed_b):
            try:
                cursor.fetchone()
            except Exception as error:
                errors.append((type(error).__name__, str(error), error.sqlstate))
            else:
                raise AssertionError("Closed business cursor fetch unexpectedly succeeded")
        assert errors[0] == errors[1] and errors[0][0] == "InterfaceError"
        server_now = conn.execute("SELECT transaction_timestamp()").fetchone()[0]
        assert expiry_a[0] - server_now == datetime.timedelta(seconds=120.5)
        conn.commit()
    item = trace(folder, "same-transaction-original-sql-surface", capture, "inconclusive",
                 businessColumnsAndReturningPreserved=True, originalAndObservedShareTransactionNow=True,
                 exactExpiryDeltaSeconds=120.5, closedCursorErrorMatched=True,
                 coverageReason="plain-mirror and verifier SQL intentionally outside the declared business profile; comparison is not a complete trace")
    item.update(finish(setup, capture, observed))
    return item


def unread_case(connect, setup, schema, folder):
    capture, client = prepared(connect, setup, schema, "unread_returning")
    with connect() as raw:
        conn = capture.wrap(raw)
        cursor = conn.execute(client.renew_query(), (60, KEYS[0], OWNERS[0]))
        conn.commit()  # Deliberately fail to consume the original RETURNING.
    item = trace(folder, "unconsumed-original-returning", capture, "inconclusive",
                 scope="adversarial cursor-contract check, not core.renew_lease behavior")
    item.update(finish(setup, capture, client))
    return item


def business_error_case(connect, setup, schema, folder):
    capture, client = prepared(connect, setup, schema, "notnull_error")
    with connect() as raw:
        conn = capture.wrap(raw)
        before = client.read_current(conn, KEYS[0])
        try:
            client.renew(conn, KEYS[0], None, OWNERS[0])
        except Exception as error:
            assert error.sqlstate == "23502"
            error_class = type(error).__name__
        else:
            raise AssertionError("The original NOT NULL constraint did not reject a null TTL result")
        conn.rollback()
        assert ops(capture, "write") == []
        assert client.read_current(conn, KEYS[0]) == before
        conn.commit()
    item = trace(folder, "original-business-error-rollback", capture, "ready", "consistent",
                 originalErrorClass=error_class, originalSqlstate="23502", noFailedWriteInvented=True)
    item.update(finish(setup, capture, client))
    return item


def rc_wait_case(connect, setup, schema, folder):
    """Prove EvalPlanQual's actual OLD source after a real RC row-lock wait."""
    capture, client = prepared(connect, setup, schema, "rc_wait_source")
    raw1, raw2 = connect(), connect()
    from psycopg import IsolationLevel
    # Set the driver configuration while idle. The real helper's first SQL
    # then starts RC without sending a redundant explicit BEGIN command.
    raw1.isolation_level = raw2.isolation_level = IsolationLevel.READ_COMMITTED
    one, two = capture.wrap(raw1), capture.wrap(raw2)
    pid1, pid2 = raw1.info.backend_pid, raw2.info.backend_pid
    entered, renewed, permit_commit, finished = (threading.Event() for _ in range(4))
    decision = {"commit": False}
    worker_info, polls, cleanup = {}, [], []
    thread = None
    failure = None
    started = time.monotonic_ns()

    def second_writer():
        try:
            entered.set()
            worker_info["renewed"] = client.renew(two, KEYS[0], 240, OWNERS[0])
            worker_info["transaction"] = two._tx
            if worker_info["renewed"] is not True:
                raise AssertionError("The existing owner unexpectedly lost its renewal")
            renewed.set()
            if not permit_commit.wait(10):
                raise TimeoutError("Controller did not acknowledge the actual OLD source before commit")
            if decision["commit"]:
                two.commit()
                worker_info["outcome"] = "committed"
            else:
                two.rollback()
                worker_info["outcome"] = "controller-aborted"
        except BaseException as error:
            worker_info["error"] = {"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
                "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                           for f in traceback.extract_tb(error.__traceback__)]}
            try:
                two.rollback()
            except BaseException as rollback_error:
                worker_info["rollbackError"] = type(rollback_error).__name__
        finally:
            try:
                two.close()
            except BaseException as close_error:
                worker_info["closeError"] = type(close_error).__name__
            finished.set()

    try:
        # This earlier read is a separate committed transaction. Reading v0 and
        # v1 inside the UPDATE transaction would itself be a non-repeatable-read
        # history; this case tests the successful RC UPDATE's source instead.
        assert client.read_current(two, KEYS[0])[1] == OWNERS[0]
        previous_token = ops(capture, "read")[-1]["version"]
        two.commit()
        assert client.renew(one, KEYS[0], 180, OWNERS[0]) is True
        first_token = ops(capture, "write")[-1]["version"]
        assert first_token != previous_token
        thread = threading.Thread(target=second_writer, name="dislock-rc-source", daemon=True)
        thread.start()
        if not entered.wait(5):
            raise TimeoutError("Second writer did not enter its explicit RC transaction")
        deadline = time.monotonic() + 5
        proved_wait = False
        while time.monotonic() < deadline:
            row = setup.execute(
                "SELECT pg_catalog.pg_blocking_pids(pid),wait_event_type,wait_event,state "
                "FROM pg_catalog.pg_stat_activity WHERE pid=%s", (pid2,)).fetchone()
            observation = {"elapsedNs": time.monotonic_ns() - started,
                           "blockers": list(row[0]) if row else [],
                           "waitEventType": row[1] if row else None,
                           "waitEvent": row[2] if row else None,
                           "state": row[3] if row else None}
            polls.append(observation)
            if row and pid1 in row[0] and row[1] == "Lock":
                proved_wait = True
                break
            if finished.is_set():
                raise AssertionError("Second writer exited before a real lock wait was proved")
            # Poll pacing only. The PostgreSQL blocking-PID observation, not
            # elapsed time or sleep, is the evidence that the row wait exists.
            finished.wait(0.02)
        if not proved_wait:
            raise TimeoutError("PostgreSQL did not confirm the expected first-writer row wait")
        one.commit()
        if not renewed.wait(10):
            raise TimeoutError("Blocked renewal did not finish after the first acknowledged commit")
        transaction = worker_info["transaction"]
        second_ops = [e["op"] for e in capture.document()["events"]
                      if e["kind"] == "op" and e["tx"] == transaction]
        reads = [op["version"] for op in second_ops if op["type"] == "read"]
        writes = [op["version"] for op in second_ops if op["type"] == "write"]
        assert reads == [first_token], "Second UPDATE OLD token did not name the first writer's actual version"
        assert len(writes) == 1 and writes[0] not in (first_token, previous_token)
        decision["commit"] = True
        permit_commit.set()
        if not finished.wait(10):
            raise TimeoutError("Second transaction did not acknowledge commit and close")
        thread.join(1)
        assert not thread.is_alive() and "error" not in worker_info
        assert worker_info["outcome"] == "committed" and raw2.closed
        second_token = writes[0]
        audit = capture.installation.audit(setup)
        by_token = {row["token"]: row for row in audit}
        assert by_token[first_token]["predecessor"] == previous_token
        assert by_token[second_token]["predecessor"] == first_token
        verify_audit(audit)
        facts = {"blockingPidObserved": True, "firstBackendPid": pid1, "secondBackendPid": pid2,
            "configuredIsolation": "READ COMMITTED; driver setting assigned while idle before wrapping",
            "previousCommittedReadToken": previous_token, "firstWriteToken": first_token,
            "secondUpdateOldToken": reads[0], "secondWriteToken": second_token,
            "workerCommittedAndClosed": True,
            "versionOrderingClaim": "actual same-statement OLD/NEW and predecessor facts only; no order inferred from UUIDs, clocks or threads"}
    except BaseException as error:
        failure = {"class": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None)}
        raise
    finally:
        if one._tx is not None:
            try:
                one.rollback()
            except BaseException as error:
                cleanup.append({"operation": "first-rollback", "errorClass": type(error).__name__})
        permit_commit.set()  # On controller failure, ask the worker to abort.
        if thread is not None and thread.is_alive():
            try:
                raw2.cancel()
            except BaseException as error:
                cleanup.append({"operation": "second-cancel", "errorClass": type(error).__name__})
            thread.join(12)
        if thread is None:
            two.close()
        one.close()
        protocol = {"firstBackendPid": pid1, "secondBackendPid": pid2,
            "polls": polls, "worker": worker_info, "failure": failure, "cleanupErrors": cleanup,
            "threadStillAlive": bool(thread is not None and thread.is_alive()),
            "firstConnectionClosed": raw1.closed, "secondConnectionClosed": raw2.closed,
            "evidence": "independent pg_blocking_pids/wait_event observations; polling delay is not a wait proof"}
        (folder / "read-committed-wait.protocol.json").write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    item = trace(folder, "read-committed-wait-old-source", capture, "ready", "consistent", **facts)
    item["protocol"] = "read-committed-wait.protocol.json"
    item.update(finish(setup, capture, client))
    return item


def main():
    from moontxnwitness_capture.presence import implementation_bindings
    implementation_before = implementation_bindings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-schema", action="store_true")
    args = parser.parse_args()
    controlled_schema(args.schema)
    evidence = verify_sources()
    import psycopg
    connect = connection_factory(psycopg)
    if connect is None:
        print(json.dumps({"status": "not-executed", "actualDatabaseExecution": False, "reason": "no controlled database configured"}))
        return 3
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=False)
    try:
        with connect(autocommit=True) as setup:
            assert 180000 <= setup.info.server_version < 190000, "This fixed profile requires PostgreSQL 18"
            server = setup.execute("SELECT version()").fetchone()[0]
            setup.execute("CREATE SCHEMA " + identifier(args.schema))
            try:
                scenarios = [case(connect, setup, args.schema, folder) for case in
                    (success_case, rollback_case, owner_case, surface_case, unread_case, business_error_case, rc_wait_case)]
            finally:
                if not args.keep_schema:
                    # This fixture created the new schema successfully; it never
                    # adopts, drops or reuses an existing schema.
                    setup.execute("DROP SCHEMA " + identifier(args.schema) + " CASCADE")
        receipt = {"status": "driver-passed-core-pending", "actualDatabaseExecution": True,
            "server": server, "driver": psycopg.__version__, "python": platform.python_version(),
            "upstream": evidence, "upstreamFunctionsExecuted": ["core.try_acquire_run_lock (setup)",
                "core.renew_lease", "_queries.read_current_query", "_queries.renew_lease_query"],
            "scenarios": scenarios, "schemaRetained": args.keep_schema,
            "adoptionScope": "existing upstream component with controlled data; not a production deployment, historical defect, full CLI/heartbeat test or full v0.1.7 acceptance",
            "notMeasured": ["full capture C/A", "CPU/RSS", "thread/reconnect/cleanup coverage", "contended multi-worker outcomes"],
            "sources": {p.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__), HERE / "business.py", PROVENANCE / "returning_profile.py", PROVENANCE / "capture_profile.py")}}
        implementation_after = implementation_bindings()
        assert implementation_before == implementation_after, "Installed implementation changed during execution"
        receipt["implementationSources"] = {"before": implementation_before, "after": implementation_after, "unchanged": True}
        receipt["legacySourceRole"] = "Compatibility shim / fixture hashes; implementationSources binds package code"
        (folder / "business-database.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "actualDatabaseExecution": True, "scenarios": len(scenarios)}))
        return 0
    except BaseException as error:
        receipt = {"status": "failed", "actualDatabaseExecution": True,
            "errorClass": type(error).__name__, "sqlstate": getattr(error, "sqlstate", None),
            "frames": [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                       for f in traceback.extract_tb(error.__traceback__)]}
        (folder / "business-failure.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
