"""Shared queue/grouped source durability tests; real local files, no DB."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.source_sink import GroupedSourceSink,SourceSinkError,verify_grouped_source
from moontxnwitness_capture._orm_source_sink import SourceSink,verify as verify_legacy
from moontxnwitness_capture._durable_policy import CapacityQueue,sync_due,sync_wait,should_sync

BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(Path.cwd()/'artifacts/source-sink-unit')))
RUN=BASE/('source-group-'+uuid.uuid4().hex);RUN.mkdir(parents=True)


class Tests(unittest.TestCase):
    def setUp(self):self.sinks=[]
    def sink(self,**options):
        path=RUN/(self.id().split('.')[-1]+'-'+uuid.uuid4().hex+'.jsonl')
        sink=GroupedSourceSink(path,**options);self.sinks.append(sink);return sink
    def tearDown(self):
        for sink in self.sinks:
            try:sink.close()
            except SourceSinkError:pass
    def test_shared_capacity_counts_inflight_and_reservation(self):
        q=CapacityQueue(512);q.reserve(256);q.enqueue(('data',),200);q.release_reservation(256)
        self.assertTrue(q.can_reserve(256));self.assertEqual(q.pop(),('data',))
        self.assertEqual(q.used_bytes,200);q.complete(200);self.assertEqual(q.used_bytes,0)
    def test_shared_sync_policies(self):
        self.assertTrue(sync_due(True,1,1.1,.1));self.assertFalse(sync_due(False,1,2,.1))
        self.assertEqual(sync_wait(False,1,2,.1),None)
        self.assertTrue(should_sync(False,False,True,256,256,1,1,.1))
        self.assertTrue(should_sync(False,True,False,0,256,1,1,.1))
    def test_accepted_is_not_immediate_durability(self):
        sink=self.sink(flush_interval=60,flush_bytes=1024*1024)
        result=sink.append({'kind':'source-batch','value':1})
        self.assertTrue(result.accepted);self.assertLess(result.durable_seq,result.source_seq)
        self.assertGreaterEqual(sink.flush(),result.source_seq)
    def test_default_source_wire_matches_legacy_bytes(self):
        sink=self.sink();legacy_path=Path(str(sink.path)+'.legacy')
        legacy=SourceSink(legacy_path)
        records=[{'kind':'source-batch','values':[1,'same',True,None]}, {'kind':'source-gap','gap':'test'}]
        for record in records:self.assertTrue(sink.append(record).accepted);legacy.append(record)
        old=legacy.close();new=sink.close()
        self.assertEqual(legacy_path.read_bytes(),sink.path.read_bytes())
        self.assertEqual(old['sha256'],new['sha256']);self.assertFalse(new['completeCapture'])
        self.assertEqual(verify_legacy(sink.path)['sha256'],new['sha256'])
    def test_group_synchronization_is_not_per_record_fsync(self):
        sink=self.sink(flush_interval=60,flush_bytes=1024*1024)
        for i in range(100):self.assertTrue(sink.append({'kind':'source-batch','n':i}).accepted)
        result=sink.close();self.assertTrue(result['storageSealed'])
        self.assertLess(result['stats']['fsyncCount'],100)
        self.assertEqual(result['durableSourceSeq'],102)
        self.assertEqual(result['stats']['durableRecords'],102)
    def test_size_trigger_advances_durable_watermark(self):
        sink=self.sink(flush_interval=60,flush_bytes=128)
        accepted=sink.append({'kind':'source-batch','x':'x'*200})
        end=time.monotonic()+2
        while sink._durable_seq<accepted.source_seq and time.monotonic()<end:time.sleep(.005)
        self.assertGreaterEqual(sink._durable_seq,accepted.source_seq)
    def test_timed_trigger_synchronizes_dirty_tail(self):
        sink=self.sink(flush_interval=.02,flush_bytes=1024*1024)
        accepted=sink.append({'kind':'source-batch','x':1})
        end=time.monotonic()+2
        while sink._durable_seq<accepted.source_seq and time.monotonic()<end:time.sleep(.005)
        self.assertGreaterEqual(sink._durable_seq,accepted.source_seq)
    def test_invalid_record_is_visible_not_silent(self):
        sink=self.sink();result=sink.append({'kind':'invented-kind'})
        self.assertFalse(result.accepted);self.assertEqual(result.gap,'source_record_rejected')
        self.assertFalse(sink.close()['storageSealed'])
    def test_oversized_source_returns_gap_without_write(self):
        sink=self.sink(max_record_bytes=256)
        self.assertFalse(sink.append({'kind':'source-batch','value':'x'*500}).accepted)
        result=sink.close();self.assertFalse(result['storageSealed']);self.assertEqual(result['records'],2)
    def test_caller_cannot_supply_source_seq_or_seal(self):
        sink=self.sink()
        self.assertFalse(sink.append({'kind':'source-batch','sourceSeq':999}).accepted)
        self.assertFalse(sink.append({'kind':'seal','prefixSha256':'fake'}).accepted)
    def test_total_budget_refusal_does_not_claim_sealed_source(self):
        sink=self.sink(max_total_bytes=512,max_record_bytes=256)
        for i in range(20):sink.append({'kind':'source-batch','n':i})
        try:result=sink.close()
        except SourceSinkError:return
        self.assertFalse(result['storageSealed'])
    def test_close_twice_preserves_raw_bytes(self):
        sink=self.sink();first=sink.close();raw=sink.path.read_bytes();second=sink.close()
        self.assertEqual(raw,sink.path.read_bytes());self.assertEqual(first,second)
    def test_append_after_close_invalidates_original_source(self):
        sink=self.sink();sink.close();raw=sink.path.read_bytes()
        self.assertFalse(sink.append({'kind':'source-batch'}).accepted)
        self.assertEqual(raw,sink.path.read_bytes())
        with self.assertRaises(SourceSinkError):verify_grouped_source(sink.path)
    def test_tampering_data_is_rejected(self):
        sink=self.sink();sink.append({'kind':'source-batch','value':1});sink.close()
        sink.path.write_bytes(sink.path.read_bytes().replace(b'"value":1',b'"value":2'))
        with self.assertRaises(SourceSinkError):verify_grouped_source(sink.path)
    def test_tampering_index_is_rejected(self):
        sink=self.sink();sink.close();raw=json.loads(sink.index.read_text());raw['bytes']+=1
        sink.index.write_text(json.dumps(raw),encoding='utf8')
        with self.assertRaises(SourceSinkError):verify_grouped_source(sink.path)
    def test_missing_seal_or_partial_tail_rejected(self):
        sink=self.sink();sink.close();sink.path.write_bytes(sink.path.read_bytes()[:-5])
        with self.assertRaises(SourceSinkError):verify_grouped_source(sink.path)
    def test_duplicate_target_is_never_overwritten(self):
        sink=self.sink();raw=sink.path.read_bytes()
        with self.assertRaises(FileExistsError):GroupedSourceSink(sink.path)
        self.assertEqual(raw,sink.path.read_bytes())
    def test_writer_failure_preserves_failure_guard(self):
        sink=self.sink(flush_interval=60);sink.flush()
        with mock.patch.object(sink,'_sync',side_effect=OSError('fsync failed')):
            with self.assertRaises(SourceSinkError):sink.flush()
        self.assertTrue(sink.lock_path.exists())
        with self.assertRaises(SourceSinkError):sink.close()
        with self.assertRaises(SourceSinkError):verify_grouped_source(sink.path)
    def test_index_failure_cannot_acknowledge_durable_tail(self):
        sink=self.sink(flush_interval=60);sink.flush();old=sink._durable_seq
        sink.append({'kind':'source-batch','n':1})
        with mock.patch.object(sink,'_persist_index',side_effect=OSError('index failed')):
            with self.assertRaises(SourceSinkError):sink.flush()
        self.assertEqual(sink._durable_seq,old);self.assertTrue(sink.lock_path.exists())
    def test_queue_backpressure_is_measured(self):
        sink=self.sink(max_queue_bytes=512,max_record_bytes=256,flush_interval=60);sink.flush()
        original=sink._file
        entered,release=threading.Event(),threading.Event()
        class Gate:
            def write(self,raw):entered.set();release.wait(3);return original.write(raw)
            def __getattr__(self,name):return getattr(original,name)
        sink._file=Gate()
        payload={'kind':'source-batch','x':'x'*100}
        sink.append(payload);self.assertTrue(entered.wait(1));sink.append(payload)
        done=threading.Event()
        def append():sink.append(payload);done.set()
        thread=threading.Thread(target=append);thread.start()
        self.assertFalse(done.wait(.03));release.set();thread.join(3)
        self.assertTrue(done.is_set());self.assertGreater(sink.stats['backpressureCount'],0)
        self.assertGreater(sink.stats['backpressureNs'],0)
        self.assertLessEqual(sink.stats['maxQueueBytes'],512)


if __name__=='__main__':
    result=unittest.main(verbosity=2,exit=False).result
    receipt={'schema':1,'kind':'shared-queue-grouped-source-io-tests','tests':result.testsRun,
             'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'passed':result.wasSuccessful(),'actualDatabaseExecution':False,'formalPerformanceMeasurement':False}
    (RUN/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt));raise SystemExit(0 if result.wasSuccessful() else 1)
