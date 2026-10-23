"""Explicit opt-in capacity/streaming guards using small real files only.

No database, no performance timing, no large log generation. Large declarations
are exercised with short files; this does not validate GiB-scale throughput.
"""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import sys
import unittest
import uuid
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture._experimental_budget import PROFILE,LIMITS
from moontxnwitness_capture.source_sink import GroupedSourceSink,SourceSinkError,verify_grouped_source
from moontxnwitness_capture.instrumentation import Instrumentation,verify_lifecycle_storage
from moontxnwitness_capture.capture_v3 import CaptureV3Session
from moontxnwitness_capture.journal_v3 import SegmentedJournal,JournalReader,JournalIOError,_Identities,_json,INDEX,TRANSACTIONS,LOCK
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(ROOT/'artifacts/capacity-small-files')))/('capacity-'+uuid.uuid4().hex)
BASE.mkdir(parents=True)

class Tests(unittest.TestCase):
    def path(self,name):return BASE/(self._testMethodName+'-'+name+'-'+uuid.uuid4().hex)
    def source(self,**kwargs):return GroupedSourceSink(self.path('source'),**kwargs)
    def journal(self,**kwargs):return SegmentedJournal(self.path('journal'),**kwargs)
    def rewrite_index(self,path,mutate):
        data=json.loads(path.read_text(encoding='utf8'));data.pop('indexSha256');mutate(data)
        data['indexSha256']=hashlib.sha256(_json(data)).hexdigest();path.write_bytes(_json(data)+b'\n')
    def complete(self,journal,transactions=1):
        journal.append({'seq':1,'time':0,'kind':'snapshot','initial':{},'consistent':True})
        seq=2
        for i in range(transactions):
            tx='tx-'+str(i)+'-'+'0'*32
            for kind in ('begin','commit_request','commit_ok'):
                self.assertTrue(journal.append({'seq':seq,'time':seq,'kind':kind,'tx':tx}).accepted);seq+=1
        return journal.close(source_closed=True)
    def test_legacy_source_large_records_still_rejected(self):
        with self.assertRaises(ValueError):self.source(max_records=1_000_001)
    def test_legacy_source_large_bytes_still_rejected(self):
        with self.assertRaises(ValueError):self.source(max_total_bytes=1024**3+1)
    def test_optin_source_high_limits_real_short_file_matching_reader(self):
        source=self.source(experimental_budget=PROFILE,max_records=LIMITS['sourceRecords'],max_total_bytes=LIMITS['sourceBytes'])
        source.append({'kind':'source-batch','value':'retained'});result=source.close()
        self.assertTrue(result['storageSealed']);self.assertLess(source.path.stat().st_size,4096)
        self.assertEqual(verify_grouped_source(source.path,experimental_budget=PROFILE)['sha256'],result['sha256'])
        with self.assertRaises(ValueError):verify_grouped_source(source.path)
    def test_unknown_source_profile_rejected(self):
        with self.assertRaises(ValueError):self.source(experimental_budget=PROFILE+'-unregistered')
    def test_source_reader_rejects_rehashed_above_profile_limit(self):
        source=self.source(experimental_budget=PROFILE);source.close()
        self.rewrite_index(source.index,lambda d:d['limits'].update(records=LIMITS['sourceRecords']+1))
        with self.assertRaises(SourceSinkError):verify_grouped_source(source.path,experimental_budget=PROFILE)
    def test_source_tiny_runtime_budget_keeps_failure(self):
        source=self.source(experimental_budget=PROFILE,max_total_bytes=512,max_record_bytes=256)
        refusal=False
        for i in range(20):refusal=not source.append({'kind':'source-batch','n':i}).accepted or refusal
        self.assertTrue(refusal)
        try:result=source.close()
        except SourceSinkError:return
        self.assertFalse(result['storageSealed'])
    def test_legacy_lifecycle_large_bytes_still_rejected(self):
        with self.assertRaises(ValueError):Instrumentation(self.path('life'),max_lifecycle_bytes=1024**3+1)
    def test_legacy_lifecycle_large_records_still_rejected(self):
        with self.assertRaises(ValueError):Instrumentation(self.path('life'),max_lifecycle_records=2_000_001)
    def test_optin_lifecycle_short_stream_verifies_and_requires_optin(self):
        observer=Instrumentation(self.path('observer'),experimental_budget=PROFILE,max_lifecycle_bytes=LIMITS['lifecycleBytes'],max_lifecycle_records=LIMITS['lifecycleRecords'])
        observer.note('small-observation',value='retained');observer.close()
        meta=json.loads((observer.output/'instrumentation.json').read_text(encoding='utf8'))['lifecycle']
        result=verify_lifecycle_storage(observer.output/'lifecycle.jsonl',meta,experimental_budget=PROFILE)
        self.assertTrue(result['storageSealed']);self.assertFalse(result['semanticCoverage'])
        self.assertLess(result['bytes'],4096)
        with self.assertRaises(ValueError):verify_lifecycle_storage(observer.output/'lifecycle.jsonl',meta)
    def test_lifecycle_stream_rejects_tampering(self):
        observer=Instrumentation(self.path('observer'),experimental_budget=PROFILE);observer.note('small-observation',value='old');observer.close()
        meta=json.loads((observer.output/'instrumentation.json').read_text(encoding='utf8'))['lifecycle'];path=observer.output/'lifecycle.jsonl'
        path.write_bytes(path.read_bytes().replace(b'"value":"old"',b'"value":"bad"'))
        with self.assertRaises(ValueError):verify_lifecycle_storage(path,meta,experimental_budget=PROFILE)
    def test_lifecycle_tiny_budget_never_claims_sealed(self):
        observer=Instrumentation(self.path('observer'),experimental_budget=PROFILE,max_lifecycle_bytes=4096,max_lifecycle_records=128)
        for i in range(50):observer.note('small-observation',value='x'*100)
        observer.close();meta=json.loads((observer.output/'instrumentation.json').read_text(encoding='utf8'))['lifecycle']
        self.assertFalse(meta['sealed'])
        with self.assertRaises(ValueError):verify_lifecycle_storage(observer.output/'lifecycle.jsonl',meta,experimental_budget=PROFILE)
    def test_journal_experimental_requires_explicit_reader(self):
        journal=self.journal(experimental_budget=PROFILE,max_total_bytes=LIMITS['journalBytes'],transaction_index_bytes=64*1024)
        self.assertTrue(self.complete(journal).complete)
        self.assertFalse(JournalReader(journal.path).verify().valid)
        self.assertTrue(JournalReader(journal.path,experimental_budget=PROFILE).verify().complete)
        meta=json.loads((journal.path/INDEX).read_text(encoding='utf8'))
        self.assertEqual(meta['limits']['totalBytes'],LIMITS['journalBytes']);self.assertEqual(meta['transactionIndex']['maxBytes'],64*1024)
    def test_journal_experimental_above_profile_ceiling_refused(self):
        with self.assertRaises(ValueError):self.journal(experimental_budget=PROFILE,max_total_bytes=LIMITS['journalBytes']+1)
    def test_legacy_journal_format_has_no_new_marker(self):
        journal=self.journal();self.assertTrue(self.complete(journal).complete)
        meta=json.loads((journal.path/INDEX).read_text(encoding='utf8'))
        self.assertNotIn('experimentalBudget',meta);self.assertNotIn('maxBytes',meta['transactionIndex'])
    def test_sqlite_page_cap_enforced_before_growth(self):
        path=self.path('sqlite');identities=_Identities(path,byte_limit=8192)
        try:
            self.assertEqual(identities.connection.execute('PRAGMA max_page_count').fetchone()[0],2)
            with self.assertRaises(sqlite3.OperationalError):
                for i in range(500):identities.add('tx-'+str(i)+'-'+'a'*128,i)
        finally:identities.close()
        self.assertLessEqual(path.stat().st_size,8192)
    def test_sqlite_budget_requires_optin_and_alignment(self):
        for kwargs in [{'transaction_index_bytes':8192},{'experimental_budget':PROFILE,'transaction_index_bytes':8193},{'experimental_budget':PROFILE,'transaction_index_bytes':4096}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.journal(**kwargs)
    def test_rebuilt_sqlite_cannot_silently_expand_declared_budget(self):
        journal=self.journal(experimental_budget=PROFILE,transaction_index_bytes=64*1024);self.assertTrue(self.complete(journal,transactions=180).complete)
        self.assertGreater((journal.path/TRANSACTIONS).stat().st_size,8192)
        self.rewrite_index(journal.path/INDEX,lambda d:d['transactionIndex'].update(maxBytes=8192))
        result=JournalReader(journal.path,experimental_budget=PROFILE).verify();self.assertFalse(result.valid)
    def test_optin_does_not_extend_export_limit(self):
        journal=self.journal(experimental_budget=PROFILE);self.complete(journal)
        target=self.path('export')
        with self.assertRaises(ValueError):JournalReader(journal.path,experimental_budget=PROFILE).export(target,clock_domain='test',max_bytes=8*1024*1024+1)
        self.assertFalse(target.exists())
    def test_session_cannot_hide_profile_inside_journal_options(self):
        with self.assertRaises(ValueError):CaptureV3Session(self.path('session'),journal_options={'experimental_budget':PROFILE})
    def test_verifiers_do_not_use_read_bytes_for_whole_logs(self):
        source=self.source(experimental_budget=PROFILE);source.close()
        journal=self.journal(experimental_budget=PROFILE);self.complete(journal)
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read forbidden')):
            self.assertTrue(verify_grouped_source(source.path,experimental_budget=PROFILE)['storageSealed'])
            self.assertTrue(JournalReader(journal.path,experimental_budget=PROFILE).verify().complete)

if __name__=='__main__':unittest.main(verbosity=2)
