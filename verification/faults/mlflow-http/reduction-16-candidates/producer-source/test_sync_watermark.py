"""Deterministic flush-watermark liveness regressions. No DB or performance claim."""
import os
from pathlib import Path
import sys
import threading
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.journal_v3 import SegmentedJournal
from moontxnwitness_capture.source_sink import GroupedSourceSink
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(Path.cwd()/'artifacts/sync-watermark')))
RUN=BASE/('watermark-'+uuid.uuid4().hex);RUN.mkdir(parents=True)


class Tests(unittest.TestCase):
    def test_journal_flush_reaches_target_after_partial_generation_ack(self):
        entered,release=threading.Event(),threading.Event()
        class Writer(SegmentedJournal):
            def _write_line(self,line):
                if not entered.is_set():entered.set();release.wait(3)
                super()._write_line(line)
        writer=Writer(RUN/'journal',flush_interval=60,flush_bytes=1024*1024)
        writer.append({'seq':1,'time':0,'kind':'snapshot','initial':{},'consistent':True})
        self.assertTrue(entered.wait(1))
        writer.append({'seq':2,'time':1,'kind':'begin','tx':'t','connection':'c'})
        done=threading.Event();observed=[]
        def flush():observed.append(writer.flush());done.set()
        thread=threading.Thread(target=flush);thread.start()
        with writer._cv:
            self.assertTrue(writer._cv.wait_for(lambda:writer._flush_target_seq==2,timeout=1))
        release.set()
        try:
            self.assertTrue(done.wait(2),'Explicit flush must not wait for the 60s timer after partial sync')
            self.assertGreaterEqual(observed[0],2)
        finally:writer.close();thread.join(3)

    def test_source_flush_reaches_target_after_partial_generation_ack(self):
        entered,release=threading.Event(),threading.Event()
        sink=GroupedSourceSink(RUN/'source.jsonl',flush_interval=60,flush_bytes=1024*1024)
        sink.flush()
        raw=sink._file
        class Gate:
            def write(self,line):
                if not entered.is_set():entered.set();release.wait(3)
                return raw.write(line)
            def __getattr__(self,name):return getattr(raw,name)
        sink._file=Gate()
        sink.append({'kind':'source-batch','n':1});self.assertTrue(entered.wait(1))
        target=sink.append({'kind':'source-batch','n':2}).source_seq
        done=threading.Event();observed=[]
        def flush():observed.append(sink.flush());done.set()
        thread=threading.Thread(target=flush);thread.start()
        with sink._cv:self.assertTrue(sink._cv.wait_for(lambda:sink._flush_target_seq==target,timeout=1))
        release.set()
        try:
            self.assertTrue(done.wait(2),'Explicit source flush must reach its recorded target')
            self.assertGreaterEqual(observed[0],target)
        finally:sink.close();thread.join(3)


if __name__=='__main__':unittest.main(verbosity=2)
