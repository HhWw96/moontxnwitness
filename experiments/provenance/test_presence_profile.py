"""Fake-driver contracts only: real helper visibility needs presence_postgres.py."""
import copy
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg.rows import tuple_row, dict_row

from presence_profile import (PROJECTION, PresenceCapture, PresencePointProfile,
                              _observation, presence_ddl, verify_presence_installation)
from capture_profile import _function_source
from prototype import Installation, ProvenanceError


P = PresencePointProfile("mtw_provenance_presence_unit")


class Cursor:
    def __init__(self, connection):
        self.connection, self.row_factory, self.closed, self.arraysize = connection, connection.row_factory, False, 1
        self.rows, self.position, self.rowcount, self.description, self.statusmessage = None, 0, -1, None, None

    @property
    def rownumber(self):
        return self.position if self.rows is not None else None

    def execute(self, query, params=None, **kwargs):
        c = self.connection
        c.calls.append((query, params))
        self.rows, self.position, self.rowcount, self.description, self.statusmessage = None, 0, -1, None, None
        if query == "COMMIT":
            c.commit()
            self.pgresult = SimpleNamespace(status=psycopg.pq.ExecStatus.COMMAND_OK)
            self.statusmessage = "COMMIT"
        elif query.startswith("BEGIN"):
            c.begin()
            self.statusmessage = "BEGIN"
        elif query.startswith("LOCK TABLE") or query.startswith(("CREATE ", "ALTER ")):
            pass
        elif "FROM pg_catalog.pg_class c JOIN" in query:
            self.rows = [(42, "r", False, False, True)]
        elif query.startswith("SELECT count(*) FROM pg_catalog."):
            self.rows = [(0,)]
        elif query.startswith('SELECT "id" FROM '):
            self.rows = [(key,) for key in c.data["rows"]]
        elif query.startswith("UPDATE ") and "gen_random_uuid" in query:
            for key, (value, _) in c.data["rows"].items():
                c.data["rows"][key] = (value, str(uuid.uuid4()))
        elif query.startswith("INSERT INTO ") and "_installation" in query:
            pass
        elif query.startswith("INSERT INTO ") and " SELECT " in query:
            if query.startswith("INSERT INTO " + P.names.object("audit")):
                for key, (value, token) in c.data["rows"].items():
                    c.data["audit"][token] = (key, None, True)
            else:
                for token, (key, _, present) in c.data["audit"].items():
                    c.data["state"][key] = (token, present)
        elif query.startswith("INSERT INTO ") and "_audit" in query:
            token, key = params
            c.data["audit"][token] = (key, None, False)
        elif query.startswith("INSERT INTO ") and "_state" in query:
            key, token = params
            c.data["state"][key] = (token, False)
        else:
            if c.info.transaction_status == 0 and not c.autocommit:
                c.begin()
            if c.execute_error is not None:
                raise c.execute_error
        if query == P.observed_read_sql:
            key = params[0]
            item, state = c.data["rows"].get(key), c.data["state"].get(key)
            self.rows = [(item is not None, item[0] if item else None,
                          state[0] if state else None, state[1] if state else None, item[1] if item else None)]
            self.description = [SimpleNamespace(name=name, type_code=25) for name in ("?column?", "value", "token", "present", "version")]
            self.rowcount, self.statusmessage = 1, "SELECT 1"
        elif query in [P.observed(a) for a in ("insert", "update", "delete")]:
            action = next(a for a in ("insert", "update", "delete") if query == P.observed(a))
            key = params[1] if action == "update" else params[0]
            existed = key in c.data["rows"]
            if action == "insert" and existed:
                raise psycopg.errors.UniqueViolation("duplicate key")
            if action != "insert" and not existed:
                self.rows, self.rowcount = [], 0
            else:
                old = c.data["state"][key][0]
                new = str(uuid.uuid4())
                c.data["audit"][new] = (key, old, action != "delete")
                c.data["state"][key] = (new, action != "delete")
                if action == "delete":
                    del c.data["rows"][key]
                else:
                    c.data["rows"][key] = (params[1] if action == "insert" else params[0], new)
                self.rows = [(new, old)] if action == "insert" else [(old, new)]
                self.rowcount = 1
            self.description = [SimpleNamespace(name="token", type_code=25)] * 2
            self.statusmessage = ("INSERT 0 " if action == "insert" else action.upper() + " ") + str(self.rowcount)
        elif query == "SELECT 1":
            self.rows, self.rowcount, self.statusmessage = [(1,)], 1, "SELECT 1"
            self.description = [SimpleNamespace(name="?column?", type_code=23)]
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

    def fetchmany(self, size=0):
        size = size or self.arraysize
        if not isinstance(size, int):
            raise TypeError("size must be an integer")
        rows = []
        for _ in range(max(0, size)):
            row = self.fetchone()
            if row is None:
                break
            rows.append(row)
        return rows

    def fetchall(self):
        return self.fetchmany(10_000)

    def close(self):
        self.closed = True
        self.rows, self.description, self.statusmessage, self.rowcount = None, None, None, -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Connection:
    def __init__(self, store=None, autocommit=False):
        self.store = store or {"rows": {"a": ("same", str(uuid.uuid4()))}, "state": {}, "audit": {}}
        self.working, self.autocommit, self.row_factory = None, autocommit, tuple_row
        self.info = SimpleNamespace(transaction_status=0, server_version=180006)
        self.closed, self.calls, self.execute_error, self.commit_error = False, [], None, None

    @property
    def data(self):
        return self.working if self.working is not None else self.store

    def begin(self):
        if self.working is None:
            self.working = copy.deepcopy(self.store)
        self.info.transaction_status = 2

    def cursor(self, *args, **kwargs):
        cursor = Cursor(self)
        cursor.row_factory = kwargs.get("row_factory", self.row_factory)
        return cursor

    def execute(self, query, params=None, **kwargs):
        return self.cursor().execute(query, params, **kwargs)

    def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        if self.working is not None:
            self.store.clear()
            self.store.update(self.working)
        self.working, self.info.transaction_status = None, 0

    def rollback(self):
        self.working, self.info.transaction_status = None, 0

    def close(self):
        self.closed = True


