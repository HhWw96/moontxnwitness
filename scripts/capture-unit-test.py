"""Driver-interface unit tests; these are not real PostgreSQL acceptance."""
import asyncio
import base64
import gc
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations" / "python"))
from moontxnwitness_capture import CaptureSession, CaptureSetupError, PointRead, PointWrite, Table, load_jsonl

READ = "SELECT value,version FROM registers WHERE id=%s"
WRITE = "UPDATE registers SET value=%s,version=%s WHERE id=%s"
TABLE = Table("public", "registers", "id", "version")


class BusinessError(Exception):
    sqlstate = "40001"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.position = 0
        self.rowcount = -1
        self.arraysize = 1
        self.closed = False
        self.fetch_error = None

    def execute(self, query, params=None, **kwargs):
        conn = self.connection
        conn.calls.append((query, params, kwargs))
        self.rows, self.position, self.rowcount = [], 0, -1
        if query.startswith("BEGIN") or query == "START TRANSACTION":
            conn.begin()
        elif query in ("COMMIT", "COMMIT;"):
            conn.commit()
        elif query == "ROLLBACK":
            conn.rollback()
        elif query.startswith("LOCK TABLE"):
            pass
        elif "FROM pg_catalog.pg_class" in query:
            self.rows = [conn.catalog]
        elif query.startswith('SELECT "id","version" FROM '):
            self.rows = [(key, value[1]) for key, value in conn.store.items()]
        else:
            if conn.info.transaction_status == 0 and not conn.autocommit:
                conn.begin()
            if query == "FAIL":
                conn.info.transaction_status = 3
                raise conn.business_error
            data = conn.working if conn.working is not None else conn.store
            if query == READ:
                key = params[0] if not isinstance(params, dict) else params["key"]
                self.rows = [data[key]] if key in data else []
            elif query == WRITE:
                if params[2] in data:
                    data[params[2]] = (params[0], params[1])
                    self.rowcount = 1
                else:
                    self.rowcount = 0
            elif query.startswith("SAVEPOINT"):
                pass
        if self.rowcount == -1:
            self.rowcount = len(self.rows) if self.rows or query.startswith("SELECT") else -1
        return self

    def fetchone(self):
        if self.fetch_error is not None:
            raise self.fetch_error
        if self.position >= len(self.rows):
            return None
        row = self.rows[self.position]
        self.position += 1
        return row

    def fetchmany(self, size=None):
        result = []
        for _ in range(self.arraysize if size is None else size):
            row = self.fetchone()
            if row is None:
                break
            result.append(row)
        return result

    def fetchall(self):
        return self.fetchmany(len(self.rows) - self.position)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def executemany(self, query, params):
        for item in params:
            self.execute(query, item)


class FakeConnection:
    def __init__(self, *, store=None, autocommit=False):
        self.store = {1: (10, "v0")} if store is None else store
        self.autocommit = autocommit
        self.info = SimpleNamespace(transaction_status=0)
        self.calls = []
        self.working = None
        self.closed = False
        self.catalog = ("r", False, False, True)
        self.business_error = BusinessError("preserve this exact business exception")
        self.commit_error = None
        self.commit_error_status = None
        self.rollback_error = None
        self.isolation_level = None

    def begin(self):
        if self.working is None:
            self.working = dict(self.store)
        self.info.transaction_status = 2

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def execute(self, query, params=None, **kwargs):
        return self.cursor().execute(query, params, **kwargs)

    def commit(self):
        if self.commit_error:
            if self.commit_error_status is not None:
                self.info.transaction_status = self.commit_error_status
            raise self.commit_error
        if self.working is not None and self.info.transaction_status != 3:
            self.store.clear()
            self.store.update(self.working)
        self.working = None
        self.info.transaction_status = 0

    def rollback(self):
        if self.rollback_error:
            raise self.rollback_error
        self.working = None
        self.info.transaction_status = 0

    def close(self):
        self.closed = True
        self.info.transaction_status = 4

    def __enter__(self):
        return self

    def transaction(self):
        return "raw transaction context"


class AsyncFakeCursor:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def __setattr__(self, name, value):
        if name == "base":
            object.__setattr__(self, name, value)
        else:
            setattr(self.base, name, value)

    async def execute(self, query, params=None, **kwargs):
        self.base.execute(query, params, **kwargs)
        return self

    async def fetchone(self):
        return self.base.fetchone()

    async def fetchmany(self, size=None):
        return self.base.fetchmany(size)

    async def fetchall(self):
        return self.base.fetchall()

    async def close(self):
        self.base.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.base.close()


