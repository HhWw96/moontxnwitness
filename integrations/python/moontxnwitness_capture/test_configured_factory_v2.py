"""Local-factory admission/lifecycle tests; fake connections, no database."""
import asyncio
import functools
import inspect
import json
import os
from pathlib import Path
import threading
import tempfile
import types
import unittest
from unittest.mock import patch

from . import configured_factory_v2 as gate
from .configured_point_capture_v2 import PointCaptureV2
from .configured_window_v2 import ConfiguredCaptureWindowV2
from .instrumentation import DiagnosticConnection, Instrumentation
from .configured_fetch import ConfiguredInstrumentation
from .journal_v3 import JournalIOError, JournalReader
from . import journal_v3


class Raw:
    def __init__(self, *, close_error=None, closed=False):
        self.close_error = close_error
        self.close_calls = 0
        self.closed = closed

    def close(self):
        self.close_calls += 1
        if self.close_error:
            raise self.close_error
        self.closed = True


class Observer:
    def __init__(self, *, wrap_error=None, gap_error=None):
        self.wrap_error, self.gap_error = wrap_error, gap_error
        self.wrapped, self.gaps = [], []

    def wrap(self, raw):
        if self.wrap_error:
            raise self.wrap_error
        result = types.SimpleNamespace(_raw=raw)
        self.wrapped.append(result)
        return result

    def gap(self, code, message):
        if self.gap_error:
            raise self.gap_error
        if (code, message) not in self.gaps:
            self.gaps.append((code, message))


def window(observer=None):
    value = object.__new__(ConfiguredCaptureWindowV2)
    value._lock = threading.RLock()
    value._state = 'open'
    value._participants = []
    value._pending_factories = 0
    value._factory_observation_failed = False
    value.control = Raw()
    value.observer = observer or Observer()
    return value


def point(observer=None):
    observer = observer or Observer()
    value = object.__new__(PointCaptureV2)
    value.wrap, value.gap = observer.wrap, observer.gap
    return value, observer


