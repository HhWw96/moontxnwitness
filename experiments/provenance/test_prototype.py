"""Fast, database-free checks for the experimental provenance contracts."""
import dataclasses
import json
import unittest
import uuid

from prototype import (Installation, Names, Observation, ProvenanceError,
                       controlled_schema, ddl, function_body, identifier,
                       install, read_sql, verify_audit)


class ReadConnection:
    def __init__(self, row):
        self.row, self.calls = row, []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self.row


def installation(mode):
    names = Names("mtw_provenance_unit", "items", mode)
    token = str(uuid.uuid4())
    return Installation(names, str(uuid.uuid4()), 10, {"a": Observation("a", True, 7, token)})


def audit_fixture():
    tokens = [str(uuid.uuid4()) for _ in range(4)]
    rows = [
        {"token": tokens[0], "key": "a", "action": "initial", "present": True,
         "predecessor": None, "oldValue": None, "newValue": 7},
        {"token": tokens[1], "key": "a", "action": "UPDATE", "present": True,
         "predecessor": tokens[0], "oldValue": 7, "newValue": 7},
        {"token": tokens[2], "key": "a", "action": "DELETE", "present": False,
         "predecessor": tokens[1], "oldValue": 7, "newValue": None},
        {"token": tokens[3], "key": "a", "action": "INSERT", "present": True,
         "predecessor": tokens[2], "oldValue": None, "newValue": 7},
    ]
    return rows


class PrototypeTests(unittest.TestCase):
    def test_identifier_quotes_instead_of_interpolating_sql(self):
        self.assertEqual(identifier('a"; DROP SCHEMA public; --'), '"a""; DROP SCHEMA public; --"')
        for value in ("", "x\x00y", "x" * 64, "中" * 22, None):
            with self.assertRaises(ValueError):
                identifier(value)

    def test_only_explicit_controlled_schema_accepted(self):
        for schema in ("public", "pg_catalog", "information_schema", "other_app"):
            with self.assertRaises(ValueError):
                controlled_schema(schema)
        self.assertEqual(controlled_schema("mtw_provenance_local"), "mtw_provenance_local")

    def test_invalid_schema_cannot_send_any_ddl(self):
        connection = ReadConnection(None)
        with self.assertRaises(ValueError):
            install(connection, schema="public", table="accounts", mode="sidecar")
        self.assertEqual(connection.calls, [])

    def test_function_body_delimiter_cannot_be_injected_via_identifier(self):
        body = 'SELECT "x$mtw$$mtw1$";'
        quoted = function_body(body)
        self.assertTrue(quoted.startswith("$mtw2$\n"))
        self.assertTrue(quoted.endswith("\n$mtw2$"))
        self.assertEqual(quoted.count("$mtw2$"), 2)
        names = Names("mtw_provenance_unit", "items", "sidecar", key_column="id$mtw$")
        function = next(sql for sql in ddl(names) if sql.startswith("CREATE FUNCTION"))
        self.assertIn("AS $mtw1$", function)

    def test_names_deterministic_and_modes_cannot_collide(self):
        column = Names("mtw_provenance_unit", "items", "column")
        sidecar = Names("mtw_provenance_unit", "items", "sidecar")
        self.assertEqual(column.prefix, Names("mtw_provenance_unit", "items", "column").prefix)
        self.assertNotEqual(column.prefix, sidecar.prefix)
        with self.assertRaises(ValueError):
            Names("mtw_provenance_unit", "items", "unknown")

    def test_ddl_is_scoped_and_not_destructive_replacement(self):
        for mode in ("column", "sidecar"):
            names = Names("mtw_provenance_unit", "items", mode)
            statements = ddl(names)
            self.assertFalse(any("OR REPLACE" in sql or "CASCADE" in sql or "CREATE EXTENSION" in sql for sql in statements))
            self.assertTrue(all('"mtw_provenance_unit".' in sql for sql in statements))
            self.assertEqual(any(sql.startswith("ALTER TABLE") for sql in statements), mode == "column")
            self.assertTrue(any("DELETE" in sql and names.object("state") in sql for sql in statements))

    def test_positive_and_negative_column_read_are_single_statements(self):
        capture = installation("column")
        for row in ((True, 7, capture.initial["a"].token, None), (False, None, str(uuid.uuid4()), False)):
            connection = ReadConnection(row)
            observed = capture.observe(connection, "a")
            self.assertEqual(observed.exists, row[0])
            self.assertEqual(len(connection.calls), 1)
            self.assertEqual(connection.calls[0][1], ("a",))
            self.assertIn("LEFT JOIN", connection.calls[0][0])

    def test_sidecar_same_statement_presence_check(self):
        capture = installation("sidecar")
        self.assertTrue(capture.observe(ReadConnection((True, 7, str(uuid.uuid4()), True)), "a").exists)
        for row in ((True, 7, str(uuid.uuid4()), False), (False, None, str(uuid.uuid4()), None),
                    (False, None, None, None)):
            with self.assertRaises(ProvenanceError):
                capture.observe(ReadConnection(row), "a")

    def test_unknown_key_has_no_fabricated_initial_absence(self):
        capture = installation("column")
        connection = ReadConnection((False, None, None, None))
        with self.assertRaises(ProvenanceError):
            capture.observe(connection, "not-in-initial-scope")
        self.assertFalse(connection.calls)

    def test_audit_verifier_handles_repeated_value_delete_reinsert_without_order(self):
        rows = audit_fixture()
        self.assertEqual(verify_audit(list(reversed(rows)))["writes"], 3)

    def test_audit_verifier_rejects_duplicate_and_missing_cross_key_sources(self):
        rows = audit_fixture()
        with self.assertRaises(ProvenanceError):
            verify_audit(rows + [rows[0]])
        for change in ({"predecessor": str(uuid.uuid4())}, {"key": "different"}, {"oldValue": 9}):
            altered = [dict(row) for row in rows]
            altered[1].update(change)
            with self.assertRaises(ProvenanceError):
                verify_audit(altered)

    def test_audit_verifier_rejects_cycle_even_if_values_agree(self):
        left, right = str(uuid.uuid4()), str(uuid.uuid4())
        rows = [{"token": left, "key": "a", "action": "UPDATE", "present": True,
                 "predecessor": right, "oldValue": 7, "newValue": 7},
                {"token": right, "key": "a", "action": "UPDATE", "present": True,
                 "predecessor": left, "oldValue": 7, "newValue": 7}]
        with self.assertRaises(ProvenanceError):
            verify_audit(rows)

    def test_audit_verifier_rejects_multiple_initial_versions_and_forks(self):
        rows = audit_fixture()
        duplicate_initial = dict(rows[0], token=str(uuid.uuid4()))
        with self.assertRaises(ProvenanceError):
            verify_audit(rows + [duplicate_initial])
        fork = dict(rows[1], token=str(uuid.uuid4()))
        with self.assertRaises(ProvenanceError):
            verify_audit(rows + [fork])

    def test_read_query_never_uses_key_value_as_sql(self):
        capture = installation("sidecar")
        key = "'; DROP SCHEMA public; --"
        capture.initial[key] = Observation(key, False, None, str(uuid.uuid4()))
        connection = ReadConnection((False, None, capture.initial[key].token, False))
        capture.observe(connection, key)
        self.assertNotIn(key, connection.calls[0][0])
        self.assertEqual(connection.calls[0][1], (key,))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PrototypeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "provenance-prototype-unit", "tests": result.testsRun,
                      "passed": result.wasSuccessful(), "actualDatabaseExecution": False}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
