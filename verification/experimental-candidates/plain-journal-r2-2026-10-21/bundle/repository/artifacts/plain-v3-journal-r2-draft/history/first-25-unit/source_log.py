"""Bounded experimental side evidence; never a traceSchema3 extension."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import threading

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"integrations/python"))
from moontxnwitness_capture.journal_v3 import _bounded_copy, _sync_directory


class SourceLogError(RuntimeError):pass


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode("utf-8")


def exists(path):return path.exists() or path.is_symlink()


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise SourceLogError("Duplicate source-log field")
        result[key]=value
    return result


class SourceLog:
    def __init__(self,path,*,record_bytes=65536,total_bytes=8388608,max_records=8192):
        if (any(type(v) is not int for v in (record_bytes,total_bytes,max_records))
                or not 1024<=record_bytes<=65536 or not record_bytes<=total_bytes<=8388608
                or not 1<=max_records<=8192):raise ValueError("Source limits exceed the draft contract")
        self.path=Path(path);self.path.mkdir(parents=False,exist_ok=False)
        self.record_bytes,self.total_bytes,self.max_records=record_bytes,total_bytes,max_records
        self.count,self.size,self.previous=0,0,"0"*64
        self._lock=threading.RLock()
        self.hasher=hashlib.sha256();self.closed=False;self.failed=False;self.invalidated=False
        self.lock=self.path/"writer.lock"
        with self.lock.open("xb") as file:file.write(b"plain-source-log/1\n");file.flush();os.fsync(file.fileno())
        _sync_directory(self.path)
        self.file=(self.path/"records.jsonl").open("xb")

    def append(self,payload):
        with self._lock:return self._append(payload)

    def _append(self,payload):
        if self.closed:
            self.invalidated=True
            try:
                with (self.path/"invalidated.json").open("xb") as file:
                    file.write(encoded({"reason":"activity_after_close"}));file.flush();os.fsync(file.fileno())
                _sync_directory(self.path)
            except Exception:pass
            raise SourceLogError("Closed source log observed later activity")
        if self.failed:raise SourceLogError("Source log already failed")
        try:
            copied=_bounded_copy(payload,self.record_bytes-512,node_limit=4080)
            record={"sourceSchema":1,"seq":self.count+1,"previous":self.previous,"payload":copied}
            raw=encoded(record)+b"\n"
            if len(raw)>self.record_bytes or self.size+len(raw)>self.total_bytes or self.count>=self.max_records:
                raise SourceLogError("Source record/aggregate budget exhausted")
            if self.file.write(raw)!=len(raw):raise SourceLogError("Short source write")
            self.hasher.update(raw);self.previous=hashlib.sha256(raw).hexdigest()
            self.size+=len(raw);self.count+=1
            return self.count
        except BaseException:
            self.failed=True;raise

    def close(self):
        with self._lock:return self._close()

    def _close(self):
        if self.closed:return {"closed":True,"complete":not self.failed and not self.invalidated}
        self.closed=True
        try:
            self.file.flush();os.fsync(self.file.fileno());self.file.close()
            index={"sourceSchema":1,"closed":not self.failed,"records":self.count,"bytes":self.size,
                "sha256":self.hasher.hexdigest(),"lastRecordSha256":self.previous,
                "limits":{"recordBytes":self.record_bytes,"totalBytes":self.total_bytes,"maxRecords":self.max_records}}
            with (self.path/"index.json").open("xb") as file:
                file.write(encoded(index)+b"\n");file.flush();os.fsync(file.fileno())
            _sync_directory(self.path)
            if not self.failed:self.lock.unlink()  # Temporary guard; no later durability promise.
            return index
        except BaseException:
            self.failed=True
            try:self.file.close()
            except Exception:pass
            raise


class SourceLogReader:
    def __init__(self,path):self.path=Path(path)

    def _index(self):
        if any(exists(self.path/name) for name in ("writer.lock","invalidated.json")):
            raise SourceLogError("Source log is active, failed or invalidated")
        path=self.path/"index.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size>4096:
            raise SourceLogError("Missing or oversized source index")
        raw=path.read_bytes();value=json.loads(raw,object_pairs_hook=unique)
        if (set(value)!={"sourceSchema","closed","records","bytes","sha256","lastRecordSha256","limits"}
                or type(value["sourceSchema"]) is not int or value["sourceSchema"]!=1 or value["closed"] is not True
                or type(value["records"]) is not int or not 0<=value["records"]<=8192
                or type(value["bytes"]) is not int or not 0<=value["bytes"]<=8388608):
            raise SourceLogError("Invalid source index")
        limits=value["limits"]
        if (set(limits)!={"recordBytes","totalBytes","maxRecords"}
                or any(type(v) is not int for v in limits.values())
                or not 1024<=limits["recordBytes"]<=65536
                or not limits["recordBytes"]<=limits["totalBytes"]<=8388608
                or not 1<=limits["maxRecords"]<=8192
                or value["bytes"]>limits["totalBytes"] or value["records"]>limits["maxRecords"]):
            raise SourceLogError("Source index limits")
        return value,hashlib.sha256(raw).hexdigest()

    def iter_records(self):
        index,index_hash=self._index();path=self.path/"records.jsonl"
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=index["bytes"]:
            raise SourceLogError("Source data size changed")
        hashed=hashlib.sha256();previous="0"*64;count=0;size=0
        with path.open("rb") as file:
            identity=os.fstat(file.fileno())
            while raw:=file.readline(index["limits"]["recordBytes"]+1):
                size+=len(raw);count+=1
                if not raw.endswith(b"\n") or len(raw)>index["limits"]["recordBytes"] or count>index["records"] or size>index["bytes"]:
                    raise SourceLogError("Truncated/oversized source record")
                value=json.loads(raw,object_pairs_hook=unique)
                _bounded_copy(value,index["limits"]["recordBytes"],node_limit=4096)
                if (set(value)!={"sourceSchema","seq","previous","payload"} or type(value["sourceSchema"]) is not int or value["sourceSchema"]!=1
                        or type(value["seq"]) is not int or value["seq"]!=count or value["previous"]!=previous):
                    raise SourceLogError("Source sequence/chain mismatch")
                hashed.update(raw);previous=hashlib.sha256(raw).hexdigest();yield value
        current=path.stat()
        if (path.is_symlink() or not stat.S_ISREG(current.st_mode) or (identity.st_dev,identity.st_ino)!=(current.st_dev,current.st_ino)
                or size!=index["bytes"] or count!=index["records"] or hashed.hexdigest()!=index["sha256"]
                or previous!=index["lastRecordSha256"] or self._index()[1]!=index_hash):
            raise SourceLogError("Source final byte/index binding changed")

    def verify(self):
        try:
            count=sum(1 for _ in self.iter_records())
            return {"valid":True,"complete":True,"records":count,"coreProofImplemented":False}
        except Exception as error:return {"valid":False,"complete":False,"error":type(error).__name__+": "+str(error)}
