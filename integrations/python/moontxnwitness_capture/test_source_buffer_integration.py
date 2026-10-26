"""Source-buffer integration boundaries: real local files and fake profiles; no DB."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import types
import unittest
from unittest import mock
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture import source_sink as source
from moontxnwitness_capture import _orm_source_sink as legacy
from moontxnwitness_capture.instrumentation import Instrumentation, instrument_engine, instrument_psycopg
from moontxnwitness_capture.profiles import fastapi_users as users, model_profile as models
from moontxnwitness_capture.profiles.orm_control import ControlConnection

BASE = Path(os.environ.get('MTW_JOURNAL_TEST_ROOT', str(Path.cwd() / 'artifacts/source-buffer-integration')))
RUN = BASE / ('source-buffer-integration-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)
SIZES = (0, 128, 65536, 262144)
FILE_IO_EXECUTED = False
FAULT_COMBINATIONS = []
WATERMARK_SIZES = []


class Tests(unittest.TestCase):
    def setUp(self):
        self.sinks = []

    def sink(self, size=65536):
        global FILE_IO_EXECUTED
        path = RUN / (self.id().split('.')[-1] + '-' + uuid.uuid4().hex + '.jsonl')
        sink = source.GroupedSourceSink(path, write_buffer_bytes=size, flush_interval=60, flush_bytes=1024*1024)
        self.sinks.append(sink)
        FILE_IO_EXECUTED = True
        sink.flush()
        return sink

    def tearDown(self):
        for sink in self.sinks:
            try:
                sink.close()
            except source.SourceSinkError:
                pass

    def test_buffered_file_write_counter_does_not_acknowledge_persistence(self):
        sink = self.sink()
        before_size = sink.path.stat().st_size
        before_durable = sink.stats['durableRecords']
        before_written = sink.stats['bytesWritten']
        result = sink.append({'kind': 'source-batch', 'value': 'buffered tail'})
        self.assertTrue(result.accepted)
        with sink._cv:
            self.assertTrue(sink._cv.wait_for(lambda: sink._written_seq == result.source_seq, timeout=2))
            self.assertEqual(sink.stats['acceptedRecords'], result.source_seq)
            self.assertGreater(sink.stats['bytesWritten'], before_written)
            self.assertEqual(sink.stats['durableRecords'], before_durable)
            self.assertEqual(sink._durable_seq, before_durable)
        self.assertEqual(result.durable_seq, before_durable)
        self.assertEqual(sink.path.stat().st_size, before_size)
        self.assertGreaterEqual(sink.flush(), result.source_seq)
        self.assertGreater(sink.path.stat().st_size, before_size)

    def test_explicit_flush_reaches_target_after_partial_generation_with_each_buffer(self):
        for size in SIZES:
            with self.subTest(bufferBytes=size):
                sink = self.sink(size)
                entered, release, done = threading.Event(), threading.Event(), threading.Event()
                original = sink._file
                class Gate:
                    def write(self, line):
                        if not entered.is_set():
                            entered.set()
                            if not release.wait(3):
                                raise OSError('test source write gate timeout')
                        return original.write(line)
                    def __getattr__(self, name):
                        return getattr(original, name)
                sink._file = Gate()
                sink.append({'kind': 'source-batch', 'n': 1})
                self.assertTrue(entered.wait(1))
                target = sink.append({'kind': 'source-batch', 'n': 2}).source_seq
                results, errors = [], []
                def flush():
                    try:
                        results.append(sink.flush())
                    except BaseException as error:
                        errors.append(error)
                    finally:
                        done.set()
                thread = threading.Thread(target=flush)
                thread.start()
                try:
                    with sink._cv:
                        self.assertTrue(sink._cv.wait_for(lambda: sink._flush_target_seq == target, timeout=1))
                    release.set()
                    self.assertTrue(done.wait(2), 'flush must reach its target without waiting for the 60s timer')
                    self.assertEqual(errors, [])
                    self.assertGreaterEqual(results[0], target)
                finally:
                    release.set()
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertTrue(sink.close()['storageSealed'])
                WATERMARK_SIZES.append(size)

    def test_source_sync_failure_matrix_preserves_prefix_and_guards(self):
        for size in SIZES:
            for phase in ('data-fsync', 'index-replace', 'directory-sync'):
                with self.subTest(bufferBytes=size, phase=phase):
                    sink = self.sink(size)
                    previous = sink._durable_seq
                    self.assertTrue(sink.append({'kind': 'source-batch', 'value': phase}).accepted)
                    if phase == 'data-fsync':
                        descriptor, original = sink._file.fileno(), source.os.fsync
                        def fail(target):
                            if target == descriptor:
                                raise OSError(28, 'injected source data fsync failure')
                            return original(target)
                        context = mock.patch.object(source.os, 'fsync', fail)
                    elif phase == 'index-replace':
                        context = mock.patch.object(source.os, 'replace', side_effect=OSError(28, 'injected index replacement failure'))
                    else:
                        context = mock.patch.object(source, '_sync_directory', side_effect=OSError(28, 'injected directory sync failure'))
                    with context, self.assertRaises(source.SourceSinkError):
                        sink.flush()
                    self.assertEqual(sink._durable_seq, previous)
                    self.assertIn('source_write_failed', sink._gaps)
                    self.assertTrue(sink.lock_path.exists())
                    with self.assertRaises(source.SourceSinkError):
                        sink.close()
                    with self.assertRaises(source.SourceSinkError):
                        source.verify_grouped_source(sink.path)
                    FAULT_COMBINATIONS.append({'bufferBytes': size, 'phase': phase})

    def test_file_close_error_propagates_and_prevents_a_sealed_result(self):
        sink = self.sink()
        original = sink._file
        injected = OSError('injected buffered file close failure')
        class BadClose:
            def close(self):
                original.close()
                raise injected
            def __getattr__(self, name):
                return getattr(original, name)
        sink._file = BadClose()
        self.assertTrue(sink.append({'kind': 'source-batch', 'value': 1}).accepted)
        with self.assertRaises(source.SourceSinkError) as caught:
            sink.close()
        self.assertIs(caught.exception.__cause__, injected)
        self.assertTrue(sink.lock_path.exists())
        self.assertTrue(sink.failure_path.exists())
        self.assertFalse(json.loads(sink.index.read_bytes())['closed'])
        with self.assertRaises(source.SourceSinkError):
            source.verify_grouped_source(sink.path)
        with self.assertRaises(source.SourceSinkError) as repeated:
            sink.close()
        self.assertIs(repeated.exception.__cause__, injected)

    def test_final_closed_index_failure_propagates_after_data_close(self):
        sink = self.sink()
        original = sink._persist_index
        injected = OSError('injected final sealed index failure')
        def persist(closed):
            if closed:
                raise injected
            return original(closed)
        with mock.patch.object(sink, '_persist_index', persist):
            with self.assertRaises(source.SourceSinkError) as caught:
                sink.close()
        self.assertIs(caught.exception.__cause__, injected)
        self.assertTrue(sink._file.closed)
        self.assertTrue(sink.lock_path.exists())
        self.assertFalse(json.loads(sink.index.read_bytes())['closed'])
        with self.assertRaises(source.SourceSinkError):
            source.verify_grouped_source(sink.path)

    def test_legacy_append_still_waits_for_actual_file_fsync(self):
        path = RUN / ('legacy-' + uuid.uuid4().hex + '.jsonl')
        sink = legacy.SourceSink(path)
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        descriptor, original = sink._file.fileno(), legacy.os.fsync
        errors, results = [], []
        def gated(target):
            if target == descriptor:
                entered.set()
                if not release.wait(3):
                    raise OSError('test legacy fsync gate timeout')
            return original(target)
        def append():
            try:
                results.append(sink.append({'kind': 'source-batch', 'value': 1}))
            except BaseException as error:
                errors.append(error)
            finally:
                done.set()
        thread = threading.Thread(target=append)
        try:
            with mock.patch.object(legacy.os, 'fsync', gated):
                thread.start()
                try:
                    self.assertTrue(entered.wait(2))
                    self.assertFalse(done.is_set(), 'legacy append must wait for the actual fsync')
                finally:
                    release.set()
                    thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [2])
        finally:
            release.set()
            sink.close()
        self.assertEqual(legacy.verify(path)['records'], 3)

    def test_diagnostic_engine_rejects_source_buffer_before_resource_allocation(self):
        path = RUN / ('engine-' + uuid.uuid4().hex)
        with mock.patch.object(Instrumentation, 'attach_engine') as attach:
            with self.assertRaises(TypeError):
                instrument_engine(object(), path, write_buffer_bytes=65536)
        attach.assert_not_called()
        self.assertFalse(path.exists())

    def test_local_connection_entry_rejects_source_buffer_before_resource_allocation(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                path = RUN / ('factory-' + uuid.uuid4().hex)
                factory = mock.Mock()
                with self.assertRaises(TypeError):
                    instrument_psycopg(factory, path, asynchronous=asynchronous, write_buffer_bytes=65536)
                factory.assert_not_called()
                self.assertFalse(path.exists())

    def test_local_connection_factory_does_not_silently_configure_source_storage(self):
        path = RUN / ('factory-default-' + uuid.uuid4().hex)
        raw, calls = object(), []
        def factory(*args, **kwargs):
            calls.append((args, kwargs))
            return raw
        observer, connect = instrument_psycopg(factory, path)
        try:
            self.assertEqual(calls, [])
            with mock.patch.object(observer, 'wrap', return_value=raw):
                self.assertIs(connect('fixture-only', application_name='unit'), raw)
            self.assertEqual(calls, [(('fixture-only',), {'application_name': 'unit'})])
            self.assertFalse(hasattr(observer, 'sink'))
            self.assertFalse(any(path.rglob('sources.jsonl')))
        finally:
            observer.close()

    def profile_stub(self, cls):
        capture = cls.__new__(cls)
        capture._closed = capture._profile_finalized = False
        capture._lock = threading.RLock()
        capture._connections, capture._borrowed = [], set()
        capture._factory_attached = True
        capture._quiescing = False
        capture.sink = mock.Mock()
        capture.sink.append.return_value = source.SourceAppendResult(True, 1, 0)
        capture.note = mock.Mock()
        capture.gap = mock.Mock()
        capture.installation = types.SimpleNamespace(nonce='unit') if cls is users.UserProfileCapture else {'nonce': 'unit'}
        capture.scope = object()
        control = ControlConnection.__new__(ControlConnection)
        control.sink = capture.sink
        return capture, control

    def test_user_finalization_propagates_source_close_failure(self):
        capture, control = self.profile_stub(users.UserProfileCapture)
        injected = source.SourceSinkError('injected original source failure')
        capture.sink.close.side_effect = injected
        record = {'finalizationWindow': [{'querySeq': 1}], 'finalSnapshotQuerySeq': 1, 'ledgerQuerySeq': 1}
        with mock.patch.object(users.orm_install, 'finalize', return_value=record):
            with self.assertRaises(source.SourceSinkError) as caught:
                capture.finalize(control)
        self.assertIs(caught.exception, injected)
        self.assertFalse(capture._profile_finalized)

    def test_model_finalization_propagates_source_close_failure(self):
        capture, control = self.profile_stub(models.ModelProfileCapture)
        injected = source.SourceSinkError('injected original source failure')
        capture.sink.close.side_effect = injected
        with mock.patch.object(models, '_window', return_value={}):
            with self.assertRaises(source.SourceSinkError) as caught:
                capture.finalize(control)
        self.assertIs(caught.exception, injected)
        self.assertFalse(capture._profile_finalized)

    def test_profile_cleanup_records_source_error_as_gap_without_claiming_seal(self):
        for cls, gap in ((users.UserProfileCapture, 'profile_source_storage_failed'),
                         (models.ModelProfileCapture, 'model_source_storage_failed')):
            with self.subTest(profile=cls.__name__):
                capture, _ = self.profile_stub(cls)
                capture.sink.close.side_effect = source.SourceSinkError('injected source close failure')
                with mock.patch.object(Instrumentation, 'close', return_value='diagnostic-result'):
                    self.assertEqual(capture.close(), 'diagnostic-result')
                self.assertIn(gap, [call.args[0] for call in capture.gap.call_args_list])
                self.assertFalse(capture._profile_finalized)

    def test_documented_source_writer_example_runs_without_database(self):
        document = Path(__file__).resolve().parents[3] / 'docs/capture-write-buffer-candidate.md'
        blocks = re.findall(r'```python\n(.*?)```', document.read_text(encoding='utf8'), re.S)
        self.assertEqual(len(blocks), 3)
        output = RUN / ('documented-example-' + uuid.uuid4().hex + '.jsonl')
        code = blocks[0].replace('"new-sources.jsonl"', repr(str(output)))
        namespace = {}
        exec(compile(code, str(document), 'exec'), namespace)
        self.assertTrue(namespace['storage']['storageSealed'])
        self.assertEqual(namespace['storage']['writeBufferBytes'], 65536)
        self.assertFalse(namespace['storage']['completeCapture'])


class InstallationOptionsTests(unittest.TestCase):
    OMITTED = object()

    def setUp(self):
        self.sinks = []
        self.user_scope = users.UserScope('mtw_orm_v3_buffer_unit', 'observed_user',
            ('00000000-0000-4000-8000-000000000001',))
        self.model_scope = models.ModelScope('buffer_unit', 'append-list-v1', ('x',))

    def tearDown(self):
        for sink in self.sinks:
            try:
                sink.close()
            except source.SourceSinkError:
                pass

    def cases(self):
        return ((users, users.install_user_profile, self.user_scope),
                (models, models.install_model_profile, self.model_scope))

    def isolated_install(self, module, installer, scope, path, size=OMITTED,
                         capture_options=None, injected=None, example=None):
        options = dict(capture_options or {})
        if size is not self.OMITTED:
            options['source_write_buffer_bytes'] = size
        setup = mock.Mock(name='setup-with-no-native-driver')
        control = mock.Mock(name='fake-control')
        control.query_sequences = []
        control.references_since.return_value = []
        capture_name = 'UserProfileCapture' if module is users else 'ModelProfileCapture'
        def make_sink(*args, **kwargs):
            sink = source.GroupedSourceSink(*args, **kwargs)
            self.sinks.append(sink)
            return sink
        def make_capture(*args, **kwargs):
            return types.SimpleNamespace(sink=args[2], options=kwargs)
        with ExitStack() as stack:
            sink_factory = stack.enter_context(mock.patch.object(module, 'GroupedSourceSink', side_effect=make_sink))
            control_factory = stack.enter_context(mock.patch.object(module, 'ControlConnection', return_value=control))
            capture_factory = stack.enter_context(mock.patch.object(module, capture_name, side_effect=make_capture))
            if module is users:
                installation = stack.enter_context(mock.patch.object(users.orm_install, 'install', return_value=object()))
                if injected is not None:
                    installation.side_effect = injected
            else:
                stack.enter_context(mock.patch.object(models, 'ddl', return_value=['unit-ddl-1', 'unit-ddl-2']))
                stack.enter_context(mock.patch.object(models, '_window', return_value={}))
                if injected is not None:
                    control.execute.side_effect = [injected, None]
            if example is None:
                result = installer(setup, scope, path, **options)
            else:
                namespace = {'setup_connection': setup, 'user_scope': self.user_scope,
                             'model_scope': self.model_scope}
                exec(compile(example, '<documented-profile-installation>', 'exec'), namespace)
                result = namespace['capture'], namespace['control']
            setup.assert_not_called()
            self.assertEqual(setup.mock_calls, [])
            control_factory.assert_called_once()
            capture_factory.assert_called_once()
            return result, sink_factory.call_args, capture_factory.call_args

    def test_supported_installers_forward_only_source_option_and_preserve_other_budgets(self):
        for module, installer, scope in self.cases():
            for size in (self.OMITTED, 0, 128, 65536, 262144):
                expected = 0 if size is self.OMITTED else size
                with self.subTest(installer=installer.__name__, bufferBytes=expected, omitted=size is self.OMITTED):
                    path = RUN / ('install-option-' + uuid.uuid4().hex)
                    journal_options = {'flush_interval': 0.2}
                    options = {'max_connections': 7, 'journal_options': journal_options}
                    (capture, control), sink_call, capture_call = self.isolated_install(
                        module, installer, scope, path, size, options)
                    self.assertEqual(sink_call.kwargs, {'write_buffer_bytes': expected})
                    self.assertEqual(capture_call.kwargs, options)
                    self.assertIs(capture_call.kwargs['journal_options'], journal_options)
                    self.assertEqual(capture.sink.write_buffer_bytes, expected)
                    self.assertEqual(capture.sink._capacity.max_bytes, 4*1024*1024)
                    self.assertEqual(capture.sink.max_record_bytes, 128*1024)
                    self.assertEqual(capture.sink.max_total_bytes, 16*1024*1024)
                    self.assertEqual(capture.sink.max_records, 16384)
                    self.assertEqual(capture.sink.flush_bytes, 256*1024)
                    self.assertEqual(capture.sink.flush_interval, 0.1)
                    storage = capture.sink.close()
                    self.assertTrue(storage['storageSealed'])
                    meta = json.loads(capture.sink.index.read_bytes())
                    self.assertEqual(meta.get('writeBufferBytes', 0), expected)
                    self.assertEqual('writeBufferBytes' in meta, expected != 0)

    def test_invalid_configuration_precedes_path_resources_and_database_installation(self):
        class IntSubclass(int):
            pass
        class ForbiddenPath:
            def __fspath__(self):
                raise AssertionError('Invalid source buffer must fail before output path resolution')
        invalid = (-1, 1, 127, 262145, True, False, 0.0, None, '65536', IntSubclass(65536))
        for module, installer, scope in self.cases():
            for value in invalid:
                with self.subTest(installer=installer.__name__, value=repr(value)):
                    setup = mock.Mock()
                    with mock.patch.object(module, 'GroupedSourceSink') as sink, \
                         mock.patch.object(module, 'ControlConnection') as control, \
                         mock.patch.object(module.Path, 'mkdir') as mkdir:
                        with self.assertRaisesRegex(ValueError, 'Source write buffer must be 0 or 128..262144 bytes'):
                            installer(setup, scope, ForbiddenPath(), source_write_buffer_bytes=value)
                        sink.assert_not_called()
                        control.assert_not_called()
                        mkdir.assert_not_called()
                    self.assertEqual(setup.mock_calls, [])

    def test_invalid_configuration_leaves_new_and_existing_output_paths_untouched(self):
        for module, installer, scope in self.cases():
            for existing in (False, True):
                with self.subTest(installer=installer.__name__, existing=existing):
                    path = RUN / ('invalid-install-' + uuid.uuid4().hex)
                    if existing:
                        path.mkdir()
                        (path / 'marker').write_bytes(b'original-marker')
                    with self.assertRaises(ValueError):
                        installer(object(), scope, path, source_write_buffer_bytes=True)
                    if existing:
                        self.assertEqual([p.name for p in path.iterdir()], ['marker'])
                        self.assertEqual((path / 'marker').read_bytes(), b'original-marker')
                    else:
                        self.assertFalse(path.exists())

    def test_keyword_only_option_and_old_scope_and_budget_error_order(self):
        for module, installer, scope in self.cases():
            path = RUN / ('old-order-' + uuid.uuid4().hex)
            with self.assertRaises(TypeError):
                installer(object(), scope, path, 65536)
            expected = 'Explicit fixed UserScope required' if module is users else 'Explicit immutable ModelScope required'
            with self.assertRaisesRegex(users.CoverageRequired, expected):
                installer(object(), object(), path, source_write_buffer_bytes=True)
            self.assertFalse(path.exists())
        path = RUN / ('old-budget-order-' + uuid.uuid4().hex)
        with self.assertRaisesRegex(ValueError, 'Positive bounded integer budgets required'):
            source.GroupedSourceSink(path, max_queue_bytes=0, write_buffer_bytes=True)
        self.assertFalse(path.exists())

    def test_existing_installation_failure_identity_and_cleanup_are_preserved(self):
        for module, installer, scope in self.cases():
            for size in (self.OMITTED, 65536):
                with self.subTest(installer=installer.__name__, omitted=size is self.OMITTED):
                    path = RUN / ('failed-install-' + uuid.uuid4().hex)
                    injected = RuntimeError('original fake installation failure')
                    with self.assertRaises(RuntimeError) as caught:
                        self.isolated_install(module, installer, scope, path, size, injected=injected)
                    self.assertIs(caught.exception, injected)
                    self.assertTrue(self.sinks[-1]._closed)
                    self.assertFalse(self.sinks[-1].lock_path.exists())

    def test_documented_profile_options_run_with_fake_control_and_real_source_files(self):
        document = Path(__file__).resolve().parents[3] / 'docs/capture-write-buffer-candidate.md'
        blocks = re.findall(r'```python\n(.*?)```', document.read_text(encoding='utf8'), re.S)
        self.assertEqual(len(blocks), 3)
        for (module, installer, scope), block, name in zip(self.cases(), blocks[1:], ('new-user-profile', 'new-model-profile')):
            with self.subTest(installer=installer.__name__):
                path = RUN / ('documented-install-' + uuid.uuid4().hex)
                code = block.replace('"' + name + '"', repr(str(path)))
                (capture, control), sink_call, capture_call = self.isolated_install(module, installer, scope, path, example=code)
                self.assertEqual(sink_call.kwargs, {'write_buffer_bytes': 65536})
                self.assertEqual(capture_call.kwargs, {})
                self.assertTrue(capture.sink.close()['storageSealed'])


if __name__ == '__main__':
    result = unittest.main(verbosity=2, exit=False).result
    receipt = {'schema': 1, 'kind': 'source-buffer-integration-boundaries',
               'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
               'sourceSyncFaultCombinations': FAULT_COMBINATIONS, 'flushWatermarkBufferSizes': WATERMARK_SIZES,
               'actualFileIOExecuted': FILE_IO_EXECUTED, 'actualDatabaseExecution': False,
               'networkExecuted': False, 'formalPerformanceMeasurement': False}
    (RUN / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps(receipt))
    raise SystemExit(0 if result.wasSuccessful() else 1)
