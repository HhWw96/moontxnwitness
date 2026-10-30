"""Fault tests for checksum-pinned inputs; fixtures and caches stay in artifacts."""
from __future__ import annotations

import copy
import errno
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('input_cache_under_test', ROOT / 'scripts/input_cache.py')
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)

WORKER = r'''
import importlib.util,json,pathlib,sys,time
spec=importlib.util.spec_from_file_location('isolated_input_cache',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
if len(sys.argv)>4:
 gate=pathlib.Path(sys.argv[4]);pathlib.Path(str(gate)+'.'+str(__import__('os').getpid())+'.ready').write_text('ready')
 deadline=time.monotonic()+20
 while not gate.exists():
  if time.monotonic()>deadline:raise TimeoutError('Test start gate was not released')
  time.sleep(.01)
print(json.dumps(module.prepare(root=pathlib.Path(sys.argv[2]),cache_dir=pathlib.Path(sys.argv[3]),offline=True)))
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


class InputCacheTests(unittest.TestCase):
    def setUp(self):
        artifact_root = ROOT / 'artifacts'
        artifact_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='input-cache-test-', dir=artifact_root)
        self.base = Path(self.temporary.name).resolve()
        self.base.relative_to(artifact_root.resolve())
        self.addCleanup(self.temporary.cleanup)
        self.root = self.base / 'checkout'
        self.root.mkdir()
        (self.root / 'scripts').mkdir()
        (self.root / 'artifacts').mkdir()
        self.store = self.base / 'cache'
        self.payloads = {
            'cmd/legacy/unit/identity.txt': (b'frozen-runtime-identity\n', 'runtime'),
            'fixtures/cache-unit/observation.json': (b'{"status":"invalid","original":true}\n', 'tests'),
            'verification/cache-unit/original.json': (b'{"status":"invalid","original":true}\n', 'tests'),
        }
        self.seed = self.root / 'artifacts/seed.zip'
        self.entries = {}
        with zipfile.ZipFile(self.seed, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, (data, group) in self.payloads.items():
                member = 'FrozenFixture-v0.3.1/' + name
                archive.writestr(member, data)
                self.entries[name] = {'bytes': len(data), 'sha256': digest(data), 'member': member,
                                      'provider': 'public031', 'group': group}
        archive_bytes = self.seed.read_bytes()
        self.manifest = {
            'format': 'moontxnwitness-frozen-input-index/v1',
            'sourceCommit': '0' * 40,
            'index': 'frozen-unit.json.gz',
            'providers': {'public031': {
                'url': 'https://github.com/HhWw96/moontxnwitness/releases/download/v0.3.1/unit-test.zip',
                'sha256': digest(archive_bytes), 'bytes': len(archive_bytes), 'seed': self.seed.name,
            }},
        }
        self.write_index(self.entries)

    def write_manifest(self):
        (self.root / 'scripts/frozen-inputs.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def write_index(self, entries, raw=None):
        raw = json.dumps(entries, sort_keys=True).encode() if raw is None else raw
        compressed = gzip.compress(raw, mtime=0)
        (self.root / 'scripts' / self.manifest['index']).write_bytes(compressed)
        self.manifest.update(indexBytes=len(compressed), indexSha256=digest(compressed),
                             fileCount=len(entries), logicalBytes=sum(r['bytes'] for r in entries.values()))
        self.write_manifest()

    def repin_seed(self):
        data = self.seed.read_bytes()
        self.manifest['providers']['public031'].update(bytes=len(data), sha256=digest(data))
        self.write_manifest()

    def prepare(self, **kwargs):
        with mock.patch.object(cache.urllib.request, 'build_opener', side_effect=AssertionError('Unit tests must not use the network')):
            return cache.prepare(root=self.root, cache_dir=self.store, offline=True, **kwargs)

    def blob(self, name='fixtures/cache-unit/observation.json'):
        sha = self.entries[name]['sha256']
        return self.store / 'blobs' / sha[:2] / sha

    def assert_payloads(self):
        for name, (data, _) in self.payloads.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)

    def assert_no_staging(self):
        if self.store.exists():
            leftovers = [p for p in self.store.rglob('*') if p.name.startswith(('archive-', 'blob-', '.frozen-'))]
            self.assertEqual(leftovers, [])

    def spawn(self, gate=None):
        args = [sys.executable, '-B', '-c', WORKER, str(ROOT / 'scripts/input_cache.py'), str(self.root), str(self.store)]
        if gate is not None:
            args.append(str(gate))
        process = subprocess.Popen(args, cwd=self.base, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        return process

    def directory_link(self, link, target):
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            result = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                                    capture_output=True, timeout=10)
            if result.returncode:
                self.skipTest('Creating directory links is unavailable on this filesystem')
        def remove():
            if link.is_symlink():
                link.unlink()
            elif link.exists():
                os.rmdir(link)
        self.addCleanup(remove)

    def file_link(self, link, target):
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest('Creating file symlinks requires unavailable OS privileges')
        self.addCleanup(lambda: link.unlink(missing_ok=True))

    def test_cold_seed_offline_restores_exact_payloads(self):
        result = self.prepare()
        self.assertTrue(result['passed'])
        self.assertEqual(result['verifiedFiles'], len(self.entries))
        self.assertEqual(result['logicalBytes'], sum(len(d) for d, _ in self.payloads.values()))
        self.assert_payloads()
        self.assert_no_staging()

    def test_runtime_scope_does_not_materialize_test_inputs(self):
        result = self.prepare(scope='runtime')
        self.assertEqual(result['verifiedFiles'], 1)
        self.assertFalse((self.root / 'fixtures').exists())
        self.assertTrue((self.root / 'cmd/legacy/unit/identity.txt').is_file())
        self.assertEqual(self.prepare()['verifiedFiles'], 3)

    def test_complete_blobs_restore_offline_without_seed_or_archive(self):
        self.prepare()
        self.seed.unlink()
        for archive in (self.store / 'archives').glob('*.zip'):
            archive.unlink()
        for name in self.entries:
            (self.root / name).unlink()
        with mock.patch.object(cache, 'archive_file', side_effect=AssertionError('Complete blob cache must not require a ZIP')):
            result = self.prepare()
        self.assertTrue(result['passed'])
        self.assert_payloads()

    def test_offline_missing_archive_fails_and_cleans_staging(self):
        self.seed.unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assertFalse((self.root / 'cmd/legacy/unit/identity.txt').exists())
        self.assert_no_staging()

    def test_two_processes_first_prepare_share_one_cache(self):
        gate = self.base / 'start-gate'
        processes = [self.spawn(gate), self.spawn(gate)]
        deadline = time.monotonic() + 15
        while len(list(self.base.glob('start-gate.*.ready'))) < 2:
            self.assertLess(time.monotonic(), deadline, 'Both test workers must reach the start gate')
            time.sleep(.02)
        gate.write_text('go', encoding='utf-8')
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr.decode('utf-8', 'replace'))
            self.assertTrue(json.loads(stdout)['passed'])
            self.assertEqual(json.loads(stdout)['verifiedFiles'], 3)
        self.assert_payloads()
        self.assert_no_staging()

    def test_failed_prepare_propagates_nonzero_to_caller(self):
        self.seed.unlink()
        process = self.spawn()
        stdout, stderr = process.communicate(timeout=30)
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn(b'"passed": true', stdout)
        self.assertIn(b'FileNotFoundError', stderr)
        self.assert_no_staging()

    def test_existing_different_input_is_never_overwritten(self):
        target = self.root / 'fixtures/cache-unit/observation.json'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'locally-edited-original')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(target.read_bytes(), b'locally-edited-original')

    def test_competing_different_bytes_before_atomic_publish_are_preserved(self):
        target = self.root / 'fixtures/cache-unit/observation.json'
        original_link = os.link
        injected = []
        def competing_link(source, destination, *args, **kwargs):
            if Path(destination) == target and not injected:
                target.write_bytes(b'concurrent-writer-original')
                injected.append(True)
            return original_link(source, destination, *args, **kwargs)
        with mock.patch.object(cache.os, 'link', side_effect=competing_link):
            with self.assertRaises(ValueError):
                self.prepare()
        self.assertTrue(injected)
        self.assertEqual(target.read_bytes(), b'concurrent-writer-original')

    def test_editing_a_materialized_hardlink_invalidates_blob_cache(self):
        self.prepare()
        target = self.root / 'fixtures/cache-unit/observation.json'
        if not os.path.samefile(target, self.blob()):
            self.skipTest('This volume does not provide materialized hardlinks')
        target.write_bytes(b'changed-through-hardlink')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(target.read_bytes(), b'changed-through-hardlink')
        self.assertEqual(self.blob().read_bytes(), b'changed-through-hardlink')

    def test_corrupt_seed_digest_is_rejected(self):
        self.seed.write_bytes(self.seed.read_bytes() + b'corrupt')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assert_no_staging()

    def test_truncated_repin_archive_still_fails_zip_parsing(self):
        self.seed.write_bytes(self.seed.read_bytes()[:20])
        self.repin_seed()
        with self.assertRaises(zipfile.BadZipFile):
            self.prepare()
        self.assert_no_staging()

    def test_corrupt_cached_archive_is_not_replaced_from_good_seed(self):
        folder = self.store / 'archives'
        folder.mkdir(parents=True)
        path = folder / (self.manifest['providers']['public031']['sha256'] + '.zip')
        path.write_bytes(b'corrupt-cache-archive')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(path.read_bytes(), b'corrupt-cache-archive')

    def test_duplicate_zip_inventory_is_rejected(self):
        member = next(iter(self.entries.values()))['member']
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.seed, 'a') as archive:
                archive.writestr(member, b'duplicate')
        self.repin_seed()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.prepare()

    def test_zip_symlink_member_is_rejected_even_with_matching_hash(self):
        with zipfile.ZipFile(self.seed, 'w') as archive:
            for name, row in self.entries.items():
                info = zipfile.ZipInfo(row['member'])
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, self.payloads[name][0])
        self.repin_seed()
        with self.assertRaisesRegex(ValueError, 'member shape'):
            self.prepare()

    def test_index_digest_mismatch_is_rejected(self):
        self.manifest['indexSha256'] = '0' * 64
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            cache.load_index(self.root)

    def test_index_expansion_budget_is_enforced_before_json_parsing(self):
        self.write_index(self.entries, raw=b' ' * (cache.MAX_INDEX + 1))
        with self.assertRaisesRegex(ValueError, 'expansion budget'):
            cache.load_index(self.root)

    def test_truncated_gzip_with_matching_digest_is_rejected(self):
        path = self.root / 'scripts' / self.manifest['index']
        compressed = path.read_bytes()[:15]
        path.write_bytes(compressed)
        self.manifest.update(indexBytes=len(compressed), indexSha256=digest(compressed))
        self.write_manifest()
        with self.assertRaises(EOFError):
            cache.load_index(self.root)

    def test_unsafe_names_and_active_source_replacement_are_rejected(self):
        for name in ['', '../escape', '/absolute', 'fixtures//x', 'fixtures/../src/x', 'fixtures/./x', 'fixtures\\x', 'C:/x']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    cache.safe_name(name)
        entries = {'src/types.mbt': copy.deepcopy(next(iter(self.entries.values())))}
        self.write_index(entries)
        with self.assertRaisesRegex(ValueError, 'active sources'):
            cache.load_index(self.root)

    def test_wrong_source_domains_and_nonpublic_urls_are_rejected(self):
        urls = ['http://github.com/HhWw96/moontxnwitness/releases/download/v0.3.1/a.zip',
                'https://example.invalid/HhWw96/moontxnwitness/releases/download/v0.3.1/a.zip',
                'https://untrusted@github.com/HhWw96/moontxnwitness/releases/download/v0.3.1/a.zip',
                'https://github.com/HhWw96/other/releases/download/v0.3.1/a.zip',
                'https://github.com/HhWw96/moontxnwitness/releases/download/v0.3.1/a.zip?query=1']
        for url in urls:
            with self.subTest(url=url):
                self.manifest['providers']['public031']['url'] = url
                self.write_manifest()
                with self.assertRaisesRegex(ValueError, 'declared public release'):
                    cache.load_index(self.root)

    def test_case_collisions_and_conflicting_hash_sizes_are_rejected(self):
        row = copy.deepcopy(next(iter(self.entries.values())))
        entries = {'fixtures/Case.json': copy.deepcopy(row), 'fixtures/case.json': copy.deepcopy(row)}
        self.write_index(entries)
        with self.assertRaisesRegex(ValueError, 'Case-colliding'):
            cache.load_index(self.root)
        entries = {'fixtures/first.json': copy.deepcopy(row), 'fixtures/second.json': copy.deepcopy(row)}
        entries['fixtures/second.json']['bytes'] += 1
        self.write_index(entries)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            cache.load_index(self.root)

    def test_directory_link_in_cache_ancestry_is_rejected(self):
        outside = self.base / 'other-cache'
        outside.mkdir()
        self.directory_link(self.store, outside)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_file_symlink_is_rejected(self):
        target = self.root / 'fixtures/cache-unit/observation.json'
        target.parent.mkdir(parents=True)
        other = self.base / 'same-original.json'
        other.write_bytes(self.payloads['fixtures/cache-unit/observation.json'][0])
        self.file_link(target, other)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(other.read_bytes(), self.payloads['fixtures/cache-unit/observation.json'][0])

    def test_reparse_file_metadata_is_rejected(self):
        fake = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0x400)
        with mock.patch.object(Path, 'lstat', return_value=fake):
            with self.assertRaises(ValueError):
                cache.regular(self.base / 'file')

    def test_lockfile_hardlink_to_unrelated_file_is_rejected(self):
        self.store.mkdir()
        original = self.base / 'unrelated.txt'
        original.write_bytes(b'0')
        try:
            os.link(original, self.store / '.prepare.lock')
        except OSError:
            self.skipTest('This filesystem cannot create hardlinks')
        with self.assertRaises(ValueError):
            with cache.preparation_lock(self.store):
                self.fail('A multi-link lockfile must not be used')
        self.assertEqual(original.read_bytes(), b'0')

    def test_filesystem_without_hardlinks_uses_verified_copy_fallback(self):
        with mock.patch.object(cache.os, 'link', side_effect=OSError(errno.ENOTSUP, 'Hardlinks unavailable')):
            result = self.prepare()
        self.assertTrue(result['passed'])
        self.assertEqual(result['copied'], len(self.entries))
        self.assert_payloads()
        self.assert_no_staging()

    def test_partial_copy_failure_removes_only_its_own_new_file(self):
        source = self.base / 'copy-source'
        target = self.base / 'copy-target'
        data = b'complete-original'
        source.write_bytes(data)
        def interrupted(incoming, outgoing, length):
            outgoing.write(incoming.read(3))
            raise OSError(errno.ENOSPC, 'Injected partial write failure')
        with mock.patch.object(cache.shutil, 'copyfileobj', side_effect=interrupted):
            with self.assertRaises(OSError):
                cache.exclusive_copy(source, target, {'bytes': len(data), 'sha256': digest(data)})
        self.assertFalse(target.exists(), 'Failed publication must not leave partial bytes')
        self.assertEqual(source.read_bytes(), data)

    def test_exclusive_copy_keeps_existing_different_file(self):
        source = self.base / 'copy-source'
        target = self.base / 'copy-target'
        source.write_bytes(b'original-pinned')
        target.write_bytes(b'preserve-existing')
        with self.assertRaises(ValueError):
            cache.exclusive_copy(source, target, {'bytes': source.stat().st_size, 'sha256': digest(source.read_bytes())})
        self.assertEqual(target.read_bytes(), b'preserve-existing')

    def test_postcopy_checksum_failure_removes_partial_publication(self):
        source = self.base / 'copy-source'
        target = self.base / 'copy-target'
        source.write_bytes(b'wrong-but-complete')
        with self.assertRaises(ValueError):
            cache.exclusive_copy(source, target, {'bytes': source.stat().st_size, 'sha256': '0' * 64})
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
