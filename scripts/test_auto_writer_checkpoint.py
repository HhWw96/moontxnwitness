"""The optional probe cannot replace the actual COMMIT response."""
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/python'))
from moontxnwitness_capture.configured_fetch import ConfiguredConnection
from moontxnwitness_capture.configured_session import ConfiguredPointWindow
from moontxnwitness_capture.instrumentation import DiagnosticConnection


class Tests(unittest.TestCase):
    def connection(self, *, enabled=True, tx='t1', status=2, callback=None):
        connection = object.__new__(ConfiguredConnection)
        connection._operation_lock = threading.RLock()
        connection._tx = tx
        connection._raw = SimpleNamespace(info=SimpleNamespace(transaction_status=status))
        self.gaps = []
        connection._session = SimpleNamespace(_enabled=enabled,
            gap=lambda *args: self.gaps.append(args))
        if callback is not None:
            connection._session._configured_before_commit = callback
        return connection

    def test_default_diagnostics_issue_no_probe(self):
        connection = self.connection()
        with patch.object(DiagnosticConnection, 'commit', return_value='actual') as commit:
            self.assertEqual(connection.commit(), 'actual')
        commit.assert_called_once()
        self.assertEqual(self.gaps, [])

    def test_probe_precedes_actual_commit_and_its_return_is_preserved(self):
        calls = []
        connection = self.connection(callback=lambda c: calls.append(('probe', c._tx)))
        with patch.object(DiagnosticConnection, 'commit', side_effect=lambda: calls.append('commit') or 123):
            self.assertEqual(connection.commit(), 123)
        self.assertEqual(calls, [('probe', 't1'), 'commit'])

    def test_default_path_preserves_original_call_and_lock_order(self):
        class PoisonLock:
            def __enter__(self):
                raise AssertionError('New lock acquired before inherited call observation')
            def __exit__(self, *args):
                pass
        for enabled, callback in ((True, None), (False, lambda c: None)):
            connection = self.connection(enabled=enabled, callback=callback)
            connection._operation_lock = PoisonLock()
            with patch.object(DiagnosticConnection, 'commit', return_value='original'):
                self.assertEqual(connection.commit(), 'original')

    def test_disabled_idle_and_aborted_transactions_are_not_probed(self):
        for arguments in ({'enabled': False}, {'tx': None}, {'status': 0}, {'status': 3}):
            calls = []
            connection = self.connection(callback=lambda c: calls.append(c), **arguments)
            with patch.object(DiagnosticConnection, 'commit', return_value=None) as commit:
                connection.commit()
            self.assertEqual(calls, [])
            commit.assert_called_once()

    def test_probe_failure_marks_gap_and_still_observes_commit(self):
        def fail(connection):
            raise OSError('source unavailable')
        connection = self.connection(callback=fail)
        with patch.object(DiagnosticConnection, 'commit', return_value='confirmed') as commit:
            self.assertEqual(connection.commit(), 'confirmed')
        commit.assert_called_once()
        self.assertEqual(self.gaps[0][0], 'configured_writer_checkpoint_missing')

    def test_commit_exception_is_the_original_object(self):
        error = ConnectionError('response lost')
        calls = []
        connection = self.connection(callback=lambda c: calls.append(c._tx))
        with patch.object(DiagnosticConnection, 'commit', side_effect=error):
            with self.assertRaises(ConnectionError) as actual:
                connection.commit()
        self.assertIs(actual.exception, error)
        self.assertEqual(calls, ['t1'])

    def test_probe_does_not_mutate_transaction_identity(self):
        seen = []
        connection = self.connection(callback=lambda c: seen.append(c._tx))
        with patch.object(DiagnosticConnection, 'commit', side_effect=lambda: seen.append(connection._tx)):
            connection.commit()
        self.assertEqual(seen, ['t1', 't1'])

    def test_cancellation_does_not_continue_to_commit(self):
        def cancel(connection):
            raise KeyboardInterrupt()
        connection = self.connection(callback=cancel)
        with patch.object(DiagnosticConnection, 'commit') as commit:
            with self.assertRaises(KeyboardInterrupt):
                connection.commit()
        commit.assert_not_called()

    def test_invalid_option_is_rejected_before_output_or_connection_use(self):
        for value in (None, 1, 'true', []):
            with self.assertRaisesRegex(ValueError, 'boolean checkpoint'):
                ConfiguredPointWindow(None, None, None, None, None,
                                      automatic_writer_checkpoints=value)


if __name__ == '__main__':
    unittest.main()
