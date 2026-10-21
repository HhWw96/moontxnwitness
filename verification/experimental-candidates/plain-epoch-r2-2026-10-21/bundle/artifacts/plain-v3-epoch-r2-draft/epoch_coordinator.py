"""Two quiescent point epochs. No SQL proof, source pruning or auto-resume."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import uuid

from epoch_sources import (Boundary,Control,EpochError,Installation,References,SourceLog,SourceLogReader,
                           canonical,idle_setup,plain,require)
from point_epoch import EpochCapture
from initialization_guard import bounded_keys
from moontxnwitness_capture.journal_v3 import JournalReader,_sync_directory


def present(path):
    try:path.lstat();return True
    except FileNotFoundError:return False


def fd_identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode)


def confirm_path(path,info):
    # Windows stat(path) and fstat(fd) have different ctime API semantics.
    # Compare ctime only through the same fd API, never silently drop identity.
    require(not path.is_symlink(),"Source path became symlink")
    with path.open("rb") as probe:
        fresh=os.fstat(probe.fileno())  # Identity-only probe: no content read.
        require(stat.S_ISREG(fresh.st_mode) and fd_identity(fresh)==fd_identity(info),"Source path handle changed")
    current=path.stat()
    require(not path.is_symlink() and stat.S_ISREG(current.st_mode)
            and (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)==
                (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns),"Source path metadata changed")


def read_json(path,limit=131072):
    require(not path.is_symlink(),"Symlink metadata")
    with path.open("rb") as file:
        before=os.fstat(file.fileno());require(stat.S_ISREG(before.st_mode),"Nonregular metadata")
        raw=file.read(limit+1);after=os.fstat(file.fileno())
    require(len(raw)<=limit and fd_identity(before)==fd_identity(after) and len(raw)==after.st_size,"Metadata size/race")
    confirm_path(path,after)
    def unique(items):
        result={}
        for key,value in items:
            require(key not in result,"Duplicate metadata key");result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)


def write_json(path,value,*,replace=False):
    raw=canonical(value)+b"\n";require(len(raw)<=131072,"Coordinator metadata byte budget")
    temporary=path.with_name(path.name+".tmp-"+uuid.uuid4().hex) if replace else path
    with temporary.open("xb") as file:file.write(raw);file.flush();os.fsync(file.fileno())
    if replace:os.replace(temporary,path)
    _sync_directory(path.parent)


def file_binding(path,max_bytes=16*1024*1024):
    require(not path.is_symlink(),"Source symlink")
    hashed=hashlib.sha256();size=0
    with path.open("rb") as file:
        info=os.fstat(file.fileno());require(stat.S_ISREG(info.st_mode) and info.st_size<=max_bytes,"Source type/byte budget")
        while raw:=file.read(min(65536,max_bytes-size+1)):
            size+=len(raw);require(size<=max_bytes,"Source grew beyond budget");hashed.update(raw)
        after=os.fstat(file.fileno())
    require(fd_identity(info)==fd_identity(after) and size==after.st_size,"Source changed during bounded read")
    confirm_path(path,after)
    return {"bytes":size,"sha256":hashed.hexdigest()}


def tree_bindings(path):
    require(not path.is_symlink() and path.is_dir(),"Source tree type")
    result={};size=0;nodes=0
    for file in path.rglob("*"):
        nodes+=1;require(nodes<=256,"Source tree node budget")
        require(not file.is_symlink(),"Source tree symlink")
        if not file.is_file():continue
        require(len(result)<128,"Source file-count budget")
        item=file_binding(file);size+=item["bytes"];require(size<=32*1024*1024,"Epoch aggregate disk budget")
        result[file.relative_to(path).as_posix()]=item
    return dict(sorted(result.items()))  # Only the already-bounded file map.


def exact_children(path,expected):
    found=set()
    for child in path.iterdir():
        require(child.name in expected and child.name not in found and not child.is_symlink() and child.is_dir(),"Unexpected chain child")
        found.add(child.name)
    require(found==expected,"Missing chain child")


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


class NativeMutex:
    def __init__(self,path,nonce):self.path,self.nonce,self.file=path,nonce,None
    def acquire(self):
        require(not self.path.is_symlink(),"Mutex symlink")
        self.file=self.path.open("r+b")
        try:
            os_lock(self.file)  # Windows must lock before reading the protected byte.
            identity=os.fstat(self.file.fileno());self.file.seek(0);raw=self.file.read(2049)
            require(len(raw)<=2048 and json.loads(raw)=={"kind":"epoch-native-mutex/1","nonce":self.nonce},"Mutex authority")
            current=self.path.stat()
            require(not self.path.is_symlink() and stat.S_ISREG(identity.st_mode)
                    and (identity.st_dev,identity.st_ino)==(current.st_dev,current.st_ino),"Mutex path/inode changed")
            return self
        except BaseException:
            self.file.close();self.file=None;raise
    def release(self):
        if self.file is None:return
        try:os_unlock(self.file)
        finally:self.file.close();self.file=None
    def __enter__(self):return self.acquire()
    def __exit__(self,*args):self.release()


class EpochCoordinator:
    def __init__(self,path):
        self.path=Path(path);self.manifest=read_json(self.path/"manifest.json")
        self.nonce=self.manifest["nonce"];self.registry=References(self.path/"references.sqlite3")
        self.current=None;self._captures=[];self._poisoned=False;self._caller=None;self._local=threading.RLock()

    @classmethod
    def create(cls,path,setup,*,schema,keys,table="items",exclusive_writers=False,max_live=128):
        require(exclusive_writers is True,"Explicit controlled writers required")
        keys=bounded_keys(keys)
        path=Path(path);path.mkdir(parents=False,exist_ok=False);(path/"epochs").mkdir();(path/"boundaries").mkdir()
        nonce=str(uuid.uuid4());write_json(path/"coordination.lock",{"kind":"epoch-native-mutex/1","nonce":nonce})
        References(path/"references.sqlite3",create=True)
        state={"schema":"point-epoch-chain/1","nonce":nonce,"generation":0,"phase":"creating","current":"epoch-0000",
               "scope":{"schema":schema,"table":table,"keys":list(keys),"exclusiveWriters":True},"sealed":[],"boundaries":[],
               "sourceClosureVerified":False,"coreProofImplemented":False,"formalEligible":False}
        write_json(path/"manifest.json",state);result=cls(path)
        with result._operation("create"):
            write_json(path/"intent.json",{"kind":"create","nonce":nonce,"generation":0})
            capture=EpochCapture(path/"epochs/epoch-0000",epoch="epoch-0000",registry=result.registry,coordinator=result,
                schema=schema,table=table,keys=keys,exclusive_writers=True,max_live=max_live)
            result.current=capture;result._captures.append(capture)
            capture.initialize(setup)
            result.manifest["phase"]="running";result._write_manifest();(path/"intent.json").unlink()
        capture._released=True;return result

    def _stage(self,name):pass  # Test observation hook; never source proof.
    def _write_manifest(self):write_json(self.path/"manifest.json",self.manifest,replace=True)
    def _failure_marker(self,code):write_json(self.path/"failed.json",{"nonce":self.nonce,"reason":code},replace=present(self.path/"failed.json"))
    def invalidate(self,code):
        self._poisoned=True
        try:self._failure_marker(code)
        except Exception:pass

    @contextlib.contextmanager
    def _operation(self,kind,preflight=None):
        with self._local:
            require(not self._poisoned and not present(self.path/"failed.json"),"Coordinator poisoned")
            mutex=NativeMutex(self.path/"coordination.lock",self.nonce).acquire()
            owner={"nonce":self.nonce,"token":uuid.uuid4().hex,"kind":kind,"generation":self.manifest["generation"]}
            owner_path=self.path/"operation.lock";owned=False;primary=None;removed=False
            try:
                require(not present(owner_path),"Existing operation requires explicit recovery inspection")
                if preflight is not None:preflight()  # Native lock held; no new owner/intent yet.
                write_json(owner_path,owner);owned=True
                yield
                require(not self._poisoned,"Coordinator invalidated during operation")
                require(read_json(owner_path)==owner,"Owner changed before protected sync")
                _sync_directory(self.path)  # All data/intent work is committed while guard remains.
                require(read_json(owner_path)==owner,"Owner changed at commit")
                self._stage("data_committed")
                owner_path.unlink();removed=True  # No durability promise for temporary guard deletion.
            except BaseException as error:
                primary=error
                if owned:self.invalidate("operation_failed")
                raise
            finally:
                try:mutex.release()
                except BaseException:
                    self._poisoned=True
                    if removed:
                        try:write_json(owner_path,owner)
                        except Exception:pass  # Confirmed post-data-commit coordination boundary.
                    try:self._failure_marker("native_release_failed")
                    except Exception:pass
                    if primary is None:raise

    def quiesce(self,*,expected_generation):
        with self._local:
            require(self.current is not None and expected_generation==self.manifest["generation"],"Stale generation/current observer")
            require(not self._poisoned,"Coordinator poisoned")
            with self.current._lock:
                self.current._admissions_stopped=True
                if self._caller is None:self._caller={"nonce":self.nonce,"generation":expected_generation,"token":uuid.uuid4().hex}
                return dict(self._caller)

    def _boundary(self,setup,epoch,*,max_ledger=1024):
        idle_setup(setup);old=self.current;installation=old.installation;n=installation.names
        path=self.path/"boundaries"/("boundary-"+str(self.manifest["generation"]).zfill(4));log=SourceLog(path)
        control=Control(setup,log)
        try:
            require(control.execute("BEGIN ISOLATION LEVEL READ COMMITTED").statusmessage=="BEGIN","Boundary BEGIN not confirmed")
            control.identity()
            lock="LOCK TABLE "+",".join([n.business]+[n.object(s) for s in ("installation","audit","state")])+" IN ACCESS EXCLUSIVE MODE"
            require(control.execute(lock).statusmessage=="LOCK TABLE","Boundary lock not acknowledged")
            first=control.verify(installation);final=control.snapshot(n)
            ledger,count=control.ledger(n,max_rows=max_ledger)
            second=control.verify(installation);next_snapshot=control.snapshot(n)
            self._stage("boundary_prepared")
            acknowledgement=control.execute("COMMIT")
            require(acknowledgement.statusmessage=="COMMIT","Setup returned rollback instead of COMMIT")
            summary={"nonce":installation.nonce,"tableOid":installation.table_oid,"serverVersion":setup.info.server_version,
                "connection":control.connection,"backendPid":control.backend_pid,"transaction":control.txid,
                "lockSeq":3,"verifyRanges":[first,second],"finalSnapshot":final,"nextSnapshot":next_snapshot,
                "ledgerRange":ledger,"ledgerRows":count,"commitSeq":control.last}
            log.append({"kind":"boundary-end","summary":summary});log.close()
            self._stage("database_acknowledged")
            packet=Boundary(path,summary,installation,tuple(sorted(old.keys)));packet.validate();return packet
        except BaseException:
            log.failed=True
            try:setup.execute("ROLLBACK")
            except Exception:pass  # An idle rollback never manufactures the missing COMMIT acknowledgement.
            try:log.close()
            except Exception:pass
            raise

    def _transition(self,setup,caller,expected_generation,*,next_epoch,max_ledger=1024):
        def preflight():
            require(expected_generation==self.manifest["generation"] and caller==self._caller,"Stale generation or wrong caller barrier")
            require(self.current is not None and not self.current.admission(),"Epoch not quiescent by observed close acknowledgements")
            require(self.current._admissions_stopped and self.manifest["phase"]=="running","Explicit quiescent barrier required")
            require(not next_epoch or len(self._captures)<2,"Two-epoch slice limit")
            on_disk=read_json(self.path/"manifest.json")
            require(on_disk==self.manifest,"Manifest generation changed")
        new=None
        with self._operation("handoff" if next_epoch else "finish",preflight):
            old=self.current
            intent={"kind":"handoff" if next_epoch else "finish","nonce":self.nonce,"generation":expected_generation,
                "old":old.epoch,"next":"epoch-0001" if next_epoch else None,"caller":caller}
            write_json(self.path/"intent.json",intent);self._stage("intent_durable")
            packet=self._boundary(setup,old.epoch,max_ledger=max_ledger)
            boundary_files=tree_bindings(packet.path)
            old.sources.append({"kind":"ledger-end","rows":packet.summary["ledgerRows"],"complete":True,
                "commandTag":"COMMIT","boundaryId":packet.path.name,"boundaryBindings":boundary_files})
            old._ledger_complete=True
            status=old.close(source_closed=True);require(status.complete,"Old epoch failed sealing")
            self.registry.index_epoch(old.epoch,old)
            sealed={"epoch":old.epoch,"clockDomain":old.clock_domain,"files":tree_bindings(old.path)}
            self._stage("old_sealed")
            if next_epoch:
                scope=self.manifest["scope"]
                new=EpochCapture(self.path/"epochs/epoch-0001",epoch="epoch-0001",registry=self.registry,coordinator=self,
                    schema=scope["schema"],table=scope["table"],keys=scope["keys"],exclusive_writers=True,max_live=old._max_live)
                self._captures.append(new);new.initialize_from_boundary(packet)
                self._stage("new_published")
            self.manifest["sealed"].append(sealed)
            self.manifest["boundaries"].append({"name":packet.path.name,"files":boundary_files,"summary":packet.summary})
            self.manifest["generation"]+=1;self.manifest["phase"]="running" if next_epoch else "closed"
            self.manifest["current"]="epoch-0001" if next_epoch else None
            require(not old._invalidated and not old.gaps and JournalReader(old.journal.path).verify().complete,"Old epoch invalidated before manifest")
            self._write_manifest();self._stage("manifest_published")
            (self.path/"intent.json").unlink()
            # These are in-memory admission state only. The native commit point
            # and permanent mutex release still occur before any caller returns.
            self.current=new;self._caller=None
        with self._local:
            require(not self._poisoned and not old._invalidated,"Late old activity blocks new admission")
            if new is not None:new._released=True
        return new if next_epoch else self.verify_chain()

    def handoff(self,setup,*,caller,expected_generation,max_ledger=1024):
        return self._transition(setup,caller,expected_generation,next_epoch=True,max_ledger=max_ledger)
    def finish(self,setup,*,caller,expected_generation,max_ledger=1024):
        return self._transition(setup,caller,expected_generation,next_epoch=False,max_ledger=max_ledger)

    def verify_chain(self):
        result={"valid":True,"rawEpochChainComplete":False,"sourceClosureVerified":False,"coreProofImplemented":False,"formalEligible":False,"reasons":[]}
        try:
            require(not self._poisoned,"Live coordinator poisoned")
            with NativeMutex(self.path/"coordination.lock",self.nonce):
                require(not any(present(self.path/name) for name in ("operation.lock","failed.json","intent.json")),"Failure/recovery authority present")
                state=read_json(self.path/"manifest.json");require(state["nonce"]==self.nonce,"Manifest nonce")
                require(state["schema"]=="point-epoch-chain/1" and state["phase"] in ("running","closed"),"Manifest schema/phase")
                count=len(state["sealed"])
                require(type(state["generation"]) is int and 0<=count<=2 and state["generation"]==count==len(state["boundaries"]),"Manifest generation/chain length")
                expected_epochs=["epoch-"+str(i).zfill(4) for i in range(count)]
                require([record["epoch"] for record in state["sealed"]]==expected_epochs,"Manifest epoch sequence")
                require([record["name"] for record in state["boundaries"]]==["boundary-"+str(i).zfill(4) for i in range(count)],"Manifest boundary sequence")
                if state["phase"]=="closed":
                    require(count>=1 and state["current"] is None,"Closed chain current observer")
                    expected_directories=set(expected_epochs)
                else:
                    require(count<2 and state["current"]=="epoch-"+str(count).zfill(4),"Running chain current observer")
                    expected_directories=set(expected_epochs+[state["current"]])
                exact_children(self.path/"epochs",expected_directories)
                exact_children(self.path/"boundaries",{record["name"] for record in state["boundaries"]})
                names=plain.ColumnPointProfile(state["scope"]["schema"],state["scope"]["table"]).names
                snapshots=[];initial_sources=[]
                for record in state["sealed"]:
                    path=self.path/"epochs"/record["epoch"]
                    require(tree_bindings(path)==record["files"],"Sealed epoch bytes/marker changed")
                    require(JournalReader(path/"journal").verify().complete and SourceLogReader(path/"sources").verify()["complete"],"Sealed epoch evidence incomplete")
                    first=next(JournalReader(path/"journal").iter_events(require_complete=True),None)
                    require(first is not None and first["kind"]=="snapshot" and first["consistent"] is True,"Actual epoch initial snapshot")
                    snapshots.append(first["initial"])
                    source_first=None;source_last=None
                    for raw in SourceLogReader(path/"sources").iter_records():
                        if source_first is None:source_first=raw["payload"]
                        source_last=raw["payload"]
                    initial_sources.append(source_first)
                    boundary=state["boundaries"][len(snapshots)-1]
                    require(source_last is not None and source_last.get("kind")=="ledger-end" and source_last.get("complete") is True
                            and source_last.get("commandTag")=="COMMIT" and source_last.get("boundaryId")==boundary["name"]
                            and source_last.get("boundaryBindings")==boundary["files"],"Old ledger footer/boundary binding")
                for i,boundary in enumerate(state["boundaries"]):
                    path=self.path/"boundaries"/boundary["name"]
                    require(tree_bindings(path)==boundary["files"],"Boundary bytes changed")
                    summary=boundary["summary"]
                    packet=Boundary(path,summary,Installation(names,summary["nonce"],summary["tableOid"],{}),tuple(state["scope"]["keys"]))
                    values=packet.validate()
                    if i+1<len(snapshots):
                        require(snapshots[i+1]=={key:row[1] for key,row in values.items()},"Cross-epoch token discontinuity")
                        source=initial_sources[i+1]
                        require(source["kind"]=="boundary-initialization" and source["boundaryId"]==boundary["name"]
                                and source["boundarySummary"]==summary and source["boundaryBindings"]==packet.bindings()
                                and source["initialRows"]==[[key,value,version] for key,(value,version) in sorted(values.items())],"New observer boundary source binding")
                require(not any(c._invalidated for c in self._captures),"Live late-use invalidation")
                result["rawEpochChainComplete"]=state["phase"]=="closed" and bool(state["sealed"])
                if not result["rawEpochChainComplete"]:result["reasons"].append("current-epoch-open")
        except Exception as error:
            result["valid"]=False;result["reasons"].append(type(error).__name__+": "+str(error))
        return result

    def recover(self,*,owner):
        with NativeMutex(self.path/"coordination.lock",self.nonce):
            require(present(self.path/"operation.lock") and read_json(self.path/"operation.lock")==owner,"Exact recovery owner required")
            return {"mode":"inspect-only","canResume":False,"rawEpochChainComplete":False,"sourceClosureVerified":False,
                "intent":read_json(self.path/"intent.json") if present(self.path/"intent.json") else None,
                "reason":"No automatic COMMIT/observer recovery proof; original guards and all source remain."}

    def prune(self,**kwargs):
        return {"allowed":False,"deleted":0,"sourceClosureVerified":False,"reason":"SQL-bearing dependency graph remains unproved; all source retained"}
