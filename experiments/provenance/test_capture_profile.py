"""Database-free contract checks; this does not prove SQL/trigger execution."""
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg.rows import tuple_row, dict_row

from capture_profile import (ColumnCapture, ColumnPointProfile, _function_source,
                             _verify_metadata_constraints, verify_installation)
from prototype import Installation, ProvenanceError, ddl


PROFILE = ColumnPointProfile("mtw_provenance_profile_unit")


class Cursor:
    def __init__(self, conn):
        self.connection = conn
        self.row_factory = conn.row_factory
        self.closed = False
        self.arraysize = 1
        self.rows, self.position = None, 0
        self.description, self.rowcount, self.statusmessage = None, -1, None

    @property
    def rownumber(self):
        return self.position if self.rows is not None else None

    def execute(self, query, params=None, **kwargs):
        c = self.connection
        c.calls.append((query, params))
        self.rows, self.position, self.description, self.rowcount = None, 0, None, -1
        if query.startswith("BEGIN"):
            c.begin()
        elif query.startswith("LOCK TABLE") or query.startswith(("CREATE ", "ALTER ")):
            pass
        elif "FROM pg_catalog.pg_class c JOIN" in query:
            self.rows = [(42, "r", False, False, True)]
        elif query.startswith("SELECT count(*) FROM pg_catalog."):
            self.rows = [(int(c.unsupported_feature is not None and c.unsupported_feature in query),)]
        elif query.startswith('SELECT "id" FROM '):
            self.rows = [(k,) for k in c.store]
        elif query.startswith('INSERT INTO ') and "_installation" in query:
            pass
        elif query.startswith('SELECT "id","mtwp_'):
            self.rows = [(k, row[1]) for k, row in c.store.items()]
        elif query.startswith("UPDATE ") and "gen_random_uuid" in query:
            c.begin()
        else:
            if c.info.transaction_status == 0 and not c.autocommit:
                c.begin()
            data = c.working if c.working is not None else c.store
            if c.execute_error is not None:
                raise c.execute_error
            if query in (PROFILE.read_sql, PROFILE.observed_read_sql):
                row = data.get(params[0])
                self.rows = [] if row is None else [row if query == PROFILE.observed_read_sql else row[:1]]
                self.description = [SimpleNamespace(name="value", type_code=23)]
                if query == PROFILE.observed_read_sql:
                    self.description.append(SimpleNamespace(name=PROFILE.names.version_column, type_code=25))
                self.rowcount = len(self.rows)
                self.statusmessage = "SELECT " + str(self.rowcount)
            elif query in (PROFILE.write_sql, PROFILE.observed_write_sql):
                key = params[1]
                self.rowcount = int(key in data)
                if self.rowcount:
                    token = str(uuid.uuid4())
                    data[key] = (params[0], token)
                if query == PROFILE.observed_write_sql:
                    self.rows = [(data[key][1],)] if self.rowcount else []
                    self.description = [SimpleNamespace(name=PROFILE.names.version_column, type_code=25)]
                self.statusmessage = "UPDATE " + str(self.rowcount)
            elif query == "SELECT 1":
                self.rows = [(1,)]
                self.description = [SimpleNamespace(name="?column?", type_code=23)]
                self.rowcount, self.statusmessage = 1, "SELECT 1"
        return self

    def fetchone(self):
        if self.closed:
            raise psycopg.InterfaceError("the cursor is closed")
        if self.rows is None:
            raise psycopg.ProgrammingError("the last operation didn't produce records (command status: " + self.statusmessage + ")")
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
        return self.fetchmany(10_000)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Connection:
    def __init__(self, store=None, autocommit=False):
        self.store = store if store is not None else {"a": (7, str(uuid.uuid4())), "b": (11, str(uuid.uuid4()))}
        self.working = None
        self.autocommit, self.row_factory = autocommit, tuple_row
        self.info = SimpleNamespace(transaction_status=0, server_version=180006)
        self.closed, self.calls, self.commit_calls = False, [], 0
        self.execute_error = self.commit_error = None
        self.unsupported_feature = None

    def begin(self):
        if self.working is None:
            self.working = dict(self.store)
        self.info.transaction_status = 2

    def cursor(self, *args, **kwargs):
        cursor = Cursor(self)
        cursor.row_factory = kwargs.get("row_factory", self.row_factory)
        return cursor

    def execute(self, query, params=None, **kwargs):
        return self.cursor().execute(query, params, **kwargs)

    def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.commit_calls += 1
        if self.working is not None:
            self.store.clear()
            self.store.update(self.working)
        self.working, self.info.transaction_status = None, 0

    def rollback(self):
        self.working, self.info.transaction_status = None, 0

    def close(self):
        self.closed = True