class FactoryTests(unittest.TestCase):
    def test_async_function_and_partial_refused_at_configuration(self):
        calls = []
        async def factory(*args):
            calls.append(args)
        for original in (factory, functools.partial(factory, 'bound')):
            with self.subTest(original=type(original).__name__):
                with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
                    window().psycopg_factory(original)
                capture, _ = point()
                with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
                    capture.psycopg_factory(original)
        self.assertEqual(calls, [])

    def test_async_callable_object_and_async_generator_refused(self):
        class Factory:
            async def __call__(self):
                raise AssertionError('must not execute')
        async def generated():
            yield Raw()
        for original in (Factory(), generated):
            with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
                window().psycopg_factory(original)

    def test_sync_mode_requires_callable_and_boolean_false(self):
        capture, _ = point()
        for value in (True, None, 0, 'false'):
            with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
                capture.psycopg_factory(lambda: Raw(), asynchronous=value)
        with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
            window().psycopg_factory(None)

    def test_hidden_coroutine_rejected_without_running_or_closing_it(self):
        calls = []
        async def original():
            calls.append('ran')
            return Raw()
        raw = original()
        self.addCleanup(raw.close)  # Caller, not the adapter, owns async cleanup.
        value = window()
        with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
            value.psycopg_factory(lambda: raw)()
        self.assertEqual(inspect.getcoroutinestate(raw), inspect.CORO_CREATED)
        self.assertEqual(calls, [])
        self.assertEqual(value.observer.wrapped, [])
        self.assertEqual(value._pending_factories, 0)
        self.assertEqual(value.observer.gaps, [(gate.FACTORY_GAP_CODE, gate.FACTORY_GAP_MESSAGE)])

    def test_custom_awaitable_never_awaited_or_closed(self):
        calls = []
        class Awaitable:
            def __await__(self):
                calls.append('awaited')
                yield
            def close(self):
                calls.append('closed')
        raw = Awaitable()
        capture, observer = point()
        with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
            capture.psycopg_factory(lambda: raw)()
        self.assertEqual(calls, [])
        self.assertEqual(observer.wrapped, [])

    def test_scheduled_future_is_not_cancelled(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        raw = loop.create_future()
        self.addCleanup(raw.cancel)
        with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
            window().psycopg_factory(lambda: raw)()
        self.assertFalse(raw.done())
        self.assertFalse(raw.cancelled())

    def test_async_connection_and_context_lease_methods_are_not_invoked(self):
        calls = []
        class AsyncConnection:
            async def execute(self):
                calls.append('execute')
            async def close(self):
                calls.append('close')
        class Lease:
            async def __aenter__(self):
                calls.append('enter')
            async def __aexit__(self, *args):
                calls.append('exit')
            def close(self):
                calls.append('lease-close')
        for raw in (AsyncConnection(), Lease()):
            with self.assertRaises(gate.UnsupportedConfiguredFactoryV2):
                window().psycopg_factory(lambda: raw)()
        self.assertEqual(calls, [])

    def test_factory_arguments_identity_result_and_order_are_preserved(self):
        raw, token, calls = Raw(), object(), []
        def original(*args, **kwargs):
            calls.append((args, kwargs))
            return raw
        value = window()
        result = value.psycopg_factory(original)(token, password='private-not-recorded')
        self.assertIs(result._raw, raw)
        self.assertEqual(calls, [((token,), {'password': 'private-not-recorded'})])
        self.assertEqual(value._participants, [result])
        self.assertEqual(raw.close_calls, 0)
        self.assertEqual(value._pending_factories, 0)
        self.assertEqual(value.observer.gaps, [])

    def test_factory_exception_identity_and_fixed_gap_are_preserved(self):
        error = RuntimeError('private-dsn-and-password')
        def original():
            raise error
        value = window()
        with self.assertRaises(RuntimeError) as caught:
            value.psycopg_factory(original)()
        self.assertIs(caught.exception, error)
        self.assertEqual(value._pending_factories, 0)
        self.assertNotIn('private', repr(value.observer.gaps))
        self.assertEqual(value.observer.gaps, [(gate.FACTORY_GAP_CODE, gate.FACTORY_GAP_MESSAGE)])

    def test_window_cleanup_failure_does_not_replace_admission_exception(self):
        error = ValueError('admission failed')
        raw = Raw(close_error=RuntimeError('cleanup failed'))
        value = window(Observer(wrap_error=error))
        with self.assertRaises(ValueError) as caught:
            value.psycopg_factory(lambda: raw)()
        self.assertIs(caught.exception, error)
        self.assertEqual(raw.close_calls, 1)
        self.assertEqual(value._pending_factories, 0)

    def test_point_cleanup_failure_does_not_replace_admission_exception(self):
        error = ValueError('point admission failed')
        raw = Raw(close_error=RuntimeError('cleanup failed'))
        capture, _ = point(Observer(wrap_error=error))
        with self.assertRaises(ValueError) as caught:
            capture.psycopg_factory(lambda: raw)()
        self.assertIs(caught.exception, error)
        self.assertEqual(raw.close_calls, 1)

    def test_dedicated_control_is_never_closed_on_rejected_enrollment(self):
        value = window()
        with self.assertRaises(ValueError):
            value.psycopg_factory(lambda: value.control)()
        self.assertEqual(value.control.close_calls, 0)
        self.assertFalse(value.control.closed)
        self.assertEqual(value._pending_factories, 0)

    def test_foreign_observer_wrapper_is_not_closed(self):
        raw = object.__new__(DiagnosticConnection)
        calls = []
        object.__setattr__(raw, '_raw', Raw())
        object.__setattr__(raw, 'close', lambda: calls.append('closed'))
        error = ValueError('foreign observer')
        for capture in (window(Observer(wrap_error=error)), point(Observer(wrap_error=error))[0]):
            with self.assertRaises(ValueError) as caught:
                capture.psycopg_factory(lambda: raw)()
            self.assertIs(caught.exception, error)
        self.assertEqual(calls, [])

    def test_original_base_exception_survives_cleanup_and_gap_failures(self):
        error = KeyboardInterrupt('stop')
        raw = Raw(close_error=RuntimeError('cleanup failed'))
        value = window(Observer(wrap_error=error, gap_error=OSError('journal unavailable')))
        with self.assertRaises(KeyboardInterrupt) as caught:
            value.psycopg_factory(lambda: raw)()
        self.assertIs(caught.exception, error)
        self.assertTrue(value._factory_observation_failed)
        with self.assertRaisesRegex(ValueError, 'observation was not retained'):
            value.seal()

    def test_closed_window_factory_rejects_before_invoking_user_function(self):
        calls = []
        value = window()
        connect = value.psycopg_factory(lambda: calls.append('called'))
        for state in ('opening', 'sealing', 'sealed', 'failed'):
            value._state = state
            with self.assertRaisesRegex(ValueError, 'must be open'):
                connect()
        self.assertEqual(calls, [])
        self.assertEqual(value._pending_factories, 0)

    def test_inflight_factory_budget_refuses_before_invocation(self):
        value, calls = window(), []
        value._pending_factories = 32
        with self.assertRaisesRegex(ValueError, 'factory budget'):
            value.psycopg_factory(lambda: calls.append('called'))()
        self.assertEqual(calls, [])
        self.assertEqual(value._pending_factories, 32)

    def test_seal_cannot_race_an_unfinished_factory(self):
        value = window()
        value._participants = [types.SimpleNamespace(_raw=Raw(closed=True))]
        value._snapshot = lambda side: self.fail('seal must not access database while factory is pending')
        entered, release = threading.Event(), threading.Event()
        results, errors, raw = [], [], Raw()
        def original():
            entered.set()
            if not release.wait(5):
                raise AssertionError('test factory release not signalled')
            return raw
        def run():
            try:
                results.append(value.psycopg_factory(original)())
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(value._pending_factories, 1)
            with self.assertRaisesRegex(ValueError, 'all local factory calls'):
                value.seal()
            self.assertEqual(value._state, 'open')
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertIs(results[0]._raw, raw)
        self.assertEqual(value._pending_factories, 0)
        self.assertEqual(len(value._participants), 2)

    def test_repeated_failed_factories_use_one_bounded_gap_message(self):
        value = window(Observer(wrap_error=ValueError('not observed')))
        for _ in range(12):
            with self.assertRaises(ValueError):
                value.psycopg_factory(Raw)()
        self.assertEqual(len(value.observer.gaps), 1)
        self.assertEqual(value._pending_factories, 0)


class FactoryJournalTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('MTW_JOURNAL_TEST_ROOT', str(Path.cwd() / 'artifacts/factory-v2-unit')))
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def observer(self):
        observer = Instrumentation(self.root / 'capture')
        def close():
            try:
                observer.close()
            except BaseException:
                pass
        self.addCleanup(close)
        observer.flush()
        return observer

    def test_silent_journal_gap_loss_is_retained_in_actual_diagnostic_export(self):
        observer = self.observer()
        with patch.object(observer.journal, '_gap', return_value=None):
            self.assertTrue(gate.record_factory_gap_v2(observer))
        observer.close()
        stored = JournalReader(observer.journal.path).verify()
        self.assertTrue(stored.valid)
        self.assertFalse(any(item['code'] == gate.FACTORY_GAP_CODE for item in stored.gaps))
        trace = self.root / 'diagnostic.json'
        receipt = observer.export_diagnostic(trace)
        self.assertFalse(receipt['complete'])
        data = json.loads(trace.read_text(encoding='utf8'))
        gaps = [item for item in data['gaps'] if item['code'] == gate.FACTORY_GAP_CODE]
        self.assertEqual(gaps, [{'code': gate.FACTORY_GAP_CODE, 'message': gate.FACTORY_GAP_MESSAGE}])

    def test_real_writer_io_failure_and_nonthrowing_gap_cannot_seal_success(self):
        observer = self.observer()
        with patch.object(observer.journal, '_write_line', side_effect=OSError('injected journal disk failure')):
            observer.emit('snapshot', initial={}, consistent=False)
            with self.assertRaises(JournalIOError):
                observer.flush()
        # gap() records in memory but intentionally does not synchronously fail
        # merely because the asynchronous writer already holds an IO error.
        self.assertTrue(gate.record_factory_gap_v2(observer))
        self.assertTrue(any(item['code'] == gate.FACTORY_GAP_CODE for item in observer.gaps))
        observer.frame = types.MethodType(ConfiguredInstrumentation.frame, observer)
        value = window(observer)
        value.output = self.root / 'window'
        value.output.mkdir()
        value._participants = [types.SimpleNamespace(_raw=Raw(closed=True))]
        # This test exercises persistence/publication, with no database snapshot.
        value._snapshot = lambda side: setattr(value, '_end_digest', '0' * 64)
        with self.assertRaises(JournalIOError):
            value.seal()
        self.assertEqual(value._state, 'failed')
        self.assertTrue((value.output / 'window-failure.json').is_file())
        self.assertFalse((value.output / 'window-receipt.json').exists())
        self.assertFalse((value.output / 'configured-window-input.json').exists())

    def writer_failure_schedule(self, *, finished):
        observer = self.observer()
        journal = observer.journal
        original_error = OSError('deterministic writer IO failure')
        reached, release = threading.Event(), threading.Event()
        original_json = journal_v3._json
        def marker_json(value):
            if isinstance(value, dict) and value.get('code') == 'journal_write_failed':
                reached.set()
                if not release.wait(5):
                    raise AssertionError('failure marker release was not signalled')
            return original_json(value)
        try:
            with patch.object(journal, '_write_line', side_effect=original_error), patch.object(journal_v3, '_json', marker_json):
                observer.emit('snapshot', initial={}, consistent=False)
                with self.assertRaises(JournalIOError) as flushed:
                    observer.flush()
                self.assertIs(flushed.exception.__cause__, original_error)
                self.assertTrue(reached.wait(5))
                self.assertIs(journal._error, original_error)
                if finished:
                    release.set()
                    journal._thread.join(5)
                    self.assertFalse(journal._thread.is_alive())
                    self.assertTrue(journal._closed)
                else:
                    self.assertFalse(journal._closed)
                    self.assertTrue(journal._thread.is_alive())
                with self.assertRaises(JournalIOError) as references:
                    journal.set_references(active_transactions=['tx:retained'])
                self.assertIs(references.exception.__cause__, original_error)
                self.assertEqual(journal._refs['activeTransactions'], [])
                with self.assertRaises(JournalIOError) as checkpoint:
                    journal.checkpoint(source_closed=True)
                self.assertIs(checkpoint.exception.__cause__, original_error)
                with self.assertRaises(JournalIOError) as closed:
                    observer.close()
                self.assertIs(closed.exception.__cause__, original_error)
                self.assertIs(observer._close_error, closed.exception)
                with self.assertRaises(JournalIOError) as repeated:
                    observer.close()
                self.assertIs(repeated.exception, closed.exception)
                # Failed reference publication cannot release the durable lock
                # or turn an unsuccessful writer into a complete source window.
                self.assertTrue((journal.path / journal_v3.LOCK).is_file())
        finally:
            release.set()
            journal._thread.join(5)
            self.assertFalse(journal._thread.is_alive())

    def test_writer_io_cause_survives_before_finally_marks_closed(self):
        self.writer_failure_schedule(finished=False)

    def test_writer_io_cause_survives_after_finally_marks_closed(self):
        self.writer_failure_schedule(finished=True)

    def test_healthy_reference_argument_failure_remains_retryable(self):
        observer = self.observer()
        original_error = ValueError('reference validation failed')
        with patch.object(observer.journal, 'set_references', side_effect=original_error):
            with self.assertRaises(ValueError) as caught:
                observer.close()
        self.assertIs(caught.exception, original_error)
        self.assertFalse(observer._closed)
        self.assertIsNone(observer._close_error)
        observer.close()
        self.assertTrue(observer._closed)
        self.assertIsNone(observer._close_error)


if __name__ == '__main__':
    unittest.main(verbosity=2)
