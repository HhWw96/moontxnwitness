"""Public transport/ZIP regressions; fake HTTP only, no network or compiler."""
from __future__ import annotations
import hashlib
import io
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from publication_download import (CHUNK_BYTES, MAX_DOWNLOAD_BYTES, PublicationDownloadError,
                                  download_file, extract_zip, sha256_file)

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'artifacts/publication-download-tests'
PARENT.mkdir(parents=True, exist_ok=True)
SESSION = Path(tempfile.mkdtemp(prefix='run-', dir=PARENT)).resolve()
assert SESSION.is_relative_to(PARENT.resolve())


class FakeResponse:
    def __init__(self, content=b'abc', *, size=None, length='auto', status=200):
        self.content, self.size = content, len(content) if size is None else size
        self.position, self.read_sizes, self.status = 0, [], status
        self.headers = {} if length is None else {'Content-Length': str(self.size) if length == 'auto' else str(length)}
        self.before_eof = None
        self.url = 'https://example.test/asset'
    def __enter__(self):return self
    def __exit__(self, *args):return False
    def geturl(self):return self.url
    def read(self, count):
        self.read_sizes.append(count)
        if self.position == self.size:
            if self.before_eof:self.before_eof();self.before_eof = None
            return b''
        count = min(count, self.size - self.position)
        if self.content == b'q':value = b'q' * count
        else:value = self.content[self.position:self.position + count]
        self.position += len(value)
        return value


class PublicationDownloadTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=SESSION))
        self.target = self.root / 'asset.zip'
    def opener(self, response):
        def open_(request, **options):
            self.assertNotIn('Authorization', request.headers)
            self.assertEqual(request.full_url, 'https://example.test/asset')
            return response
        return open_
    def fetch(self, response, **options):
        return download_file('https://example.test/asset', self.target, opener=self.opener(response), **options)
    def failed_partial(self):
        self.assertFalse(self.target.exists())
        paths = list(self.root.glob('asset.zip.partial-*'))
        self.assertEqual(len(paths), 1)
        return paths[0]
    def make_zip(self, entries, filename='input.zip'):
        path = self.root / filename
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as packed:
                for name, value in entries:packed.writestr(name, value)
        return path
    def reject_zip(self, entries, **limits):
        path = self.make_zip(entries)
        destination = self.root / 'expanded'
        with self.assertRaises((PublicationDownloadError, zipfile.BadZipFile)):
            extract_zip(path, destination, **limits)
        self.assertTrue(destination.is_dir())
        return destination

    def test_large_response_above_old_16mib_limit_uses_bounded_reads(self):
        response = FakeResponse(b'q', size=17 * 1024 * 1024 + 3)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Whole-file read')):
            self.fetch(response)
            actual = sha256_file(self.target)
        digest = hashlib.sha256()
        remaining = response.size
        while remaining:
            count = min(CHUNK_BYTES, remaining);digest.update(b'q' * count);remaining -= count
        self.assertEqual(actual, digest.hexdigest())
        self.assertGreater(len(response.read_sizes), 200)
        self.assertLessEqual(max(response.read_sizes), CHUNK_BYTES)
        self.assertFalse(list(self.root.glob('*.partial-*')))

    def test_chunked_response_and_exact_digest(self):
        expected = hashlib.sha256(b'abc').hexdigest()
        self.fetch(FakeResponse(length=None), expected_sha256=expected)
        self.assertEqual(sha256_file(self.target), expected)

    def test_exact_small_download_limit_is_accepted(self):
        self.fetch(FakeResponse(), max_bytes=3)
        self.assertEqual(self.target.stat().st_size, 3)

    def test_advertised_oversize_does_not_read_body(self):
        response = FakeResponse(size=MAX_DOWNLOAD_BYTES + 1)
        with self.assertRaises(PublicationDownloadError):self.fetch(response)
        self.assertEqual(response.read_sizes, [])
        self.assertEqual(self.failed_partial().stat().st_size, 0)

    def test_chunked_overrun_retains_first_failure_bytes(self):
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(b'123456789', length=None), max_bytes=8)
        self.assertEqual(self.failed_partial().read_bytes(), b'123456789')

    def test_short_content_length_is_not_success(self):
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(length=8))
        self.assertEqual(self.failed_partial().read_bytes(), b'abc')

    def test_malformed_content_length_is_rejected(self):
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(length='-1'))
        self.failed_partial()

    def test_wrong_digest_retains_complete_failed_download(self):
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(), expected_sha256='0' * 64)
        self.assertEqual(self.failed_partial().read_bytes(), b'abc')

    def test_http_failure_is_not_published(self):
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(status=404))
        self.failed_partial()

    def test_network_exception_retains_empty_attempt(self):
        def unavailable(*args, **kwargs):raise OSError('offline')
        with self.assertRaises(OSError):download_file('https://example.test/asset', self.target, opener=unavailable)
        self.failed_partial()

    def test_existing_download_is_never_overwritten(self):
        self.target.write_bytes(b'existing')
        with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse())
        self.assertEqual(self.target.read_bytes(), b'existing')

    def test_destination_race_is_exclusive_and_preserves_download(self):
        response = FakeResponse();response.before_eof = lambda:self.target.write_bytes(b'new owner')
        with self.assertRaises(FileExistsError):self.fetch(response)
        self.assertEqual(self.target.read_bytes(), b'new owner')
        self.assertEqual(next(self.root.glob('asset.zip.partial-*')).read_bytes(), b'abc')

    def test_download_wall_clock_budget(self):
        with patch('publication_download.time.monotonic', side_effect=[0, 100]):
            with self.assertRaises(PublicationDownloadError):self.fetch(FakeResponse(), max_seconds=1)
        self.failed_partial()

    def test_response_cannot_return_more_than_requested(self):
        response = FakeResponse()
        response.read = lambda count:b'x' * (count + 1)
        with self.assertRaises(PublicationDownloadError):self.fetch(response, max_bytes=8)
        self.failed_partial()

    def test_non_https_or_embedded_credentials_are_rejected(self):
        for url in ('http://example.test/asset', 'https://user:secret@example.test/asset', 'https://@example.test/asset'):
            with self.subTest(url=url), self.assertRaises(PublicationDownloadError):
                download_file(url, self.target, opener=lambda *a, **k:None)

    def test_redirect_cannot_downgrade_https(self):
        response=FakeResponse();response.url='http://example.test/asset'
        with self.assertRaises(PublicationDownloadError):self.fetch(response)
        self.assertEqual(response.read_sizes,[]);self.failed_partial()

    def test_hash_budget_is_enforced(self):
        self.target.write_bytes(b'1234')
        with self.assertRaises(PublicationDownloadError):sha256_file(self.target, max_bytes=3)

    def test_normal_zip_streams_and_returns_member_hashes(self):
        path = self.make_zip([('release/', b''), ('release/a.txt', b'hello'), ('release/sub/b.txt', b'world')])
        destination = self.root / 'expanded'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Whole-file read')):
            result = extract_zip(path, destination)
        self.assertEqual(result['entries'], 3);self.assertEqual(result['files'], 2)
        self.assertEqual(result['uncompressedBytes'], 10)
        self.assertEqual(result['members']['release/a.txt']['sha256'], hashlib.sha256(b'hello').hexdigest())
        self.assertEqual((destination/'release/sub/b.txt').read_bytes(), b'world')

    def test_existing_extraction_destination_is_preserved(self):
        path = self.make_zip([('file', b'data')]);destination = self.root/'expanded';destination.mkdir()
        marker = destination/'existing';marker.write_bytes(b'keep')
        with self.assertRaises(PublicationDownloadError):extract_zip(path, destination)
        self.assertEqual(marker.read_bytes(), b'keep')

    def test_traversal_absolute_and_windows_unsafe_names(self):
        names = ('../outside', '/absolute', 'C:/drive', 'dir\\name', 'dir/../outside', 'dir//file', 'CON.txt',
                 'dir/nul', 'trailing.', 'space ', 'dir/name:stream', 'dir/./file', 'dir/pipe|name')
        for index, name in enumerate(names):
            with self.subTest(name=name):
                path=self.make_zip([(name,b'bad')], filename=str(index)+'.zip')
                if '\\' in name:
                    # Windows ZipInfo normalizes os.sep during construction;
                    # patch both raw header names to exercise a real bad ZIP.
                    path.write_bytes(path.read_bytes().replace(name.replace('\\','/').encode(),name.encode()))
                with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/('out-'+str(index)))
        self.assertFalse((self.root/'outside').exists())

    def test_symlink_and_special_zip_entries_are_refused(self):
        for index, mode in enumerate((stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR)):
            item=zipfile.ZipInfo('link');item.create_system=3;item.external_attr=(mode|0o777)<<16
            path=self.make_zip([(item,b'../outside')],filename=str(index)+'.zip')
            with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/('out-'+str(index)))

    def test_duplicate_member_is_rejected_before_any_payload(self):
        destination=self.reject_zip([('file',b'a'),('file',b'b')])
        self.assertEqual(list(destination.iterdir()), [])

    def test_casefold_and_unicode_directory_aliases_are_rejected(self):
        for index, entries in enumerate(([('A/x',b'1'),('a/y',b'2')], [('Café/x',b'1'),('Café/y',b'2')])):
            path=self.make_zip(entries,filename=str(index)+'.zip')
            with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/('out-'+str(index)))

    def test_file_parent_conflict_is_rejected(self):
        self.reject_zip([('parent',b'x'),('parent/child',b'y')])

    def test_member_and_aggregate_expansion_limits(self):
        path=self.make_zip([('a',b'1234'),('b',b'5678')])
        with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/'member',max_member_bytes=3)
        with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/'total',max_total_bytes=7)

    def test_entry_budget_is_checked_before_zipfile_metadata_allocation(self):
        path=self.make_zip([('a',b'1'),('b',b'2')])
        with patch('publication_download.zipfile.ZipFile',side_effect=AssertionError('Allocated unbounded metadata')):
            with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/'expanded',max_entries=1)

    def test_directory_size_budget_is_checked_before_zipfile(self):
        path=self.make_zip([('a',b'1')]);raw=bytearray(path.read_bytes());offset=raw.rfind(b'PK\x05\x06')
        struct.pack_into('<L',raw,offset+12,33*1024*1024);path.write_bytes(raw)
        with patch('publication_download.zipfile.ZipFile',side_effect=AssertionError('Allocated oversized metadata')):
            with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/'expanded')

    def test_zip64_and_multiple_volumes_are_refused_by_preflight(self):
        for index, (field, value) in enumerate(((10,65535),(4,1))):
            path=self.make_zip([('a',b'1')],filename=str(index)+'.zip');raw=bytearray(path.read_bytes())
            offset=raw.rfind(b'PK\x05\x06');struct.pack_into('<H',raw,offset+field,value);path.write_bytes(raw)
            with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/('out-'+str(index)))

    def test_nul_name_truncation_is_not_accepted(self):
        path=self.make_zip([('evilXname',b'1')]);path.write_bytes(path.read_bytes().replace(b'evilXname',b'evil\0name'))
        with self.assertRaises(PublicationDownloadError):extract_zip(path,self.root/'expanded')

    def test_actual_zip_stream_overrun_keeps_first_partial_output(self):
        path=self.make_zip([('a',b'abc')]);destination=self.root/'expanded'
        with patch.object(zipfile.ZipFile,'open',return_value=io.BytesIO(b'abcX')):
            with self.assertRaises(PublicationDownloadError):extract_zip(path,destination)
        self.assertTrue((destination/'a').is_file())


if __name__ == '__main__':
    print('Publication download test artifacts: ' + str(SESSION),flush=True)
    unittest.main(verbosity=2)