def capture(**budgets):
    session = PresenceCapture(P, keys=("a", "new", "never"), exclusive_writers=True, **budgets)
    setup = Connection(autocommit=True)
    with patch("presence_profile.verify_presence_installation"), patch("presence_profile._business_columns"):
        session.initialize(setup)
    raw = Connection(setup.store)
    return session, session.wrap(raw), raw


def ops(session):
    return [e for e in session.document()["events"] if e["kind"] == "op"]


class Catalog:
    """Exact projected PG18 catalog, including implicit PK NOT NULL rows."""
    def __init__(self, mutation=None):
        self.installation = Installation(P.names, str(uuid.uuid4()), 42, {})
        self.mutation = mutation

    def execute(self, query, params=None):
        n = P.names
        sources = [_function_source(s) for s in presence_ddl(n) if s.startswith("CREATE FUNCTION ")]
        shapes = {
            "installation": [("nonce", "uuid", True), ("mode", "text", True), ("table_oid", "oid", True)],
            "audit": [("token", "uuid", True), ("key", "text", True), ("action", "text", True), ("present", "boolean", True),
                      ("predecessor", "uuid", False), ("old_value", "jsonb", False), ("new_value", "jsonb", False)],
            "state": [("key", "text", True), ("token", "uuid", True), ("present", "boolean", True)]}
        if query.startswith("SELECT nonce::text"):
            rows = [(self.installation.nonce, "presence", 42)]
        elif query.startswith("SELECT count(*)"):
            bad = ((self.mutation == "deferred-primary" and "condeferrable" in query)
                   or (self.mutation == "non-native-index" and "pg_opclass" in query))
            rows = [(int(bad),)]
        elif "FROM pg_catalog.pg_class c JOIN" in query:
            rows = [(42, "r", False, True, True)]
        elif query.startswith("SELECT a.attname") and "a.atthasdef" in query:
            rows = [("id", "text", False, "", ""), ("value", "text", False, "", ""), (n.version_column, "uuid", False, "", "")]
        elif query.startswith("SELECT a.attnotnull"):
            rows = [(True,)]
        elif query.startswith("SELECT t.tgname"):
            rows = [(n.prefix + "_before", 31, "O", n.prefix + "_before", n.schema, sources[0], False,
                     ["search_path=pg_catalog"], 0, True, "plpgsql", 0, b"", "", True, False, False, "v")]
            if self.mutation == "trigger-bits":
                rows[0] = tuple(29 if i == 1 else value for i, value in enumerate(rows[0]))
        elif query.startswith("SELECT p.prosrc"):
            suffix = "delete_token" if params[1].endswith("_delete_token") else "predecessor"
            argnames = ["target_key", "old_token"] if suffix == "delete_token" else ["new_token"]
            rows = [(sources[1 if suffix == "delete_token" else 2], False, ["search_path=pg_catalog"], "v", True, "plpgsql", "f", False, False, "u",
                     argnames, True, True, 0, 0)]
            if self.mutation == "helper-stable":
                rows[0] = tuple("s" if i == 3 else value for i, value in enumerate(rows[0]))
            elif self.mutation == "helper-argnames":
                rows[0] = tuple(["wrong"] if i == 10 else value for i, value in enumerate(rows[0]))
        else:
            suffix = next(s for s in shapes if params and params[0] == n.object(s))
            shape = shapes[suffix]
            if query.startswith("SELECT a.attname"):
                rows = shape
            elif query.startswith("SELECT relkind"):
                rows = [("r", False, False, "p")]
            elif query.startswith("SELECT c.contype"):
                rows = [("n", [i + 1], False, False, True, None, None, None, " ", " ", " ", True, True, 0, 0, False, False)
                        for i, column in enumerate(shape) if column[2]]
                rows.append(("p", [1], False, False, True, None, None, None, " ", " ", " ", True, True, 0, 0, True, False))
                if suffix != "installation":
                    rows.append(("f", [5 if suffix == "audit" else 2], False, False, True, n.schema,
                                 n.prefix + "_audit", [1], "a", "a", "s", True, True, 0, 0, False, False))
                if self.mutation == "missing-notnull":
                    rows.pop(0)
                elif self.mutation == "duplicate-notnull":
                    rows.append(rows[0])
            elif query.startswith("SELECT (SELECT count(*)"):
                rows = [(0, 0, 0)]
            elif query.startswith("SELECT ci.relname"):
                rows = [(n.prefix + "_" + suffix + "_pkey", True, True, True, True, 1, 1, "1", None, True)]
                if suffix == "audit":
                    rows.append((n.prefix + "_successor", False, True, True, True, 1, 1, "5", "(predecessor IS NOT NULL)", True))
                    if self.mutation == "missing-successor":
                        rows.pop()
                    elif self.mutation == "nonunique-successor":
                        rows[1] = tuple(False if i == 2 else value for i, value in enumerate(rows[1]))
                    elif self.mutation == "wrong-predicate":
                        rows[1] = tuple(None if i == 8 else value for i, value in enumerate(rows[1]))
            else:
                raise AssertionError("Unmodeled catalog projection")
        return SimpleNamespace(fetchall=lambda: rows, fetchone=lambda: rows[0] if rows else None)