def capture():
    session = ColumnCapture(PROFILE, keys=("a", "b"), exclusive_writers=True)
    setup = Connection(autocommit=True)
    # SQL execution/DDL checking is a separate actual PostgreSQL fixture. These
    # fake rows test publish ordering and the Python business-surface contract.
    with patch("capture_profile.verify_installation") as verify:
        session.initialize(setup)
        verify.assert_called_once()
    raw = Connection(store=setup.store)
    return session, session.wrap(raw), raw


def ops(session, type=None):
    return [e["op"] for e in session.document()["events"] if e["kind"] == "op" and (type is None or e["op"]["type"] == type)]


def metadata_constraints(suffix, nonnull_flags):
    """PG18 SELECT projection fixture, including implicit PK NOT NULL rows."""
    shape = [("column_" + str(i), "text", flag) for i, flag in enumerate(nonnull_flags)]
    rows = [("n", [i + 1], False, False, True, None, None, None, " ", " ", " ",
             True, True, 0, 0, False, False) for i, flag in enumerate(nonnull_flags) if flag]
    rows.append(("p", [1], False, False, True, None, None, None, " ", " ", " ",
                 True, True, 0, 0, True, False))
    if suffix in ("audit", "state"):
        rows.append(("f", [5 if suffix == "audit" else 2], False, False, True,
                     PROFILE.names.schema, PROFILE.names.prefix + "_audit", [1], "a", "a", "s",
                     True, True, 0, 0, False, False))
    return shape, rows


