"""Mocked probe mechanics only; no actual native locks or journal/FS scenarios."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import os
import py_compile
import stat
import sys
import types
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('independent_r4_r2_mocked', HERE / 'counterexample.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RUN = HERE / 'unit-artifacts' / ('run-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)
INFO = types.SimpleNamespace(st_mode=stat.S_IFREG, st_dev=4, st_ino=9)
NONCE = '0123456789abcdef0123456789abcdef'
RAW = json.dumps({'kind':'archive-coordination/1','nonce':NONCE},sort_keys=True,separators=(',',':')).encode()


class FakeStream(io.BytesIO):
    def fileno(self): return 7


class FakePath:
    def __init__(self, stream): self.stream = stream
    def lstat(self): return INFO
    def is_symlink(self): return False
    def open(self, mode):
        assert mode == 'r+b'
        return self.stream


class NoReadStream:
    def __enter__(self): return self
    def __exit__(self, *unused): return False
    def fileno(self): return 7
    def seek(self, *unused): pass
    def read(self, *unused): raise AssertionError('Must not read mandatory locked bytes before native attempt')


class ProbeTests(unittest.TestCase):
    def test_python_syntax_and_declared_unchanged_sites(self):
        for name in ('counterexample.py','test_probe_mock.py'):
            py_compile.compile(str(HERE/name), cfile=str(RUN/(name+'.pyc')), doraise=True)
        site = json.loads((HERE/'r4-callsite-binding.json').read_bytes())
        self.assertEqual(site['finalSync']['line'],331)
        self.assertEqual(site['secondaryMarkerIO']['line'],357)
        self.assertEqual(hashlib.sha256((HERE/'events-v1.json').read_bytes()).hexdigest(),
                         '8ff02ad102a7046907ab0b993e882e810acac0584d674a053a1857c30c61c91c')
        self.assertEqual(hashlib.sha256((HERE/'contract-v1.json').read_bytes()).hexdigest(),
                         '66e3b568335c8f85ba16b1ac245b8b3a25ff3a8e52d332b26320b5a4eed64670')

    def test_windows_probe_attempts_native_lock_without_reading(self):
        call = unittest.mock.Mock(side_effect=OSError(errno.EACCES,'mocked contention'))
        native = types.SimpleNamespace(locking=call,LK_NBLCK=2,LK_UNLCK=0)
        output = io.StringIO()
        with patch.object(m.os,'name','nt'), patch.object(m.os,'fstat',return_value=INFO), \
             patch.dict(sys.modules,{'msvcrt':native}), contextlib.redirect_stdout(output):
            code = m.native_probe(FakePath(NoReadStream()),NONCE)
        self.assertEqual(code,17)
        call.assert_called_once_with(7,2,1)
        actual = json.loads(output.getvalue())
        self.assertEqual(actual['nativeCallStage'],'msvcrt.LK_NBLCK/1')
        self.assertEqual(actual['result'],'blocked')
        self.assertFalse(actual['authorityBytesReadByProbe'])

    def test_posix_probe_uses_real_nonblocking_argument_contract(self):
        call = unittest.mock.Mock(side_effect=OSError(errno.EAGAIN,'mocked contention'))
        native = types.SimpleNamespace(flock=call,LOCK_EX=2,LOCK_NB=4,LOCK_UN=8)
        output = io.StringIO()
        with patch.object(m.os,'name','posix'), patch.object(m.os,'fstat',return_value=INFO), \
             patch.dict(sys.modules,{'fcntl':native}), contextlib.redirect_stdout(output):
            code = m.native_probe(FakePath(NoReadStream()),NONCE)
        self.assertEqual(code,17)
        call.assert_called_once_with(7,6)
        self.assertEqual(json.loads(output.getvalue())['nativeCallStage'],'fcntl.LOCK_EX|LOCK_NB')

    def test_holding_handle_checks_all_bytes_nonce_and_inode(self):
        stream = FakeStream(RAW);stream.seek(5)
        with patch.object(m.os,'fstat',return_value=INFO):
            value = m.held_authority(FakePath(stream),NONCE,stream)
            self.assertEqual(stream.tell(),5)
            self.assertEqual(value['sha256'],hashlib.sha256(RAW).hexdigest())
            with self.assertRaisesRegex(RuntimeError,'full bytes/nonce'):
                m.held_authority(FakePath(stream),'different',stream)
            extra = FakeStream(RAW+b' ')
            with self.assertRaisesRegex(RuntimeError,'full bytes/nonce'):
                m.held_authority(FakePath(extra),NONCE,extra)
        wrong = types.SimpleNamespace(st_mode=stat.S_IFREG,st_dev=4,st_ino=10)
        with patch.object(m.os,'fstat',return_value=wrong):
            with self.assertRaisesRegex(RuntimeError,'inode'):
                m.held_authority(FakePath(stream),NONCE,stream)

    def test_failed_native_result_is_saved_before_assertion(self):
        authority = {'nonce':NONCE,'device':4,'inode':9,'bytes':len(RAW),'sha256':hashlib.sha256(RAW).hexdigest()}
        returned = {'phase':'native-lock','result':'acquired-unexpectedly','device':4,'inode':9,
                    'nativeCallStage':'msvcrt.LK_NBLCK/1' if os.name=='nt' else 'fcntl.LOCK_EX|LOCK_NB'}
        child = types.SimpleNamespace(returncode=0,stdout=json.dumps(returned)+'\n',stderr='original stderr')
        saved = []
        def save(path,value):
            saved.append(json.loads(json.dumps(value)))
            return {'bytes':1,'sha256':'mock'}
        with patch.object(m,'held_authority',return_value=authority), patch.object(m.subprocess,'run',return_value=child), \
             patch.object(m,'save',side_effect=save):
            with self.assertRaisesRegex(RuntimeError,'prove contention'):
                m.probe(Path('fake-mutex'),NONCE,object(),Path('not-created'))
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['exitCode'],0)
        self.assertEqual(saved[0]['rawStdout'],child.stdout)
        self.assertEqual(saved[0]['stderr'],'original stderr')

    def test_malformed_native_stdout_is_preserved(self):
        authority = {'nonce':NONCE,'device':4,'inode':9,'bytes':len(RAW),'sha256':hashlib.sha256(RAW).hexdigest()}
        child = types.SimpleNamespace(returncode=2,stdout='not JSON\n',stderr='raw failure')
        saved = []
        with patch.object(m,'held_authority',return_value=authority), patch.object(m.subprocess,'run',return_value=child), \
             patch.object(m,'save',side_effect=lambda path,value:saved.append(dict(value))):
            with self.assertRaises(json.JSONDecodeError):
                m.probe(Path('fake-mutex'),NONCE,object(),Path('not-created'))
        self.assertEqual(saved[0]['rawStdout'],'not JSON\n')
        self.assertEqual(saved[0]['stderr'],'raw failure')
        self.assertEqual(saved[0]['errorClass'],'JSONDecodeError')

    def test_child_different_inode_is_rejected_after_raw_save(self):
        authority = {'nonce':NONCE,'device':4,'inode':9,'bytes':len(RAW),'sha256':hashlib.sha256(RAW).hexdigest()}
        returned = {'phase':'native-lock','result':'blocked','device':4,'inode':10,
                    'nativeCallStage':'msvcrt.LK_NBLCK/1' if os.name=='nt' else 'fcntl.LOCK_EX|LOCK_NB'}
        child = types.SimpleNamespace(returncode=17,stdout=json.dumps(returned),stderr='')
        with patch.object(m,'held_authority',return_value=authority), patch.object(m.subprocess,'run',return_value=child), \
             patch.object(m,'save',return_value={'bytes':1,'sha256':'mock'}) as saved:
            with self.assertRaisesRegex(RuntimeError,'another inode'):
                m.probe(Path('fake-mutex'),NONCE,object(),Path('not-created'))
        saved.assert_called_once()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests))
    receipt = {'schema':1,'passed':result.wasSuccessful(),'testsRun':result.testsRun,
               'scope':'Python syntax and mocked native call/owning-handle/error preservation only',
               'actualFilesystemScenarioExecuted':False,'actualNativeLockExecuted':False,'nodeCompileDBBenchmarkExecuted':False,
               'failures':[s.replace(str(HERE),'<candidate>') for _,s in result.errors+result.failures],
               'finishedAt':datetime.now(timezone.utc).isoformat()}
    raw = (json.dumps(receipt,indent=2)+'\n').encode();(RUN/'receipt.json').open('xb').write(raw)
    print(json.dumps({'passed':receipt['passed'],'testsRun':result.testsRun,'receipt':str((RUN/'receipt.json').relative_to(HERE)),
                      'sha256':hashlib.sha256(raw).hexdigest()}))
    raise SystemExit(0 if receipt['passed'] else 1)
