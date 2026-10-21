"""Prepared controlled-PG fixture; no automatic server startup or benchmark."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback
import uuid

from epoch_coordinator import EpochCoordinator,EpochError,tree_bindings
from epoch_sources import ROOT,BASE,SourceLogReader,identifier
from moontxnwitness_capture.journal_v3 import JournalReader
from prototype import controlled_schema


class InjectedLostAck(Exception):pass


class LostCommitAck:
    """Fault injection after a real COMMIT; not a real network-disconnect test."""
    def __init__(self,raw):self.raw=raw;self.original=InjectedLostAck("injected discarded setup COMMIT response")
    def __getattr__(self,name):return getattr(self.raw,name)
    def execute(self,sql,params=None):
        result=self.raw.execute(sql,params)
        if sql=="COMMIT":raise self.original
        return result


def bindings():
    here=Path(__file__).resolve().parent
    files=[p for p in here.iterdir() if p.is_file() and p.suffix in (".py",".json") and p.name!="candidate-index.json"]
    files.extend(BASE/name for name in ("profile.py","source_log.py"))
    files.extend(ROOT/name for name in ("integrations/python/moontxnwitness_capture/__init__.py","integrations/python/moontxnwitness_capture/capture.py",
        "integrations/python/moontxnwitness_capture/capture_v3.py","integrations/python/moontxnwitness_capture/journal_v3.py",
        "experiments/provenance/prototype.py","experiments/provenance/capture_profile.py"))
    return {p.relative_to(ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}


def run_case(name,index,connect,setup,schema_base,output):
    schema=schema_base+"_"+str(index);controlled_schema(schema);setup.execute("CREATE SCHEMA "+identifier(schema))
    table=identifier(schema)+'."items"';setup.execute("CREATE TABLE "+table+" (id text PRIMARY KEY,value integer NOT NULL)")
    setup.execute("INSERT INTO "+table+" VALUES('k',1),('other',2)")
    path=output/name;path.mkdir();c=EpochCoordinator.create(path/"chain",setup,schema=schema,keys=("k","other"),exclusive_writers=True)
    detail={"name":name,"passed":False,"actualDatabaseExecution":True,"coreProofImplemented":False,"formalEligible":False}
    active=[]
    def connection():
        result=c.current.wrap(connect());active.append(result);return result
    def handoff():
        generation=c.manifest["generation"];caller=c.quiesce(expected_generation=generation)
        return c.handoff(setup,caller=caller,expected_generation=generation)
    def finish():
        generation=c.manifest["generation"];caller=c.quiesce(expected_generation=generation)
        return c.finish(setup,caller=caller,expected_generation=generation)
    try:
        old=c.current;n=old.profile.names
        if name=="two-epochs-same-value":
            a=connection();a.execute(old.profile.write_sql,(5,"k"));a.execute(old.profile.write_sql,(5,"k"))
            assert a.execute(old.profile.read_sql,("k",)).fetchone()==(5,);a.commit();a.close()
            new=handoff();first=list(JournalReader(old.journal.path).iter_events(require_complete=True))
            writes=[e for e in first if e["kind"]=="write"];assert len(writes)==2 and writes[0]["version"]!=writes[1]["version"]
            initial=next(SourceLogReader(new.sources.path).iter_records(),None) if new.sources.closed else None
            assert initial is None  # Do not stream a still-open source as complete.
            b=connection();assert b.execute(new.profile.read_sql,("k",)).fetchone()==(5,)
            b.execute(new.profile.write_sql,(7,"k"));b.commit();b.close();chain=finish();assert chain["rawEpochChainComplete"]
            second=list(JournalReader(new.journal.path).iter_events(require_complete=True))
            assert second[0]["initial"]["k"]==writes[-1]["version"]
            assert setup.execute("SELECT value FROM "+table+" WHERE id='k'").fetchone()==(7,)
            detail.update(rawChain=chain,writeTokens=[w["version"] for w in writes],tokenContinuity=True)
        elif name=="rollback-and-savepoint":
            a=connection();a.execute(old.profile.write_sql,(9,"k"));a.rollback()
            a.execute(old.profile.write_sql,(10,"k"));a.execute("SAVEPOINT cut");a.execute(old.profile.write_sql,(11,"k"))
            a.execute("ROLLBACK TO SAVEPOINT cut");a.execute("RELEASE SAVEPOINT cut");a.commit();a.close()
            handoff();chain=finish();assert chain["rawEpochChainComplete"]
            events=list(JournalReader(old.journal.path).iter_events(require_complete=True));writes=[e for e in events if e["kind"]=="write"]
            assert len(writes)==3 and all(any(e["kind"]==kind for e in events) for kind in ("rollback_ok","savepoint","rollback_to","release"))
            actual=setup.execute("SELECT token::text FROM "+n.object("audit")+" WHERE token=ANY(%s::uuid[])",([w["version"] for w in writes],)).fetchall()
            assert actual==[(writes[1]["version"],)]
            detail.update(rawChain=chain,revertedAndAbortedRawWrites=2,actualCommittedWriteTokens=[r[0] for r in actual])
        elif name=="unsupported-statement":
            a=connection();assert a.execute("SELECT value+1 FROM "+table+" WHERE id=%s",("k",)).fetchone()==(2,);a.commit();a.close()
            caller=c.quiesce(expected_generation=0)
            try:c.handoff(setup,caller=caller,expected_generation=0)
            except EpochError:pass
            else:raise AssertionError("Unsupported SQL cannot enter complete handoff")
            assert not (c.path/"operation.lock").exists() and not c.verify_chain()["rawEpochChainComplete"]
            detail.update(originalResultPreserved=True,explicitCoverageGap=True)
        elif name=="discarded-setup-commit-ack":
            caller=c.quiesce(expected_generation=0);probe=LostCommitAck(setup)
            try:c.handoff(probe,caller=caller,expected_generation=0)
            except InjectedLostAck as error:assert error is probe.original
            else:raise AssertionError("Missing boundary COMMIT ACK cannot be accepted")
            assert (c.path/"operation.lock").exists() and not c.verify_chain()["rawEpochChainComplete"]
            detail.update(injectedAckLoss=True,actualNetworkFault=False,originalExceptionIdentity=True,authorityRetained=True)
        detail["passed"]=True
    finally:
        for wrapped in active:
            if not wrapped._raw.closed:
                try:wrapped.rollback();wrapped.close()
                except Exception:pass
        for capture in c._captures:
            try:capture.close(source_closed=False)
            except Exception:pass
        detail["rawFileBindings"]=tree_bindings(c.path)
        (path/"case-receipt.json").write_text(json.dumps(detail,indent=2)+"\n",encoding="utf-8")
    return detail


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--schema",default="mtw_provenance_epoch_"+uuid.uuid4().hex[:10]);args=parser.parse_args()
    try:import psycopg
    except ImportError:
        print(json.dumps({"status":"not-executed","actualDatabaseExecution":False,"reason":"missing pinned driver"}));return 3
    if psycopg.__version__!="3.3.6":raise RuntimeError("Require psycopg3.3.6")
    defaults={"connect_timeout":5,"options":"-c statement_timeout=15000 -c lock_timeout=5000"}
    if os.environ.get("MTW_PG_CONNECTION_FILE"):
        parameters=json.loads(Path(os.environ["MTW_PG_CONNECTION_FILE"]).read_text(encoding="utf-8"))
        def connect(**kwargs):return psycopg.connect(**(defaults|parameters|kwargs))
    elif os.environ.get("MTW_PG_DSN"):
        def connect(**kwargs):return psycopg.connect(os.environ["MTW_PG_DSN"],**(defaults|kwargs))
    else:
        print(json.dumps({"status":"not-executed","actualDatabaseExecution":False,"reason":"no controlled PostgreSQL"}));return 3
    controlled_schema(args.schema);args.output.mkdir(parents=True,exist_ok=False);before=bindings()
    receipt={"schema":1,"passed":False,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,"coreProofImplemented":False,
        "sourceClosureVerified":False,"formalEligible":False,"independentAcceptance":False,"sourceBindingsBefore":before,"cases":[]}
    code=1
    try:
        with connect(autocommit=True) as setup:
            if setup.info.server_version!=180006:raise RuntimeError("Freeze actual fixture at PostgreSQL18.6")
            receipt.update(actualDatabaseExecution=True,serverVersion=setup.info.server_version,driver=psycopg.__version__)
            for index,name in enumerate(("two-epochs-same-value","rollback-and-savepoint","unsupported-statement","discarded-setup-commit-ack")):
                receipt["activeCase"]=name;receipt["cases"].append(run_case(name,index,connect,setup,args.schema,args.output))
        receipt.pop("activeCase",None);receipt["passed"]=True;code=0
    except BaseException as error:
        receipt["failure"]={"class":type(error).__name__,"sqlstate":getattr(error,"sqlstate",None),"frames":[{"file":Path(f.filename).name,"line":f.lineno,"function":f.name} for f in traceback.extract_tb(error.__traceback__)]}
    finally:
        receipt["sourceBindingsAfter"]=bindings();receipt["sourceBindingsUnchanged"]=before==receipt["sourceBindingsAfter"]
        receipt["passed"]=receipt["passed"] and receipt["sourceBindingsUnchanged"]
        (args.output/"postgres-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"passed":receipt["passed"],"actualDatabaseExecution":receipt["actualDatabaseExecution"],"cases":len(receipt["cases"]),"coreProofImplemented":False}))
    return code if receipt["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
