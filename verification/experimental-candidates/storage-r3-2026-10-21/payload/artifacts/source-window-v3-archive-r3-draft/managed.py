"""Archive-backed original segment retirement; isolated experimental protocol."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import struct
import sys
import tempfile
import time
import uuid
import zipfile
from protocol import canonical, digest, checked, ProtocolError, validate_manifest, validate_intent

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "integrations/python"))
from moontxnwitness_capture.journal_v3 import JournalReader, INDEX, LOCK, INVALIDATED, TRANSACTIONS

OLD = ROOT / "artifacts/source-window-v3-draft/windows.py"
checked(digest(OLD.read_bytes()) == "0c63c64fef00eaefd9f480e10bb79f932e0e62d7840fa93ca2d53b31ffacec05", "Frozen source closure changed")
spec = importlib.util.spec_from_file_location("_frozen_point_windows", OLD)
point = importlib.util.module_from_spec(spec); spec.loader.exec_module(point)
LIMITS = json.loads((Path(__file__).parent / "contract-v1.json").read_text())["limits"]


class Incomplete(ProtocolError): pass


class Budget:
    def __init__(self, *, max_io=None, seconds=None):
        self.maximum = LIMITS["operationIoBytes"] if max_io is None else max_io
        self.seconds = LIMITS["operationWallSeconds"] if seconds is None else seconds
        checked(type(self.maximum) is int and 0 < self.maximum <= LIMITS["operationIoBytes"], "IO budget")
        checked(type(self.seconds) in (int,float) and 0 < self.seconds <= LIMITS["operationWallSeconds"], "Wall budget")
        self.used, self.started, self.steps = 0,time.monotonic(),0
    def check(self):
        if time.monotonic()-self.started > self.seconds: raise Incomplete("Cooperative operation wall budget exceeded")
    def charge(self, size):
        self.check()
        if size > self.maximum-self.used: raise Incomplete("Aggregate operation IO budget exceeded")
        self.used += size
    def progress(self):
        self.steps += 1000
        return int(self.steps > 5_000_000 or time.monotonic()-self.started > self.seconds)


class _Discard:
    def write(self,block):return len(block)


def present(path):
    try: path.lstat(); return True
    except FileNotFoundError: return False


def safe(path, maximum):
    if path.is_symlink(): raise Incomplete("Symlink source/metadata rejected")
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum: raise Incomplete("Missing/nonregular/oversized source")
    return info.st_size


def stream_copy(source, target, size, expected, budget, *, expected_lines=None):
    hashed, consumed, lines=hashlib.sha256(),0,0
    while consumed < size:
        amount=min(65536,size-consumed);budget.charge(amount*2)
        block=source.read(amount)
        if len(block)!=amount: raise Incomplete("Truncated source")
        if expected_lines is not None:
            lines+=block.count(b"\n")
            if lines>expected_lines:raise Incomplete("Segment event count exceeded before raw decode")
        target.write(block);hashed.update(block);consumed+=len(block)
    budget.charge(1)
    if source.read(1) or hashed.hexdigest()!=expected or expected_lines is not None and lines!=expected_lines: raise Incomplete("Source hash/size/event count changed")


def file_hash(path, maximum, budget):
    size=safe(path,maximum);hashed=hashlib.sha256()
    with path.open("rb") as file:
        remaining=size
        while remaining:
            amount=min(65536,remaining);budget.charge(amount);block=file.read(amount)
            if len(block)!=amount: raise Incomplete("Short source binding")
            hashed.update(block);remaining-=len(block)
        budget.charge(1)
        if file.read(1): raise Incomplete("Source grew during binding")
    return {"bytes":size,"sha256":hashed.hexdigest()}


def load(path, maximum=1048576, *, budget=None):
    size=safe(path,maximum)
    if budget is not None:budget.charge(size+1)
    with path.open("rb") as file: raw=file.read(maximum+1)
    if len(raw)>maximum: raise Incomplete("Metadata grew beyond budget")
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise Incomplete("Duplicate metadata field")
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique),digest(raw)


def read_index(source,budget=None):
    if budget is not None:budget.charge(safe(source/INDEX,2*1024*1024)*2)
    return JournalReader(source)._index()


def open_bounded_zip(path,budget):
    """Bound central-directory parsing before ZipFile allocates member objects."""
    size=safe(path,LIMITS["archiveBytes"])
    amount=min(size,65557);budget.charge(amount)
    with path.open("rb") as file:file.seek(size-amount);tail=file.read(amount)
    offset=tail.rfind(b"PK\x05\x06")
    checked(offset>=0 and len(tail)-offset>=22,"ZIP end record")
    signature,disk,directory_disk,disk_entries,entries,directory_size,directory_offset,comment_size=struct.unpack("<4s4H2LH",tail[offset:offset+22])
    checked(disk==directory_disk==0 and disk_entries==entries and entries<=LIMITS["segmentCount"]+2,"ZIP entry budget/multidisk")
    checked(directory_size<=65536 and directory_offset+directory_size==size-amount+offset
        and offset+22+comment_size==len(tail),"ZIP central directory bound/ZIP64/trailing bytes")
    return zipfile.ZipFile(path)


def os_lock(file):
    file.seek(0)
    if os.name=="nt":
        import msvcrt
        msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)


def os_unlock(file):
    file.seek(0)
    if os.name=="nt":
        import msvcrt
        msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        fcntl.flock(file.fileno(),fcntl.LOCK_UN)


class ManagedSource:
    def __init__(self,path):
        self.path=Path(path).resolve();self.poisoned=False;self.dirty=False;self.fault=None;self._budget=None

    def _publish(self,state,*,budget=None):
        self.dirty=True
        state={k:v for k,v in state.items() if k!="manifestSha256"}
        state["manifestSha256"]=digest(canonical(state))
        raw=canonical(state)
        checked(len(raw)<=LIMITS["manifestBytes"],"Manifest budget")
        active=budget if budget is not None else self._budget
        if active is not None:active.charge(len(raw)*3)
        temp=self.path/(".manifest-"+uuid.uuid4().hex)
        with temp.open("xb") as file:file.write(raw);file.flush();os.fsync(file.fileno())
        os.replace(temp,self.path/"manifest.json");self._hit("manifest-replaced-before-sync");point.sync_directory(self.path)
        if digest((self.path/"manifest.json").read_bytes())!=digest(raw):raise Incomplete("Published manifest changed")
        return state

    def _state(self,*,allow_failed=False):
        if self.poisoned:raise Incomplete("Instance permanently failed")
        if not allow_failed and present(self.path/"operation-failed.json"):raise Incomplete("Persisted failed operation needs explicit recovery")
        state,_=load(self.path/"manifest.json",budget=self._budget)
        source=Path(state["source"])
        index,index_sha=read_index(source,self._budget)
        checked(index_sha==state["sourceIndexSha256"],"Original index epoch changed")
        validate_manifest(state,index)
        return state,index

    @classmethod
    def adopt(cls,path,source,*,model="point-register-v1",exclusive_source_ownership=False):
        checked(model=="point-register-v1" and exclusive_source_ownership is True,"Explicit fixed source scope required")
        requested,source=Path(path),Path(source).resolve()
        checked(not requested.is_symlink(),"Unsafe store")
        path=requested.resolve()
        checked(not path.is_relative_to(source) and not source.is_relative_to(path),"Store/source overlap")
        budget=Budget();reader=JournalReader(source);index,index_sha=read_index(source,budget)
        checked(index["eventCount"]<=LIMITS["sourceEvents"] and len(index["segments"])<=LIMITS["segmentCount"]
            and sum(s["bytes"] for s in index["segments"])<=LIMITS["sourceEventBytes"],"Source bound")
        cache_size=safe(source/TRANSACTIONS,LIMITS["transactionCacheBytes"])
        # Reject excessive/misbound physical record counts before the raw
        # reader allocates identities or decodes every event tree.
        for segment in index["segments"]:
            checked(safe(source/segment["name"],LIMITS["sourceEventBytes"])==segment["bytes"],"Preflight source size")
            with (source/segment["name"]).open("rb") as incoming:
                stream_copy(incoming,_Discard(),segment["bytes"],segment["sha256"],budget,expected_lines=segment["eventCount"])
        budget.charge(sum(s["bytes"] for s in index["segments"])*2+cache_size*2)
        status=reader.verify();budget.check()
        checked(status.complete and index_sha==status.index_sha256,"Adoption needs complete sealed raw storage and unchanged epoch")
        path.mkdir(parents=False,exist_ok=False);store=cls(path);nonce=uuid.uuid4().hex
        fence={"kind":"archive-managed-readonly-fence/1","nonce":nonce,"store":str(path),"sourceIndexSha256":index_sha}
        raw=canonical(fence)
        with (source/LOCK).open("xb") as file:file.write(raw);file.flush();os.fsync(file.fileno())
        point.sync_directory(source)
        state={"schema":1,"dataModel":model,"nonce":nonce,"source":str(source),"sourceIndexSha256":index_sha,
            "fenceSha256":digest(raw),"transactionBinding":file_hash(source/TRANSACTIONS,LIMITS["transactionCacheBytes"],budget),
            "generation":0,"archive":None,"checkpoints":{},"pins":{},"pending":None,
            "locations":[{"name":s["name"],"storage":"hot"} for s in index["segments"]]}
        store._publish(state,budget=budget)
        with store._operation(budget=budget) as budget:
            state,index=store._state()
            with store._view(state,index,budget) as view:
                db=store._graph(view,budget)
                try:point.SourceWindows._closure(None,db,**store._roots(state,index))
                finally:db.close()
        return store

    @contextlib.contextmanager
    def _operation(self,*,recover=False,budget=None):
        if self.poisoned:raise Incomplete("Poisoned instance")
        target=self.path/"operation.lock";checked(not target.is_symlink(),"Unsafe operation lock")
        file=None;acquired=False;success=False;previous=self._budget
        try:
            file=target.open("r+b" if recover else "xb+")
            if not recover:file.write(b"!");file.flush()
            os_lock(file);acquired=True
            self.dirty=False
            self._budget=Budget() if budget is None else budget
            state,_=self._state(allow_failed=recover)
            self.operation_owner_nonce=state["nonce"]
            if recover:
                file.seek(0);token=json.loads(file.read(4097))
                checked(type(token) is dict and set(token)=={"kind","nonce","token"} and token["kind"]=="archive-operation/1"
                    and token["nonce"]==state["nonce"] and type(token["token"]) is str and len(token["token"])==32
                    and all(c in "0123456789abcdef" for c in token["token"]),"Foreign abandoned lock")
                self.operation_token=token["token"]
            else:
                self.operation_token=uuid.uuid4().hex
                file.seek(0);file.truncate();file.write(canonical({"kind":"archive-operation/1","nonce":state["nonce"],"token":self.operation_token}));file.flush();os.fsync(file.fileno())
            yield self._budget
            success=True
        except BaseException:
            if acquired and self.dirty:
                self.poisoned=True
                # The lock predates all destructive work. Failure of this
                # additional diagnostic marker never releases that guard.
                try:self._failure_marker()
                except BaseException:pass
            raise
        finally:
            if file is not None:
                if acquired:os_unlock(file)
                file.close()
            if acquired:self._budget=previous
            if acquired and not self.dirty and (not recover or success):
                target.unlink();point.sync_directory(self.path)

    def _failure_marker(self):
        payload={"kind":"archive-operation-failed/1","nonce":self.operation_owner_nonce,"operationToken":self.operation_token}
        with (self.path/"operation-failed.json").open("xb") as file:file.write(canonical(payload));file.flush();os.fsync(file.fileno())
        point.sync_directory(self.path)

    def _guard(self,state,index,budget,*,pending=False):
        source=Path(state["source"])
        actual,_=load(self.path/"manifest.json",budget=budget);validate_manifest(actual,index)
        checked(actual["manifestSha256"]==state["manifestSha256"],"Manifest generation/root binding changed during operation")
        if not pending and (state["pending"] is not None or present(self.path/"prune-intent.json")):
            raise Incomplete("Unresolved prune intent")
        for marker in (INVALIDATED,"journal-failure.json"):
            if present(source/marker):raise Incomplete("Original source invalidation/failure marker")
        fence,_=load(source/LOCK,4096,budget=budget)
        checked(fence=={"kind":"archive-managed-readonly-fence/1","nonce":state["nonce"],"store":str(self.path),"sourceIndexSha256":state["sourceIndexSha256"]},"Foreign or missing source fence")
        checked(file_hash(source/LOCK,4096,budget)["sha256"]==state["fenceSha256"],"Source fence changed")
        checked(read_index(source,budget)[1]==state["sourceIndexSha256"],"Source epoch changed")
        checked(file_hash(source/TRANSACTIONS,LIMITS["transactionCacheBytes"],budget)==state["transactionBinding"],"Original transaction cache changed")
        checked(not any(present(source/(TRANSACTIONS+suffix)) for suffix in ("-wal","-shm","-journal")),"Original cache has unsealed SQLite sidecar")
        checked(index["closed"] is True and index["sourceClosed"] is True,"Unsealed source")
        checked(not index["activeTransactions"] and not index["commitRequests"] and not index["references"]["activeTransactions"] and not index["references"]["unreadResults"],"Active source references")
        actual={p.name for p in source.glob("segment-*.jsonl")}
        expected={s["name"] for s in index["segments"]}
        checked(actual<=expected,"Unindexed original segment")

    @contextlib.contextmanager
    def _view(self,state,index,budget,*,pending=False):
        self._guard(state,index,budget,pending=pending)
        source=Path(state["source"]);raw_bytes=sum(s["bytes"] for s in index["segments"])
        checked(raw_bytes<=LIMITS["sourceEventBytes"] and index["eventCount"]<=LIMITS["sourceEvents"],"Source limit")
        checked(raw_bytes+state["transactionBinding"]["bytes"]+16*1024*1024<=LIMITS["temporaryBytes"],"Temporary reservation")
        archive=None
        with contextlib.ExitStack() as stack:
            if state["archive"] is not None:
                record=state["archive"];path=Path(record["path"])
                checked(not path.resolve().is_relative_to(source) and not path.resolve().is_relative_to(self.path),"Unsafe archive boundary")
                checked(file_hash(path,LIMITS["archiveBytes"],budget)=={k:record[k] for k in ("sha256","bytes")},"Archive byte binding")
                archive=stack.enter_context(open_bounded_zip(path,budget));members=archive.infolist()
                expected={INDEX:(source/INDEX).stat().st_size,TRANSACTIONS:state["transactionBinding"]["bytes"],**{s["name"]:s["bytes"] for s in index["segments"]}}
                checked(len(members)==len(expected) and len({m.filename for m in members})==len(members),"Archive member count/duplicates")
                checked(sum(m.file_size for m in members)<=LIMITS["archiveUncompressedBytes"],"Archive expanded bound")
                for member in members:
                    checked(member.filename in expected and member.file_size==expected[member.filename] and not member.flag_bits&1 and stat.S_IFMT(member.external_attr>>16)!=stat.S_IFLNK,"Unsafe archive member")
            temp=stack.enter_context(tempfile.TemporaryDirectory(prefix="mtw-archive-view-",dir=os.environ.get("MTW_JOURNAL_SCRATCH")))
            view=Path(temp)
            for name,expected in ((INDEX,{"bytes":(source/INDEX).stat().st_size,"sha256":state["sourceIndexSha256"]}),(TRANSACTIONS,state["transactionBinding"])):
                with (source/name).open("rb") as incoming,(view/name).open("xb") as outgoing:stream_copy(incoming,outgoing,expected["bytes"],expected["sha256"],budget)
                if archive is not None:
                    with archive.open(name) as incoming,(view/(".archived-"+name)).open("xb") as outgoing:stream_copy(incoming,outgoing,expected["bytes"],expected["sha256"],budget)
                    (view/(".archived-"+name)).unlink()
            for item,location in zip(index["segments"],state["locations"]):
                original=source/item["name"]
                if present(original):checked(file_hash(original,LIMITS["sourceEventBytes"],budget)=={k:item[k] for k in ("sha256","bytes")},"Original segment changed")
                if location["storage"]=="hot":incoming=stack.enter_context(original.open("rb"))
                else:
                    checked(archive is not None,"Missing archive location")
                    incoming=stack.enter_context(archive.open(item["name"]))
                with (view/item["name"]).open("xb") as outgoing:stream_copy(incoming,outgoing,item["bytes"],item["sha256"],budget,expected_lines=item["eventCount"])
                incoming.close()
            # Account for the raw reader's bounded verification/identity work,
            # including its own streaming passes, rather than calling it free.
            budget.charge(raw_bytes*8+state["transactionBinding"]["bytes"]*4+(view/INDEX).stat().st_size*16)
            verified=JournalReader(view).verify();budget.check()
            checked(verified.complete and verified.index_sha256==state["sourceIndexSha256"],"Reconstructed raw journal failed")
            yield view
            checked(sum(p.stat().st_size for p in view.rglob("*") if p.is_file())<=LIMITS["temporaryBytes"],"Actual temporary bound")
            self._guard(state,index,budget,pending=pending)
            if state["archive"] is not None:
                record=state["archive"];checked(file_hash(Path(record["path"]),LIMITS["archiveBytes"],budget)=={k:record[k] for k in ("sha256","bytes")},"Archive changed during delivery")

    def _graph(self,view,budget):
        db=point.connect(view/"sources.sqlite3");db.execute("PRAGMA max_page_count=2048");db.set_progress_handler(budget.progress,1000)
        def events():
            for count,event in enumerate(JournalReader(view).iter_events(),1):
                budget.check();checked(count<=LIMITS["sourceEvents"],"Event bound");yield event
        try:
            result=point.build_catalog(db,events());checked(not result["gaps"],"Unproven point source coverage")
            return db
        except BaseException:db.close();raise

    def _roots(self,state,index):
        groups={"transactions":[],"versions":list(index["references"]["versionSources"]),"sequences":[]}
        for pin in state["pins"].values():
            for key in groups:groups[key].extend(pin[key])
        checked(sum(map(len,groups.values()))<=LIMITS["retainedRoots"] and len(canonical(groups))<=LIMITS["retainedRootBytes"],"Root bound")
        return groups

    def verify(self):
        try:
            with self._operation() as budget:
                state,index=self._state()
                with self._view(state,index,budget) as view:
                    db=self._graph(view,budget)
                    try:point.SourceWindows._closure(None,db,**self._roots(state,index))
                    finally:db.close()
                return {"valid":True,"complete":True,"eventCount":index["eventCount"],"sourceIndexSha256":state["sourceIndexSha256"],"generation":state["generation"],"ioBudgetCharged":budget.used}
        except Exception as error:return {"valid":False,"complete":False,"gap":type(error).__name__+": "+str(error)}

    def archive_checkpoint(self,name,destination):
        point.SourceWindows._label(name);destination=Path(destination)
        checked(not present(destination),"Refuse archive overwrite")
        with self._operation() as budget:
            state,index=self._state();checked(state["archive"] is None and len(state["checkpoints"])<16,"Single archive checkpoint scope")
            checked(not destination.resolve().is_relative_to(Path(state["source"])) and not destination.resolve().is_relative_to(self.path),"Archive must be outside store/source")
            with self._view(state,index,budget) as view:
                budget.charge(sum(s["bytes"] for s in index["segments"])*4+state["transactionBinding"]["bytes"]*3)
                JournalReader(view).archive(destination);budget.check()
            record={"path":str(destination.resolve()),**file_hash(destination,LIMITS["archiveBytes"],budget)}
            candidate={**state,"archive":record,"locations":[{"name":s["name"],"storage":"archive"} for s in index["segments"]]}
            with self._view(candidate,index,budget) as view:
                db=self._graph(view,budget);db.close()
            state["archive"]=record;state["checkpoints"][name]={"archiveSha256":record["sha256"],"sourceIndexSha256":state["sourceIndexSha256"]};state["generation"]+=1
            self._publish(state);self.dirty=False
            return {"archiveVerified":True,"originalSegmentsDeleted":0,"archive":record}

    def pin(self,name,*,transactions=(),versions=(),sequences=()):
        point.SourceWindows._label(name)
        for group in (transactions,versions,sequences):checked(type(group) in (list,tuple) and len(group)<=LIMITS["retainedRoots"],"Bounded root sequence required")
        checked(len(transactions)+len(versions)+len(sequences)<=LIMITS["retainedRoots"],"Aggregate root count before copy")
        checked(all(point.scalar(v) for v in (*transactions,*versions)) and all(type(v) is int and 0<v<=9_007_199_254_740_991 for v in sequences),"Root labels/sequence bounds")
        with self._operation() as budget:
            state,index=self._state();checked(name not in state["pins"] and len(state["pins"])<32,"Pin exists/bound")
            state["pins"][name]={"transactions":list(transactions),"versions":list(versions),"sequences":list(sequences)}
            with self._view(state,index,budget) as view:
                db=self._graph(view,budget)
                try:count=point.SourceWindows._closure(None,db,**self._roots(state,index))
                finally:db.close()
            state["generation"]+=1;self._publish(state);self.dirty=False
            return {"sourceClosureComplete":True,"retainedEvents":count}

    def release(self,name):
        point.SourceWindows._label(name)
        with self._operation() as budget:
            state,index=self._state();checked(name in state["pins"],"Unknown pin/window")
            with self._view(state,index,budget) as view:
                db=self._graph(view,budget);db.close()
            del state["pins"][name];state["generation"]+=1;self._publish(state);self.dirty=False

    def read_window(self,name):
        point.SourceWindows._label(name)
        with self._operation() as budget:
            state,index=self._state();checked(name in state["pins"],"Unknown pin/window")
            selected={**state,"pins":{name:state["pins"][name]}}
            with self._view(state,index,budget) as view:
                db=self._graph(view,budget)
                try:
                    point.SourceWindows._closure(None,db,**self._roots(selected,index))
                    for event in JournalReader(view).iter_events():
                        budget.check()
                        if db.execute("SELECT 1 FROM keep WHERE seq=?",(event["seq"],)).fetchone():yield event
                finally:db.close()
                checked(self._state()[0]["manifestSha256"]==state["manifestSha256"],"Manifest changed during window delivery")

    def iter_events(self):
        with self._operation() as budget:
            state,index=self._state()
            with self._view(state,index,budget) as view:
                db=self._graph(view,budget);db.close()
                for event in JournalReader(view).iter_events():budget.check();yield event
                checked(self._state()[0]["manifestSha256"]==state["manifestSha256"],"Manifest changed during delivery")

    def _hit(self,stage):
        if self.fault:self.fault(stage)

    def prune(self,*,before_seq):
        checked(type(before_seq) is int and 0<=before_seq<=9007199254740991,"Cutoff")
        with self._operation() as budget:
            state,index=self._state();checked(state["archive"] is not None and state["checkpoints"],"Verified archive checkpoint required")
            with self._view(state,index,budget) as view:
                db=self._graph(view,budget)
                try:
                    roots=self._roots(state,index);point.SourceWindows._closure(None,db,**roots)
                    targets=[item for item,location in zip(index["segments"],state["locations"]) if location["storage"]=="hot" and item["lastSeq"]<before_seq and db.execute("SELECT 1 FROM keep WHERE seq BETWEEN ? AND ? LIMIT 1",(item["firstSeq"],item["lastSeq"])).fetchone() is None]
                finally:db.close()
            if not targets:return {"originalSegmentsDeleted":[],"archivesDeleted":False}
            intent={"schema":1,"plan":uuid.uuid4().hex,"nonce":state["nonce"],"operationToken":self.operation_token,"sourceIndexSha256":state["sourceIndexSha256"],"baseGeneration":state["generation"],"baseManifestSha256":state["manifestSha256"],"rootsSha256":digest(canonical(roots)),"archive":state["archive"],"targets":targets,"beforeSeq":before_seq}
            self.dirty=True
            with (self.path/"prune-intent.json").open("xb") as file:file.write(canonical(intent));file.flush();os.fsync(file.fileno())
            point.sync_directory(self.path);self._hit("after-intent")
            result=self._finish(state,index,intent,budget)
            self.dirty=False;return result

    def _finish(self,state,index,intent,budget):
        validate_intent(intent,state,index);checked(intent["operationToken"]==self.operation_token,"Abandoned operation token differs from prepared intent")
        checked(digest(canonical(self._roots(state,index)))==intent["rootsSha256"],"Retained roots changed")
        self._guard(state,index,budget,pending=True)
        if state["generation"]==intent["baseGeneration"]:
            checked(state["manifestSha256"]==intent["baseManifestSha256"],"Base manifest changed")
            names={item["name"] for item in intent["targets"]}
            state={**state,"locations":[{"name":loc["name"],"storage":"archive" if loc["name"] in names else loc["storage"]} for loc in state["locations"]],"pending":intent["plan"],"generation":state["generation"]+1}
            state=self._publish(state);self._hit("after-manifest")
        with self._view(state,index,budget,pending=True) as view:
            db=self._graph(view,budget)
            try:
                point.SourceWindows._closure(None,db,**self._roots(state,index))
                for item in intent["targets"]:
                    checked(item["lastSeq"]<intent["beforeSeq"] and db.execute("SELECT 1 FROM keep WHERE seq BETWEEN ? AND ? LIMIT 1",(item["firstSeq"],item["lastSeq"])).fetchone() is None,"Intent touches retained closure/cutoff")
                    checked(next(loc["storage"] for loc in state["locations"] if loc["name"]==item["name"])=="archive","Target was not published to archive")
            finally:db.close()
        deleted=[]
        for item in intent["targets"]:
            self._guard(state,index,budget,pending=True)
            record=state["archive"];checked(file_hash(Path(record["path"]),LIMITS["archiveBytes"],budget)=={k:record[k] for k in ("sha256","bytes")},"Archive disappeared before unlink")
            target=Path(state["source"])/item["name"]
            if present(target):
                checked(file_hash(target,LIMITS["sourceEventBytes"],budget)=={k:item[k] for k in ("sha256","bytes")},"Retiring original segment changed")
                target.unlink();point.sync_directory(target.parent);deleted.append(item["name"]);self._hit("after-unlink")
        with self._view(state,index,budget,pending=True) as view:
            db=self._graph(view,budget);db.close()
        if state["generation"]!=intent["baseGeneration"]+2:
            state={**state,"pending":None,"generation":intent["baseGeneration"]+2,"completedPlan":intent["plan"],"completedIntent":intent};state=self._publish(state)
        (self.path/"prune-intent.json").unlink();point.sync_directory(self.path)
        self._hit("after-intent-clear")
        # Final publication is not a substitute for checking the delivered
        # binding. Recheck the original guards and actual archive contents.
        with self._view(state,index,budget,pending=True) as view:
            db=self._graph(view,budget);db.close()
        return {"originalSegmentsDeleted":deleted,"archivesDeleted":False,"rawSourceVerifiedAfterDeletion":True,"plan":intent["plan"]}

    def recover(self,*,expected_plan,exclusive_recovery=False):
        checked(exclusive_recovery is True,"Explicit recovery scope required")
        with self._operation(recover=True) as budget:
            state,index=self._state(allow_failed=True)
            intent=load(self.path/"prune-intent.json",budget=budget)[0] if present(self.path/"prune-intent.json") else state.get("completedIntent")
            checked(type(intent) is dict,"No explicit recoverable plan")
            checked(intent.get("plan")==expected_plan,"Unexpected recovery plan")
            # Refuse unauthorised or malformed requests before marking this
            # recovery as mutating. A rejected request must not create a new
            # failure marker bound to a foreign lock token and poison a valid
            # prepared plan. _finish repeats these checks before mutation.
            validate_intent(intent,state,index)
            checked(intent["operationToken"]==self.operation_token,"Abandoned operation token differs from prepared intent")
            checked(digest(canonical(self._roots(state,index)))==intent["rootsSha256"],"Retained roots changed")
            marker=self.path/"operation-failed.json";marker_sha=None
            if present(marker):
                failure,marker_sha=load(marker,4096,budget=budget)
                checked(failure=={"kind":"archive-operation-failed/1","nonce":state["nonce"],"operationToken":self.operation_token},"Foreign failed-operation marker")
            self.dirty=True
            # A terminal manifest may have been published before intent removal
            # or the owner lock cleanup failed. Recreate only its exact plan,
            # never a synthetic source record, so _finish uses the same path.
            if not present(self.path/"prune-intent.json"):
                with (self.path/"prune-intent.json").open("xb") as file:file.write(canonical(intent));file.flush();os.fsync(file.fileno())
                point.sync_directory(self.path)
            result=self._finish(state,index,intent,budget)
            if present(marker):
                failure,current_marker_sha=load(marker,4096,budget=budget)
                checked(failure=={"kind":"archive-operation-failed/1","nonce":state["nonce"],"operationToken":self.operation_token},"Foreign failed-operation marker")
                checked(marker_sha==current_marker_sha,"Failed-operation marker changed during recovery")
                marker.unlink();point.sync_directory(self.path)
            self.dirty=False;return result

    def delete_archive(self):raise Incomplete("Archive retention is mandatory; deletion unimplemented")