class AsyncFakeConnection:
    def __init__(self, base=None):
        self.base = base or FakeConnection()

    def __getattr__(self, name):
        return getattr(self.base, name)

    def cursor(self, *args, **kwargs):
        return AsyncFakeCursor(self.base.cursor(*args, **kwargs))

    async def execute(self, query, params=None, **kwargs):
        cursor = self.cursor()
        return await cursor.execute(query, params, **kwargs)

    async def commit(self):
        self.base.commit()

    async def rollback(self):
        self.base.rollback()

    async def close(self):
        self.base.close()

    async def __aenter__(self):
        return self


def session(**kwargs):
    capture = CaptureSession([PointRead(READ, TABLE), PointWrite(WRITE, TABLE)],
                             exclusive_writers=True, **kwargs)
    setup = FakeConnection(autocommit=True)
    capture.initialize(setup)
    return capture, setup


def kinds(capture, kind):
    return [item for item in capture.document()["events"] if item["kind"] == kind]


def gap_codes(capture):
    return {item["code"] for item in capture.document()["gaps"]}


class CaptureUnitTests(unittest.TestCase):
    def test_memoryview_element_count_cannot_bypass_binary_byte_budget(self):
        for payload in (memoryview(bytearray(200_000)).cast("I"),
                        memoryview(bytearray(262_144)).cast("B", shape=(512, 512))):
            capture, _ = session()
            raw = FakeConnection()
            conn = capture.wrap(raw)
            with patch("moontxnwitness_capture.capture.base64.b64encode") as encode:
                conn.execute(WRITE, (payload, "v1", 1))
                conn.commit()
                encode.assert_not_called()
            self.assertIs(raw.store[1][0], payload)
            self.assertIn("raw_value_budget", gap_codes(capture))

    def test_noncontiguous_memoryview_is_gap_before_binary_copy(self):
        payload = memoryview(bytearray(range(32)))[::2]
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        with patch("moontxnwitness_capture.capture.base64.b64encode") as encode:
            conn.execute(WRITE, (payload, "v1", 1))
            conn.commit()
            encode.assert_not_called()
        self.assertIs(raw.store[1][0], payload)
        self.assertIn("raw_value_unsupported", gap_codes(capture))

    def test_memoryview_binary_boundary_charges_base64_expansion(self):
        payload = memoryview(bytearray(65_536)).cast("I")
        capture, _ = session()
        encoded = capture._safe_value(payload)
        self.assertEqual(encoded, {"captureType": "bytes", "base64": base64.b64encode(payload).decode("ascii")})
        self.assertFalse(capture.document()["gaps"])
        capture, _ = session(max_value_bytes=65_536)
        with patch("moontxnwitness_capture.capture.base64.b64encode") as encode:
            self.assertEqual(capture._safe_value(payload), {"captureType": "budget-exhausted"})
            encode.assert_not_called()
        self.assertIn("raw_value_budget", gap_codes(capture))

    def test_aggregate_nodes_stop_expanding_shared_short_list_tree(self):
        class CountedList(list):
            visited = 0
            def __iter__(self):
                for value in super().__iter__():
                    type(self).visited += 1
                    yield value
        payload = CountedList([1])
        for _ in range(7):
            payload = CountedList([payload] * 4)
        capture, _ = session(max_value_nodes=64)
        raw = FakeConnection()
        conn = capture.wrap(raw)
        result = conn.execute(WRITE, (payload, "v1", 1))
        conn.commit()
        self.assertEqual(result.rowcount, 1)
        self.assertIs(raw.store[1][0], payload)
        self.assertLess(CountedList.visited, 80)
        self.assertIn("raw_value_budget", gap_codes(capture))

    def test_aggregate_string_bytes_do_not_change_original_business_value(self):
        payload = ["x" * 64, "y" * 64, "z" * 64]
        capture, _ = session(max_value_bytes=128)
        raw = FakeConnection()
        conn = capture.wrap(raw)
        conn.execute(WRITE, (payload, "v1", 1))
        conn.commit()
        self.assertIs(raw.store[1][0], payload)
        self.assertIn("raw_value_budget", gap_codes(capture))
        request = next(e for e in kinds(capture, "sql") if e["phase"] == "execute-request")
        self.assertEqual(request["parameters"], {"captureType": "budget-exhausted"})

    def test_raw_node_boundary_is_shared_across_all_containers(self):
        value = [list(range(31)), list(range(30))]  # 1 + 2 + 61 = 64 nodes
        capture, _ = session(max_value_nodes=64)
        self.assertEqual(capture._safe_value(value), value)
        self.assertFalse(capture.document()["gaps"])
        value[1].append(30)
        self.assertEqual(capture._safe_value(value), {"captureType": "budget-exhausted"})
        self.assertIn("raw_value_budget", gap_codes(capture))

    def test_raw_byte_boundary_counts_utf8_and_json_escapes_before_encoding(self):
        value = ["é\n", '"', "中", "😀"]
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        capture, _ = session(max_value_bytes=size)
        self.assertEqual(capture._safe_value(value), value)
        self.assertFalse(capture.document()["gaps"])
        too_small, _ = session(max_value_bytes=size - 1)
        self.assertEqual(too_small._safe_value(value), {"captureType": "budget-exhausted"})
        self.assertIn("raw_value_budget", gap_codes(too_small))

    def test_returned_tree_budget_preserves_row_identity_and_records_gap(self):
        payload = [["a" * 50] * 8] * 8
        capture, _ = session(max_value_bytes=128)
        raw = FakeConnection(store={1: (payload, "v0")})
        conn = capture.wrap(raw)
        row = conn.execute(READ, (1,)).fetchone()
        self.assertIs(row, raw.working[1])
        self.assertIs(row[0], payload)
        conn.commit()
        self.assertIn("raw_value_budget", gap_codes(capture))
        fetch = next(e for e in kinds(capture, "sql") if e["phase"] == "fetch")
        self.assertNotIn("rows", fetch)

    def test_session_byte_budget_stops_evidence_without_stopping_business(self):
        capture, _ = session(max_session_bytes=2048)
        raw = FakeConnection()
        conn = capture.wrap(raw)
        for index in range(20):
            conn.execute(WRITE, (index, "version-" + str(index), 1))
            conn.commit()
        self.assertEqual(raw.store[1], (19, "version-19"))
        self.assertIn("session_budget_exhausted", gap_codes(capture))
        self.assertLessEqual(capture._retained_bytes, 2048 - 512)
        self.assertLessEqual(len(json.dumps(capture.document(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")), 2048)
        events = len(capture.document()["events"])
        with self.assertRaises(BusinessError) as caught:
            conn.execute("FAIL")
        self.assertIs(caught.exception, raw.business_error)
        self.assertEqual(len(capture.document()["events"]), events)

    def test_session_node_budget_is_independent_of_event_count_and_bytes(self):
        capture, _ = session(max_session_nodes=128)
        raw = FakeConnection()
        conn = capture.wrap(raw)
        for index in range(12):
            conn.execute(WRITE, (index, "v" + str(index + 1), 1))
            conn.commit()
        self.assertEqual(raw.store[1][0], 11)
        self.assertIn("session_budget_exhausted", gap_codes(capture))
        self.assertLessEqual(capture._retained_nodes, 128)

    def test_event_budget_rejects_large_payload_before_retaining_it(self):
        capture, _ = session(max_event_bytes=512)
        raw = FakeConnection()
        conn = capture.wrap(raw)
        version = "v" * 1000
        conn.execute(WRITE, (9, version, 1))
        conn.commit()
        self.assertEqual(raw.store[1], (9, version))
        self.assertIn("event_value_budget", gap_codes(capture))
        self.assertNotIn(version, json.dumps(capture.document()))

    def test_gap_records_have_a_hard_count_and_payload_bound(self):
        capture, _ = session(max_gaps=2)
        for index in range(100):
            capture.gap("gap-" + str(index), "m" * 1000)
        gaps = capture.document()["gaps"]
        self.assertEqual(len(gaps), 3)
        self.assertEqual(gaps[-1]["code"], "gap_budget_exhausted")
        self.assertTrue(all(len(gap["message"]) <= 512 for gap in gaps))

    def test_sql_budget_passes_the_original_query_unchanged(self):
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        query = "SELECT " + " " * 70_000
        conn.execute(query)
        conn.rollback()
        self.assertIs(raw.calls[0][0], query)
        self.assertIn("sql_value_budget", gap_codes(capture))
        self.assertNotIn(query, json.dumps(capture.document()))

    def test_snapshot_budget_rejects_before_creating_a_large_initial_dictionary(self):
        capture = CaptureSession([PointRead(READ, TABLE)], max_event_bytes=512)
        setup = FakeConnection(autocommit=True, store={1: (7, "v" * 1000)})
        with self.assertRaises(CaptureSetupError):
            capture.initialize(setup)
        self.assertIn("snapshot_budget_exhausted", gap_codes(capture))
        self.assertFalse(kinds(capture, "snapshot"))

    def test_generated_templates_have_known_shape_and_quoted_identifiers(self):
        table = Table("public", 'acc"ounts', "id", "version")
        read = PointRead.for_table(table, value_columns=("balance",))
        write = PointWrite.for_table(table, value_columns=("balance",))
        self.assertEqual(read.sql, 'SELECT "balance","version" FROM "public"."acc""ounts" WHERE "id"=%s')
        self.assertEqual(write.sql, 'UPDATE "public"."acc""ounts" SET "balance"=%s,"version"=%s WHERE "id"=%s')
        self.assertEqual((read.key_parameter, read.version_result), (0, 1))
        self.assertEqual((write.key_parameter, write.version_parameter), (2, 1))
        with self.assertRaises(ValueError):
            PointRead.for_table(table, value_columns=("id",))

    def test_discarded_unconsumed_cursor_is_gap_and_wrapping_is_idempotent(self):
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        self.assertIs(capture.wrap(raw), conn)
        cursor = conn.execute(READ, (1,))
        del cursor
        gc.collect()
        self.assertIn("unconsumed_result", gap_codes(capture))

    def test_raw_parameters_and_rows_are_actual_driver_observations(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        conn.execute(READ, (1,)).fetchone()
        conn.commit()
        sql = kinds(capture, "sql")
        self.assertEqual(next(e for e in sql if e["phase"] == "execute-request")["parameters"], [1])
        self.assertEqual(next(e for e in sql if e["phase"] == "fetch")["rows"], [[10, "v0"]])

    def test_raw_large_integers_preserve_precision_for_js_consumers(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        value = 9_223_372_036_854_775_807
        conn.execute(WRITE, (value, "v1", 1))
        self.assertEqual(conn.execute(READ, (1,)).fetchone(), (value, "v1"))
        conn.commit()
        sql = kinds(capture, "sql")
        parameter_event = next(e for e in sql if e["phase"] == "execute-request")
        result_event = next(e for e in sql if e["phase"] == "fetch")
        expected = {"captureType": "int", "value": str(value)}
        self.assertEqual(parameter_event["parameters"][0], expected)
        self.assertEqual(result_event["rows"][0][0], expected)
        self.assertFalse(capture.document()["gaps"])

    def test_oversized_raw_result_omits_rows_with_gap_preserving_business_result(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        cursor = conn.execute("SELECT unsupported_many_rows")
        rows = [(i,) for i in range(10_001)]
        cursor._raw.rows = rows
        cursor._raw.rowcount = len(rows)
        self.assertEqual(cursor.fetchall(), rows)
        conn.rollback()
        result_event = next(e for e in kinds(capture, "sql") if e["phase"] == "fetch")
        self.assertNotIn("rows", result_event)
        self.assertIn("raw_value_unsupported", gap_codes(capture))

    def test_sync_read_write_commit_preserves_results_and_parameters(self):
        capture, setup = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        self.assertIs(conn.execute(READ, (1,)).connection, conn)
        # Using a new statement with a pending read is deliberately incomplete.
        conn.rollback()
        capture, setup = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        result = conn.execute(READ, (1,), prepare=False)
        self.assertEqual(result.fetchone(), (10, "v0"))
        self.assertEqual(result.rowcount, 1)
        self.assertEqual(conn.execute(WRITE, (9, "v1", 1)).rowcount, 1)
        conn.commit()
        capture.close()
        self.assertEqual(raw.store[1], (9, "v1"))
        self.assertEqual(raw.calls[0], (READ, (1,), {"prepare": False}))
        self.assertEqual([e["op"]["type"] for e in kinds(capture, "op")], ["read", "write"])
        self.assertEqual(kinds(capture, "end")[0]["status"], "committed")
        self.assertFalse(capture.document()["gaps"])

    def test_locked_snapshot_precedes_transactions_and_preserves_initial(self):
        capture, setup = session()
        self.assertTrue(setup.calls[1][0].startswith('LOCK TABLE "public"."registers" IN SHARE MODE'))
        self.assertEqual(capture.document()["events"][0]["initial"], {TABLE.key(1): "v0"})
        conn = capture.wrap(FakeConnection())
        conn.execute("BEGIN")
        conn.execute(WRITE, (10, "v1", 1))
        conn.rollback()
        self.assertEqual(kinds(capture, "snapshot")[0]["initial"][TABLE.key(1)], "v0")
        self.assertEqual(kinds(capture, "end")[0]["status"], "aborted")

    def test_snapshot_requires_idle_dedicated_setup_and_cannot_repeat(self):
        capture = CaptureSession([PointRead(READ, TABLE)])
        with self.assertRaises(CaptureSetupError):
            capture.initialize(FakeConnection())
        capture.initialize(FakeConnection(autocommit=True))
        with self.assertRaises(CaptureSetupError):
            capture.initialize(FakeConnection(autocommit=True))

    def test_snapshot_rejects_trigger_or_rls_and_preserves_failure(self):
        for catalog in (("r", True, False, True), ("r", False, True, True), ("p", False, False, True), ("r", False, False, False)):
            capture = CaptureSession([PointRead(READ, TABLE)])
            setup = FakeConnection(autocommit=True)
            setup.catalog = catalog
            with self.assertRaises(CaptureSetupError):
                capture.initialize(setup)
            self.assertIn("initialization_failed", gap_codes(capture))
            self.assertFalse(kinds(capture, "snapshot"))

    def test_snapshot_rejects_non_string_version(self):
        capture = CaptureSession([PointRead(READ, TABLE)])
        with self.assertRaises(CaptureSetupError):
            capture.initialize(FakeConnection(autocommit=True, store={1: (10, 42)}))
        self.assertIn("initialization_failed", gap_codes(capture))

    def test_typed_keys_cannot_collide(self):
        self.assertEqual(len({TABLE.key(1), TABLE.key(True), TABLE.key("1")}), 3)
        self.assertNotEqual(TABLE.key('x/y"'), TABLE.key('x/y'))

    def test_multiple_writes_and_own_read_preserve_order(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        conn.execute(WRITE, (10, "v1", 1))
        conn.execute(WRITE, (10, "v2", 1))
        self.assertEqual(conn.execute(READ, (1,)).fetchall(), [(10, "v2")])
        conn.commit()
        self.assertEqual([e["op"]["version"] for e in kinds(capture, "op")], ["v1", "v2", "v2"])
        self.assertFalse(capture.document()["gaps"])

    def test_business_exception_identity_not_swallowed(self):
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        with self.assertRaises(BusinessError) as caught:
            conn.execute("FAIL")
        self.assertIs(caught.exception, raw.business_error)
        conn.rollback()
        self.assertEqual(kinds(capture, "end")[0]["status"], "aborted")
        self.assertIn("unsupported_sql", gap_codes(capture))

    def test_failed_commit_is_unknown_and_exception_identity_preserved(self):
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        conn.execute(WRITE, (9, "v1", 1))
        raw.commit_error = OSError("connection lost")
        with self.assertRaises(OSError) as caught:
            conn.commit()
        self.assertIs(caught.exception, raw.commit_error)
        self.assertEqual(kinds(capture, "end")[0]["status"], "unknown")
        self.assertIn("commit_unknown", gap_codes(capture))

    def test_commit_server_rollback_requires_diagnostics_and_idle_state(self):
        for state, after, diagnostics, expected in (
            ("40001", 0, True, "aborted"), ("40P01", 0, True, "aborted"),
            ("40001", 4, True, "unknown"), ("40001", 3, True, "unknown"),
            ("40001", 0, False, "unknown"), ("40003", 0, True, "unknown"),
        ):
            with self.subTest(state=state, after=after, diagnostics=diagnostics):
                capture, _ = session()
                raw = FakeConnection()
                conn = capture.wrap(raw)
                conn.execute(WRITE, (9, "v1", 1))
                failure = BusinessError("server rollback or local failure")
                failure.sqlstate = state
                if diagnostics:
                    failure.diag = SimpleNamespace(sqlstate=state)
                raw.commit_error = failure
                raw.commit_error_status = after
                with self.assertRaises(BusinessError) as caught:
                    conn.commit()
                self.assertIs(caught.exception, failure)
                self.assertEqual(kinds(capture, "end")[-1]["status"], expected)
                self.assertEqual("commit_unknown" in gap_codes(capture), expected == "unknown")

    def test_explicit_commit_sql_server_rollback_is_aborted(self):
        capture, _ = session()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        conn.execute(WRITE, (9, "v1", 1))
        failure = BusinessError("server rollback")
        failure.diag = SimpleNamespace(sqlstate="40001")
        raw.commit_error, raw.commit_error_status = failure, 0
        with self.assertRaises(BusinessError):
            conn.execute("COMMIT")
        self.assertEqual(kinds(capture, "end")[-1]["status"], "aborted")
        self.assertFalse(capture.document()["gaps"])

    def test_context_commit_error_matches_psycopg_336_close_order(self):
        capture, _ = session()
        raw = FakeConnection()
        failure = OSError("commit lost")
        with self.assertRaises(OSError) as caught:
            with capture.wrap(raw) as conn:
                conn.execute(WRITE, (9, "v1", 1))
                raw.commit_error = failure
        self.assertIs(caught.exception, failure)
        self.assertFalse(raw.closed)
        self.assertEqual(kinds(capture, "end")[-1]["status"], "unknown")

    def test_commit_after_server_error_is_aborted(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        try:
            conn.execute("FAIL")
        except BusinessError:
            pass
        conn.commit()
        self.assertEqual(kinds(capture, "end")[0]["status"], "aborted")

    def test_pending_read_before_next_sql_is_incomplete(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        pending = conn.execute(READ, (1,))
        conn.execute(WRITE, (9, "v1", 1))
        self.assertEqual(pending.fetchone(), (10, "v0"))
        conn.commit()
        self.assertIn("unconsumed_result", gap_codes(capture))
        self.assertFalse([e for e in kinds(capture, "op") if e["op"]["type"] == "read"])

    def test_pending_read_on_close_or_commit_is_incomplete(self):
        for action in ("close", "commit"):
            capture, _ = session()
            conn = capture.wrap(FakeConnection())
            cursor = conn.execute(READ, (1,))
            cursor.close() if action == "close" else conn.commit()
            self.assertIn("unconsumed_result", gap_codes(capture))

    def test_fetchmany_arraysize_and_iteration_preserved(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        cursor = conn.execute(READ, (1,))
        cursor.arraysize = 4
        self.assertEqual(cursor._raw.arraysize, 4)
        self.assertEqual(cursor.fetchmany(), [(10, "v0")])
        self.assertEqual(list(conn.execute(READ, (1,))), [(10, "v0")])
        conn.rollback()
        self.assertFalse(capture.document()["gaps"])

    def test_fetch_failure_preserves_exception_and_marks_gap(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        cursor = conn.execute(READ, (1,))
        failure = ValueError("row factory failed")
        cursor._raw.fetch_error = failure
        with self.assertRaises(ValueError) as caught:
            cursor.fetchone()
        self.assertIs(caught.exception, failure)
        self.assertIn("fetch_failed", gap_codes(capture))

    def test_zero_row_result_does_not_fabricate_initial_or_tombstone(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        self.assertIsNone(conn.execute(READ, (99,)).fetchone())
        conn.commit()
        self.assertIn("point_cardinality", gap_codes(capture))
        self.assertFalse(kinds(capture, "op"))

    def test_savepoint_and_unmapped_sql_execute_but_gap(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        conn.execute("BEGIN")
        conn.execute("SAVEPOINT example")
        conn.execute(READ, (1,)).fetchone()
        conn.rollback()
        self.assertIn("unsupported_sql", gap_codes(capture))

    def test_autocommit_does_not_claim_supported_complete_capture(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection(autocommit=True))
        conn.execute(WRITE, (9, "v1", 1))
        self.assertIn("autocommit_unsupported", gap_codes(capture))
        self.assertEqual(kinds(capture, "end")[0]["status"], "unknown")

    def test_explicit_transaction_on_autocommit_connection_is_supported(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection(autocommit=True))
        conn.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
        conn.execute(WRITE, (9, "v1", 1))
        conn.execute("COMMIT")
        self.assertFalse(capture.document()["gaps"])
        self.assertEqual(kinds(capture, "end")[0]["status"], "committed")

    def test_connection_context_preserves_business_exception_after_rollback_error(self):
        capture, _ = session()
        raw = FakeConnection()
        raw.rollback_error = OSError("rollback lost")
        failure = LookupError("business failure")
        with self.assertRaises(LookupError) as caught:
            with capture.wrap(raw) as conn:
                conn.execute(WRITE, (9, "v1", 1))
                raise failure
        self.assertIs(caught.exception, failure)
        self.assertTrue(raw.closed)
        self.assertIn("rollback_unknown", gap_codes(capture))

    def test_context_commits_and_closes_without_extra_transactions(self):
        capture, _ = session()
        raw = FakeConnection()
        with capture.wrap(raw) as conn:
            conn.execute(WRITE, (9, "v1", 1))
        self.assertTrue(raw.closed)
        self.assertEqual(raw.store[1], (9, "v1"))
        self.assertEqual(len(kinds(capture, "begin")), 1)
        self.assertFalse(capture.document()["gaps"])

    def test_unknown_connection_method_and_raw_access_record_gap(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        self.assertEqual(conn.transaction(), "raw transaction context")
        self.assertIn("unsupported_connection_method", gap_codes(capture))

    def test_scope_not_inferred_and_inflight_transaction_is_gap(self):
        capture = CaptureSession([PointRead(READ, TABLE)])
        capture.initialize(FakeConnection(autocommit=True))
        raw = FakeConnection()
        raw.begin()
        capture.wrap(raw)
        self.assertFalse(capture.document()["scope"]["exclusiveWriters"])
        self.assertIn("inflight_transaction", gap_codes(capture))

    def test_raw_log_roundtrip_and_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.jsonl"
            capture, _ = session(jsonl_path=path)
            conn = capture.wrap(FakeConnection())
            conn.execute(READ, (1,)).fetchone()
            conn.commit()
            capture.close()
            self.assertEqual(load_jsonl(path), capture.document())
            lines = path.read_bytes().splitlines(keepends=True)
            path.write_bytes(b"".join(lines[:-1]))
            self.assertIn("log_unclosed", {g["code"] for g in load_jsonl(path)["gaps"]})

    def test_raw_log_tampering_and_content_after_footer_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.jsonl"
            capture, _ = session(jsonl_path=path)
            capture.close()
            original = path.read_bytes()
            path.write_bytes(original.replace(b'"v0"', b'"tampered"'))
            self.assertIn("log_corrupt", {g["code"] for g in load_jsonl(path)["gaps"]})
            path.write_bytes(original + b'{}\n')
            self.assertIn("log_corrupt", {g["code"] for g in load_jsonl(path)["gaps"]})

    def test_raw_log_non_object_records_preserve_valid_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.jsonl"
            capture, _ = session(jsonl_path=path)
            capture.close()
            prefix = b"".join(path.read_bytes().splitlines(keepends=True)[:2])
            for invalid in (b"null\n", b"[]\n", b"42\n", b'"text"\n',
                            b'{"record":"event","event":null}\n', b'{"record":"gap","gap":[]}\n'):
                with self.subTest(invalid=invalid):
                    path.write_bytes(prefix + invalid)
                    result = load_jsonl(path)
                    self.assertEqual(len(result["events"]), 1)
                    self.assertIn("log_corrupt", {g["code"] for g in result["gaps"]})

    def test_raw_log_size_line_and_event_limits_preserve_valid_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.jsonl"
            capture, _ = session(jsonl_path=path)
            conn = capture.wrap(FakeConnection())
            conn.execute(READ, (1,)).fetchone()
            conn.commit()
            capture.close()
            original = path.read_bytes()
            lines = original.splitlines(keepends=True)
            for limits, count in (({"max_bytes": len(lines[0]) + len(lines[1])}, 1),
                                  ({"max_events": 1}, 1)):
                result = load_jsonl(path, **limits)
                self.assertEqual(len(result["events"]), count)
                self.assertIn("log_budget_exhausted", {g["code"] for g in result["gaps"]})
            path.write_bytes(b"".join(lines[:2]) + b" " * 1024 + b"\n")
            result = load_jsonl(path, max_line_bytes=max(len(lines[0]), len(lines[1]), 512))
            self.assertEqual(len(result["events"]), 1)
            self.assertIn("log_budget_exhausted", {g["code"] for g in result["gaps"]})

    def test_raw_log_invalid_header_and_deep_json_are_corrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.jsonl"
            path.write_bytes(b'{"record":"header","traceSchema":1,"clockDomain":null,"scope":null}\n')
            self.assertIn("log_corrupt", {g["code"] for g in load_jsonl(path)["gaps"]})
            path.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000 + b"\n")
            self.assertIn("log_corrupt", {g["code"] for g in load_jsonl(path)["gaps"]})

    def test_log_write_failure_never_masks_business_error(self):
        class BrokenStream:
            def write(self, line):
                raise OSError("disk full")
            def close(self):
                pass
        capture, _ = session()
        capture._stream = BrokenStream()
        raw = FakeConnection()
        conn = capture.wrap(raw)
        with self.assertRaises(BusinessError) as caught:
            conn.execute("FAIL")
        self.assertIs(caught.exception, raw.business_error)
        self.assertIn("log_write_failed", gap_codes(capture))

    def test_bounded_events_and_outstanding_transaction_are_not_complete(self):
        capture, _ = session(max_events=3)
        conn = capture.wrap(FakeConnection())
        conn.execute(WRITE, (9, "v1", 1))
        capture.close()
        self.assertIn("event_budget_exhausted", gap_codes(capture))
        self.assertIn("transaction_outstanding", gap_codes(capture))

    def test_seq_and_time_monotonic(self):
        capture, _ = session()
        conn = capture.wrap(FakeConnection())
        for i in range(5):
            conn.execute(WRITE, (10, "v" + str(i + 1), 1))
            conn.commit()
        events = capture.document()["events"]
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))
        self.assertEqual([e["time"] for e in events], sorted(e["time"] for e in events))

    def test_capture_close_leaves_business_connection_alone(self):
        capture, _ = session()
        raw = FakeConnection()
        capture.wrap(raw)
        capture.close()
        self.assertFalse(raw.closed)
        self.assertEqual(raw.info.transaction_status, 0)


class AsyncCaptureUnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.capture = CaptureSession([PointRead(READ, TABLE), PointWrite(WRITE, TABLE)], exclusive_writers=True)
        setup = AsyncFakeConnection(FakeConnection(autocommit=True))
        await self.capture.ainitialize(setup)
        self.raw = AsyncFakeConnection()
        self.conn = self.capture.awrap(self.raw)

    async def test_async_read_write_commit(self):
        cursor = await self.conn.execute(READ, (1,))
        self.assertEqual(await cursor.fetchone(), (10, "v0"))
        await self.conn.execute(WRITE, (9, "v1", 1))
        await self.conn.commit()
        self.assertEqual(self.raw.store[1], (9, "v1"))
        self.assertFalse(self.capture.document()["gaps"])

    async def test_async_fetchmany_all_iteration_and_cursor_context(self):
        async with self.conn.cursor() as cursor:
            await cursor.execute(READ, (1,))
            self.assertEqual(await cursor.fetchmany(1), [(10, "v0")])
        cursor = await self.conn.execute(READ, (1,))
        self.assertEqual(await cursor.fetchall(), [(10, "v0")])
        cursor = await self.conn.execute(READ, (1,))
        self.assertEqual([row async for row in cursor], [(10, "v0")])
        await self.conn.rollback()
        self.assertFalse(self.capture.document()["gaps"])

    async def test_async_context_preserves_exception(self):
        failure = LookupError("business failure")
        with self.assertRaises(LookupError) as caught:
            async with self.conn as connection:
                await connection.execute(WRITE, (9, "v1", 1))
                raise failure
        self.assertIs(caught.exception, failure)
        self.assertEqual(kinds(self.capture, "end")[0]["status"], "aborted")

    async def test_async_unknown_commit(self):
        await self.conn.execute(WRITE, (9, "v1", 1))
        self.raw.base.commit_error = OSError("connection lost")
        with self.assertRaises(OSError):
            await self.conn.commit()
        self.assertEqual(kinds(self.capture, "end")[0]["status"], "unknown")

    async def test_async_confirmed_server_rollback(self):
        await self.conn.execute(WRITE, (9, "v1", 1))
        failure = BusinessError("server rollback")
        failure.diag = SimpleNamespace(sqlstate="40001")
        self.raw.base.commit_error, self.raw.base.commit_error_status = failure, 0
        with self.assertRaises(BusinessError) as caught:
            await self.conn.commit()
        self.assertIs(caught.exception, failure)
        self.assertEqual(kinds(self.capture, "end")[-1]["status"], "aborted")
        self.assertFalse(self.capture.document()["gaps"])

    async def test_async_context_commit_error_matches_driver_close_order(self):
        failure = OSError("commit lost")
        with self.assertRaises(OSError) as caught:
            async with self.conn:
                await self.conn.execute(WRITE, (9, "v1", 1))
                self.raw.base.commit_error = failure
        self.assertIs(caught.exception, failure)
        self.assertFalse(self.raw.closed)

    async def test_async_cancellation_is_not_swallowed(self):
        await self.conn.execute(WRITE, (9, "v1", 1))
        failure = asyncio.CancelledError()
        self.raw.base.commit_error = failure
        with self.assertRaises(asyncio.CancelledError):
            await self.conn.commit()
        self.assertEqual(kinds(self.capture, "end")[0]["status"], "unknown")

    async def test_async_unconsumed_read_and_savepoint_gap(self):
        await self.conn.execute(READ, (1,))
        await self.conn.execute("SAVEPOINT nested")
        await self.conn.rollback()
        self.assertIn("unconsumed_result", gap_codes(self.capture))
        self.assertIn("unsupported_sql", gap_codes(self.capture))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "python-capture-unit", "actualDatabaseExecution": False,
                      "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "passed": result.wasSuccessful()}))
    sys.exit(0 if result.wasSuccessful() else 1)
