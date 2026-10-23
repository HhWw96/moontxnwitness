"""Post-measurement retention tests; no database or performance run."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('cell_archive',Path(__file__).with_name('cell_archive.py'))
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cell=self.root/'cell-0';self.cell.mkdir()
        (self.cell/'receipt.json').write_bytes(b'{"status":"passed","formalProtocolCompleted":true}\r\n')
        (self.cell/'capture').mkdir();(self.cell/'capture/raw.jsonl').write_bytes(b'{"x":1}\r\n'+bytes(range(256)))
        (self.cell/'empty').write_bytes(b'')
    def tearDown(self):self.temp.cleanup()
    def test_exact_roundtrip_and_default_retains_originals(self):
        pointer=m.archive_cell(self.root,self.cell)
        self.assertTrue((self.cell/'capture/raw.jsonl').exists())
        result=m.restore_archive(self.root/pointer['archive'],self.root/'restored',expected_sha256=pointer['archiveSha256'])
        self.assertTrue(result['verified']);self.assertEqual((self.root/'restored/capture/raw.jsonl').read_bytes(),(self.cell/'capture/raw.jsonl').read_bytes())
        self.assertEqual((self.root/'restored/receipt.json').read_bytes(),(self.cell/'receipt.json').read_bytes())
    def test_release_only_after_verified_archive_keeps_pointer(self):
        pointer=m.archive_cell(self.root,self.cell);m.release_cell(self.root,self.cell,pointer)
        self.assertEqual([p.name for p in self.cell.iterdir()],['archive-pointer.json'])
        self.assertTrue(m.verify_archive(self.root/pointer['archive'],expected_sha256=pointer['archiveSha256'])['verified'])
    def test_tampered_archive_keeps_raw(self):
        pointer=m.archive_cell(self.root,self.cell);path=self.root/pointer['archive']
        path.write_bytes(path.read_bytes()+b'tampered')
        with self.assertRaises(ValueError):m.release_cell(self.root,self.cell,pointer)
        self.assertTrue((self.cell/'capture/raw.jsonl').exists())
    def test_changed_raw_keeps_all_originals(self):
        pointer=m.archive_cell(self.root,self.cell);(self.cell/'empty').write_bytes(b'changed')
        with self.assertRaises(ValueError):m.release_cell(self.root,self.cell,pointer)
        self.assertTrue((self.cell/'receipt.json').exists())
    def test_new_unarchived_file_prevents_release(self):
        pointer=m.archive_cell(self.root,self.cell);(self.cell/'new').write_bytes(b'new')
        with self.assertRaises(ValueError):m.release_cell(self.root,self.cell,pointer)
        self.assertTrue((self.cell/'receipt.json').exists())
    def test_refuse_outside_or_noncell_targets(self):
        with self.assertRaises(ValueError):m.archive_cell(self.root,self.root)
        with self.assertRaises(ValueError):m.archive_cell(self.root,self.root/'other')
    def test_existing_restore_refused(self):
        pointer=m.archive_cell(self.root,self.cell)
        with self.assertRaises(FileExistsError):m.restore_archive(self.root/pointer['archive'],self.cell)
    def test_cli_restore_in_fresh_process_uses_expected_zip_sha(self):
        pointer=m.archive_cell(self.root,self.cell);m.release_cell(self.root,self.cell,pointer)
        result=subprocess.run([sys.executable,'-B',m.__file__,str(self.root/pointer['archive']),
            '--sha256',pointer['archiveSha256'],'--restore',str(self.root/'restored-by-cli')],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        self.assertTrue(json.loads(result.stdout)['verified'])
        self.assertEqual(hashlib.sha256((self.root/'restored-by-cli/receipt.json').read_bytes()).hexdigest(),pointer['originalReceiptSha256'])
    def test_unsafe_zip_path_refused(self):
        path=self.root/'bad.zip'
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('../escape',b'bad')
        with self.assertRaises(ValueError):m.verify_archive(path)
        self.assertFalse((self.root.parent/'escape').exists())
    def test_duplicate_member_refused(self):
        pointer=m.archive_cell(self.root,self.cell);path=self.root/pointer['archive']
        with zipfile.ZipFile(path,'a') as archive:
            import warnings
            with warnings.catch_warnings():warnings.simplefilter('ignore');archive.writestr('receipt.json',b'bad')
        with self.assertRaises(ValueError):m.verify_archive(path)
    def test_expanded_size_limit_refused(self):
        pointer=m.archive_cell(self.root,self.cell)
        with self.assertRaises(ValueError):m.verify_archive(self.root/pointer['archive'],max_total_bytes=1)
    def test_failed_receipt_remains_failed_after_restoration(self):
        (self.cell/'receipt.json').write_text('{"status":"failed","formalProtocolCompleted":false}')
        pointer=m.archive_cell(self.root,self.cell)
        self.assertEqual(pointer['cellStatus'],'failed')
        m.release_cell(self.root,self.cell,pointer)
        m.restore_archive(self.root/pointer['archive'],self.root/'restored')
        self.assertFalse(json.loads((self.root/'restored/receipt.json').read_text())['formalProtocolCompleted'])
    def test_symlink_refused_when_supported(self):
        link=self.cell/'link'
        try:link.symlink_to(self.cell/'receipt.json')
        except OSError:self.skipTest('host does not permit symlink creation')
        with self.assertRaises(ValueError):m.archive_cell(self.root,self.cell)

if __name__=='__main__':unittest.main(verbosity=2)
