"""Optional grouped source journal. Its records never grant model coverage.

Shares byte-capacity queue and sync scheduling with SegmentedJournal. Source
validation, framing, file/index handling and failure markers remain separate.
The legacy SourceSink still synchronizes each append and is unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from ._durable_policy import CapacityQueue, sync_due, sync_wait, should_sync, flush_pending
from ._orm_source_sink import _Encoder
from .capture import _Budget
from .journal_v3 import _json, _sync_directory


class SourceSinkError(RuntimeError): pass


@dataclass(frozen=True)
class SourceAppendResult:
    accepted: bool
    source_seq: int
    durable_seq: int
    blocked_ns: int = 0
    gap: str | None = None


class GroupedSourceSink:
    def __init__(self, path, *, max_queue_bytes=4 * 1024 * 1024,
                 max_record_bytes=128 * 1024, max_total_bytes=16 * 1024 * 1024,
                 max_records=16384, flush_bytes=256 * 1024, flush_interval=0.1):
        values = (max_queue_bytes, max_record_bytes, max_total_bytes, max_records, flush_bytes)
        if any(type(v) is not int or not 128 <= v <= 9007199254740991 for v in values): raise ValueError('Positive bounded integer budgets required')
        if max_record_bytes > min(max_queue_bytes,128*1024) or max_queue_bytes > 64*1024*1024 or max_total_bytes > 1024**3 or max_records > 1000000 or flush_bytes > 64*1024*1024:
            raise ValueError('Source size/count budgets exceed the supported range')
        if type(flush_interval) not in (float,int) or not 0 < flush_interval <= 60:
            raise ValueError('Flush interval must be in (0,60]')
        self.path = Path(path).resolve()
        self.index = Path(str(self.path)+'.index.json')
        self.lock_path = Path(str(self.path)+'.writer.lock')
        self.failure_path = Path(str(self.path)+'.failure.json')
        self.invalidated_path = Path(str(self.path)+'.invalidated.json')
        for p in (self.path,self.index,self.lock_path,self.failure_path,self.invalidated_path):
            if os.path.lexists(p): raise FileExistsError(p)
        self.max_record_bytes, self.max_total_bytes, self.max_records = max_record_bytes,max_total_bytes,max_records
        self.flush_bytes,self.flush_interval = flush_bytes,float(flush_interval)
        self._cv,self._append_lock = threading.Condition(threading.RLock()),threading.RLock()
        self._capacity = CapacityQueue(max_queue_bytes)
        self._accepted_digest,self._written_digest = hashlib.sha256(),hashlib.sha256()
        self._accepted_seq=self._written_seq=self._durable_seq=0
        self._accepted_bytes=self._written_bytes=self._pending_bytes=0
        self._flush_generation=self._flushed_generation=self._flush_target_seq=0
        self._closing=self._closed=False
        self._dirty=False;self._error=None;self._gaps=[];self._control_append=True
        self._nonce=uuid.uuid4().hex
        self.stats={'acceptedRecords':0,'durableRecords':0,'backpressureCount':0,
                    'backpressureNs':0,'maxQueueBytes':0,'fsyncCount':0,'bytesWritten':0,'indexSyncCount':0}
        with self.lock_path.open('xb') as lock:
            lock.write(_json({'writer':self._nonce,'pid':os.getpid()}));lock.flush();os.fsync(lock.fileno())
        self._file=self.path.open('xb',buffering=0)
        self._last_sync=time.monotonic()
        self._thread=threading.Thread(target=self._worker,name='mtw-source-group',daemon=True)
        self._thread.start()
        result=self.append({'kind':'header','sourceSchema':'orm-source-draft/2',
                            'controlSchema':'orm-control-query/1','coreProofAccepted':False})
        if not result.accepted: raise SourceSinkError('Source header was not accepted')
        self._control_append=False

    def _gap(self, code):
        with self._cv:
            if code not in self._gaps and len(self._gaps)<64: self._gaps.append(code)
            self._dirty=True;self._cv.notify_all()
        return code

    def append(self, record):
        started=None;blocked=0
        with self._append_lock:
            with self._cv:
                if self._closing or self._closed or self._error:
                    if self._closing or self._closed:
                        try:
                            with self.invalidated_path.open('xb') as marker:
                                marker.write(_json({'gap':'append_after_close'}));marker.flush();os.fsync(marker.fileno())
                        except OSError: pass
                    return SourceAppendResult(False,0,self._durable_seq,gap=self._gap('source_not_writable'))
                while not self._capacity.can_reserve(self.max_record_bytes) and self._error is None:
                    if started is None: started=time.monotonic_ns()
                    self._cv.wait()
                if started is not None:
                    blocked=time.monotonic_ns()-started
                    self.stats['backpressureCount']+=1;self.stats['backpressureNs']+=blocked
                if self._error:
                    return SourceAppendResult(False,0,self._durable_seq,blocked,self._gap('source_write_failed'))
                self._capacity.reserve(self.max_record_bytes)
                self.stats['maxQueueBytes']=max(self.stats['maxQueueBytes'],self._capacity.used_bytes)
            try:
                if not isinstance(record,dict) or 'sourceSeq' in record:
                    raise ValueError('A source record without sourceSeq is required')
                allowed={'header','control-query','installation','source-batch','source-gap','final-effect-ledger','seal'}
                if record.get('kind') not in allowed or record.get('kind') in ('header','seal') and not self._control_append:
                    raise ValueError('Unknown source kind or caller supplied control record')
                value=_Encoder()._value({'sourceSeq':self._accepted_seq+1,**record},_Budget(4096,self.max_record_bytes))
                raw=_json(value)+b'\n'
                with self._cv:
                    if self._error:
                        return SourceAppendResult(False,0,self._durable_seq,blocked,self._gap('source_write_failed'))
                    if len(raw)>self.max_record_bytes or self._accepted_bytes+len(raw)>self.max_total_bytes:
                        raise ValueError('Source byte budget exhausted')
                    if self._accepted_seq>=self.max_records-1 and record.get('kind')!='seal':
                        raise ValueError('Source count budget exhausted')
                    if self._accepted_seq>=self.max_records: raise ValueError('Source count budget exhausted')
                    self._accepted_seq+=1;self._accepted_bytes+=len(raw);self._accepted_digest.update(raw)
                    self._capacity.enqueue((raw,self._accepted_seq),len(raw))
                    self.stats['acceptedRecords']+=1
                    self._cv.notify_all()
                    return SourceAppendResult(True,self._accepted_seq,self._durable_seq,blocked)
            except Exception:
                return SourceAppendResult(False,0,self._durable_seq,blocked,self._gap('source_record_rejected'))
            finally:
                with self._cv:
                    self._capacity.release_reservation(self.max_record_bytes);self._cv.notify_all()

    def flush(self):
        with self._cv:
            target=self._accepted_seq
            self._flush_target_seq=max(self._flush_target_seq,target)
            self._flush_generation+=1;generation=self._flush_generation
            self._cv.notify_all()
            while self._error is None and (self._durable_seq<target or self._flushed_generation<generation):
                if self._closed: break
                self._cv.wait()
            if self._error: raise SourceSinkError('Source synchronization failed') from self._error
            return self._durable_seq

    def _persist_index(self, closed):
        with self._cv:
            generation=self._flush_generation
            payload={'format':'moontxnwitness-grouped-source/v1','closed':closed,
                     'durableSourceSeq':self._written_seq,'bytes':self._written_bytes,
                     'sha256':self._written_digest.hexdigest(),'gaps':list(self._gaps),
                     'limits':{'queueBytes':self._capacity.max_bytes,'recordBytes':self.max_record_bytes,
                               'totalBytes':self.max_total_bytes,'records':self.max_records,
                               'flushBytes':self.flush_bytes,'flushIntervalSeconds':self.flush_interval},
                     'stats':{**self.stats,'durableRecords':self._written_seq,'indexSyncCount':self.stats['indexSyncCount']+1},'completeCapture':False,'coreProofAccepted':False}
            payload['indexSha256']=hashlib.sha256(_json(payload)).hexdigest()
        tmp=Path(str(self.index)+'.'+self._nonce+'.tmp')
        with tmp.open('wb') as file:
            raw=_json(payload)+b'\n'
            if file.write(raw)!=len(raw): raise OSError('Short source index write')
            file.flush();os.fsync(file.fileno())
        os.replace(tmp,self.index);_sync_directory(self.index.parent)
        with self._cv:
            self._durable_seq=self._written_seq
            self.stats['durableRecords']=self._written_seq;self.stats['indexSyncCount']+=1
            self._flushed_generation=generation;self._dirty=False;self._cv.notify_all()

    def _sync(self):
        self._file.flush();os.fsync(self._file.fileno());self.stats['fsyncCount']+=1
        self._persist_index(False)
        self._pending_bytes=0;self._last_sync=time.monotonic()


    def _worker(self):
        try:
            while True:
                with self._cv:
                    while not self._capacity.items:
                        explicit=flush_pending(self._flush_generation,self._flushed_generation,self._durable_seq,self._flush_target_seq)
                        if self._closing or explicit or sync_due(self._dirty,self._last_sync,time.monotonic(),self.flush_interval): break
                        self._cv.wait(sync_wait(self._dirty,self._last_sync,time.monotonic(),self.flush_interval))
                    item=self._capacity.pop()
                if item is not None:
                    raw,seq=item
                    view=memoryview(raw)
                    while view:
                        n=self._file.write(view)
                        if not n: raise OSError('Zero-byte source write')
                        view=view[n:]
                    self._written_digest.update(raw)
                    with self._cv:
                        self._written_seq=seq;self._written_bytes+=len(raw);self._pending_bytes+=len(raw)
                        self.stats['bytesWritten']+=len(raw)
                        self._capacity.complete(len(raw));self._dirty=True;self._cv.notify_all()
                with self._cv:
                    closing=self._closing and not self._capacity.items
                    explicit=flush_pending(self._flush_generation,self._flushed_generation,self._durable_seq,self._flush_target_seq)
                    sync=should_sync(closing,explicit,self._dirty,self._pending_bytes,self.flush_bytes,
                                     self._last_sync,time.monotonic(),self.flush_interval)
                if closing:
                    self._sync();self._file.close();self._persist_index(True)
                    return
                if sync: self._sync()
        except BaseException as error:
            with self._cv:
                self._error=error;self._gap('source_write_failed');self._capacity.clear();self._cv.notify_all()
            try:
                with self.failure_path.open('xb') as marker:
                    marker.write(_json({'gap':'source_write_failed','errorClass':type(error).__name__}))
                    marker.flush();os.fsync(marker.fileno())
            except Exception: pass
            try: self._file.close()
            except Exception: pass

    def close(self):
        with self._append_lock:
            if self._closed and self._error is None:
                # A post-close append can fail to persist its invalidation
                # marker (for example on a full disk). Never forget the
                # refusal already known by this live writer object merely
                # because the old, formerly sealed bytes still verify.
                with self._cv:
                    if 'source_not_writable' in self._gaps:
                        raise SourceSinkError('Known unretained source append; invalidation marker may be unavailable')
                return verify_grouped_source(self.path)
            if not self._closing and not self._closed:
                self._control_append=True
                result=self.append({'kind':'seal','prefixSha256':self._accepted_digest.hexdigest(),
                                    'sourceRecords':self._accepted_seq})
                self._control_append=False
                if not result.accepted: self._gap('source_seal_not_retained')
                with self._cv:
                    self._closing=True;self._cv.notify_all()
        self._thread.join(timeout=30)
        if self._thread.is_alive():
            self._gap('source_close_timeout')
            raise SourceSinkError('Source close timed out; preserve the writer lock')
        with self._append_lock:
            with self._cv:
                self._closed=True
                if self._error: raise SourceSinkError('Source writer failed; preserve original files') from self._error
                if 'source_not_writable' in self._gaps:
                    raise SourceSinkError('Known unretained source append; preserve original source guards')
            # All data/index synchronization and file closes finished before
            # removing the writer guard. Serialize this final read with append
            # so a known post-close refusal cannot be lost in the response.
            self.lock_path.unlink()
            return verify_grouped_source(self.path)


def verify_grouped_source(path):
    """Stream and bind the source/index. Storage integrity never means SQL proof."""
    supplied=Path(path)
    if supplied.is_symlink(): raise SourceSinkError('Symbolic source files are not accepted')
    path=supplied.resolve()
    index=Path(str(path)+'.index.json')
    if index.is_symlink(): raise SourceSinkError('Symbolic source indexes are not accepted')
    if any(os.path.lexists(str(path)+suffix) for suffix in ['.writer.lock','.failure.json','.invalidated.json']):
        raise SourceSinkError('Active, failed or invalidated source storage')
    with index.open('rb') as file:
        raw_index=file.read(1024*1024+1)
    if len(raw_index)>1024*1024: raise SourceSinkError('Source index exceeds bound')
    meta=json.loads(raw_index)
    original=meta.pop('indexSha256')
    if hashlib.sha256(_json(meta)).hexdigest()!=original: raise SourceSinkError('Source index digest mismatch')
    if meta.get('format')!='moontxnwitness-grouped-source/v1' or not meta.get('closed'):
        raise SourceSinkError('Source storage is not sealed')
    if meta.get('completeCapture') is not False or meta.get('coreProofAccepted') is not False:
        raise SourceSinkError('Grouped storage cannot claim model/source proof')
    limits=meta['limits']
    required={'queueBytes','recordBytes','totalBytes','records','flushBytes','flushIntervalSeconds'}
    if not isinstance(limits,dict) or set(limits)!=required:
        raise SourceSinkError('Invalid source limit declaration')
    for key in required-{'flushIntervalSeconds'}:
        if type(limits[key]) is not int or not 128<=limits[key]<=9007199254740991:
            raise SourceSinkError('Unsafe source limit')
    if not 128<=limits['recordBytes']<=min(limits['queueBytes'],128*1024) or limits['queueBytes']>64*1024*1024 or limits['totalBytes']>1024**3 or limits['records']>1000000 or limits['flushBytes']>64*1024*1024:
        raise SourceSinkError('Source limits exceed supported bounds')
    if type(limits['flushIntervalSeconds']) not in (int,float) or not 0<limits['flushIntervalSeconds']<=60:
        raise SourceSinkError('Invalid source flush interval')
    digest=hashlib.sha256();count=total=0;sealed=False
    allowed={'header','control-query','installation','source-batch','source-gap','final-effect-ledger','seal'}
    with path.open('rb') as source:
        while True:
            raw=source.readline(limits['recordBytes']+1)
            if not raw: break
            if sealed or len(raw)>limits['recordBytes'] or not raw.endswith(b'\n'):
                raise SourceSinkError('Partial, trailing or oversized source record')
            record=json.loads(raw);count+=1;total+=len(raw)
            if record.get('sourceSeq')!=count or count>limits['records'] or total>limits['totalBytes']:
                raise SourceSinkError('Source ordering/count/byte bound mismatch')
            if record.get('kind') not in allowed: raise SourceSinkError('Unknown source record kind')
            if count==1 and (record.get('kind')!='header' or record.get('sourceSchema')!='orm-source-draft/2'
                             or record.get('controlSchema')!='orm-control-query/1' or record.get('coreProofAccepted') is not False):
                raise SourceSinkError('Explicit unaccepted source header required')
            if record.get('kind')=='seal':
                if record.get('prefixSha256')!=digest.hexdigest() or record.get('sourceRecords')!=count-1:
                    raise SourceSinkError('Source seal mismatch')
                sealed=True
            digest.update(raw)
    if not sealed or count!=meta['durableSourceSeq'] or total!=meta['bytes'] or digest.hexdigest()!=meta['sha256']:
        raise SourceSinkError('Source/index bound mismatch')
    return {'storageSealed':not meta['gaps'],'records':count,'bytes':total,'sha256':digest.hexdigest(),
            'durableSourceSeq':meta['durableSourceSeq'],'gaps':meta['gaps'],'stats':meta['stats'],
            'completeCapture':False,'coreProofAccepted':False,'actualDatabaseExecution':False}
