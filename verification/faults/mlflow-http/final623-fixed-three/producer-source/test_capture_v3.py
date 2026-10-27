"""Bounded protocol tests with a fake driver; no database execution."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture import capture_v3 as c
from moontxnwitness_capture.journal_v3 import JournalReader, JournalError, SegmentedJournal, INVALIDATED

BASE = Path(os.environ.get("MTW_JOURNAL_TEST_ROOT", tempfile.gettempdir()))
BASE.mkdir(parents=True, exist_ok=True)
RUN = BASE / ("collector-run-" + uuid.uuid4().hex)
RUN.mkdir()


class BusinessError(Exception):
    pass


class Raw:
    def __init__(self):
        self.info = types.SimpleNamespace(transaction_status=0, encoding="utf-8")
        self.autocommit, self.closed = False, False
        self.responses, self.executed = {}, []
        self.commit_error = self.execute_error = self.rollback_error = None
        self.commit_result, self.commit_tag = object(), b"COMMIT"
        self._pipeline = self._tpc = None
    def cursor(self, *args, **kwargs):
        return RawCursor(self)
    def _exec_command(self, command):
        if False:
            yield None
        return types.SimpleNamespace(command_status=self.commit_tag)
    def commit(self):
        if self.commit_error:
            self.info.transaction_status = 0
            raise self.commit_error
        generator = self._exec_command(b"COMMIT")
        try:
            while True:
                next(generator)
        except StopIteration:
            pass
        self.info.transaction_status = 0
        return self.commit_result
    def rollback(self):
        if self.rollback_error:
            raise self.rollback_error
        self.info.transaction_status = 0
    def close(self):
        self.closed = True
    def __enter__(self):
        return self


class RawCursor:
    def __init__(self, connection):
        self.connection, self.closed, self.arraysize = connection, False, 1
        self.description, self.rows, self.rownumber, self.rowcount = None, [], 0, -1
        self.row_factory = None
        self.statusmessage = None
        self.fetch_error = None
    def execute(self, sql, params=None, **kwargs):
        self.connection.executed.append((sql, params, kwargs))
        self.connection.info.transaction_status = 2
        if self.connection.execute_error:
            self.connection.info.transaction_status = 3
            raise self.connection.execute_error
        kind_sql = sql.lstrip()
        self.rows = list(self.connection.responses.get(sql, [(1,)] if kind_sql.startswith("SELECT") else []))
        self.description = [types.SimpleNamespace(name="c" + str(n), type_code=25)
                            for n in range(len(self.rows[0]) if self.rows else 1)] if kind_sql.startswith(("SELECT", "UPDATE", "INSERT")) else None
        self.rownumber, self.rowcount = 0, len(self.rows)
        self.statusmessage = "SELECT " + str(self.rowcount) if sql.startswith("SELECT") else "UPDATE " + str(self.rowcount)
        return self
    def fetchone(self):
        if self.fetch_error:
            raise self.fetch_error
        if self.closed:
            raise BusinessError("cursor closed")
        if self.description is None:
            raise BusinessError("no result")
        if self.rownumber >= len(self.rows):
            return None
        result = self.rows[self.rownumber]
        self.rownumber += 1
        return result
    def fetchmany(self, size=None):
        size = self.arraysize if size is None else size
        if size == 0:
            return self.fetchall()  # pinned psycopg behavior
        result = self.rows[self.rownumber:self.rownumber + size]
        self.rownumber += len(result)
        return result
    def fetchall(self):
        result = self.rows[self.rownumber:]
        self.rownumber = len(self.rows)
        return result
    def close(self):
        self.closed = True
    def __enter__(self):
        return self


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.path = RUN / self._testMethodName
        self.sessions = []
    def tearDown(self):
        for session in self.sessions:
            if not session._closed:
                session.close()
    def session(self, **options):
        session = c.CaptureV3Session(self.path, **options)
        self.sessions.append(session)
        session.publish_snapshot({"x": "x0"}, consistent=True)
        return session
    def events(self, session):
        session.flush()
        # The writer is deliberately still open in many tests. Inspect each
        # exact durable segment without retaining production event history.
        index = json.loads((session.journal.path / "journal-index.json").read_bytes())
        return [json.loads(line) for item in index["segments"] for line in (session.journal.path / item["name"]).read_bytes().splitlines()]

    def test_automatic_begin_commit_and_rows(self):
        session, raw = self.session(), Raw()
        conn = session.wrap(raw)
        with conn.cursor() as cursor:
            self.assertIs(cursor.execute("SELECT 1"), cursor)
            self.assertEqual(cursor.fetchone(), (1,))
        result = conn.commit()
        self.assertIs(result, raw.commit_result)
        events = self.events(session)
        self.assertEqual([e["kind"] for e in events], ["snapshot", "begin", "statement", "rows", "commit_request", "commit_ok"])
        self.assertTrue(session.close(source_closed=True).complete)
        self.assertFalse(hasattr(session, "_events"))

    def test_exception_identity_execute(self):
        session, raw = self.session(), Raw()
        error = raw.execute_error = BusinessError("same object")
        conn = session.wrap(raw)
        try:
            conn.execute("SELECT 1")
        except BusinessError as observed:
            self.assertIs(observed, error)
        else:
            self.fail("Original business error did not propagate")
        conn.rollback()
        self.assertFalse(session.close(source_closed=True).complete)

    def test_exception_identity_fetch(self):
        session = self.session()
        cursor = session.wrap(Raw()).execute("SELECT 1")
        error = cursor._raw.fetch_error = BusinessError("fetch failed")
        with self.assertRaises(BusinessError) as observed:
            cursor.fetchone()
        self.assertIs(observed.exception, error)

    def test_commit_error_then_idle_rollback_stays_unknown(self):
        session, raw = self.session(), Raw()
        conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall()
        error = raw.commit_error = BusinessError("lost acknowledgement")
        with self.assertRaises(BusinessError) as observed:
            conn.commit()
        self.assertIs(observed.exception, error)
        raw.commit_error = None
        conn.rollback()
        events = self.events(session)
        self.assertIn("disconnect", [e["kind"] for e in events])
        self.assertNotIn("rollback_ok", [e["kind"] for e in events])
        self.assertFalse(session.close(source_closed=True).complete)

    def test_retry_has_new_transaction_identity(self):
        session, raw = self.session(), Raw()
        conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall(); conn.rollback()
        conn.execute("SELECT 1").fetchall(); conn.commit()
        identities = [e["tx"] for e in self.events(session) if e["kind"] == "begin"]
        self.assertEqual(len(set(identities)), 2)

    def test_reconnect_has_new_connection_and_transaction_identity(self):
        session = self.session()
        for _ in range(2):
            conn = session.wrap(Raw())
            conn.execute("SELECT 1").fetchall(); conn.commit(); conn.close()
        begins = [e for e in self.events(session) if e["kind"] == "begin"]
        self.assertNotEqual(begins[0]["connection"], begins[1]["connection"])
        self.assertNotEqual(begins[0]["tx"], begins[1]["tx"])

    def test_duplicate_savepoint_names_and_reveal_older(self):
        session = self.session()
        conn = session.wrap(Raw())
        for sql in ('SAVEPOINT same', 'SAVEPOINT "same"', 'ROLLBACK TO same', 'RELEASE same', 'ROLLBACK TO same'):
            conn.execute(sql)
        conn.rollback()
        events = [e for e in self.events(session) if e["kind"] in ("savepoint", "release", "rollback_to")]
        self.assertNotEqual(events[0]["instance"], events[1]["instance"])
        self.assertEqual(events[2]["instance"], events[1]["instance"])
        self.assertEqual(events[3]["instance"], events[1]["instance"])
        self.assertEqual(events[4]["instance"], events[0]["instance"])

    def test_control_parser_rejects_multiple_statements_and_truncation(self):
        self.assertIsNone(c._control("SAVEPOINT a; SELECT 1"))
        session = self.session(); conn = session.wrap(Raw())
        conn.execute('SAVEPOINT "' + "x" * 64 + '"')
        self.assertFalse(conn._savepoints)
        self.assertIn("savepoint_name_or_mapping_unsupported", {g["code"] for g in session.gaps})

    def test_savepoint_depth_is_bounded(self):
        session = self.session(); conn = session.wrap(Raw())
        for n in range(70):
            conn.execute("SAVEPOINT s" + str(n))
        self.assertEqual(len(conn._savepoints), 64)
        self.assertIn("savepoint_depth_budget", {g["code"] for g in session.gaps})

    def test_mapping_preserves_business_row_surface(self):
        mapping = c.SQLMapping("SELECT value", "fixture.read/1", "SELECT value,token", 1)
        session = self.session(mappings=[mapping]); raw = Raw()
        raw.responses[mapping.executed_sql] = [(9, "actual-token")]
        cursor = session.wrap(raw).execute(mapping.sql)
        self.assertEqual(len(cursor.description), 1)
        self.assertEqual(cursor.rowcount, 1)
        self.assertEqual(cursor.fetchone(), (9,))
        self.assertEqual(cursor.rownumber, 1)
        self.assertIsNone(cursor.fetchone())
        events = self.events(session)
        statement = next(e for e in events if e["kind"] == "statement")
        rows = [e for e in events if e["kind"] == "rows"]
        self.assertEqual(statement["sql"], mapping.sql)
        self.assertEqual(statement["executedSql"], mapping.executed_sql)
        self.assertEqual(rows[0]["rows"], [[9]])
        self.assertEqual(rows[0]["serverRows"], [[9, "actual-token"]])
        self.assertEqual(rows[0]["columns"], [{"name": "c0", "typeCode": 25}])
        self.assertEqual(set(rows[0]["columns"][0]), {"name", "typeCode"})
        self.assertEqual(len(rows), 1)

    def test_mapped_fact_binds_actual_statement(self):
        def observe(cursor, rows, exhausted):
            for row in rows:
                cursor.fact("read", key="x", version=row[1], evidence={"tokenColumn": 1})
        mapping = c.SQLMapping("SELECT value", "fixture.read/1", "SELECT value,token", 1, observe)
        session = self.session(mappings=[mapping]); raw = Raw()
        raw.responses[mapping.executed_sql] = [(9, "token")]
        cursor = session.wrap(raw).execute(mapping.sql); cursor.fetchone()
        events = self.events(session)
        statement = next(e for e in events if e["kind"] == "statement")
        read = next(e for e in events if e["kind"] == "read")
        self.assertEqual(read["statement"], statement["seq"])
        self.assertEqual(read["mappingId"], mapping.mapping_id)
        self.assertEqual(read["version"], "token")

    def test_fetchmany_zero_preserves_driver_behavior_and_prefix(self):
        mapping = c.SQLMapping("SELECT value", "fixture/1", "SELECT value,token", 1)
        session = self.session(mappings=[mapping]); raw = Raw()
        raw.responses[mapping.executed_sql] = [(1, "a"), (2, "b")]
        cursor = session.wrap(raw).execute(mapping.sql)
        self.assertEqual(cursor.fetchmany(0), [(1,), (2,)])

    def test_arraysize_assignment_is_forwarded(self):
        session = self.session(); cursor = session.wrap(Raw()).cursor()
        cursor.arraysize = 8
        self.assertEqual(cursor._raw.arraysize, 8)

    def test_configuration_assignment_forwarded_and_gap(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.autocommit = True
        self.assertTrue(raw.autocommit)
        self.assertIn("connection_configuration_changed", {g["code"] for g in session.gaps})

    def test_custom_factory_is_not_rewritten(self):
        mapping = c.SQLMapping("SELECT value", "fixture/1", "SELECT value,token", 1)
        session, raw = self.session(mappings=[mapping]), Raw(); conn = session.wrap(raw)
        cursor = conn.cursor(); cursor._raw.row_factory = lambda _: dict
        cursor.execute("SELECT value")
        self.assertEqual(raw.executed[-1][0], "SELECT value")

    def test_pending_cursor_close_and_result_replacement_gap(self):
        session = self.session(); conn = session.wrap(Raw()); cursor = conn.execute("SELECT 1")
        cursor.execute("SELECT 1")
        cursor.close()
        self.assertTrue({"result_replaced", "unconsumed_result"}.issubset({g["code"] for g in session.gaps}))

    def test_unknown_sql_executes_original_text_params_and_kwargs(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        params = ("not-a-parser",)
        conn.execute("SELECT business_func(%s)", params, prepare=False).fetchall()
        self.assertEqual(raw.executed[-1], ("SELECT business_func(%s)", params, {"prepare": False}))
        self.assertNotIn("mapped", next(e for e in self.events(session) if e["kind"] == "statement"))

    def test_large_result_preserved_without_observer_clone(self):
        session, raw = self.session(max_value_bytes=128), Raw()
        raw.responses["SELECT huge"] = [("x" * 2000,)]
        result = session.wrap(raw).execute("SELECT huge").fetchall()
        self.assertEqual(result, [("x" * 2000,)])
        self.assertIn("result_observation_failed", {g["code"] for g in session.gaps})

    def test_typed_timestamp_has_no_client_substitution(self):
        session = self.session()
        value = datetime.datetime(2026, 10, 21, 8, 9, 10, 123456, datetime.timezone.utc)
        self.assertEqual(session.encode(value), {"captureType": "datetime", "value": str(value)})

    def test_driver_facade_does_not_mutate_original_driver(self):
        session = self.session(); raw = Raw()
        original = lambda *a, **k: raw
        driver = types.SimpleNamespace(connect=original, marker="driver")
        facade = session.driver(driver)
        self.assertIs(driver.connect, original)
        self.assertIs(facade.connect()._raw, raw)
        self.assertEqual(facade.marker, "driver")

    def test_context_preserves_original_business_exception(self):
        session, raw = self.session(), Raw(); error = BusinessError("business")
        with self.assertRaises(BusinessError) as observed:
            with session.wrap(raw):
                raise error
        self.assertIs(observed.exception, error)
        self.assertTrue(raw.closed)

    def test_pinned_commit_hook_restores_method_and_observes_rollback_tag(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall()
        raw.info.transaction_status, raw.commit_tag = 3, b"ROLLBACK"
        original = raw._exec_command
        with mock.patch.object(c, "_pinned_connection", return_value=True):
            result = conn.commit()
        self.assertIs(result, raw.commit_result)
        self.assertEqual(raw._exec_command, original)
        self.assertNotIn("_exec_command", raw.__dict__)
        outcome = next(e for e in self.events(session) if e["kind"] == "rollback_ok")
        self.assertEqual(outcome["commitResponse"]["commandTag"], "ROLLBACK")
        self.assertTrue(session.close(source_closed=True).complete)

    def test_pinned_commit_hook_exception_restores_method_identity(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall(); error = raw.commit_error = BusinessError("commit")
        original = raw._exec_command
        with mock.patch.object(c, "_pinned_connection", return_value=True):
            with self.assertRaises(BusinessError) as observed:
                conn.commit()
        self.assertIs(observed.exception, error)
        self.assertEqual(raw._exec_command, original)
        self.assertNotIn("_exec_command", raw.__dict__)

    def test_client_constructed_sqlstate_is_not_server_abort_proof(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall()
        error = BusinessError("client fake")
        error.sqlstate, error.diag = "40001", types.SimpleNamespace(sqlstate="40001")
        raw.commit_error = error
        with self.assertRaises(BusinessError):
            conn.commit()
        self.assertNotIn("rollback_ok", [e["kind"] for e in self.events(session)])

    def test_real_driver_client_constructed_error_without_pgresult_is_not_proof(self):
        try:
            import psycopg
            from psycopg.pq import DiagnosticField
        except ImportError:
            self.skipTest("Optional psycopg is unavailable; no database used by this test")
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall()
        error = psycopg.errors.SerializationFailure("locally constructed", info={DiagnosticField.SQLSTATE: b"40001"})
        self.assertEqual(error.sqlstate, "40001")
        self.assertEqual(error.diag.sqlstate, "40001")
        self.assertIsNone(error.pgresult)
        raw.commit_error = error
        with self.assertRaises(psycopg.Error) as observed:
            conn.commit()
        self.assertIs(observed.exception, error)
        self.assertNotIn("rollback_ok", [e["kind"] for e in self.events(session)])

    def test_wrap_before_snapshot_rejected(self):
        session = c.CaptureV3Session(self.path); self.sessions.append(session)
        with self.assertRaises(JournalError):
            session.wrap(Raw())

    def test_diagnostic_export_incomplete_has_explicit_gaps(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall()
        raw.commit_error = BusinessError("lost ACK")
        with self.assertRaises(BusinessError):
            conn.commit()
        self.assertFalse(session.close(source_closed=True).complete)
        target = self.path.with_suffix(".json")
        result = session.export_diagnostic(target)
        self.assertFalse(result["complete"])
        document = json.loads(target.read_bytes())
        self.assertTrue(document["gaps"])
        self.assertIn("disconnect", [e["kind"] for e in document["events"]])
        with self.assertRaises(JournalError):
            session.export_diagnostic(target)

    def test_diagnostic_budget_failure_preserves_reason_and_source(self):
        session = self.session(); session.close()
        target = self.path.with_suffix(".json")
        with self.assertRaises(JournalError):
            session.export_diagnostic(target, max_bytes=128)
        self.assertFalse(target.exists())
        self.assertEqual(len(list(target.parent.glob(target.name + ".refused-*.json"))), 1)
        self.assertTrue(JournalReader(self.path).verify().valid)

    def test_fixed_registry_final_eof_does_not_invent_false_guard(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "experiments/business/dislock"))
        from v3_registry import registry, mappings
        manifest = registry("mtw_provenance_unit_v3")
        mapping = next(m for m in mappings(manifest) if m.mapping_id == "dislock.renew/1")
        session, raw = self.session(mappings=[mapping]), Raw()
        now = datetime.datetime(2026, 10, 21, 8, 0, tzinfo=datetime.timezone.utc)
        raw.responses[mapping.executed_sql] = [(now, "old", "new", "owner", now, now)]
        conn = session.wrap(raw); cursor = conn.execute(mapping.sql, (5.0, "x", "owner"))
        cursor._raw.rowcount = -1  # Require a separate EOF batch, rather than known client count.
        self.assertEqual(cursor.fetchone(), (now,))
        self.assertIsNone(cursor.fetchone())
        self.assertIsNone(cursor.fetchone())
        events = self.events(session)
        conditions = [e for e in events if e["kind"] == "condition"]
        self.assertEqual(len(conditions), 1)
        self.assertTrue(conditions[0]["matched"])
        self.assertEqual([e["kind"] for e in events if e["kind"] in ("read", "write")], ["write"])

    def test_fixed_zero_row_guard_does_not_invent_source(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "experiments/business/dislock"))
        from v3_registry import registry, mappings
        mapping = next(m for m in mappings(registry("mtw_provenance_unit_zero")) if m.mapping_id == "dislock.renew/1")
        session, raw = self.session(mappings=[mapping]), Raw()
        raw.responses[mapping.executed_sql] = []
        cursor = session.wrap(raw).execute(mapping.sql, (5.0, "x", "owner"))
        self.assertIsNone(cursor.fetchone())
        events = self.events(session)
        conditions = [e for e in events if e["kind"] == "condition"]
        self.assertEqual(len(conditions), 1)
        self.assertFalse(conditions[0]["matched"])
        self.assertNotIn("sourceVersion", conditions[0])
        self.assertFalse([e for e in events if e["kind"] in ("read", "write")])

    def test_postclose_activity_invalidates_fresh_readers_without_rewriting_sealed_bytes(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall(); conn.commit()
        self.assertTrue(session.close(source_closed=True).complete)
        original = {p.name: p.read_bytes() for p in self.path.iterdir() if p.is_file()}
        raw.responses["SELECT 2"] = [(2,)]
        self.assertEqual(conn.execute("SELECT 2").fetchone(), (2,))
        self.assertIs(conn.commit(), raw.commit_result)
        self.assertTrue((self.path / INVALIDATED).exists())
        for name, content in original.items():
            self.assertEqual((self.path / name).read_bytes(), content, name)
        status = JournalReader(self.path).verify()
        self.assertTrue(status.valid)
        self.assertFalse(status.complete)
        self.assertFalse(session.close(source_closed=True).complete)
        with self.assertRaises(JournalError):
            session.export(self.path.with_suffix(".json"))
        with self.assertRaises(JournalError):
            session.export_diagnostic(self.path.with_suffix(".diagnostic.json"))
        with self.assertRaises(JournalError):
            JournalReader(self.path).export(self.path.with_suffix(".fresh.json"), clock_domain="c")
        with self.assertRaises(JournalError):
            JournalReader(self.path).archive(self.path.with_suffix(".zip"))
        with self.assertRaises(JournalError):
            SegmentedJournal.reopen(self.path, exclusive_continuation=True)

    def test_postclose_driver_facade_connect_is_business_compatible_but_invalidated(self):
        session = self.session(); session.close(source_closed=True)
        raw = Raw()
        facade = session.driver(types.SimpleNamespace(connect=lambda *a, **k: raw))
        result = facade.connect()
        self.assertIs(result, raw)
        self.assertEqual(result.cursor().execute("SELECT 1").fetchone(), (1,))
        self.assertTrue((self.path / INVALIDATED).exists())
        self.assertFalse(JournalReader(self.path).verify().complete)

    def test_postclose_marker_io_failure_still_permanently_blocks_session_export(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        conn.execute("SELECT 1").fetchall(); conn.commit(); session.close(source_closed=True)
        original_open = Path.open
        def refuse_marker(path, *args, **kwargs):
            if path.name == INVALIDATED:
                raise PermissionError("injected marker storage failure")
            return original_open(path, *args, **kwargs)
        raw.responses["SELECT 2"] = [(2,)]
        with mock.patch.object(Path, "open", refuse_marker):
            self.assertEqual(conn.execute("SELECT 2").fetchone(), (2,))
            self.assertIs(conn.commit(), raw.commit_result)
        self.assertFalse((self.path / INVALIDATED).exists())
        self.assertTrue(session._invalidated)
        self.assertFalse(session._invalidation_persisted)
        self.assertIn("invalidation_marker_io_failed", {g["code"] for g in session.gaps})
        with self.assertRaises(JournalError):
            session.export(self.path.with_suffix(".json"))
        self.assertFalse(session.close(source_closed=True).complete)
        # The unchanged disk prefix cannot communicate a completely failed
        # invalidation write to a fresh process. No such claim is made here.

    def test_postclose_fetch_commit_rollback_are_observed(self):
        for operation in ("fetch", "commit", "rollback"):
            self.path = RUN / (self._testMethodName + "_" + operation)
            session, raw = self.session(), Raw(); conn = session.wrap(raw)
            cursor = conn.execute("SELECT 1"); cursor.fetchall(); conn.commit()
            session.close(source_closed=True)
            if operation == "fetch":
                self.assertIsNone(cursor.fetchone())
            elif operation == "commit":
                self.assertIs(conn.commit(), raw.commit_result)
            else:
                self.assertIsNone(conn.rollback())
            self.assertTrue(session._invalidated)
            self.assertFalse(JournalReader(self.path).verify().complete)

    def test_pure_cleanup_and_idempotent_close_do_not_invalidate(self):
        session, raw = self.session(), Raw(); conn = session.wrap(raw)
        cursor = conn.execute("SELECT 1"); cursor.fetchall(); conn.commit()
        self.assertTrue(session.close(source_closed=True).complete)
        cursor.close(); conn.close()
        self.assertTrue(session.close(source_closed=True).complete)
        self.assertFalse(session._invalidated)
        self.assertFalse((self.path / INVALIDATED).exists())


if __name__ == "__main__":
    program = unittest.main(exit=False)
    result = program.result
    (RUN / "collector-unit-receipt.json").write_text(json.dumps({"schema": 1,
        "suite": "v3-protocol-fake-driver", "testsRun": result.testsRun,
        "passed": result.wasSuccessful(), "actualDatabaseExecution": False,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "sourceSha256": hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest()}, indent=2) + "\n", encoding="utf-8")
    print("Collector test artifacts: " + str(RUN))
    sys.exit(0 if result.wasSuccessful() else 1)
