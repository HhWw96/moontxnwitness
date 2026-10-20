"""Database-free proxy checks, never PostgreSQL or application acceptance.

The deterministic cursor below models only the reviewed SELECT/UPDATE shape.
It does not execute SQL, triggers, MVCC, NOW(), locks or the external project.
Actual PostgreSQL and frozen dislock execution use separate fixtures/receipts.
"""
import datetime
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg import sql

from returning_profile import ReturningColumnCapture, ReturningPointProfile
from test_capture_profile import Connection as SetupConnection, Cursor as SetupCursor
from prototype import Names


NAMES = Names("mtw_provenance_returning_unit", "items", "column")
READ_SQL = "SELECT expire_at,value FROM " + NAMES.business + " WHERE id=%s"
WRITE_SQL = ("UPDATE " + NAMES.business
             + " SET expire_at=NOW()+(%s*INTERVAL '1 second')"
             + " WHERE id=%s AND value=%s RETURNING expire_at")
TOKEN = '"' + NAMES.version_column + '"'
PROFILE = ReturningPointProfile(
    NAMES.schema, NAMES.table, "id", "value", READ_SQL, WRITE_SQL,
    "SELECT expire_at,value," + TOKEN + "::text FROM " + NAMES.business + " WHERE id=%s",
    WRITE_SQL + ",OLD." + TOKEN + "::text,NEW." + TOKEN + "::text")
NOW = datetime.datetime(2026, 10, 20, 0, 0, tzinfo=datetime.timezone.utc)


def column(name, type_code):
    return SimpleNamespace(name=name, type_code=type_code)


class RawCursor(SetupCursor):
    def execute(self, query, params=None, **kwargs):
        text = query if isinstance(query, str) else query.as_string(self.connection)
        if text.startswith('SELECT "id","mtwp_'):
            self.connection.calls.append((query, params))
            self.rows = [(key, row[2]) for key, row in self.connection.store.items()]
            self.position, self.rowcount = 0, len(self.rows)
            return self
        # The fake SQL oracle accepts harmless surrounding whitespace; capture
        # must still distinguish the exact reviewed declaration from that SQL.
        statement = text.strip()
        if statement not in (READ_SQL, WRITE_SQL, PROFILE.observed_read_sql, PROFILE.observed_write_sql):
            result = super().execute(text, params, **kwargs)
            self.connection.calls[-1] = (query, params)
            return result
        connection = self.connection
        connection.calls.append((query, params))
        if connection.info.transaction_status == 0 and not connection.autocommit:
            connection.begin()
        if connection.execute_error is not None:
            connection.info.transaction_status = 3
            raise connection.execute_error
        data = connection.working if connection.working is not None else connection.store
        self.position = 0
        if statement in (READ_SQL, PROFILE.observed_read_sql):
            row = data.get(params[0])
            self.rows = [] if row is None else [row if statement == PROFILE.observed_read_sql else row[:2]]
            self.description = [column("expire_at", 1184), column("value", 25)]
            if statement == PROFILE.observed_read_sql:
                self.description.append(column(NAMES.version_column, 25))
            self.rowcount = len(self.rows)
            self.statusmessage = "SELECT " + str(self.rowcount)
        else:
            old = data.get(params[1])
            matched = old is not None and old[1] == params[2]
            self.rowcount = int(matched)
            self.rows = []
            if matched:
                # Only a predictable business value for proxy comparisons. This
                # clock is not a model of PostgreSQL transaction timestamps.
                expires = connection.now + datetime.timedelta(seconds=params[0])
                new = (expires, old[1], str(uuid.uuid4()))
                data[params[1]] = new
                self.rows = [(expires, old[2], new[2]) if statement == PROFILE.observed_write_sql else (expires,)]
            if statement == PROFILE.observed_write_sql and connection.returning_override is not None:
                self.rows = list(connection.returning_override)
            self.description = [column("expire_at", 1184)]
            if statement == PROFILE.observed_write_sql:
                self.description.extend([column("old_token", 25), column("new_token", 25)])
            self.statusmessage = "UPDATE " + str(self.rowcount)
        return self

    def fetchone(self):
        if self.connection.fetch_error is not None:
            raise self.connection.fetch_error
        return super().fetchone()

    def fetchmany(self, size=0):
        # Pinned psycopg 3.3.6: zero/default means arraysize, including an
        # arraysize of zero. This deliberately corrects the older setup fake.
        requested = self.arraysize if not size else size
        return [row for _ in range(requested) if (row := self.fetchone()) is not None]

    def fetchall(self):
        rows = []
        while (row := self.fetchone()) is not None:
            rows.append(row)
        return rows


