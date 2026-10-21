"""Author-support byte/fact crosscheck of downloaded CI; never runs a DB."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
RAW=HERE/"authorized-attempt2-raw"
WORK=RAW/"plain-journal-work-39604038471-1"
CONTEXT=RAW/"plain-journal-context-39604038471-1"
EXPECTED="bb6409c7ad51d2b999cf80043d98572f3350616c"
checks=[]


def check(condition,label):
    if not condition:raise AssertionError(label)
    checks.append(label)


def load(path):
    check(path.stat().st_size<=262144,"JSON budget "+path.name)
    return json.loads(path.read_bytes())


def binding(path):
    hashed=hashlib.sha256();size=0
    with path.open("rb") as file:
        while raw:=file.read(65536):hashed.update(raw);size+=len(raw)
    return {"bytes":size,"sha256":hashed.hexdigest()}


def lines(path,max_lines=8192,max_line=524288):
    result=[]
    with path.open("rb") as file:
        while raw:=file.readline(max_line+1):
            check(len(raw)<=max_line and raw.endswith(b"\n"),"Bounded complete JSONL line")
            result.append((raw,json.loads(raw)));check(len(result)<=max_lines,"JSONL aggregate record bound")
    return result


def main():
    execution=load(WORK/"evidence/execution-receipt.json")
    source=load(CONTEXT/"source-context.json")
    check(source["sourceCommit"]==source["workflowCommit"]==source["requestedRef"]==EXPECTED,"Exact CI source/workflow")
    check(execution["checkedOutSourceCommit"]==execution["workflowCommit"]==EXPECTED,"Execution source binding")
    check(execution["passed"] and execution["sourceBindingsUnchanged"],"Actual execution result")
    check(execution["actualDatabaseExecution"] and not execution["coreProofImplemented"] and not execution["formalEligible"],"Capture not SQL proof or formal cost")
    check(execution["restoredFilesBefore"]==execution["restoredFilesAfter"],"All recorded source before/after equal")
    before=execution["restoredFilesBefore"]
    check(len(before)==62,"62 source/dependency files")
    for name,value in before.items():
        check(binding(WORK/"restored-repository"/name)==value,"Direct restored source "+name)
        public=REPO/"verification/experimental-candidates/plain-journal-r2-2026-10-21/bundle/repository"/name
        check(binding(public)==value,"Public frozen source "+name)
    raw_bindings=execution["rawEvidenceBindings"]
    for name,value in raw_bindings.items():check(binding(WORK/"evidence"/name)==value,"Actual evidence byte binding "+name)
    unit_run,pg_run=execution["runs"]
    for run in execution["runs"]:
        check(run["executed"] and run["passed"] and run["exitCode"]==0,"Executed successful child "+run["name"])
        check(binding(WORK/"evidence"/run["log"])==run["logBinding"],"Child stdout/stderr binding")
        check(binding(WORK/"evidence"/run["receipt"])==run["receiptBinding"],"Child original receipt binding")
    unit=load(WORK/"evidence"/unit_run["receipt"])
    check(unit["tests"]==31 and unit["passed"] and not unit["failures"] and not unit["skipped"],"31 actual FS/mock tests, zero skips")
    check(unit["actualFilesystemExecution"] and unit["actualMockExecution"] and not unit["actualDatabaseExecution"],"Unit scope markers")
    pg=load(WORK/"evidence/postgres/postgres-receipt.json")
    check(pg["serverVersion"]==180006 and pg["driver"]=="3.3.6" and pg["passed"],"Actual PG18.6/psycopg3.3.6")
    check(len(pg["cases"])==7,"Seven actual PostgreSQL scenarios")
    prefix="artifacts/plain-v3-journal-r2-draft"
    declared={name:value for name,value in before.items() if Path(name).parent.as_posix()==prefix and Path(name).suffix in (".py",".json") and Path(name).name!="candidate-index.json"}
    index=load(WORK/"restored-repository"/prefix/"candidate-index.json");declared.update(index["runtimeDependencies"])
    check(unit["sourceBindingsBefore"]==unit["sourceBindingsAfter"]==declared,"Unit exact runtime dependencies")
    check(pg["sourceBindingsBefore"]==pg["sourceBindingsAfter"]==declared,"PG exact runtime dependencies")
    summaries=[];scenario_events={};scenario_sources={};case_raw_count=0
    for case in pg["cases"]:
        name=case["name"];base=WORK/"evidence/postgres"/name
        check(load(base/"case-receipt.json")==case,"Embedded/standalone scenario "+name)
        check(case["actualDatabaseExecution"] and not case["coreProofImplemented"] and not case["formalEligible"],"Actual-only claim "+name)
        for relative,value in case["rawFileBindings"].items():
            check(binding(base/relative)==value,"Scenario raw bytes "+name+"/"+relative);case_raw_count+=1
        journal=base/"capture/journal";jindex=load(journal/"journal-index.json");events=[];last_time=-1
        for segment in jindex["segments"]:
            check(binding(journal/segment["name"])=={k:segment[k] for k in ("bytes","sha256")},"Segment binding")
            for raw,event in lines(journal/segment["name"]):
                check(event["seq"]==len(events)+1 and event["time"]>=last_time,"Contiguous event seq/nondecreasing time")
                last_time=event["time"];events.append(event)
        check(len(events)==jindex["eventCount"]==case["rawJournal"]["eventCount"],"Actual event count "+name)
        sources=base/"capture/sources";sindex=load(sources/"index.json");rows=lines(sources/"records.jsonl",max_line=65536)
        previous="0"*64
        for number,(raw,record) in enumerate(rows,1):
            check(record["seq"]==number and record["previous"]==previous,"Source sequence/hash chain")
            previous=hashlib.sha256(raw).hexdigest()
        check(binding(sources/"records.jsonl")=={k:sindex[k] for k in ("bytes","sha256")},"Entire source byte binding")
        check(len(rows)==sindex["records"]==case["sourceLog"]["records"] and previous==sindex["lastRecordSha256"],"Source footer count/final hash")
        source_by_seq={row["seq"]:row["payload"] for _,row in rows}
        event_by_seq={event["seq"]:event for event in events}
        check(events[0]["kind"]=="snapshot" and events[0]["consistent"] is True,"Actual initial snapshot")
        installation=source_by_seq[1]
        check(installation["kind"]=="installation" and installation["serverVersion"]==180006,"Actual installation source")
        check({row[0]:row[2] for row in installation["initialRows"]}==events[0]["initial"],"Locked source/initial token snapshot")
        for event in events:
            if event["kind"]=="write" and "sourceLogSeq" in event.get("evidence",{}):
                observed=source_by_seq[event["evidence"]["sourceLogSeq"]]
                check(observed["kind"]=="command-effect" and observed["statement"]==event["statement"] and observed["tx"]==event["tx"],"Internal effect belongs to same statement/tx")
                statement=event_by_seq[event["statement"]];business=event_by_seq[observed["businessRowsEvent"]]
                check(observed["actualSql"]==statement["executedSql"] and business["rows"]==[] and business["complete"],"Actual rewritten SQL/empty business command")
                check(observed["effectRows"][event["evidence"]["effectRow"]]==[event["predecessor"],event["version"]],"Same-statement OLD/NEW tokens")
                check(observed["businessCommand"]=={"rowcount":1,"statusmessage":"UPDATE 1","description":None,"rownumber":None},"Preserved command metadata")
        diagnostic=name in ("not-null-error","unsupported-sql","ledger-overflow")
        check(case["rawJournal"]["complete"]==(not diagnostic),"Expected diagnostic closure "+name)
        scenario_events[name]=events;scenario_sources[name]=source_by_seq
        summaries.append({"name":name,"actualReadFacts":sum(e["kind"]=="read" for e in events),"actualWriteFacts":sum(e["kind"]=="write" for e in events),"rawComplete":case["rawJournal"]["complete"],"sqlProof":False})
    same=scenario_events["same-value-and-self-read"];writes=[e for e in same if e["kind"]=="write"];reads=[e for e in same if e["kind"]=="read"]
    check(len(writes)==2 and writes[0]["version"]!=writes[1]["version"] and writes[0]["version"]==writes[1]["predecessor"],"Repeated values retain actual intermediate version chain")
    check(len(reads)==1 and reads[0]["version"]==writes[1]["version"],"Self-read delivered final intermediate token")
    ledger=[p["row"] for p in scenario_sources["same-value-and-self-read"].values() if p["kind"]=="ledger-row"]
    check(all(any(row[0]==w["version"] and row[4]==w["predecessor"] for row in ledger) for w in writes),"Committed intermediate effects in actual ledger")
    rolled=scenario_events["rollback-sources"];rolled_write=next(e for e in rolled if e["kind"]=="write")
    check(any(e["kind"]=="rollback_ok" and e["tx"]==rolled_write["tx"] for e in rolled),"Actual rollback acknowledgement")
    check(all(p["row"][0]!=rolled_write["version"] for p in scenario_sources["rollback-sources"].values() if p["kind"]=="ledger-row"),"Rolled-back token absent from final actual ledger")
    null=scenario_events["not-null-error"]
    check(any(e["kind"]=="rows" and e.get("error",{}).get("sqlstate")=="23502" for e in null),"Original server NOT NULL error retained")
    overflow=scenario_sources["ledger-overflow"]
    check(not any(p["kind"]=="ledger-end" for p in overflow.values()),"Overflow prefix has no complete ledger footer")
    output={"schema":1,"role":"author-support-byte-and-fact-crosscheck","passed":True,"checks":len(checks),"runId":"39604038471","sourceCommit":EXPECTED,"artifactSha256":"81921da5ae1f4db2f4fe9b556e4cfe4c143b4f23c107b1968f6b8679c9e93253","restoredSources":62,"rawEvidenceBindings":len(raw_bindings),"scenarioRawBindings":case_raw_count,"actualLocalDBExecution":False,"actualDatabaseExecutionReportedByCI":True,"unitTestsReportedAndBound":31,"actualPGScenariosReportedAndBound":7,"caseSummaries":summaries,"formalPerformanceMeasurement":False,"coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False,"limits":"This author support audit rehashes downloaded bytes and crosschecks recorded facts. It does not independently execute PostgreSQL, prove original Python object identity from serialized data or certify SQL model semantics."}
    with (HERE/"author-support-readonly-audit.json").open("x",encoding="utf-8") as file:json.dump(output,file,indent=2);file.write("\n")
    print(json.dumps(output))


if __name__=="__main__":main()
