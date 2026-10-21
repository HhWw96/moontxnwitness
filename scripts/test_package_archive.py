"""Exercise large streaming output and privacy boundaries without a full build."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from package_archive import CHUNK_BYTES, sha256, write_archive


class ArchiveTests(unittest.TestCase):
    def test_large_output_without_whole_file_reads(self):
        with tempfile.TemporaryDirectory(prefix='mtw-zip-stream-') as temporary:
            root = Path(temporary)
            payload = os.urandom(CHUNK_BYTES * 33 + 17)
            (root / 'large.json').write_bytes(payload)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
                receipt = write_archive(root, ['large.json'], root / 'result.zip', 'fixture', ['private-path'])
            with zipfile.ZipFile(root / 'result.zip') as built:
                self.assertEqual(built.read('fixture/large.json'), payload)
                self.assertEqual(built.getinfo('fixture/large.json').date_time, (2026, 10, 10, 0, 0, 0))
            self.assertEqual(receipt['sha256'], sha256(root / 'result.zip'))

    def test_private_path_across_chunk_boundary_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='mtw-zip-private-') as temporary:
            root = Path(temporary)
            private = 'private-home-sentinel'
            (root / 'boundary.json').write_bytes(b'x' * (CHUNK_BYTES - 7) + private.encode() + b'end')
            with self.assertRaisesRegex(AssertionError, 'Local path found'):
                write_archive(root, ['boundary.json'], root / 'rejected.zip', 'fixture', [private])

    def test_deterministic_content_independent_of_mtime_and_input_order(self):
        with tempfile.TemporaryDirectory(prefix='mtw-zip-fixed-') as temporary:
            root = Path(temporary)
            (root / 'a.txt').write_text('hello', encoding='utf8')
            (root / 'empty.txt').write_bytes(b'')
            first = write_archive(root, ['empty.txt', 'a.txt'], root / 'first.zip', 'fixture', [])
            os.utime(root / 'a.txt', (1_000_000, 1_000_000))
            second = write_archive(root, ['a.txt', 'empty.txt'], root / 'second.zip', 'fixture', [])
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertEqual(first['files'], 2)


if __name__ == '__main__':
    unittest.main()