class RawConnection(SetupConnection):
    def __init__(self, store=None, autocommit=False):
        if store is None:
            store = {key: (NOW + datetime.timedelta(seconds=30), owner, str(uuid.uuid4()))
                     for key, owner in (("a", "owner-a"), ("b", "owner-b"))}
        super().__init__(store=store, autocommit=autocommit)
        self.now, self.returning_override, self.fetch_error = NOW, None, None
        # Only the encoding surface used by Composed.as_string(); no libpq or
        # actual PostgreSQL connection is constructed by this fake.
        self.pgconn = SimpleNamespace(_encoding="utf-8")

    @property
    def connection(self):
        return self

    def cursor(self, *args, **kwargs):
        cursor = RawCursor(self)
        cursor.row_factory = kwargs.get("row_factory", self.row_factory)
        return cursor

    def __enter__(self):
        return self


def captured():
    session = ReturningColumnCapture(PROFILE, keys=("a", "b"), exclusive_writers=True)
    setup = RawConnection(autocommit=True)
    # This suite tests proxy behavior, not catalog or DDL execution.
    with patch("capture_profile.verify_installation"):
        session.initialize(setup)
    raw = RawConnection(store=setup.store)
    return session, session.wrap(raw), raw


def operations(session):
    return [event["op"] for event in session.document()["events"] if event["kind"] == "op"]


def gap_codes(session):
    return {gap["code"] for gap in session.document()["gaps"]}


