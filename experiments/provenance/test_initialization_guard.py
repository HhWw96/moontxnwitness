"""Independent boundary cases over the isolated real profile initializers.

Catalog/result simulation only: no PostgreSQL connection or core build occurs.
"""
import itertools
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from capture_profile import ColumnCapture, ColumnPointProfile
from presence_profile import PresenceCapture, PresencePointProfile
from initialization_guard import bounded_keys, confirm_initial_commit
from prototype import ProvenanceError
from test_capture_profile import Connection as ColumnConnection, PROFILE
from test_presence_profile import Connection as PresenceConnection, P


class SecondaryInterrupt(BaseException):
    pass


class Counted:
    def __init__(self, values):
        self.values, self.reads, self.iterations = iter(values), 0, 0

    def __iter__(self):
        self.iterations += 1
        return self

    def __next__(self):
        self.reads += 1
        return next(self.values)


class AckMixin:
    """Only the COMMIT command produces the independently configurable ACK."""
    def execute(self, query, params=None, **kwargs):
        if query != "COMMIT":
            return super().execute(query, params, **kwargs)
        self.calls.append((query, params))
        self.commit()
        if getattr(self, "lost_ack", None) is not None:
            raise self.lost_ack
        self.info.transaction_status = getattr(self, "after_ack", 0)
        return SimpleNamespace(statusmessage=getattr(self, "ack_tag", "COMMIT"),
                               pgresult=SimpleNamespace(status=getattr(self, "ack_status", psycopg.pq.ExecStatus.COMMAND_OK)),
                               description=getattr(self, "ack_description", None))


class ColumnSetup(AckMixin, ColumnConnection):
    pass


class PresenceSetup(AckMixin, PresenceConnection):
    pass


def pair(kind):
    if kind == "column":
        return ColumnCapture(PROFILE, keys=("a", "b")), ColumnSetup(autocommit=True)
    return PresenceCapture(P, keys=("a", "new")), PresenceSetup(autocommit=True)


def catalog_mocks():
    stack = ExitStack()
    stack.enter_context(patch("capture_profile.verify_installation"))
    stack.enter_context(patch("presence_profile.verify_presence_installation"))
    stack.enter_context(patch("presence_profile._business_columns"))
    return stack


class KeyAdmissionTests(unittest.TestCase):
    def test_clean_import_remains_driver_optional(self):
        profiles = Path(__file__).resolve().parent
        integration = profiles.parents[1] / "integrations/python"
        command = ("import sys;sys.path[:0]=" + repr([str(profiles), str(integration)])
                   + ";import capture_profile,presence_profile,moontxnwitness_capture;"
                   + "assert 'psycopg' not in sys.modules;print('driver-optional')")
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", command],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "driver-optional"), result.stderr)

    def test_infinite_input_stops_at_first_overflow(self):
        values = Counted(str(i) for i in itertools.count())
        with self.assertRaises(ValueError):
            bounded_keys(values)
        self.assertEqual((values.reads, values.iterations), (65, 1))

    def test_exact_64_single_pass_values(self):
        values = Counted(str(i) for i in range(64))
        self.assertEqual(bounded_keys(values), tuple(str(i) for i in range(64)))
        self.assertEqual((values.reads, values.iterations), (65, 1))

    def test_65_keys_rejected_before_recorder_constructor(self):
        for capture, profile in [(ColumnCapture, PROFILE), (PresenceCapture, P)]:
            with self.subTest(capture=capture.__name__), patch("capture_profile.CaptureSession.__init__") as constructor:
                with self.assertRaises(ValueError):
                    capture(profile, keys=map(str, range(65)))
                constructor.assert_not_called()

    def test_bad_keys_before_recorder_or_file_creation(self):
        bad = [(), ("",), ("a", "a"), ([],), (True,), (1,), ("\ud800",),
               ("a" * 513,), ("😀" * 129,), ("x\x00y",), "abc", b"abc"]
        for values in bad:
            for capture, profile in [(ColumnCapture, PROFILE), (PresenceCapture, P)]:
                with self.subTest(values=repr(values), capture=capture.__name__), patch("capture_profile.CaptureSession.__init__") as constructor:
                    with self.assertRaises(ValueError):
                        capture(profile, keys=values)
                    constructor.assert_not_called()

    def test_utf8_boundary_and_no_unicode_normalization(self):
        self.assertEqual(bounded_keys(("a" * 512, "😀" * 128)), ("a" * 512, "😀" * 128))
        self.assertEqual(bounded_keys(("é", "e\u0301")), ("é", "e\u0301"))

    def test_iterable_failure_identity(self):
        error = RuntimeError("caller iterable failed")
        def values():
            yield "a"
            raise error
        with self.assertRaises(RuntimeError) as caught:
            bounded_keys(values())
        self.assertIs(caught.exception, error)

    def test_string_subclass_does_not_invoke_custom_hash(self):
        class UnexpectedText(str):
            def __hash__(self):
                raise AssertionError("untrusted hash")
        with self.assertRaises(ValueError):
            bounded_keys((UnexpectedText("a"),))


