"""Small mocked transport/guard/failure tests; no network, Node, DB or builds."""
from pathlib import Path
import ast
import contextlib
from datetime import datetime, timezone
from email.message import Message
import hashlib
import importlib.util
import io
import json
import os
import py_compile
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transport

RUN = HERE / 'unit-artifacts' / ('run-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)


class Response(io.BytesIO):
    status = 200


class CandidateTests(unittest.TestCase):
    @staticmethod
    def assert_driver_literals(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        values = {}
        for statement in tree.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id in ('NODE_DRIVER', 'JOURNAL_DRIVER'):
                        if target.id in values:
                            raise AssertionError('Driver must have one independent literal assignment')
                        values[target.id] = ast.literal_eval(statement.value)
            if isinstance(statement, (ast.For, ast.While, ast.With, ast.Try)):
                raise AssertionError('No journal execution at Python module top level')
            if isinstance(statement, ast.ImportFrom) and (statement.module or '').startswith('moontxnwitness_capture'):
                raise AssertionError('Journal imports belong only inside its independent driver literal')
        if set(values) != {'NODE_DRIVER', 'JOURNAL_DRIVER'}:
            raise AssertionError('Two independent driver constants are required')
        if not values['NODE_DRIVER'].lstrip().startswith("import assert from 'node:assert/strict';"):
            raise AssertionError('The Node driver must import its assertion implementation')
        if 'JOURNAL_DRIVER' in values['NODE_DRIVER'] or 'from moontxnwitness_capture' in values['NODE_DRIVER']:
            raise AssertionError('Python driver cannot be embedded in Node driver')
        ast.parse(values['JOURNAL_DRIVER'])
        return values

    def test_ast_driver_semantics_and_preserved_first_failure(self):
        values = self.assert_driver_literals(HERE / 'audit-public-ci.py')
        self.assertIn('nativeReadFileSync', values['NODE_DRIVER'])
        with self.assertRaises(AssertionError):
            self.assert_driver_literals(HERE / 'candidate-history/before-driver-string-fix-3cc4f2eeb7ddd35817bc72c4726cea9a5bc6c6e0d65c08abf1eca9e30046f234.py')

    def test_environment_guard(self):
        for env in [{}, {'GITHUB_ACTIONS': 'false', 'GITHUB_REPOSITORY': transport.REPOSITORY},
                    {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'someone/else'}]:
            with self.assertRaises(ValueError):
                transport.guard_environment(env)
        transport.guard_environment({'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': transport.REPOSITORY})
        with self.assertRaises(ValueError):
            transport.guard_environment({'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': transport.REPOSITORY}, True)

    def test_child_environment_has_no_credentials(self):
        result = transport.child_environment({'PATH': 'ok', 'GITHUB_TOKEN': 'secret', 'GH_TOKEN': 'secret',
                                               'ACTIONS_RUNTIME_TOKEN': 'secret', 'OTHER_PASSWORD': 'secret'})
        self.assertEqual(result, {'PATH': 'ok'})

    def test_compile_only(self):
        for name in ('audit-public-ci.py', 'transport.py', 'test_candidate.py'):
            py_compile.compile(str(HERE / name), cfile=str(RUN / (name + '.pyc')), doraise=True)

    def test_profile_is_fixed_not_lowered(self):
        spec = importlib.util.spec_from_file_location('independent_ci_candidate', HERE / 'audit-public-ci.py')
        candidate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(candidate)
        profile = candidate.read_profile(HERE / 'profile-7863550.json')
        self.assertEqual((profile['coreTestsPerTarget'], profile['nonDistBindings']), (563, 339))
        profile['coreTestsPerTarget'] = 1
        altered = RUN / 'lowered-profile.json'
        altered.write_text(json.dumps(profile))
        with self.assertRaises(AssertionError):
            candidate.read_profile(altered)

    def test_redirect_never_forwards_token_or_records_signature(self):
        token = 'unit-only-token-never-persist'
        client = transport.Transport(token, RUN)
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append(dict(request.header_items()))
                if len(calls) == 1:
                    headers = Message()
                    headers['Location'] = 'https://example.blob.core.windows.net/file?signature=unit-private'
                    raise urllib.error.HTTPError(request.full_url, 302, 'redirect', headers, io.BytesIO())
                return Response(b'ok')
        client.opener = Opener()
        with client.open('/repos/' + transport.REPOSITORY + '/actions/artifacts/1/zip') as result:
            self.assertEqual(result.read(), b'ok')
        self.assertTrue(any(k.lower() == 'authorization' for k in calls[0]))
        self.assertFalse(any(k.lower() == 'authorization' for k in calls[1]))
        metadata = json.dumps(client.requests)
        self.assertNotIn(token, metadata)
        self.assertNotIn('signature', metadata)

    def test_stream_byte_bound_keeps_partial_never_success(self):
        path = RUN / 'bounded.part'
        with self.assertRaises(ValueError):
            transport.copy_stream(Response(b'x' * 80), path, 50, float('inf'))
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_size, 0)

    def test_stream_deadline(self):
        with self.assertRaises(TimeoutError):
            transport.copy_stream(Response(b'x'), RUN / 'expired.part', 50, 0)

    def test_incomplete_metadata_is_never_published_as_json(self):
        client = transport.Transport('unit-only', RUN)
        client.open = lambda route: Response(b'{"incomplete":')
        with self.assertRaises(json.JSONDecodeError):
            client.json('/fixed', 'incomplete-metadata.json')
        self.assertFalse((RUN / 'incomplete-metadata.json').exists())
        self.assertEqual((RUN / 'incomplete-metadata.json.pending').read_bytes(), b'{"incomplete":')

    def test_bounded_metadata_does_not_read_oversized_file(self):
        path = RUN / 'oversized-metadata.json'
        path.write_bytes(b'x' * 129)
        with self.assertRaises(ValueError):
            transport.read_bounded(path, maximum=128)

    def test_fresh_failure_marks_stage_failed_and_cannot_claim_complete(self):
        spec = importlib.util.spec_from_file_location('independent_ci_candidate_fault', HERE / 'audit-public-ci.py')
        candidate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(candidate)
        work = RUN / 'injected-fresh-failure'
        work.mkdir()
        downloads = []
        for number in range(7):
            name = str(number) + '.bin'
            (work / name).write_bytes(b'x')
            downloads.append({'file': name, **transport.file_binding(work / name), 'githubDigest': None})
        transport.immutable(work / 'fetch-complete.json', {'complete': True, 'files': 7, 'extractions': 4})
        transport.immutable(work / 'transport-audit.json', {'complete': True, 'sourceCommit': candidate.COMMIT,
                            'downloads': downloads, 'artifacts': [{}, {}, {}], 'jobs': [{}, {}, {}]})
        output = work / 'receipt.json'
        arguments = ['audit-public-ci.py', '--mode', 'github-actions', '--phase', 'audit', '--profile',
                     str(HERE / 'profile-7863550.json'), '--work', str(work), '--output', str(output)]
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': transport.REPOSITORY}, clear=True), \
             mock.patch.object(sys, 'argv', arguments), \
             mock.patch.object(candidate, 'audit', return_value=(work, work, {})), \
             mock.patch.object(candidate, 'extra_audit', return_value={'passed': True}), \
             mock.patch.object(candidate, 'extra_relation_audit', return_value={'passed': True}), \
             mock.patch.object(candidate, 'fresh', return_value=[{'passed': True}, {'passed': False}]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(candidate.main(), 1)
        result = json.loads(output.read_bytes())
        self.assertFalse(result['passed'])
        self.assertFalse(result['complete'])
        self.assertEqual([s['status'] for s in result['stages']], ['passed'] * 4 + ['failed'])
        self.assertFalse(result['fresh'][1]['passed'])

    def exercise_bounded_child(self, name, maximum):
        class Pipe:
            def __init__(self, number): self.number = number
            def fileno(self): return self.number
            def close(self): pass
        class Process:
            def __init__(self): self.stdout, self.stderr = Pipe(40), Pipe(41)
            def wait(self, timeout): return 0
            def poll(self): return 0
        class Multiplex:
            def __init__(self): self.entries = {}
            def register(self, pipe, events, data): self.entries[pipe] = SimpleNamespace(fileobj=pipe, data=data)
            def unregister(self, pipe): del self.entries[pipe]
            def get_map(self): return self.entries
            def select(self, timeout): return [(value, None) for value in list(self.entries.values())]
            def close(self): pass
        blocks = {40: [b'abc', b''], 41: [b'err', b'']}
        with mock.patch.object(transport.sys, 'platform', 'linux'), \
             mock.patch.object(transport.subprocess, 'Popen', return_value=Process()), \
             mock.patch.object(transport.selectors, 'DefaultSelector', Multiplex), \
             mock.patch.object(transport.os, 'read', side_effect=lambda fd, size: blocks[fd].pop(0)):
            return transport.run_bounded(['never-executed'], cwd=RUN, env={}, output_prefix=RUN / name,
                                         maximum=maximum)

    def test_bounded_child_mocked_pipes_preserve_exact_output(self):
        result = self.exercise_bounded_child('mocked-child-normal', 10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, 'abc', 'err'))
        self.assertEqual((RUN / 'mocked-child-normal.stdout').read_bytes(), b'abc')

    def test_bounded_child_mocked_overflow_keeps_failure_and_prefix(self):
        with self.assertRaises(ValueError):
            self.exercise_bounded_child('mocked-child-overflow', 2)
        self.assertEqual((RUN / 'mocked-child-overflow.stdout').read_bytes(), b'ab')
        failure = json.loads((RUN / 'mocked-child-overflow.failure.json').read_bytes())
        self.assertFalse(failure['complete'])
        self.assertTrue(failure['outputMayBeIncomplete'])

    def test_digest_mismatch_is_not_retried_or_accepted(self):
        client = transport.Transport('unit-only', RUN)
        calls = []
        client.open = lambda route: (calls.append(route) or Response(b'actual-bytes'))
        with self.assertRaises(RuntimeError):
            client.download('/fixed', 'digest-failure.zip', 100, 'sha256:' + '0' * 64, 12)
        self.assertEqual(len(calls), 1)
        self.assertFalse((RUN / 'digest-failure.zip').exists())
        self.assertTrue((RUN / 'digest-failure.zip.attempt-1.failure.json').exists())

    def test_transient_failure_recorded_before_bounded_success(self):
        client = transport.Transport('unit-only', RUN)
        calls = []

        def opening(route):
            calls.append(route)
            if len(calls) == 1:
                raise RuntimeError('injected transport failure')
            return Response(b'ok')
        client.open = opening
        result = client.download('/fixed', 'transient.bin', 100, 'sha256:' + hashlib.sha256(b'ok').hexdigest(), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual([a['complete'] for a in result['attempts']], [False, True])
        self.assertEqual((RUN / 'transient.bin').read_bytes(), b'ok')

    def test_zip_path_escape_rejected(self):
        path = RUN / 'escape.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('../escaped', b'not-allowed')
        with self.assertRaises(ValueError):
            transport.safe_extract(path, RUN / 'escape-output')
        self.assertFalse((RUN / 'escaped').exists())

    def test_zip_symlink_rejected(self):
        path = RUN / 'symlink.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, b'/elsewhere')
        with self.assertRaises(ValueError):
            transport.safe_extract(path, RUN / 'symlink-output')

    def test_zip_normal_file(self):
        path = RUN / 'normal.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('sub/file.txt', b'exact-bytes')
        transport.safe_extract(path, RUN / 'normal-output')
        self.assertEqual((RUN / 'normal-output/sub/file.txt').read_bytes(), b'exact-bytes')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    prefix = str(HERE.parents[1])
    receipt = {'schema': 1, 'scope': 'Local lightweight mocked/compile checks only',
               'passed': result.wasSuccessful(), 'testsRun': result.testsRun,
               'networkExecuted': False, 'nodeExecuted': False, 'databaseExecuted': False,
               'failures': [text.replace(prefix, '<workspace>') for _, text in result.failures + result.errors],
               'finishedAt': datetime.now(timezone.utc).isoformat()}
    raw = (json.dumps(receipt, indent=2) + '\n').encode()
    (RUN / 'receipt.json').open('xb').write(raw)
    print(json.dumps({'passed': receipt['passed'], 'testsRun': result.testsRun,
                      'receipt': str((RUN / 'receipt.json').relative_to(HERE)),
                      'sha256': hashlib.sha256(raw).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