class ReturningProfileTests(unittest.TestCase):
    def test_multicolumn_read_retains_original_rows_description_and_version(self):
        session, connection, raw = captured()
        expected = raw.store["a"]
        cursor = connection.execute(READ_SQL, ("a",))
        self.assertEqual([(c.name, c.type_code) for c in cursor.description],
                         [("expire_at", 1184), ("value", 25)])
        self.assertEqual((cursor.rowcount, cursor.rownumber, cursor.statusmessage), (1, 0, "SELECT 1"))
        self.assertEqual(cursor.fetchone(), expected[:2])
        self.assertEqual(cursor.rownumber, 1)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual([op["version"] for op in operations(session)], [expected[2]])
        connection.commit()
        self.assertFalse(gap_codes(session))
        self.assertEqual(raw.calls[-1][0], PROFILE.observed_read_sql)

    def test_existing_returning_surface_and_same_statement_old_new_sources(self):
        session, connection, raw = captured()
        old = raw.store["a"][2]
        cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        self.assertEqual([(c.name, c.type_code) for c in cursor.description], [("expire_at", 1184)])
        self.assertEqual((cursor.rowcount, cursor.rownumber, cursor.statusmessage), (1, 0, "UPDATE 1"))
        self.assertEqual(cursor.fetchone(), (NOW + datetime.timedelta(seconds=60),))
        self.assertEqual(cursor.rownumber, 1)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(cursor.fetchall(), [])
        observed = operations(session)
        self.assertEqual([op["type"] for op in observed], ["read", "write"])
        self.assertEqual(observed[0]["version"], old)
        self.assertEqual(observed[1]["version"], raw.working["a"][2])
        self.assertNotEqual(observed[0]["version"], observed[1]["version"])
        connection.commit()
        self.assertFalse(gap_codes(session))

    def test_returning_fetchmany_zero_default_all_iteration_and_cursor_context(self):
        for method in ("zero", "default", "all", "iterate"):
            with self.subTest(method=method):
                session, connection, _ = captured()
                with connection.cursor() as cursor:
                    cursor.execute(WRITE_SQL, (60, "a", "owner-a"))
                    cursor.arraysize = 4
                    if method == "zero":
                        rows = cursor.fetchmany(0)
                    elif method == "default":
                        rows = cursor.fetchmany()
                    elif method == "all":
                        rows = cursor.fetchall()
                    else:
                        rows = list(cursor)
                    self.assertEqual(rows, [(NOW + datetime.timedelta(seconds=60),)])
                    self.assertEqual(cursor.rownumber, 1)
                self.assertTrue(cursor.closed)
                connection.commit()
                self.assertFalse(gap_codes(session))

    def test_arraysize_zero_does_not_consume_pending_returning_rows(self):
        session, connection, _ = captured()
        cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        cursor.arraysize = 0
        self.assertEqual(cursor.fetchmany(0), [])
        self.assertEqual(cursor.rownumber, 0)
        self.assertEqual(cursor.fetchall(), [(NOW + datetime.timedelta(seconds=60),)])
        connection.commit()
        self.assertFalse(gap_codes(session))

    def test_connection_context_keeps_acknowledged_commit_and_exception_rollback(self):
        session, connection, raw = captured()
        with connection as wrapped:
            self.assertIs(wrapped, connection)
            wrapped.execute(WRITE_SQL, (60, "a", "owner-a")).fetchone()
        self.assertTrue(raw.closed)
        self.assertEqual([e["status"] for e in session.document()["events"] if e["kind"] == "end"], ["committed"])
        self.assertFalse(gap_codes(session))
        session, connection, raw = captured()
        before = dict(raw.store)
        original = RuntimeError("original business exception")
        with self.assertRaises(RuntimeError) as caught:
            with connection:
                connection.execute(WRITE_SQL, (60, "a", "owner-a")).fetchone()
                raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(raw.store, before)
        self.assertEqual([e["status"] for e in session.document()["events"] if e["kind"] == "end"], ["aborted"])

    def test_unconsumed_multicolumn_read_remains_a_coverage_gap(self):
        session, connection, _ = captured()
        cursor = connection.execute(READ_SQL, ("a",))
        self.assertEqual(len(cursor.description), 2)
        connection.commit()
        self.assertIn("unconsumed_result", gap_codes(session))
        self.assertEqual(operations(session), [])

    def test_unconsumed_returning_creates_gap_on_commit_cursor_close_and_reexecute(self):
        for action in ("commit", "close", "reexecute"):
            with self.subTest(action=action):
                session, connection, _ = captured()
                cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
                if action == "commit":
                    connection.commit()
                elif action == "close":
                    cursor.close()
                    connection.rollback()
                else:
                    cursor.execute(READ_SQL, ("a",)).fetchone()
                    connection.rollback()
                self.assertIn("unconsumed_result", gap_codes(session))

    def test_failed_predicate_retains_empty_returning_and_emits_no_invented_read_or_write(self):
        session, connection, raw = captured()
        before = dict(raw.store)
        cursor = connection.execute(WRITE_SQL, (60, "a", "wrong-owner"))
        self.assertEqual((cursor.rowcount, cursor.rownumber, cursor.statusmessage), (0, 0, "UPDATE 0"))
        self.assertEqual(len(cursor.description), 1)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(cursor.fetchall(), [])
        self.assertEqual(operations(session), [])
        self.assertIn("conditional_update_cardinality", gap_codes(session))
        connection.commit()
        self.assertEqual(raw.store, before)

    def test_invalid_old_new_and_duplicate_uuid_metadata_never_emit_operations(self):
        old = "abcdefab-cdef-4abc-8abc-abcdefabcdef"
        new = "12345678-1234-4234-8234-123456789abc"
        for metadata in (("invalid", new), (old, "invalid"), (None, new), (old, None),
                         (old, old), (old, old.upper())):
            with self.subTest(metadata=metadata):
                session, connection, raw = captured()
                raw.returning_override = [(NOW, *metadata)]
                cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
                self.assertEqual(cursor.fetchall(), [(NOW,)])
                self.assertEqual(operations(session), [])
                self.assertIn("mapping_failed", gap_codes(session))
                connection.rollback()

    def test_metadata_shape_changes_preserve_business_projection_and_add_gap(self):
        for row in ((NOW,), (NOW, str(uuid.uuid4())), (NOW, "old", "new", "unexpected")):
            with self.subTest(row=row):
                session, connection, raw = captured()
                raw.returning_override = [row]
                self.assertEqual(connection.execute(WRITE_SQL, (60, "a", "owner-a")).fetchall(), [(NOW,)])
                self.assertEqual(operations(session), [])
                self.assertIn("mapping_failed", gap_codes(session))
                connection.rollback()

    def test_closed_buffered_fetch_raises_interface_error(self):
        session, connection, _ = captured()
        cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        cursor.fetchall()
        cursor.close()
        for method in ("fetchone", "fetchmany", "fetchall"):
            with self.subTest(method=method), self.assertRaises(psycopg.InterfaceError):
                getattr(cursor, method)()
        connection.rollback()

    def test_composed_exact_match_rewrites_and_different_sql_is_preserved_with_gap(self):
        session, connection, raw = captured()
        composed = sql.Composed([sql.SQL(READ_SQL[:12]), sql.SQL(READ_SQL[12:])])
        self.assertEqual(connection.execute(composed, ("a",)).fetchone(), raw.store["a"][:2])
        self.assertEqual(raw.calls[-1][0], PROFILE.observed_read_sql)
        unregistered = sql.Composed([sql.SQL(READ_SQL), sql.SQL(" ")])
        self.assertEqual(connection.execute(unregistered, ("a",)).fetchall(), [raw.working["a"][:2]])
        self.assertIs(raw.calls[-1][0], unregistered)
        self.assertIn("unsupported_sql", gap_codes(session))
        self.assertEqual(len(operations(session)), 1)
        connection.rollback()

    def test_reexecute_unsupported_sql_uses_its_own_rows_not_stale_returning_buffer(self):
        session, connection, raw = captured()
        cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        unregistered = READ_SQL + " "
        cursor.execute(unregistered, ("b",))
        self.assertIs(raw.calls[-1][0], unregistered)
        self.assertEqual((cursor.rowcount, cursor.rownumber), (1, 0))
        self.assertEqual(len(cursor.description), 2)
        self.assertEqual(cursor.fetchall(), [raw.working["b"][:2]])
        self.assertIn("unconsumed_result", gap_codes(session))
        self.assertIn("unsupported_sql", gap_codes(session))
        self.assertEqual(len(operations(session)), 2)
        connection.rollback()

    def test_reexecute_out_of_scope_or_zero_guard_clears_buffered_business_rows(self):
        for key, owner, gap in (("missing", "owner-a", "key_outside_scope"),
                                ("a", "wrong-owner", "conditional_update_cardinality")):
            with self.subTest(key=key):
                session, connection, raw = captured()
                cursor = connection.execute(WRITE_SQL, (60, "a", "owner-a"))
                cursor.fetchall()
                cursor.execute(WRITE_SQL, (90, key, owner))
                self.assertEqual((cursor.rowcount, cursor.rownumber, cursor.statusmessage), (0, 0, "UPDATE 0"))
                self.assertEqual(len(cursor.description), 1)
                self.assertIsNone(cursor.fetchone())
                self.assertEqual(cursor.fetchall(), [])
                self.assertEqual(len(operations(session)), 2)
                self.assertIn(gap, gap_codes(session))
                self.assertEqual(raw.calls[-1][0], WRITE_SQL if key == "missing" else PROFILE.observed_write_sql)
                connection.rollback()

    def test_rollback_retains_aborted_sources_and_restores_business_rows(self):
        session, connection, raw = captured()
        before = dict(raw.store)
        connection.execute(WRITE_SQL, (60, "a", "owner-a")).fetchone()
        changed_token = operations(session)[1]["version"]
        connection.rollback()
        self.assertEqual(raw.store, before)
        self.assertNotEqual(changed_token, raw.store["a"][2])
        self.assertEqual([e["status"] for e in session.document()["events"] if e["kind"] == "end"], ["aborted"])
        self.assertFalse(gap_codes(session))

    def test_actual_execute_fetch_and_unknown_commit_exceptions_are_not_replaced(self):
        session, connection, raw = captured()
        raw.execute_error = psycopg.errors.NotNullViolation("original server error")
        with self.assertRaises(psycopg.errors.NotNullViolation) as caught:
            connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        self.assertIs(caught.exception, raw.execute_error)
        self.assertEqual(operations(session), [])
        raw.execute_error = None
        connection.rollback()
        raw.fetch_error = OSError("actual metadata fetch failure")
        with self.assertRaises(OSError) as caught:
            connection.execute(WRITE_SQL, (60, "a", "owner-a"))
        self.assertIs(caught.exception, raw.fetch_error)
        self.assertIn("fetch_failed", gap_codes(session))
        raw.fetch_error = None
        connection.rollback()
        connection.execute(WRITE_SQL, (60, "a", "owner-a")).fetchone()
        raw.commit_error = OSError("unknown commit acknowledgement")
        with self.assertRaises(OSError) as caught:
            connection.commit()
        self.assertIs(caught.exception, raw.commit_error)
        self.assertIn("commit_unknown", gap_codes(session))
        self.assertEqual([e["status"] for e in session.document()["events"] if e["kind"] == "end"][-1], "unknown")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReturningProfileTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "experimental-returning-profile", "tests": result.testsRun,
                      "actualDatabaseExecution": False, "upstreamCodeExecuted": False,
                      "passed": result.wasSuccessful()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
