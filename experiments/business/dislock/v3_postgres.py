"""Actual frozen dislock lifecycle exercises on a fresh explicitly owned PG18.

No external application or production deployment is touched. A simulated driver
failure is not substituted for real database reconnect/abort evidence here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "integrations/python"))
sys.path.insert(0, str(ROOT / "experiments/provenance"))
from moontxnwitness_capture.capture_v3 import CaptureV3Session
from moontxnwitness_capture.journal_v3 import JournalReader
from postgres_test import connection_factory
from prototype import identifier, controlled_schema
from business import load_upstream, verify_sources
from v3_install import install
from v3_registry import registry, mappings


class BodyError(Exception):
    pass


def source_bindings():
    files = [ROOT / "integrations/python/moontxnwitness_capture" / name for name in
             ("capture_v3.py", "journal_v3.py", "capture.py", "__init__.py")]
    files += [HERE / name for name in ("v3_postgres.py", "v3_install.py", "v3_registry.py", "v3_registry.json", "business.py")]
    files += [path for path in (HERE / "upstream/source").rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    result = {}
    for path in sorted(files):
        raw = path.read_bytes()
        result[path.relative_to(ROOT).as_posix()] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return result


def wait_until(predicate, *, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        threading.Event().wait(.01)
    raise TimeoutError("Bounded lifecycle observation did not reach its required state")


@contextmanager
def observed_driver(upstream, session, connect):
    """Inject only this already isolated frozen module's driver reference.

    The upstream files, original functions and process-global psycopg module are
    unchanged. Keep this scope open until all original heartbeat threads stop.
    """
    original = upstream.core.psycopg
    connections, guard = [], threading.Lock()
    class Driver:
        def connect(self, *args, **kwargs):
            # The owned configuration is supplied explicitly by the fixture;
            # upstream still calls the same connect(url,autocommit=False) API.
            raw = connect(**kwargs)
            wrapped = session.wrap(raw)
            with guard:
                connections.append(wrapped)
            return wrapped
        def __getattr__(self, name):
            return getattr(original, name)
    upstream.core.psycopg = Driver()
    try:
        yield connections
    finally:
        upstream.core.psycopg = original


def _ledger_count(setup, installed):
    return setup.execute("SELECT count(*) FROM " + installed.object("_mtw_v3_effects")).fetchone()[0]


def _finish(setup, installed, session, output):
    # Workers have stopped before this independent verification window begins.
    # The original initialize() published no snapshot until its commit returned.
    setup.execute("BEGIN")
    try:
        setup.execute("LOCK TABLE " + installed.table_sql + " IN ACCESS EXCLUSIVE MODE")
        installed.verify(setup)
        profiles = [installed.profile(setup, session.encode)]
        state = setup.execute("SELECT key,token::text,present FROM " + installed.object("_mtw_v3_state") + " ORDER BY key").fetchall()
        candidates = setup.execute("SELECT count(*) FROM " + installed.object("_mtw_v3_candidates")).fetchone()[0]
        effects = _ledger_count(setup, installed)
        final = setup.execute("SELECT key,value,expire_at FROM " + installed.table_sql + " ORDER BY key").fetchall()
        setup.commit()
    except BaseException:
        setup.rollback()
        session.gap("installation_changed", "End-of-window metadata verification failed.")
        raise
    status = session.close(source_closed=True)
    trace = output / "capture.json"
    exported = (session.export(trace, sql_profiles=profiles) if status.complete else
                session.export_diagnostic(trace, sql_profiles=profiles))
    return {"journal": status.as_dict(), "export": exported, "trace": "capture.json",
        "candidateCount": candidates, "actualEffectCount": effects,
        "state": session.encode(state), "finalBusinessRows": session.encode(final),
        "profiles": profiles, "expectedAnalysis": "inconclusive until fixed SQL/source proof is implemented"}


def business_case(name, connect, setup, schema, output, upstream):
    core = upstream.core
    table = "key_value"
    setup.execute("CREATE SCHEMA " + identifier(schema))
    target = identifier(schema) + "." + identifier(table)
    setup.execute("CREATE TABLE " + target + "(key text PRIMARY KEY,value text NOT NULL,expire_at timestamptz NOT NULL)")
    lock_key = "fixture-" + name
    lease_key, schedule_key = "cronjob-lock:lease:" + lock_key, "cronjob-lock:schedule:" + lock_key
    keys = [lease_key, schedule_key]
    owner = "owner-original"
    if name == "busy-acquisition":
        setup.execute("INSERT INTO " + target + " VALUES(%s,%s,NOW()+INTERVAL '1 minute')", (lease_key, "owner-other"))
    installed = install(setup, schema=schema, table=table, keys=keys)
    manifest = registry(schema, table, installed.version_column, "_mtw_v3_predecessor")
    session = CaptureV3Session(output / "journal", mappings=mappings(manifest), exclusive_writers=True)
    session.publish_snapshot(installed.initial, consistent=True)
    record = {"name": name, "actualDatabaseExecution": True, "upstreamOriginalMethods": True,
              "schema": schema, "ttlSeconds": 5.0, "passed": False}
    context = core.LockContext(url="owned-connection-config", table_parts=[schema, table],
        lock_key=lock_key, owner=owner, run_ttl_seconds=5.0,
        lease_interval_seconds=.30 if name == "heartbeat-reconnect" else .10)
    try:
        with observed_driver(upstream, session, connect) as connections:
            if name == "schedule-and-server-clock":
                connection = upstream.core.psycopg.connect(context.url, autocommit=False)
                observed_now = core.get_db_time(connection)
                assert observed_now.tzinfo is not None
                connection.commit(); connection.close()
                schedule = core.LockContext(url=context.url, table_parts=context.table_parts,
                    lock_key=lock_key, owner=owner, next_run_time=observed_now + datetime.timedelta(seconds=10))
                with core.ScheduleLock(schedule):
                    pass
                assert _ledger_count(setup, installed) == 1
            elif name == "busy-acquisition":
                try:
                    with core.LeaseLock(context):
                        raise AssertionError("Busy lease unexpectedly acquired")
                except upstream.core.LockNotAcquiredError:
                    record["expectedBusinessException"] = "LockNotAcquiredError"
                assert _ledger_count(setup, installed) == 0
                assert setup.execute("SELECT value FROM " + target + " WHERE key=%s", (lease_key,)).fetchone()[0] == "owner-other"
            elif name == "body-exception-cleanup":
                error = BodyError("controlled original business body exception")
                try:
                    with core.LeaseLock(context) as lease:
                        raise error
                except BodyError as observed:
                    assert observed is error
                    record["businessExceptionIdentityPreserved"] = True
                assert not lease.lease_renewer.is_alive()
                assert _ledger_count(setup, installed) >= 2
            elif name == "ownership-lost":
                lease = core.LeaseLock(context)
                lease.__enter__()
                try:
                    other = core.psycopg.connect(context.url, autocommit=False)
                    assert core.expire_lock_now(other, context.table_parts, lease_key, owner)
                    other.commit()
                    acquired, _ = core.try_acquire_run_lock(other, context.table_parts, lease_key, 5.0, "owner-other")
                    other.commit(); other.close()
                    assert acquired
                    assert lease.lease_lost.wait(5)
                finally:
                    try:
                        lease.__exit__(None, None, None)
                    except core.LeaseLostError:
                        record["expectedBusinessException"] = "LeaseLostError"
                assert not lease.lease_renewer.is_alive()
                assert record.get("expectedBusinessException") == "LeaseLostError"
                assert setup.execute("SELECT value FROM " + target + " WHERE key=%s", (lease_key,)).fetchone()[0] == "owner-other"
            else:
                with core.LeaseLock(context) as lease:
                    if name == "heartbeat-reconnect":
                        wait_until(lambda: len(connections) >= 2)
                        heartbeat = connections[1]
                        pid = heartbeat._raw.info.backend_pid
                        assert setup.execute("SELECT pg_catalog.pg_terminate_backend(%s)", (pid,)).fetchone()[0]
                        record["realBackendTerminated"] = True
                        wait_until(lambda: len(connections) >= 3 and _ledger_count(setup, installed) >= 2)
                        record["realReconnectObserved"] = True
                    else:
                        wait_until(lambda: _ledger_count(setup, installed) >= 2)
                    assert lease.lease_renewer.is_alive()
                assert not lease.lease_renewer.is_alive()
                assert _ledger_count(setup, installed) >= 3
                record["originalHeartbeatStopped"] = True
            record["connectionCount"] = len(connections)
        record.update(_finish(setup, installed, session, output))
        record["passed"] = True
        return record
    except BaseException as error:
        record["errorClass"] = type(error).__name__
        if not session._closed:
            try:
                session.close(source_closed=False)
            except Exception:
                pass
        raise
    finally:
        (output / "case-receipt.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def aborted_commit_case(connect, output):
    session = CaptureV3Session(output / "journal", exclusive_writers=True)
    session.publish_snapshot({}, consistent=True)
    with connect() as native:
        try:
            native.execute("SELECT 1/0")
        except Exception:
            pass
        assert int(native.info.transaction_status) == 3
        assert native.commit() is None
        assert int(native.info.transaction_status) == 0
    raw = connect()
    connection = session.wrap(raw)
    original_slot = dict(raw.__dict__)
    error = None
    try:
        try:
            connection.execute("SELECT 1/0")
        except Exception as observed:
            error = observed
        assert error is not None and error.sqlstate == "22012"
        assert int(raw.info.transaction_status) == 3
        assert connection.commit() is None
        assert int(raw.info.transaction_status) == 0
        assert "_exec_command" not in raw.__dict__ if "_exec_command" not in original_slot else raw.__dict__["_exec_command"] is original_slot["_exec_command"]
        connection.close()
        status = session.close(source_closed=True)
        assert not status.complete  # The failed unmapped SQL is explicitly retained.
        trace = output / "capture.json"
        session.export_diagnostic(trace)
        outcome = None
        for event in JournalReader(session.journal.path).iter_events(require_complete=False):
            if event["kind"] == "rollback_ok":
                outcome = event
        assert outcome is not None and outcome["commitResponse"]["commandTag"] == "ROLLBACK"
        return {"name": "aborted-commit-response", "passed": True, "actualDatabaseExecution": True,
                "originalCommitReturnPreserved": True, "originalHookRestored": True,
                "observedCommandTag": "ROLLBACK", "journal": status.as_dict(), "trace": "capture.json",
                "expectedAnalysis": "inconclusive: unmapped failed statement"}
    finally:
        if not raw.closed:
            raw.close()
        if not session._closed:
            session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--schema", default="mtw_provenance_dislock_v3_" + uuid.uuid4().hex[:10])
    args = parser.parse_args()
    controlled_schema(args.schema)
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "actualDatabaseExecution": False, "passed": False, "cases": [],
        "scope": "Owned PG18, frozen original synchronous dislock lifecycle, experimental point/version projection; not production adoption",
        "sourceBindings": source_bindings()}
    try:
        import psycopg
        connect = connection_factory(psycopg)
        if connect is None:
            receipt["notExecuted"] = "No explicit PostgreSQL connection configured"
            return 3
        receipt["upstream"] = verify_sources()
        upstream = load_upstream()
        with connect(autocommit=True) as setup:
            assert 180000 <= setup.info.server_version < 190000
            receipt["actualDatabaseExecution"], receipt["serverVersion"] = True, setup.info.server_version
            for index, name in enumerate(("schedule-and-server-clock", "acquire-heartbeat-cleanup", "busy-acquisition",
                    "ownership-lost", "heartbeat-reconnect", "body-exception-cleanup")):
                output = args.output / name; output.mkdir()
                result = business_case(name, connect, setup, args.schema + "_" + str(index), output, upstream)
                receipt["cases"].append(result)
            output = args.output / "aborted-commit-response"; output.mkdir()
            receipt["cases"].append(aborted_commit_case(connect, output))
        receipt["passed"] = True
    except BaseException as error:
        receipt["errorClass"] = type(error).__name__
        raise
    finally:
        receipt["sourceSha256"] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ("v3_postgres.py", "v3_install.py", "v3_registry.py", "v3_registry.json")}
        receipt["sourceBindingsAfter"] = source_bindings()
        receipt["sourceBindingsUnchanged"] = receipt["sourceBindings"] == receipt["sourceBindingsAfter"]
        if not receipt["sourceBindingsUnchanged"]:
            receipt["passed"] = False
            receipt["sourceChangedDuringRun"] = True
        (args.output / "database-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": receipt["passed"], "cases": len(receipt["cases"]), "actualDatabaseExecution": True}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
