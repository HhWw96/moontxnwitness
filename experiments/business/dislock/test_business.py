"""Execute the frozen upstream helper against fake cursors, never a database."""
import datetime
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from business import (ARCHIVE_SHA256, COMMIT, HERE, LeaseClient, SourceIntegrityError,
                      load_upstream, make_capture, observed_sql, verify_sources)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False

    def execute(self, query, params):
        self.connection.calls.append((query.as_string(), params))
        if self.connection.error is not None:
            raise self.connection.error
        return self

    def fetchone(self):
        self.connection.fetches += 1
        return self.connection.row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        self.connection.closes += 1


class Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []
        self.fetches = self.closes = 0
        self.error = None

    def cursor(self):
        return Cursor(self)


class BusinessTests(unittest.TestCase):
    def test_factory_uses_exact_upstream_queries_and_needs_real_initialization(self):
        capture, client = make_capture(None, "mtw_provenance_unit", keys=("existing",), exclusive_writers=True)
        self.assertEqual(capture.profile.read_sql, client.read_query().as_string())
        self.assertEqual(capture.profile.write_sql, client.renew_query().as_string())
        self.assertEqual((capture.profile.read_columns, capture.profile.returning_columns,
                          capture.profile.write_key_parameter), (2, 1, 1))
        self.assertFalse(capture._initialized)
        self.assertEqual(capture.document()["events"], [])

    def test_archive_license_and_sources_match_pinned_commit(self):
        evidence = verify_sources()
        self.assertEqual(evidence["commit"], COMMIT)
        self.assertEqual(evidence["archiveSha256"], ARCHIVE_SHA256)
        self.assertEqual(evidence["license"], "MIT")
        self.assertEqual(len(evidence["files"]), 11)

    def test_modified_source_is_rejected_even_if_manifest_is_edited(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "upstream"
            shutil.copytree(HERE / "upstream", target)
            path = target / "source" / "dislock" / "core.py"
            path.write_bytes(path.read_bytes() + b"\n# changed\n")
            lock = json.loads((target / "lock.json").read_text())
            import hashlib
            lock["files"]["dislock/core.py"] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
            (target / "lock.json").write_text(json.dumps(lock))
            with self.assertRaises(SourceIntegrityError):
                verify_sources(target)

    def test_module_is_loaded_from_frozen_source_namespace(self):
        upstream = load_upstream()
        self.assertTrue(Path(upstream.core.__file__).resolve().is_relative_to((HERE / "upstream").resolve()))
        self.assertTrue(upstream.core.__name__.startswith("_mtw_frozen_dislock_" + COMMIT))
        self.assertIs(upstream.core, load_upstream().core)

    def test_original_read_returns_its_two_business_values_unchanged(self):
        client = LeaseClient("mtw_provenance_unit")
        row = (datetime.datetime.now(datetime.timezone.utc), "worker:1")
        conn = Connection(row)
        self.assertIs(client.read_current(conn, "cronjob-lock:lease:work"), row)
        self.assertEqual((conn.fetches, conn.closes), (1, 1))
        self.assertEqual(conn.calls[0][1], ("cronjob-lock:lease:work",))
        self.assertIn("SELECT expire_at, value", conn.calls[0][0])

    def test_real_upstream_renewal_keeps_owner_ttl_returning_and_bool(self):
        client = LeaseClient("mtw_provenance_unit")
        conn = Connection((datetime.datetime.now(datetime.timezone.utc),))
        self.assertIs(client.renew(conn, "cronjob-lock:lease:work", 90.5, "worker:1"), True)
        query, params = conn.calls[0]
        self.assertEqual(params, (90.5, "cronjob-lock:lease:work", "worker:1"))
        self.assertIn("NOW() + (%s * INTERVAL '1 second')", query)
        self.assertIn("AND value = %s", query)
        self.assertIn("RETURNING expire_at;", query)
        self.assertEqual((len(conn.calls), conn.fetches, conn.closes), (1, 1, 1))

    def test_failed_owner_guard_returns_false_without_fabricating_expiry(self):
        client = LeaseClient("mtw_provenance_unit")
        conn = Connection(None)
        self.assertIs(client.renew(conn, "existing", 60, "wrong-owner"), False)
        self.assertEqual(conn.calls[0][1], (60, "existing", "wrong-owner"))

    def test_upstream_business_exception_identity_is_preserved(self):
        client = LeaseClient("mtw_provenance_unit")
        conn = Connection(None)
        conn.error = ValueError("same exception object")
        with self.assertRaises(ValueError) as caught:
            client.renew(conn, "existing", 60, "worker:1")
        self.assertIs(caught.exception, conn.error)
        self.assertEqual(conn.closes, 1)

    def test_projection_edits_are_exactly_reversible(self):
        client = LeaseClient("mtw_provenance_unit")
        read, write = client.read_query().as_string(), client.renew_query().as_string()
        version = '"test_version"'
        a, b = observed_sql(read, write, version)
        self.assertEqual(a.replace("," + version + "::text", "", 1), read)
        self.assertEqual(b.replace(",OLD." + version + "::text,NEW." + version + "::text", "", 1), write)
        self.assertEqual(a.count("%s"), read.count("%s"))
        self.assertEqual(b.count("%s"), write.count("%s"))

    def test_projection_shape_drift_is_refused(self):
        with self.assertRaises(SourceIntegrityError):
            observed_sql("SELECT *", "UPDATE something", '"version"')

    def test_table_identifiers_are_quoted_by_the_real_upstream_builder(self):
        client = LeaseClient("mtw_provenance_unit", 'key"value')
        self.assertIn('"key""value"', client.read_query().as_string())
        self.assertIn('"key""value"', client.renew_query().as_string())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BusinessTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"suite": "frozen-dislock-business", "actualDatabaseExecution": False,
                      "tests": result.testsRun, "passed": result.wasSuccessful()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