class InitializationTests(unittest.TestCase):
    def assert_unpublished(self, session):
        self.assertFalse(session._initialized)
        self.assertIsNone(session.installation)
        if isinstance(session, PresenceCapture):
            self.assertEqual(session.document()["presenceFacts"]["initial"], [])
        with self.assertRaises(ProvenanceError):
            session.wrap(ColumnConnection())

    def fail_and_retry(self, session, raw, error_type=ProvenanceError):
        with catalog_mocks(), self.assertRaises(error_type):
            session.initialize(raw)
        self.assert_unpublished(session)
        before = list(raw.calls)
        with self.assertRaises(ProvenanceError):
            session.initialize(raw)
        self.assertEqual(raw.calls, before)

    def test_only_confirmed_commit_publishes_both_profiles(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            seen = []
            original = session._publish_snapshot
            def publish(initial):
                seen.append((session._initialization_ack.copy(), raw.info.transaction_status))
                return original(initial)
            with self.subTest(kind=kind), catalog_mocks(), patch.object(session, "_publish_snapshot", side_effect=publish):
                session.initialize(raw)
            self.assertTrue(session._initialized)
            self.assertEqual(seen[0][1], 0)
            self.assertIs(seen[0][0]["actualCommitConfirmed"], True)
            self.assertEqual([sql for sql, _ in raw.calls].count("COMMIT"), 1)
            self.assertNotIn("initializationAck", session.document())

    def test_rollback_tag_even_idle_cannot_publish_or_retry(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            raw.ack_tag = "ROLLBACK"
            with self.subTest(kind=kind):
                self.fail_and_retry(session, raw)
                self.assertEqual(raw.info.transaction_status, 0)

    def test_non_command_result_rejected(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            raw.ack_status = psycopg.pq.ExecStatus.TUPLES_OK
            with self.subTest(kind=kind):
                self.fail_and_retry(session, raw)

    def test_boolean_status_not_command_ok(self):
        session, raw = pair("presence")
        raw.ack_status = True
        self.fail_and_retry(session, raw)

    def test_commit_result_rows_rejected_without_fetch(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            raw.ack_description = (object(),)
            with self.subTest(kind=kind):
                self.fail_and_retry(session, raw)

    def test_non_idle_after_commit_rejected(self):
        for after in (2, 3, 4):
            session, raw = pair("presence")
            raw.after_ack = after
            with self.subTest(after=after):
                self.fail_and_retry(session, raw)

    def test_missing_or_oversized_commit_tag_rejected(self):
        for tag in (None, "COMMIT " , "X" * 129):
            session, raw = pair("presence")
            raw.ack_tag = tag
            with self.subTest(tag=repr(tag)):
                self.fail_and_retry(session, raw)
                self.assertLessEqual(len(session._initialization_ack["commandTag"] or ""), 128)

    def test_missing_pgresult_is_not_confirmation(self):
        session, raw = pair("column")
        original = raw.execute
        def execute(sql, params=None):
            result = original(sql, params)
            if sql == "COMMIT":
                del result.pgresult
            return result
        with patch.object(raw, "execute", side_effect=execute):
            self.fail_and_retry(session, raw, AttributeError)

    def test_setup_commit_error_identity_and_retry_lock(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            error = psycopg.OperationalError("original setup COMMIT error")
            raw.commit_error = error
            with self.subTest(kind=kind), catalog_mocks(), self.assertRaises(psycopg.OperationalError) as caught:
                session.initialize(raw)
            self.assertIs(caught.exception, error)
            self.assert_unpublished(session)
            before = list(raw.calls)
            with self.assertRaises(ProvenanceError):
                session.initialize(raw)
            self.assertEqual(raw.calls, before)

    def test_lost_ack_after_commit_cannot_be_healed_by_rollback(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            raw.lost_ack = psycopg.OperationalError("simulated discarded COMMIT reply")
            with self.subTest(kind=kind), catalog_mocks(), self.assertRaises(psycopg.OperationalError) as caught:
                session.initialize(raw)
            self.assertIs(caught.exception, raw.lost_ack)
            self.assertEqual(raw.info.transaction_status, 0)
            self.assert_unpublished(session)
            self.assertIsNone(session._initialization_ack)
            before = list(raw.calls)
            raw.lost_ack = None
            with self.assertRaises(ProvenanceError):
                session.initialize(raw)
            self.assertEqual(raw.calls, before)

    def test_secondary_gap_and_rollback_baseexceptions_do_not_mask_driver(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            error = psycopg.OperationalError("retain exact original error")
            raw.commit_error = error
            with self.subTest(kind=kind), catalog_mocks(), patch.object(session, "gap", side_effect=SecondaryInterrupt()), patch.object(raw, "rollback", side_effect=SecondaryInterrupt()):
                with self.assertRaises(psycopg.OperationalError) as caught:
                    session.initialize(raw)
            self.assertIs(caught.exception, error)
            self.assert_unpublished(session)
            self.assertTrue(session._initialization_failed)

    def test_catalog_exception_identity_despite_cleanup_failure(self):
        for kind, target in [("column", "capture_profile.verify_installation"),
                             ("presence", "presence_profile.verify_presence_installation")]:
            session, raw = pair(kind)
            error = RuntimeError("exact catalog error")
            with self.subTest(kind=kind), catalog_mocks(), patch(target, side_effect=error), patch.object(session, "gap", side_effect=SecondaryInterrupt()), patch.object(raw, "rollback", side_effect=SecondaryInterrupt()):
                with self.assertRaises(RuntimeError) as caught:
                    session.initialize(raw)
            self.assertIs(caught.exception, error)
            self.assert_unpublished(session)

    def test_snapshot_cannot_publish_before_commit_confirmation(self):
        for kind in ("column", "presence"):
            session, _ = pair(kind)
            with self.subTest(kind=kind), self.assertRaises(ProvenanceError):
                session._publish_snapshot({"forged": str(uuid.uuid4())})
            self.assert_unpublished(session)

    def test_snapshot_omission_after_ack_still_refuses_wrapping(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            with self.subTest(kind=kind), patch.object(session, "_event", return_value=None):
                self.fail_and_retry(session, raw)
            self.assertIs(session._initialization_ack["actualCommitConfirmed"], True)

    def test_snapshot_log_fault_after_ack_still_refuses_wrapping(self):
        session, raw = pair("presence")
        original = session._event
        def lose_log(*args, **kwargs):
            original(*args, **kwargs)
            session._log_failed = True
        with patch.object(session, "_event", side_effect=lose_log):
            self.fail_and_retry(session, raw)

    def test_closed_or_gapped_recorder_sends_no_setup_sql(self):
        for closed in (True, False):
            session, raw = pair("presence")
            if closed:
                session.close()
            else:
                session.gap("prior_gap", "No trustworthy initialization")
            with self.subTest(closed=closed), self.assertRaises(ProvenanceError):
                session.initialize(raw)
            self.assertEqual(raw.calls, [])
            self.assert_unpublished(session)

    def test_failed_setup_validation_cannot_retry(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            raw.row_factory = dict_row
            with self.subTest(kind=kind):
                self.fail_and_retry(session, raw)
                self.assertEqual(raw.calls, [])

    def test_concurrent_initialization_attempt_is_rejected_without_sql(self):
        session, raw = pair("column")
        entered, proceed = threading.Event(), threading.Event()
        errors = []
        def verify(*args):
            entered.set()
            if not proceed.wait(5):
                raise RuntimeError("test barrier timed out")
        def worker():
            try:
                session.initialize(raw)
            except BaseException as error:
                errors.append(error)
        with patch("capture_profile.verify_installation", side_effect=verify):
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                other = ColumnSetup(autocommit=True)
                with self.assertRaises(ProvenanceError):
                    session.initialize(other)
                self.assertEqual(other.calls, [])
            finally:
                proceed.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(session._initialized)

    def test_initial_scan_sql_has_bounded_limit(self):
        for kind in ("column", "presence"):
            session, raw = pair(kind)
            with self.subTest(kind=kind), catalog_mocks():
                session.initialize(raw)
            scans = [sql for sql, _ in raw.calls if sql.startswith('SELECT "id"')]
            self.assertTrue(scans)
            self.assertTrue(all("LIMIT 65" in sql for sql in scans))

    def test_commit_before_status_must_be_intrans(self):
        for before in (0, 1, 3, 4):
            session, raw = pair("column")
            raw.info.transaction_status = before
            with self.subTest(before=before), self.assertRaises(ProvenanceError):
                confirm_initial_commit(session, raw)
            self.assertIs(session._initialization_ack["actualCommitConfirmed"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
