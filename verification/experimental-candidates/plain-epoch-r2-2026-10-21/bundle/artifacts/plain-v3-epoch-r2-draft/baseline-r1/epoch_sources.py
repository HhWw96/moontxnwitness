"""Bounded disk references and recorded setup evidence, not SQL-core proof."""
from __future__ import annotations
import base64
import contextlib
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"artifacts/plain-v3-journal-r2-draft"
sys.path.insert(0,str(BASE))
if hashlib.sha256((BASE/"profile.py").read_bytes()).hexdigest()!="906777ff7696a526c41426a9a0848a06ae736d1f8457deb96e7cb1f8c4e01e96":
    raise ImportError("Frozen R2 profile changed")
spec=importlib.util.spec_from_file_location("_epoch_r2_profile",BASE/"profile.py")
plain=importlib.util.module_from_spec(spec);sys.modules[spec.name]=plain;spec.loader.exec_module(plain)
from source_log import SourceLog,SourceLogReader
from capture_profile import verify_installation
from prototype import Installation,identifier,idle_setup
from moontxnwitness_capture.capture import _status
from moontxnwitness_capture.journal_v3 import JournalReader


class EpochError(RuntimeError):pass


def require(value,message):
    if not value:raise EpochError(message)


def canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode()


def pack(value):
    remaining=[4096,60000]
    def visit(item,depth=0):
        remaining[0]-=1;remaining[1]-=16
        require(depth<=32 and min(remaining)>=0,"Native observation budget")
        if item is None or type(item) in (bool,int):return item
        if type(item) is str:
            require(len(item)<=60000,"Native string budget")
            remaining[1]-=len(canonical(item));require(remaining[1]>=0,"Native string aggregate budget");return item
        if type(item) is bytes or type(item) is memoryview:
            size=item.nbytes if type(item) is memoryview else len(item)
            require(size<=remaining[1]//2 and (type(item) is not memoryview or item.c_contiguous),"Native bytes budget")
            remaining[1]-=size*2;return {"nativeType":"bytes","base64":base64.b64encode(item).decode()}
        require(type(item) in (list,tuple) and len(item)<=128,"Native container/type budget")
        return {"nativeType":"tuple" if type(item) is tuple else "list","items":[visit(child,depth+1) for child in item]}
    return visit(value)


def unpack(value):
    if type(value) is not dict:return value
    if set(value)=={"nativeType","base64"} and value["nativeType"]=="bytes":return base64.b64decode(value["base64"],validate=True)
    require(set(value)=={"nativeType","items"} and value["nativeType"] in ("list","tuple"),"Native encoding changed")
    values=[unpack(item) for item in value["items"]]
    return tuple(values) if value["nativeType"]=="tuple" else values


class References:
    """Rebuildable SQLite cache. Raw journals/side records remain authority."""
    def __init__(self,path,*,create=False):
        self.path=Path(path)
        require(create or self.path.is_file(),"Missing reference index")
        if create:require(not self.path.exists(),"Reference index already exists")
        with self.open() as db:
            if create:db.executescript("CREATE TABLE connections(id TEXT PRIMARY KEY,epoch TEXT,state TEXT,ack TEXT);CREATE TABLE versions(epoch TEXT,version TEXT,key TEXT,seq INTEGER,tx TEXT,origin_epoch TEXT,origin_seq INTEGER,PRIMARY KEY(epoch,version));CREATE TABLE reads(epoch TEXT,seq INTEGER,version TEXT,PRIMARY KEY(epoch,seq));CREATE TABLE outcomes(epoch TEXT,tx TEXT,status TEXT,PRIMARY KEY(epoch,tx));")
    @contextlib.contextmanager
    def open(self):
        require(not self.path.is_symlink(),"Reference index symlink")
        db=sqlite3.connect(self.path);db.execute("PRAGMA journal_mode=DELETE");db.execute("PRAGMA synchronous=FULL")
        try:yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def connection(self,identity,epoch,state,ack=None):
        with self.open() as db:
            if state=="open":
                require(db.execute("SELECT count(*) FROM connections").fetchone()[0]<8192,"Connection reference disk budget")
                db.execute("INSERT INTO connections VALUES(?,?,?,NULL)",(identity,epoch,state))
            else:db.execute("UPDATE connections SET state=?,ack=? WHERE id=? AND epoch=?",(state,json.dumps(ack),identity,epoch))
    def closed(self,epoch):
        with self.open() as db:return db.execute("SELECT count(*) FROM connections WHERE epoch=? AND state<>'closed'",(epoch,)).fetchone()[0]==0
    def index_epoch(self,epoch,capture):
        with self.open() as db:
            for event in JournalReader(capture.journal.path).iter_events(require_complete=True):
                kind=event["kind"]
                if kind=="snapshot":
                    for key,version in event["initial"].items():
                        old=db.execute("SELECT epoch,seq FROM versions WHERE version=? AND epoch<>? ORDER BY rowid DESC LIMIT 1",(version,epoch)).fetchone()
                        db.execute("INSERT INTO versions VALUES(?,?,?,?,NULL,?,?)",(epoch,version,key,event["seq"],old[0] if old else None,old[1] if old else None))
                elif kind=="write":db.execute("INSERT INTO versions VALUES(?,?,?,?,?,NULL,NULL)",(epoch,event["version"],event["key"],event["seq"],event["tx"]))
                elif kind=="read":db.execute("INSERT INTO reads VALUES(?,?,?)",(epoch,event["seq"],event["version"]))
                elif kind in ("commit_ok","rollback_ok","disconnect"):
                    db.execute("INSERT OR REPLACE INTO outcomes VALUES(?,?,?)",(epoch,event["tx"],kind))


class ControlCursor:
    def __init__(self,observer,raw,sql,params,before):
        self.observer,self.raw,self.sql,self.params,self.before=observer,raw,sql,params,before
        self.identity=uuid.uuid4().hex;self.part=0
        if raw.description is None:self.record([],"none",True)
    def record(self,rows,method,complete):
        require(len(rows)<=128,"Control query row budget")
        payload={"kind":"query","query":self.identity,"part":self.part,"sql":self.sql,"parameters":pack(self.params),
            "nativeRows":pack(rows),"fetch":method,"complete":complete,"connection":self.observer.connection,
            "backendPid":self.observer.backend_pid,"transaction":self.observer.txid,"statusBefore":self.before,
            "statusAfter":_status(self.observer.raw),"commandTag":self.raw.statusmessage,
            "pgStatus":int(self.raw.pgresult.status)}
        self.part+=1;self.observer.last=self.observer.log.append(payload);return self.observer.last
    def fetchone(self):
        value=self.raw.fetchone();self.record([] if value is None else [value],"one",value is None or self.raw.rownumber==self.raw.rowcount);return value
    def fetchall(self):
        rows=self.raw.fetchall();self.record(rows,"all",True);return rows
    def fetchmany(self,size):
        rows=self.raw.fetchmany(size);self.record(rows,"many",not rows or self.raw.rownumber==self.raw.rowcount);return rows
    @property
    def statusmessage(self):return self.raw.statusmessage


class Control:
    def __init__(self,raw,log):
        self.raw,self.log,self.last=raw,log,0;self.connection="setup-"+uuid.uuid4().hex
        self.backend_pid=raw.info.backend_pid;self.txid=None
    def execute(self,sql,params=None):
        before=_status(self.raw)
        try:raw=self.raw.execute(sql,params)
        except BaseException as error:
            try:self.log.append({"kind":"query-error","sql":sql,"parameters":pack(params),"connection":self.connection,
                "backendPid":self.backend_pid,"transaction":self.txid,"error":{"class":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None)}})
            except Exception:self.log.failed=True
            raise
        return ControlCursor(self,raw,sql,params,before)
    def identity(self):
        row=self.execute("SELECT pg_backend_pid(),pg_current_xact_id()::text").fetchone()
        require(type(row) is tuple and len(row)==2 and row[0]==self.backend_pid and type(row[1]) is str and row[1],"Actual setup identity")
        self.txid=row[1]
    def verify(self,installation):
        start=self.log.count+1;verify_installation(self,installation);return [start,self.log.count]
    def snapshot(self,names):
        sql=("SELECT "+identifier(names.key_column)+","+identifier(names.value_column)+","+identifier(names.version_column)
             +"::text FROM "+names.business+" ORDER BY "+identifier(names.key_column)+" LIMIT 65")
        start=self.log.count+1;cursor=self.execute(sql)
        while rows:=cursor.fetchmany(32):pass
        return [start,self.log.count]
    def ledger(self,names,*,max_rows=1024):
        require(type(max_rows) is int and 1<=max_rows<=1024,"Ledger limit")
        sql="SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM "+names.object("audit")+" ORDER BY token"
        start=self.log.count+1;count=0
        with self.raw.cursor(name="mtw_epoch_"+uuid.uuid4().hex) as cursor:
            cursor.execute(sql)
            while True:
                rows=cursor.fetchmany(32);count+=len(rows);require(count<=max_rows,"Ledger bound exceeded")
                self.log.append({"kind":"ledger-batch","sql":sql,"nativeRows":pack(rows),"countThrough":count,
                    "exhausted":not rows,"connection":self.connection,"backendPid":self.backend_pid,"transaction":self.txid,
                    "commandTag":cursor.statusmessage,"pgStatus":int(cursor.pgresult.status)})
                if not rows:break
        return [start,self.log.count],count