class CaptureProfileTests(unittest.TestCase):
    def test_postgres18_notnull_catalog_has_exact_fixed_column_sets(self):
        for suffix, flags in (("installation", (True, True, True)),
                              ("audit", (True, True, True, True, False, False, False)),
                              ("state", (True, True, True))):
            shape, constraints = metadata_constraints(suffix, flags)
            _verify_metadata_constraints(PROFILE.names, suffix, shape, constraints)

    def test_postgres18_notnull_rejects_missing_duplicate_wrong_or_weak_rows(self):
        shape, original = metadata_constraints("installation", (True, True, True))
        corruptions = []
        corruptions.append(original[1:])  # Missing a NOT NULL constraint.
        corruptions.append(original + [original[0]])  # Duplicate column.
        for index, value in ((1, [4]), (1, [1, 2]), (2, True), (3, True), (4, False),
                             (11, False), (12, False), (13, 1), (14, 1), (15, True), (16, True)):
            rows = [list(r) for r in original]
            rows[0][index] = value
            corruptions.append(rows)
        for rows in corruptions:
            with self.subTest(rows=rows[0]):
                with self.assertRaises(ProvenanceError):
                    _verify_metadata_constraints(PROFILE.names, "installation", shape, rows)

    def test_postgres18_constraint_fix_does_not_allow_unexpected_or_unenforced_keys(self):
        shape, original = metadata_constraints("audit", (True, True, True, True, False, False, False))
        for mutate in ("extra-check", "unenforced-pk", "wrong-fk"):
            rows = [list(r) for r in original]
            if mutate == "extra-check":
                rows.append(["c", [1], False, False, True, None, None, None, " ", " ", " ", True, True, 0, 0, False, False])
            elif mutate == "unenforced-pk":
                next(r for r in rows if r[0] == "p")[11] = False
            else:
                next(r for r in rows if r[0] == "f")[6] = "another_audit"
            with self.assertRaises(ProvenanceError):
                _verify_metadata_constraints(PROFILE.names, "audit", shape, rows)

    def test_older_catalog_contract_is_refused_before_installation(self):
        session = ColumnCapture(PROFILE, keys=("a", "b"))
        setup = Connection(autocommit=True)
        setup.info.server_version = 170005
        with self.assertRaises(ProvenanceError):
            session.initialize(setup)
        self.assertEqual(setup.calls, [])

    def test_wrap_and_connect_before_initialization_do_not_touch_driver(self):
        session = ColumnCapture(PROFILE, keys=("a", "b"))
        raw = Connection()
        with self.assertRaises(ProvenanceError):
            session.wrap(raw)
        with patch("psycopg.connect") as connect:
            with self.assertRaises(ProvenanceError):
                session.connect("unused-not-a-real-credential")
            connect.assert_not_called()
        self.assertEqual(raw.calls, [])

    def test_hidden_sql_features_fail_before_any_install_ddl(self):
        for feature in ("pg_inherits", "contype='f'", "pg_rewrite", "contype IN ('c','x')", "a.attgenerated", "indexprs"):
            session = ColumnCapture(PROFILE, keys=("a", "b"))
            setup = Connection(autocommit=True)
            setup.unsupported_feature = feature
            with self.assertRaises(ProvenanceError):
                session.initialize(setup)
            self.assertFalse(session.document()["events"])
            self.assertFalse(any(q.startswith(("CREATE ", "ALTER ")) for q, _ in setup.calls))

    def test_fixed_templates_quote_identifiers_and_do_not_add_business_parameters(self):
        profile = ColumnPointProfile("mtw_provenance_q", 'it"ems', 'i"d', 'val"ue')
        self.assertIn('"it""ems"', profile.read_sql)
        self.assertEqual(profile.write_sql.count("%s"), profile.observed_write_sql.count("%s"))
        self.assertTrue(profile.observed_write_sql.startswith(profile.write_sql + " RETURNING "))
        with self.assertRaises(ValueError):
            ColumnPointProfile("public")

    def test_function_source_check_handles_quoted_delimiter_text(self):
        profile = ColumnPointProfile("mtw_provenance_ AS $mtw$\n", value_column="v$mtw$ AS column")
        functions = [s for s in ddl(profile.names) if s.startswith("CREATE FUNCTION ")]
        self.assertEqual(len(functions), 2)
        self.assertTrue(_function_source(functions[0]).startswith("\nBEGIN\n"))
        self.assertIn('NEW."v$mtw$ AS column"', _function_source(functions[1]))

    def test_row_factory_change_after_execute_creates_gap(self):
        session, conn, raw = capture()
        cursor = conn.execute(PROFILE.read_sql, ("a",))
        cursor.row_factory = dict_row
        self.assertIn("unsupported_row_factory", {g["code"] for g in session.document()["gaps"]})

    def test_initialization_is_one_locked_transaction_before_publication(self):
        session, conn, raw = capture()
        self.assertEqual(len(session.document()["events"]), 1)
        self.assertEqual(session.document()["events"][0]["kind"], "snapshot")
        self.assertEqual(set(session.document()["events"][0]["initial"].values()), {r[1] for r in raw.store.values()})
        self.assertTrue(session._initialized)
        self.assertIs(session.wrap(raw), conn)

    def test_initialization_verification_failure_never_publishes_snapshot(self):
        session = ColumnCapture(PROFILE, keys=("a", "b"))
        setup = Connection(autocommit=True)
        error = ProvenanceError("tampered trigger")
        with patch("capture_profile.verify_installation", side_effect=error):
            with self.assertRaises(ProvenanceError) as caught:
                session.initialize(setup)
        self.assertIs(caught.exception, error)
        self.assertEqual(setup.commit_calls, 0)
        self.assertFalse(session._initialized)
        self.assertFalse(session.document()["events"])
        self.assertIn("initialization_failed", {g["code"] for g in session.document()["gaps"]})

    def test_initialization_commit_error_does_not_publish_confirmed_facts(self):
        session = ColumnCapture(PROFILE, keys=("a", "b"))
        setup = Connection(autocommit=True)
        setup.commit_error = OSError("lost setup commit acknowledgement")
        with patch("capture_profile.verify_installation"):
            with self.assertRaises(OSError) as caught:
                session.initialize(setup)
        self.assertIs(caught.exception, setup.commit_error)
        self.assertFalse(session._initialized)
        self.assertFalse(session.document()["events"])

    def test_declared_keys_must_match_initial_rows(self):
        session = ColumnCapture(PROFILE, keys=("a",))
        with self.assertRaises(ProvenanceError):
            session.initialize(Connection(autocommit=True))
        self.assertFalse(session.document()["events"])

    def test_read_returns_original_columns_description_and_iteration(self):
        session, conn, raw = capture()
        cursor = conn.execute(PROFILE.read_sql, ("a",))
        self.assertEqual(len(cursor.description), 1)
        self.assertEqual(cursor.description[0].name, "value")
        self.assertEqual(cursor.statusmessage, "SELECT 1")
        self.assertEqual((cursor.rowcount, cursor.rownumber), (1, 0))
        self.assertEqual(list(cursor), [(7,)])
        conn.commit()
        self.assertEqual(len(ops(session, "read")), 1)
        self.assertFalse(session.document()["gaps"])
        self.assertEqual(raw.calls[-1][0], PROFILE.observed_read_sql)

    def test_each_same_value_write_has_its_own_returned_token_and_self_read(self):
        session, conn, raw = capture()
        initial = raw.store["a"][1]
        conn.execute(PROFILE.write_sql, (7, "a"))
        first = ops(session, "write")[-1]["version"]
        self.assertEqual(conn.execute(PROFILE.read_sql, ("a",)).fetchone(), (7,))
        self.assertEqual(ops(session, "read")[-1]["version"], first)
        conn.execute(PROFILE.write_sql, (7, "a"))
        second = ops(session, "write")[-1]["version"]
        self.assertEqual(len({initial, first, second}), 3)
        self.assertEqual(conn.execute(PROFILE.read_sql, ("a",)).fetchall(), [(7,)])
        self.assertEqual(ops(session, "read")[-1]["version"], second)
        conn.commit()
        self.assertEqual(raw.store["a"], (7, second))
        self.assertFalse(session.document()["gaps"])
        self.assertEqual(sum(q == PROFILE.observed_write_sql for q, _ in raw.calls), 2)
        self.assertFalse(any("_audit" in q for q, _ in raw.calls))

    def test_no_result_write_surface_matches_plain_cursor(self):
        session, conn, raw = capture()
        business = conn.execute(PROFILE.write_sql, (9, "a"))
        plain = Connection().execute(PROFILE.write_sql, (9, "a"))
        self.assertIsNone(business.description)
        self.assertEqual((business.rowcount, business.statusmessage, business.rownumber),
                         (plain.rowcount, plain.statusmessage, plain.rownumber))
        for fetch in ("fetchone", "fetchmany", "fetchall"):
            with self.assertRaises(psycopg.ProgrammingError) as actual:
                getattr(business, fetch)()
            with self.assertRaises(psycopg.ProgrammingError) as expected:
                getattr(plain, fetch)()
            self.assertEqual(str(actual.exception), str(expected.exception))
        business.close()
        with self.assertRaises(psycopg.InterfaceError):
            business.fetchone()

    def test_rollback_retains_aborted_observation_and_restores_business_value(self):
        session, conn, raw = capture()
        before = dict(raw.store)
        conn.execute(PROFILE.write_sql, (99, "a"))
        token = ops(session, "write")[-1]["version"]
        conn.rollback()
        self.assertEqual(raw.store, before)
        self.assertNotEqual(token, raw.store["a"][1])
        self.assertEqual([e["status"] for e in session.document()["events"] if e["kind"] == "end"], ["aborted"])

    def test_business_error_identity_and_unknown_commit_are_preserved(self):
        session, conn, raw = capture()
        raw.execute_error = psycopg.errors.CheckViolation("business failure")
        with self.assertRaises(psycopg.errors.CheckViolation) as caught:
            conn.execute(PROFILE.write_sql, (-1, "a"))
        self.assertIs(caught.exception, raw.execute_error)
        raw.execute_error = None
        conn.rollback()
        conn.execute(PROFILE.write_sql, (7, "a"))
        raw.commit_error = OSError("unknown commit")
        with self.assertRaises(OSError) as caught:
            conn.commit()
        self.assertIs(caught.exception, raw.commit_error)
        self.assertIn("commit_unknown", {g["code"] for g in session.document()["gaps"]})

    def test_unknown_sql_and_out_of_scope_keys_execute_original_and_gap(self):
        session, conn, raw = capture()
        self.assertEqual(conn.execute("SELECT 1").fetchone(), (1,))
        self.assertEqual(raw.calls[-1][0], "SELECT 1")
        cursor = conn.execute(PROFILE.read_sql, ("missing",))
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(raw.calls[-1][0], PROFILE.read_sql)
        conn.commit()
        self.assertIn("unsupported_sql", {g["code"] for g in session.document()["gaps"]})
        self.assertIn("key_outside_scope", {g["code"] for g in session.document()["gaps"]})

    def test_custom_row_factory_is_not_rewritten(self):
        session, conn, raw = capture()
        cursor = conn.cursor(row_factory=dict_row)
        cursor.execute(PROFILE.read_sql, ("a",))
        self.assertEqual(raw.calls[-1][0], PROFILE.read_sql)
        self.assertIn("unsupported_row_factory", {g["code"] for g in session.document()["gaps"]})

    def test_unconsumed_read_is_not_silently_completed(self):
        session, conn, raw = capture()
        cursor = conn.execute(PROFILE.read_sql, ("a",))
        conn.commit()
        self.assertIn("unconsumed_result", {g["code"] for g in session.document()["gaps"]})

    def test_verifier_rejects_wrong_nonce_without_trusting_table_name(self):
        install = Installation(PROFILE.names, str(uuid.uuid4()), 42, {})
        setup = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchall=lambda: [(str(uuid.uuid4()), "column", 42)]))
        with self.assertRaises(ProvenanceError):
            verify_installation(setup, install)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CaptureProfileTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "experimental-column-profile", "tests": result.testsRun,
                      "actualDatabaseExecution": False, "passed": result.wasSuccessful()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
