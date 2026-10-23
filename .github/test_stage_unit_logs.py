"""Offline file-only checks for receipt-bound CI log retention."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import stage_unit_logs as controller

SCRATCH = Path(os.environ.get('MTW_CI_LOG_TEST_ROOT', str(Path(__file__).resolve().parents[1] / 'artifacts/ci-unit-log-controller-tests')))
SCRATCH.mkdir(parents=True, exist_ok=True)


def raw_json(value):
    return (json.dumps(value, indent=2) + '\n').encode()


class Tests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=SCRATCH))
        self.rows = []
        self.index = self.root / controller.INDEX
        self.index.parent.mkdir(parents=True)

    def fixture(self, label='unit-current', *, raw=b'original failure\n', reference=None, present=True, passed=False):
        name = 'verification/capture-persistence/' + label + '/receipt.json'
        parent = self.root / Path(name).parent
        parent.mkdir(parents=True)
        ref = {'file': 'first.log', 'sha256': controller.digest(raw)} if reference is None else reference
        receipt = {'passed': passed, 'testsRun': 74, 'failures': 0 if passed else 1, 'log': ref}
        data = raw_json(receipt)
        (self.root / name).write_bytes(data)
        staged = self.root / controller.DESTINATION / name
        staged.parent.mkdir(parents=True)
        staged.write_bytes(data)
        if present:
            (parent / 'first.log').write_bytes(raw)
        self.rows.append({'file': name, 'bytes': len(data), 'sha256': controller.digest(data)})
        self.refresh()
        return name, parent / 'first.log'

    def refresh(self):
        self.index.write_bytes(raw_json({'schema': 1, 'sourceCommit': 'a' * 40, 'runId': '123', 'runAttempt': '1', 'files': self.rows}))

    def run_guard(self, **kwargs):
        result = controller.retain_receipt_logs(self.root, **kwargs)
        saved = json.loads((self.root / controller.DESTINATION / controller.APPENDIX).read_bytes())
        self.assertEqual(result, saved)
        return result

    def test_exact_original_bytes_retained_and_index_receipt_unchanged(self):
        name, log = self.fixture(raw=b'\x00\xffraw\r\nbytes\n')
        before = {p: p.read_bytes() for p in [self.index, self.root/name, self.root/controller.DESTINATION/name, log]}
        result = self.run_guard(expected_run_id='123', expected_run_attempt='1')
        self.assertTrue(result['passed']); self.assertEqual(len(result['logs']), 1)
        self.assertEqual((self.root/controller.DESTINATION/log.relative_to(self.root)).read_bytes(), log.read_bytes())
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_ignored_log_not_in_original_index_is_still_retained(self):
        self.fixture(); (self.root/'.gitignore').write_bytes(b'*.log\n')
        self.assertTrue(all(not row['file'].endswith('.log') for row in self.rows))
        result = self.run_guard(); self.assertTrue(result['passed'])
        self.assertEqual(result['logs'][0]['status'], 'copied-exact-original')

    def test_missing_log_remains_explicit_failure(self):
        self.fixture(present=False); result=self.run_guard()
        self.assertFalse(result['passed']); self.assertEqual(result['logs'][0]['error'], 'source-log-missing')

    def test_log_sha_tampering_is_not_copied(self):
        _, log=self.fixture(); log.write_bytes(b'tampered')
        result=self.run_guard(); self.assertFalse(result['passed'])
        self.assertEqual(result['logs'][0]['error'], 'source-log-sha256-mismatch')
        self.assertFalse((self.root/controller.DESTINATION/log.relative_to(self.root)).exists())

    def test_original_receipt_changed_after_staging_is_rejected(self):
        name,_=self.fixture(); (self.root/name).write_bytes(b'{}')
        result=self.run_guard(); self.assertFalse(result['passed'])
        self.assertEqual(result['logs'][0]['error'], 'original-receipt-differs-from-staging')

    def test_staged_receipt_changed_after_index_is_rejected(self):
        name,_=self.fixture(); (self.root/controller.DESTINATION/name).write_bytes(b'{}')
        result=self.run_guard(); self.assertFalse(result['passed'])
        self.assertEqual(result['logs'][0]['error'], 'staged-receipt-index-mismatch')

    def test_single_windows_separator_cannot_escape_receipt_directory(self):
        raw=b'outside original log\n'
        self.fixture(reference={'file':'..'+chr(92)+'outside.log','sha256':controller.digest(raw)})
        (self.root/'verification/capture-persistence/outside.log').write_bytes(raw)
        result=self.run_guard()
        self.assertFalse(result['passed'])
        self.assertEqual(result['logs'][0]['error'],'unsafe-relative-path')

    def test_several_hundred_kib_log_is_retained_without_truncation(self):
        raw=(b'full original diagnostic line\r\n'*16384)
        self.assertGreater(len(raw),256*1024)
        _,log=self.fixture(raw=raw)
        result=self.run_guard()
        self.assertTrue(result['passed'])
        self.assertEqual(result['retainedLogBytes'],len(raw))
        self.assertEqual((self.root/controller.DESTINATION/log.relative_to(self.root)).read_bytes(),raw)

    def test_parent_escape_rejected(self):
        self.fixture(reference={'file':'../outside.log','sha256':'a'*64})
        self.assertEqual(self.run_guard()['logs'][0]['error'], 'unsafe-relative-path')

    def test_absolute_path_rejected(self):
        self.fixture(reference={'file':'/outside.log','sha256':'a'*64})
        self.assertEqual(self.run_guard()['logs'][0]['error'], 'unsafe-relative-path')

    def test_backslash_windows_escape_rejected(self):
        self.fixture(reference={'file':r'..\outside.log','sha256':'a'*64})
        self.assertEqual(self.run_guard()['logs'][0]['error'], 'unsafe-relative-path')

    def test_windows_drive_and_alternate_stream_rejected(self):
        self.fixture(reference={'file':'C:first.log','sha256':'a'*64})
        self.assertEqual(self.run_guard()['logs'][0]['error'], 'unsafe-relative-path')

    def test_subdirectory_is_outside_same_receipt_directory(self):
        self.fixture(reference={'file':'nested/first.log','sha256':'a'*64})
        self.assertEqual(self.run_guard()['logs'][0]['error'], 'log-must-be-in-receipt-directory')

    def test_per_log_budget_not_silently_skipped(self):
        self.fixture(raw=b'12345678'); result=self.run_guard(limits=controller.Limits(log_bytes=7))
        self.assertFalse(result['passed']); self.assertEqual(result['logs'][0]['error'], 'source-log-byte-budget')
        self.assertEqual(result['logs'][0]['sourceBytes'], 8); self.assertFalse(result['logs'][0]['retained'])

    def test_total_log_budget_keeps_prior_original_and_records_refusal(self):
        self.fixture('one',raw=b'12345678'); self.fixture('two',raw=b'abcdefgh')
        result=self.run_guard(limits=controller.Limits(total_log_bytes=15))
        self.assertFalse(result['passed']); self.assertTrue(result['logs'][0]['retained'])
        self.assertEqual(result['logs'][1]['error'], 'total-log-byte-budget')
        self.assertEqual(result['retainedLogBytes'], 8)

    def test_exact_log_budget_finishes(self):
        self.fixture(raw=b'12345678'); result=self.run_guard(limits=controller.Limits(log_bytes=8,total_log_bytes=8))
        self.assertTrue(result['passed']); self.assertEqual(result['retainedLogBytes'], 8)

    def test_existing_same_staged_log_is_verified_without_overwrite(self):
        _,log=self.fixture(); staged=self.root/controller.DESTINATION/log.relative_to(self.root)
        staged.write_bytes(log.read_bytes()); before=staged.stat().st_mtime_ns
        result=self.run_guard(); self.assertTrue(result['passed'])
        self.assertEqual(result['logs'][0]['status'], 'already-present-verified'); self.assertEqual(staged.stat().st_mtime_ns,before)

    def test_existing_different_staged_log_is_preserved_and_refused(self):
        _,log=self.fixture(); staged=self.root/controller.DESTINATION/log.relative_to(self.root); staged.write_bytes(b'older bytes')
        result=self.run_guard(); self.assertFalse(result['passed'])
        self.assertEqual(result['logs'][0]['error'], 'existing-staged-log-differs'); self.assertEqual(staged.read_bytes(),b'older bytes')

    def test_duplicate_index_entry_is_rejected(self):
        self.fixture(); self.rows.append(self.rows[0].copy()); self.refresh()
        result=self.run_guard(); self.assertFalse(result['passed']); self.assertIn('duplicate-index-file',result['errors'])

    def test_wrong_current_run_is_rejected(self):
        self.fixture(); result=self.run_guard(expected_run_id='456')
        self.assertFalse(result['passed']); self.assertIn('index-run-id-mismatch',result['errors'])

    def test_wrong_current_attempt_is_rejected(self):
        self.fixture(); result=self.run_guard(expected_run_attempt='2')
        self.assertFalse(result['passed']); self.assertIn('index-run-attempt-mismatch',result['errors'])

    def test_unselected_historical_receipt_is_not_followed(self):
        self.fixture(); old=self.root/'verification/older/receipt.json'; old.parent.mkdir(); old.write_bytes(raw_json({'log':{'file':'missing.log','sha256':'a'*64}}))
        result=self.run_guard(); self.assertTrue(result['passed']); self.assertEqual(result['selectedReceipts'],1)

    def test_failed_unit_receipt_stays_failed_when_log_retention_succeeds(self):
        name,_=self.fixture(passed=False); result=self.run_guard(); self.assertTrue(result['passed'])
        original=json.loads((self.root/name).read_bytes()); staged=json.loads((self.root/controller.DESTINATION/name).read_bytes())
        self.assertFalse(original['passed']); self.assertEqual(original['failures'],1); self.assertEqual(original,staged)

    def test_malformed_direct_binding_fails_visibly(self):
        self.fixture(reference={'file':'first.log'}); result=self.run_guard()
        self.assertFalse(result['passed']); self.assertEqual(result['logs'][0]['error'],'invalid-direct-log-binding')

    def test_other_good_logs_survive_missing_log_failure(self):
        self.fixture('missing',present=False); self.fixture('good')
        result=self.run_guard(); self.assertFalse(result['passed']); self.assertFalse(result['logs'][0]['retained']); self.assertTrue(result['logs'][1]['retained'])

    def test_index_traversal_is_rejected_even_when_not_receipt(self):
        self.fixture(); self.rows.append({'file':'../outside','bytes':0,'sha256':'a'*64}); self.refresh()
        result=self.run_guard(); self.assertFalse(result['passed']); self.assertIn('unsafe-relative-path',result['errors'])

    def test_unbound_receipt_does_not_invent_log_reference(self):
        name,_=self.fixture(); raw=raw_json({'passed':False})
        (self.root/name).write_bytes(raw); (self.root/controller.DESTINATION/name).write_bytes(raw)
        self.rows[0].update(bytes=len(raw),sha256=controller.digest(raw)); self.refresh()
        result=self.run_guard(); self.assertTrue(result['passed']); self.assertEqual(result['logs'],[]); self.assertEqual(result['receiptsWithoutDirectLog'],1)

    def test_missing_index_fails_and_writes_appendix(self):
        result=self.run_guard(); self.assertFalse(result['passed']); self.assertIn('index-missing',result['errors'])

    def test_existing_appendix_is_never_overwritten(self):
        self.fixture(); self.run_guard(); file=self.root/controller.DESTINATION/controller.APPENDIX; old=file.read_bytes()
        with self.assertRaisesRegex(controller.RetentionError,'already-exists'):self.run_guard()
        self.assertEqual(file.read_bytes(),old)

    def test_symlink_detection_fails_closed_without_platform_privileges(self):
        _,log=self.fixture(); original=Path.is_symlink
        with mock.patch.object(Path,'is_symlink',lambda p: p==log or original(p)):
            result=self.run_guard()
        self.assertFalse(result['passed']); self.assertEqual(result['logs'][0]['error'],'symlink-or-junction-refused')

    def test_cli_requires_ci_context(self):
        self.fixture(); env=os.environ.copy()
        for name in ['GITHUB_ACTIONS','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT']:env.pop(name,None)
        q=subprocess.run([sys.executable,'-B',str(Path(controller.__file__)),'--root',str(self.root)],env=env,capture_output=True,timeout=10)
        self.assertEqual(q.returncode,2); self.assertEqual(json.loads(q.stdout)['error'],'CI-only-controller')

    def test_cli_current_context_produces_exact_retention(self):
        self.fixture(); env=os.environ.copy(); env.update(GITHUB_ACTIONS='true',GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1')
        q=subprocess.run([sys.executable,'-B',str(Path(controller.__file__)),'--root',str(self.root)],env=env,capture_output=True,timeout=10)
        self.assertEqual(q.returncode,0,q.stderr); self.assertTrue(json.loads(q.stdout)['passed'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({'kind':'ci-unit-log-retention-controller-tests','passed':result.wasSuccessful(),
                      'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                      'skipped':len(result.skipped),'actualDatabaseExecution':False,'formalPerformanceMeasured':False}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