class ReplayCursor:
    def __init__(self,record):self.record=record
    def fetchone(self):
        require(self.record["fetch"]=="one","Different catalog fetch API");rows=unpack(self.record["nativeRows"])
        require(len(rows)<=1,"Catalog one row bound");return rows[0] if rows else None
    def fetchall(self):
        require(self.record["fetch"]=="all","Different catalog fetch API");return unpack(self.record["nativeRows"])


class Replay:
    def __init__(self,records):self.records=iter(records)
    def execute(self,sql,params=None):
        record=next(self.records)
        require(record["kind"]=="query" and record["sql"]==sql and record["parameters"]==pack(params)
                and record["complete"] and record["pgStatus"]==2,"Recorded catalog SQL/parameters/ACK changed")
        return ReplayCursor(record)
    def finish(self):require(next(self.records,None) is None,"Extra catalog records")


@dataclass(frozen=True)
class Boundary:
    path:Path
    summary:dict
    installation:object
    keys:tuple

    def bindings(self):
        # Import only at call time to avoid a module cycle. These are exact raw
        # source bytes, not a boolean installer success declaration.
        from epoch_coordinator import file_binding
        require(SourceLogReader(self.path).verify()["complete"],"Boundary not sealed")
        return {name:file_binding(self.path/name) for name in ("index.json","records.jsonl")}

    def records(self,span):
        for record in SourceLogReader(self.path).iter_records():
            if span[0]<=record["seq"]<=span[1]:yield record["payload"]
    def snapshot(self,span):
        values={};n=self.installation.names
        query=("SELECT "+identifier(n.key_column)+","+identifier(n.value_column)+","+identifier(n.version_column)
               +"::text FROM "+n.business+" ORDER BY "+identifier(n.key_column)+" LIMIT 65")
        for record in self.records(span):
            require(record["kind"]=="query" and record["fetch"]=="many" and record["pgStatus"]==2,"Snapshot actual query batches")
            require(record["sql"]==query,"Snapshot statement changed")
            for key,value,version in unpack(record["nativeRows"]):
                require(key in self.keys and key not in values and type(value) is int,"Boundary key/value")
                values[key]=(value,plain.token(version));require(len(values)<=64,"Boundary row bound")
        require(set(values)==set(self.keys) and len({v[1] for v in values.values()})==len(values),"Complete unique boundary")
        return values
    def validate(self):
        require(SourceLogReader(self.path).verify()["complete"],"Boundary source incomplete")
        summary=self.summary
        n=self.installation.names
        require(summary["nonce"]==self.installation.nonce and summary["tableOid"]==self.installation.table_oid,"Boundary installation identity")
        require(180000<=summary["serverVersion"]<190000,"Boundary PG18")
        a,b=summary["verifyRanges"];f,t=summary["finalSnapshot"],summary["nextSnapshot"];l=summary["ledgerRange"]
        require(3==summary["lockSeq"]<a[0]<=a[1]<f[0]<=f[1]<l[0]<=l[1]<b[0]<=b[1]<t[0]<=t[1]<summary["commitSeq"],"Boundary query order/intervals")
        lock=list(self.records([3,3]))
        expected_lock="LOCK TABLE "+",".join([n.business]+[n.object(s) for s in ("installation","audit","state")])+" IN ACCESS EXCLUSIVE MODE"
        require(len(lock)==1 and lock[0]["sql"]==expected_lock and lock[0]["commandTag"]=="LOCK TABLE" and lock[0]["pgStatus"]==1,"Actual complete owned-table lock")
        for span in summary["verifyRanges"]:
            replay=Replay(self.records(span));verify_installation(replay,self.installation);replay.finish()
        all_records=SourceLogReader(self.path).iter_records();first=next(all_records)["payload"]
        require(first["kind"]=="query" and first["sql"]=="BEGIN ISOLATION LEVEL READ COMMITTED"
                and first["commandTag"]=="BEGIN" and first["pgStatus"]==1,"Actual boundary BEGIN")
        identity=next(all_records)["payload"]
        require(identity["sql"]=="SELECT pg_backend_pid(),pg_current_xact_id()::text" and unpack(identity["nativeRows"])==[(summary["backendPid"],summary["transaction"])],"Actual server PID/transaction query")
        last=None
        for wrapped in SourceLogReader(self.path).iter_records():
            payload=wrapped["payload"]
            last=payload
            if payload["kind"] in ("query","ledger-batch"):
                require(payload["connection"]==summary["connection"] and payload["backendPid"]==summary["backendPid"],"Shared actual setup connection")
                if wrapped["seq"]>2:require(payload["transaction"]==summary["transaction"],"Shared actual setup transaction")
        require(last=={"kind":"boundary-end","summary":summary},"Boundary end/source-summary binding")
        commit=list(self.records([summary["commitSeq"],summary["commitSeq"]]))
        require(len(commit)==1 and commit[0]["sql"]=="COMMIT" and commit[0]["commandTag"]=="COMMIT"
                and commit[0]["pgStatus"]==1 and commit[0]["statusAfter"]==0,"Confirmed actual boundary COMMIT")
        final=self.snapshot(summary["finalSnapshot"]);next_values=self.snapshot(summary["nextSnapshot"])
        require(final==next_values,"Boundary changed under shared lock")
        targets={value[1]:(key,value[0]) for key,value in final.items()};found=set();count=0;exhausted=False
        for record in self.records(summary["ledgerRange"]):
            ledger_sql="SELECT token::text,key,action,present,predecessor::text,old_value,new_value FROM "+n.object("audit")+" ORDER BY token"
            require(record["kind"]=="ledger-batch" and record["pgStatus"]==2 and record["sql"]==ledger_sql,"Actual streamed ledger result")
            for row in unpack(record["nativeRows"]):
                count+=1;require(count<=1024 and type(row) is tuple and len(row)==7,"Ledger validation bound/shape")
                if row[0] in targets:
                    require((row[1],row[6])==targets[row[0]] and row[3] is True,"Final token actual ledger value")
                    found.add(row[0])
            require(record["countThrough"]==count,"Ledger batch ordinal")
            exhausted=record["exhausted"]
        require(exhausted and found==set(targets) and count==summary["ledgerRows"],"Complete bounded final ledger")
        return final

