"""Seven bounded actual-PG scenarios; no benchmark or generic SQL proof."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

import profile as draft
from source_log import SourceLogReader
from moontxnwitness_capture.journal_v3 import JournalReader
from prototype import controlled_schema, identifier


def bindings():
    here=Path(__file__).resolve().parent
    paths=[p for p in here.iterdir() if p.is_file() and p.suffix in (".py",".json") and p.name!="candidate-index.json"]
    paths.extend(draft.ROOT/p for p in ("integrations/python/moontxnwitness_capture/__init__.py",
        "integrations/python/moontxnwitness_capture/capture.py","integrations/python/moontxnwitness_capture/capture_v3.py",
        "integrations/python/moontxnwitness_capture/journal_v3.py","experiments/provenance/prototype.py","experiments/provenance/capture_profile.py"))
    return {p.relative_to(draft.ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths}


def surface(cursor):
    return {"description":None if cursor.description is None else [[c.name,c.type_code] for c in cursor.description],
        "rowcount":cursor.rowcount,"rownumber":cursor.rownumber,"statusmessage":cursor.statusmessage}


def fetch_error(cursor):
    try:cursor.fetchone()
    except Exception as error:return {"class":type(error).__name__,"message":str(error),"sqlstate":getattr(error,"sqlstate",None)}
    raise AssertionError("Expected original no-result fetch failure")


class ExecuteProbe:
    def __init__(self,raw):self.raw=raw;self.errors=[]
    def __getattr__(self,name):return getattr(self.raw,name)
    def execute(self,*args,**kwargs):
        try:return self.raw.execute(*args,**kwargs)
        except BaseException as error:self.errors.append(error);raise


def case(name,index,connect,setup,base_schema,output):
    schema=base_schema+"_"+str(index);controlled_schema(schema)
    quoted=identifier(schema);setup.execute("CREATE SCHEMA "+quoted)
    for table in ("items","baseline"):
        target=quoted+"."+identifier(table)
        setup.execute("CREATE TABLE "+target+" (id text PRIMARY KEY,value integer NOT NULL)")
        setup.execute("INSERT INTO "+target+" VALUES ('k',1),('other',2)")
    target=quoted+'."items"';baseline=quoted+'."baseline"';directory=output/name;directory.mkdir()
    capture=draft.PlainJournalCapture(directory/"capture",schema=schema,keys=("k","other"),exclusive_writers=True)
    connection=None;plain=None;details={};diagnostic=name in ("not-null-error","unsupported-sql","ledger-overflow")
    try:
        capture.initialize(setup)
        connection=capture.wrap(connect());plain=connect()
        if name=="command-and-read-surface":
            expected=plain.execute("SELECT value FROM "+baseline+" WHERE id=%s",("k",))
            actual=connection.execute(capture.profile.read_sql,("k",));assert surface(actual)==surface(expected)
            assert actual.fetchone()==expected.fetchone()==(1,);assert actual.fetchone() is expected.fetchone() is None
            expected=plain.execute("SELECT value FROM "+baseline+" WHERE id=%s",("k",))
            actual=connection.execute(capture.profile.read_sql,("k",))
            zero_batch=actual.fetchmany(0);assert zero_batch==expected.fetchmany(0)
            assert surface(actual)==surface(expected);assert actual.fetchall()==expected.fetchall()
            details["actualFetchmanyZeroRows"]=len(zero_batch)
            expected=plain.execute("UPDATE "+baseline+" SET value=%s WHERE id=%s",(4,"k"))
            actual=connection.execute(capture.profile.write_sql,(4,"k"));assert surface(actual)==surface(expected)
            assert fetch_error(actual)==fetch_error(expected)
            actual.close();expected.close();assert fetch_error(actual)==fetch_error(expected)
            details["commandSurfacePreserved"]=True;connection.commit();plain.commit()
        elif name=="same-value-and-self-read":
            connection.execute(capture.profile.write_sql,(5,"k"));connection.execute(capture.profile.write_sql,(5,"k"))
            assert connection.execute(capture.profile.read_sql,("k",)).fetchone()==(5,)
            connection.commit();details["expectedCommandEffects"]=2
        elif name=="rollback-sources":
            connection.execute(capture.profile.write_sql,(9,"k"));assert connection.execute(capture.profile.read_sql,("k",)).fetchone()==(9,)
            connection.rollback();assert setup.execute("SELECT value FROM "+target+" WHERE id='k'").fetchone()==(1,)
            details["rolledBackEffectMustRemainInRawButNotFinalLedger"]=True
        elif name=="native-returning":
            expected=plain.execute("UPDATE "+baseline+" SET value=%s WHERE id=%s RETURNING value",(8,"k"))
            actual=connection.execute(capture.returning_sql,(8,"k"));assert surface(actual)==surface(expected)
            assert actual.fetchall()==expected.fetchall()==[(8,)];assert surface(actual)==surface(expected)
            connection.commit();plain.commit();details["nativeReturningSurfacePreserved"]=True
        elif name=="not-null-error":
            cursor=connection.cursor();probe=ExecuteProbe(cursor._raw);cursor._raw=probe
            try:cursor.execute(capture.profile.write_sql,(None,"k"))
            except Exception as error:
                assert error.sqlstate=="23502" and len(probe.errors)==1 and error is probe.errors[0]
                details.update(sqlstate=error.sqlstate,originalExceptionIdentity=True)
            else:raise AssertionError("Expected real server NOT NULL failure")
            connection.rollback()
        elif name=="unsupported-sql":
            sql="SELECT value+1 FROM "+target+" WHERE id=%s"
            assert connection.execute(sql,("k",)).fetchone()==(2,);connection.commit()
            assert any(g["code"]=="unknown_sql" for g in capture.gaps)
            details["originalUnsupportedResultPreserved"]=True
        elif name=="ledger-overflow":
            connection.execute(capture.profile.write_sql,(3,"k"));connection.commit()
        else:raise AssertionError("Unregistered scenario")
        plain.close();plain=None;connection.close()
        if name=="ledger-overflow":
            try:capture.stream_final_ledger(setup,max_rows=1)
            except Exception as error:
                details["ledgerOverflowClass"]=type(error).__name__
                assert any(g["code"]=="ledger_incomplete" for g in capture.gaps)
            else:raise AssertionError("Budget overflow was not rejected")
        elif not diagnostic:details["ledger"]=capture.stream_final_ledger(setup)
        status=capture.close(source_closed=True)
        assert status.valid and status.complete == (not diagnostic)
        events=list(JournalReader(capture.journal.path).iter_events(require_complete=not diagnostic))
        writes=[e for e in events if e["kind"]=="write"];reads=[e for e in events if e["kind"]=="read"]
        source=SourceLogReader(capture.sources.path).verify();assert source["complete"]
        effects=[r["payload"] for r in SourceLogReader(capture.sources.path).iter_records() if r["payload"].get("kind")=="command-effect"]
        if name=="same-value-and-self-read":
            assert len(writes)==len(effects)==2 and writes[0]["version"]!=writes[1]["version"]
            assert writes[1]["predecessor"]==writes[0]["version"]==effects[1]["effectRows"][0][0]
            assert len(reads)==1 and reads[0]["version"]==writes[1]["version"]
        if name=="rollback-sources":
            assert len(writes)==1 and len(reads)==1 and any(e["kind"]=="rollback_ok" for e in events)
            assert setup.execute("SELECT count(*) FROM "+capture.profile.names.object("audit")+" WHERE token=%s",(writes[0]["version"],)).fetchone()==(0,)
        details.update({"name":name,"passed":True,"rawJournal":status.as_dict(),"sourceLog":source,
            "writeFacts":len(writes),"readFacts":len(reads),"commandSourceRecords":len(effects),
            "actualDatabaseExecution":True,"coreProofImplemented":False,"formalEligible":False,
            "scope":"controlled generated point fixture, not arbitrary SQL or full C/A"})
        file_bindings={}
        for path in directory.rglob("*"):
            if path.is_file():file_bindings[path.relative_to(directory).as_posix()]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        details["rawFileBindings"]=file_bindings
        (directory/"case-receipt.json").write_text(json.dumps(details,indent=2)+"\n",encoding="utf-8")
        return details
    finally:
        if plain is not None:plain.close()
        if connection is not None:
            try:
                if connection._tx:connection.rollback()
                connection.close()
            except Exception:pass
        try:capture.close(source_closed=False)
        except Exception:pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--schema",default="mtw_provenance_plain_"+uuid.uuid4().hex[:12]);args=parser.parse_args()
    try:import psycopg
    except ImportError:
        print(json.dumps({"status":"not-executed","actualDatabaseExecution":False,"reason":"missing pinned psycopg"}));return 3
    if psycopg.__version__!="3.3.6":raise RuntimeError("Use frozen psycopg3.3.6")
    defaults={"connect_timeout":5,"options":"-c statement_timeout=15000 -c lock_timeout=5000"}
    if os.environ.get("MTW_PG_CONNECTION_FILE"):
        parameters=json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
        def connect(**kwargs):return psycopg.connect(**(defaults|parameters|kwargs))
    elif os.environ.get("MTW_PG_DSN"):
        def connect(**kwargs):return psycopg.connect(os.environ["MTW_PG_DSN"],**(defaults|kwargs))
    else:
        print(json.dumps({"status":"not-executed","actualDatabaseExecution":False,"reason":"no controlled PostgreSQL configured"}));return 3
    controlled_schema(args.schema);args.output.mkdir(parents=True,exist_ok=False);before=bindings()
    receipt={"schema":1,"passed":False,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,
        "coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False,"sourceBindingsBefore":before,"cases":[]}
    code=1
    try:
        with connect(autocommit=True) as setup:
            if not 180000<=setup.info.server_version<190000:raise RuntimeError("PostgreSQL18 required")
            receipt.update(actualDatabaseExecution=True,serverVersion=setup.info.server_version,driver=psycopg.__version__)
            for index,name in enumerate(("command-and-read-surface","same-value-and-self-read","rollback-sources",
                    "native-returning","not-null-error","unsupported-sql","ledger-overflow")):
                receipt["activeCase"]=name
                receipt["cases"].append(case(name,index,connect,setup,args.schema,args.output))
            receipt.pop("activeCase",None)
        receipt["passed"]=True;code=0
    except BaseException as error:
        frames=[]
        for frame in traceback.extract_tb(error.__traceback__):
            try:path=Path(frame.filename).resolve().relative_to(draft.ROOT).as_posix()
            except ValueError:path=Path(frame.filename).name
            frames.append({"file":path,"line":frame.lineno,"function":frame.name})
        receipt["failure"]={"class":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None),"frames":frames}
    finally:
        receipt["sourceBindingsAfter"]=bindings();receipt["sourceBindingsUnchanged"]=before==receipt["sourceBindingsAfter"]
        receipt["passed"]=receipt["passed"] and receipt["sourceBindingsUnchanged"]
        if not receipt["passed"]:code=1
        (args.output/"postgres-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":receipt["passed"],"cases":len(receipt["cases"]),"actualDatabaseExecution":receipt["actualDatabaseExecution"],
        "coreProofImplemented":False,"formalEligible":False}));return code


if __name__=="__main__":raise SystemExit(main())