class PresenceTests(unittest.TestCase):
    def test_owned_pg18_catalog_shape_and_fail_closed_mutations(self):
        catalog = Catalog()
        verify_presence_installation(catalog, catalog.installation)
        for mutation in ("trigger-bits", "helper-stable", "helper-argnames", "missing-notnull", "duplicate-notnull", "deferred-primary", "non-native-index",
                         "missing-successor", "nonunique-successor", "wrong-predicate"):
            with self.subTest(mutation=mutation):
                catalog = Catalog(mutation)
                with self.assertRaises(ProvenanceError):
                    verify_presence_installation(catalog, catalog.installation)

    def test_generated_templates_preserve_original_point_shapes(self):
        for action in ("insert", "update", "delete"):
            self.assertTrue(P.observed(action).startswith(getattr(P, action + "_sql") + " RETURNING "))
        self.assertIn('OLD."' + P.names.version_column, P.observed("delete"))
        self.assertIn(P.names.object("delete_token"), P.observed("delete"))
        self.assertIn(P.names.object("predecessor"), P.observed("insert"))

    def test_only_before_trigger_and_immutable_helpers(self):
        ddl = presence_ddl(P.names)
        triggers = [s for s in ddl if s.startswith("CREATE TRIGGER ")]
        self.assertEqual(len(triggers), 1)
        self.assertIn("BEFORE INSERT OR UPDATE OR DELETE", triggers[0])
        self.assertIn("CREATE UNIQUE INDEX", ddl[2])
        for s in [s for s in ddl if s.startswith("CREATE FUNCTION ")]:
            self.assertIn("VOLATILE SECURITY INVOKER SET search_path=pg_catalog", s)
        helper = [s for s in ddl if s.startswith("CREATE FUNCTION ")][-2]
        self.assertIn("predecessor=old_token AND action='DELETE'", helper)
        self.assertNotIn(P.names.object("state"), helper)

    def test_trigger_leaves_null_key_and_duplicate_key_to_original_constraints(self):
        before = [s for s in presence_ddl(P.names) if s.startswith("CREATE FUNCTION ")][0]
        self.assertIn('NEW."id" IS NULL THEN RETURN NEW', before)
        self.assertIn('IF was_present THEN NEW."' + P.names.version_column, before)
        self.assertNotIn("presence metadata expected absence", before)

    def test_quoted_identifier_delimiters_are_safe(self):
        p = PresencePointProfile('mtw_provenance_a" $mtw$', 't" AS $mtw$')
        self.assertIn('""', p.read_sql)
        functions = [s for s in presence_ddl(p.names) if s.startswith("CREATE FUNCTION ")]
        self.assertTrue(all("$mtw1$" in s for s in functions))

    def test_must_initialize_and_no_stable_jsonl_claim(self):
        s = PresenceCapture(P, keys=("a",))
        with self.assertRaises(ProvenanceError):
            s.wrap(Connection())
        with self.assertRaises(ValueError):
            PresenceCapture(P, keys=("a",), jsonl_path="not-created.jsonl")

    def test_initial_absences_are_explicit_locked_facts(self):
        s, _, _ = capture()
        d = s.document()
        self.assertEqual(d["traceSchema"], 2)
        self.assertEqual(d["presenceFacts"]["projection"], PROJECTION)
        self.assertEqual(len(d["presenceFacts"]["initial"]), 3)
        self.assertEqual(sum(x["present"] for x in d["presenceFacts"]["initial"]), 1)
        self.assertEqual({x["key"]: x["version"] for x in d["presenceFacts"]["initial"]}, d["events"][0]["initial"])

    def test_positive_read_delivered_once_and_surface_hidden(self):
        s, c, _ = capture()
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual((cursor.rowcount, cursor.statusmessage, cursor.rownumber), (1, "SELECT 1", 0))
        self.assertEqual([x.name for x in cursor.description], ["value"])
        self.assertEqual(ops(s), [])
        self.assertEqual(cursor.fetchone(), ("same",))
        self.assertEqual(cursor.rownumber, 1)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(len(s.document()["presenceFacts"]["reads"]), 1)
        self.assertTrue(s.document()["presenceFacts"]["reads"][0]["present"])

    def test_closed_read_cursor_metadata_matches_driver_reset(self):
        s, c, _ = capture()
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual(cursor.fetchone(), ("same",))
        cursor.close()
        self.assertEqual(cursor.rowcount, -1)
        self.assertIsNone(cursor.description)
        self.assertIsNone(cursor.statusmessage)
        self.assertIsNone(cursor.rownumber)
        with self.assertRaises(psycopg.InterfaceError):
            cursor.fetchone()

    def test_negative_read_only_after_actual_eof(self):
        s, c, _ = capture()
        cursor = c.execute(P.read_sql, ("new",))
        self.assertEqual((cursor.rowcount, cursor.statusmessage, cursor.rownumber), (0, "SELECT 0", 0))
        self.assertEqual(ops(s), [])
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(cursor.fetchall(), [])
        fact = s.document()["presenceFacts"]["reads"][0]
        self.assertFalse(fact["present"])
        self.assertEqual(fact["seq"], ops(s)[0]["seq"])
        self.assertEqual(len(ops(s)), 1)

    def test_unfetched_negative_result_is_not_a_read(self):
        s, c, _ = capture()
        cursor = c.execute(P.read_sql, ("new",))
        c.commit()
        self.assertEqual(ops(s), [])
        self.assertIn("unconsumed_result", {g["code"] for g in s.document()["gaps"]})
        self.assertIsNone(cursor.fetchone())

    def test_fetchmany_iteration_and_sizes(self):
        s, c, _ = capture()
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual(cursor.fetchmany(0), [("same",)])
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual(cursor.fetchmany(True), [("same",)])
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual(list(cursor), [("same",)])
        cursor = c.execute(P.read_sql, ("a",))
        self.assertEqual(cursor.fetchmany(-1), [])
        self.assertEqual(cursor.fetchone(), ("same",))

    def test_zero_arraysize_does_not_claim_eof_or_discard_pending_read(self):
        s, c, _ = capture()
        for key, expected in (("a", ("same",)), ("new", None)):
            cursor = c.execute(P.read_sql, (key,))
            cursor.arraysize = 0
            count = len(ops(s))
            self.assertEqual(cursor.fetchmany(0), [])
            self.assertEqual(len(ops(s)), count)
            self.assertEqual(cursor.fetchone(), expected)
            self.assertEqual(len(ops(s)), count + 1)

    def test_crud_tombstone_reinsert_and_repeated_values(self):
        s, c, _ = capture()
        for query, params in ((P.update_sql, ("same", "a")), (P.update_sql, ("same", "a")),
                              (P.delete_sql, ("a",)), (P.insert_sql, ("a", "same"))):
            cursor = c.execute(query, params)
            self.assertEqual(cursor.rowcount, 1)
            self.assertIsNone(cursor.description)
            self.assertIsNone(cursor.rownumber)
            for method in ("fetchone", "fetchmany", "fetchall"):
                with self.assertRaises(psycopg.ProgrammingError):
                    getattr(cursor, method)()
        c.commit()
        d = s.document()
        self.assertEqual(d["presenceFacts"]["reads"], [])
        writes = d["presenceFacts"]["writes"]
        self.assertEqual([x["action"] for x in writes], ["update", "update", "delete", "insert"])
        self.assertEqual(len({x["version"] for x in writes}), 4)
        for before, after in zip(writes, writes[1:]):
            self.assertEqual(before["version"], after["predecessor"])
        self.assertFalse(writes[2]["newPresent"])
        self.assertFalse(writes[3]["oldPresent"])
        self.assertEqual({x["seq"] for x in writes}, {x["seq"] for x in ops(s)})

    def test_rollback_preserves_evidence_but_restores_database(self):
        s, c, raw = capture()
        before = copy.deepcopy(raw.store)
        c.execute(P.delete_sql, ("a",))
        self.assertIsNone(c.execute(P.read_sql, ("a",)).fetchone())
        c.execute(P.insert_sql, ("a", "again"))
        c.rollback()
        self.assertEqual(raw.store, before)
        self.assertEqual(len(s.document()["presenceFacts"]["writes"]), 2)
        self.assertEqual(s.document()["events"][-1]["status"], "aborted")

    def test_zero_row_update_and_delete_are_gaps_not_fake_absence_reads(self):
        s, c, _ = capture()
        for query, params in ((P.update_sql, ("x", "never")), (P.delete_sql, ("never",))):
            cursor = c.execute(query, params)
            self.assertEqual(cursor.rowcount, 0)
        self.assertEqual(ops(s), [])
        self.assertIn("presence_write_unproven", {g["code"] for g in s.document()["gaps"]})

    def test_unknown_sql_and_custom_factory_run_original_with_gap(self):
        s, c, raw = capture()
        self.assertEqual(c.execute("SELECT 1").fetchone(), (1,))
        cursor = c.cursor(row_factory=dict_row)
        cursor.execute(P.read_sql, ("a",))
        self.assertEqual(raw.calls[-1][0], P.read_sql)
        self.assertTrue(s.document()["gaps"])

    def test_business_error_identity_and_unknown_commit(self):
        s, c, raw = capture()
        error = psycopg.errors.NotNullViolation("business failure")
        raw.execute_error = error
        with self.assertRaises(psycopg.errors.NotNullViolation) as caught:
            c.execute(P.update_sql, (None, "a"))
        self.assertIs(caught.exception, error)
        self.assertEqual(ops(s), [])
        raw.execute_error = None
        c.rollback()
        c.execute(P.update_sql, ("x", "a"))
        error = psycopg.OperationalError("unknown acknowledgement")
        raw.commit_error = error
        with self.assertRaises(psycopg.OperationalError) as caught:
            c.commit()
        self.assertIs(caught.exception, error)
        self.assertEqual(s.document()["events"][-1]["status"], "unknown")

    def test_failed_setup_commit_does_not_publish_initial_facts(self):
        s = PresenceCapture(P, keys=("a", "new"))
        raw = Connection(autocommit=True)
        raw.commit_error = psycopg.OperationalError("setup unknown")
        with patch("presence_profile.verify_presence_installation"), patch("presence_profile._business_columns"):
            with self.assertRaises(psycopg.OperationalError):
                s.initialize(raw)
        self.assertFalse(s._initialized)
        self.assertEqual(s.document()["presenceFacts"]["initial"], [])
        self.assertEqual(s.document()["events"], [])

    def test_fact_and_event_budget_fail_closed_without_orphan_fact(self):
        s, c, _ = capture(max_events=3)
        c.execute(P.update_sql, ("new", "a"))
        self.assertEqual(ops(s), [])
        self.assertEqual(s.document()["presenceFacts"]["writes"], [])
        self.assertIn("event_budget_exhausted", {g["code"] for g in s.document()["gaps"]})
        s, c, _ = capture()
        s._retained_bytes = s._max_session_bytes - 1025
        s._fact_event("read", tx="tx-test", key="key", token=str(uuid.uuid4()), present=False)
        self.assertEqual(s.document()["presenceFacts"]["reads"], [])
        self.assertTrue({"presence_fact_budget", "gap_budget_exhausted"}.intersection(g["code"] for g in s.document()["gaps"]))

    def test_same_snapshot_metadata_disagreement_rejected(self):
        token = str(uuid.uuid4())
        for row in ((False, None, token, True, None), (True, "v", token, True, str(uuid.uuid4())),
                    (False, None, None, False, None), (False, "v", token, False, None)):
            with self.assertRaises((ProvenanceError, ValueError)):
                _observation(row)

    def test_document_copy_does_not_mutate_retained_presence(self):
        s, c, _ = capture()
        c.execute(P.insert_sql, ("new", "x"))
        d = s.document()
        d["presenceFacts"]["writes"][0]["predecessor"] = "changed"
        self.assertNotEqual(s.document()["presenceFacts"]["writes"][0]["predecessor"], "changed")


if __name__ == "__main__":
    unittest.main()
