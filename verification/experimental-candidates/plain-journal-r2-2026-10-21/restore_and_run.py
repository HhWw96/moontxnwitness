"""Manual experimental plain-profile CI. No installation, build or benchmark.

The approved frozen bundle is restored to a new repository-shaped directory.
The selected interpreter must already have the exact optional driver installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import platform
import stat
import subprocess
import sys

CANDIDATE_PREFIX="artifacts/plain-v3-journal-r2-draft"
EXPECTED_CANDIDATE_SHA="3a13b37fdf4324ceb8c899b3616d86c92e75aa256eca9d87668ddfcde46ee50a"
PUBLIC_BUNDLE="verification/experimental-candidates/plain-journal-r2-2026-10-21/bundle"
FILE_LIMIT=1024*1024
TOTAL_LIMIT=4*1024*1024
EXPECTED_TESTS=31
EXPECTED_CASES=("command-and-read-surface","same-value-and-self-read","rollback-sources",
                "native-returning","not-null-error","unsupported-sql","ledger-overflow")


def relative(name):
    if type(name) is not str or not name or "\\" in name or ":" in name:
        raise ValueError("Unsafe frozen path")
    value=PurePosixPath(name)
    if value.is_absolute() or any(part in (".","..") for part in value.parts) or value.as_posix()!=name:
        raise ValueError("Noncanonical frozen path")
    return value


def binding(path,limit=FILE_LIMIT):
    if path.is_symlink():raise ValueError("Frozen files must not be symlinks")
    hashed=hashlib.sha256();size=0
    with path.open("rb") as file:
        before=os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size>limit:raise ValueError("Frozen file budget/type")
        while raw:=file.read(min(65536,limit-size+1)):
            size+=len(raw)
            if size>limit:raise ValueError("Frozen file grew beyond read budget")
            hashed.update(raw)
        after=os.fstat(file.fileno())
    current=path.stat()
    if (path.is_symlink() or not stat.S_ISREG(current.st_mode)
            or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
            or (after.st_dev,after.st_ino,size,after.st_mtime_ns)!=(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)):
        raise ValueError("Frozen file changed during bounded reading")
    return {"bytes":size,"sha256":hashed.hexdigest()}


def load(path,limit=65536):
    expected=binding(path,limit)
    with path.open("rb") as file:raw=file.read(limit+1)
    if len(raw)>limit or {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}!=expected:
        raise ValueError("JSON binding changed")
    return json.loads(raw)


def verify_bundle(bundle):
    manifest=load(bundle/"bundle-index.json")
    if manifest["candidateIndexSha256"]!=EXPECTED_CANDIDATE_SHA:raise ValueError("Wrong candidate")
    if manifest["candidatePrefix"]!=CANDIDATE_PREFIX:raise ValueError("Wrong source layout")
    files=manifest["files"]
    if not 1<=len(files)<=128:raise ValueError("Bundle file-count budget")
    restored={};total=0
    for name,item in files.items():
        relative(name)
        if item["bundleFile"]!="repository/"+name:raise ValueError("Unexpected bundle alias")
        path=bundle/relative(item["bundleFile"])
        actual=binding(path)
        if actual!={key:item[key] for key in ("bytes","sha256")}:raise ValueError("Bundle bytes differ: "+name)
        total+=actual["bytes"]
        if total>TOTAL_LIMIT:raise ValueError("Aggregate bundle budget")
        restored[name]=actual
    index_name=CANDIDATE_PREFIX+"/candidate-index.json"
    if restored[index_name]["sha256"]!=EXPECTED_CANDIDATE_SHA:raise ValueError("Candidate index changed")
    index=load(bundle/"repository"/relative(index_name))
    dependencies=load(bundle/"repository"/relative(CANDIDATE_PREFIX+"/repository-dependencies.json"))
    expected={CANDIDATE_PREFIX+"/"+name:value for name,value in index["fileBindings"].items()}
    expected[index_name]=restored[index_name]
    for group in (index["runtimeDependencies"],dependencies["driverRequirements"]):
        for name,value in group.items():
            if name in expected and expected[name]!=value:raise ValueError("Conflicting dependency")
            expected[name]=value
    if expected!=restored:raise ValueError("Missing, extra or modified candidate source")
    return manifest,restored


def copy_files(bundle,target,files):
    for name,expected in files.items():
        source=bundle/relative("repository/"+name);destination=target/relative(name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        hashed=hashlib.sha256();size=0
        with source.open("rb") as src,destination.open("xb") as dst:
            while raw:=src.read(min(65536,expected["bytes"]-size+1)):
                size+=len(raw)
                if size>expected["bytes"]:raise ValueError("Restore source grew")
                hashed.update(raw);dst.write(raw)
        if {"bytes":size,"sha256":hashed.hexdigest()}!=expected or binding(destination)!=expected:
            raise ValueError("Restore binding failure")


def child_environment(scratch,fixture_port=None):
    # Do not copy arbitrary DB endpoints, tokens, custom Python paths or pip
    # configuration into the observed business process. Only fixture DB access
    # is constructed here; environment values are never dumped to receipts.
    allowed=("PATH","SystemRoot","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT",
             "LD_LIBRARY_PATH","LANG","LC_ALL","HOME","USERPROFILE")
    env={key:os.environ[key] for key in allowed if key in os.environ}
    env.update(MTW_JOURNAL_SCRATCH=str(scratch),TEMP=str(scratch),TMP=str(scratch),
               PYTHONDONTWRITEBYTECODE="1",PYTHONUTF8="1",PYTHONNOUSERSITE="1")
    if fixture_port is not None:
        env["MTW_PG_DSN"]="host=127.0.0.1 port="+str(fixture_port)+" dbname=mtw_plain_test user=mtw password=fixture-only"
    return env


def run_child(label,command,restored,env,evidence):
    log=evidence/(label+".log")
    record={"name":label,"executed":False,"passed":False,"log":log.name}
    try:
        with log.open("xb") as stream:
            record["executed"]=True
            result=subprocess.run(command,cwd=restored,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
        record["exitCode"]=result.returncode
    except subprocess.TimeoutExpired:
        record["failure"]={"class":"TimeoutExpired","seconds":300}
    except Exception as error:record["failure"]={"class":type(error).__name__}
    finally:
        if log.is_file():record["logBinding"]=binding(log,16*1024*1024)
    return record


def raw_files(directory):
    # Metadata only: stream hashes rather than loading retained databases/logs.
    return {p.relative_to(directory).as_posix():binding(p,64*1024*1024)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=("verify","run"))
    parser.add_argument("--bundle",type=Path,default=Path.cwd()/PUBLIC_BUNDLE)
    parser.add_argument("--work",type=Path);parser.add_argument("--fixture-port",type=int)
    args=parser.parse_args()
    if args.mode=="verify":
        manifest,files=verify_bundle(args.bundle)
        print(json.dumps({"verified":True,"candidateIndexSha256":manifest["candidateIndexSha256"],"files":len(files),
                          "actualFilesystemTests":False,"actualDatabaseExecution":False}));return 0
    if args.work is None or args.fixture_port is None or not 1024<=args.fixture_port<=65535:
        parser.error("run needs a new --work directory and the isolated fixture --fixture-port")
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=False);evidence=work/"evidence";evidence.mkdir()
    receipt={"schema":1,"kind":"plain-journal-r2-isolated-execution","passed":False,
        "candidateIndexSha256":EXPECTED_CANDIDATE_SHA,"started":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),"workflowCommit":os.environ.get("GITHUB_SHA"),
        "requestedSourceRef":os.environ.get("MTW_REQUESTED_REF"),"runs":[],"failures":[],
        "actualFilesystemTests":False,"actualDatabaseExecution":False,"formalPerformanceMeasurement":False,
        "coreProofImplemented":False,"formalEligible":False,"independentAcceptance":False}
    before={};restored=work/"restored-repository"
    try:
        manifest,before=verify_bundle(args.bundle)
        receipt["bundleIndexBinding"]=binding(args.bundle/"bundle-index.json")
        receipt["runnerSourceBinding"]=binding(Path(__file__))
        receipt["restoredFilesBefore"]=before
        restored.mkdir();copy_files(args.bundle,restored,before)
        try:import psycopg
        except ImportError:
            receipt["notExecuted"]="missing pinned driver";raise RuntimeError("Missing optional driver")
        if psycopg.__version__!="3.3.6":raise ValueError("Unexpected driver version")
        receipt["driver"]=psycopg.__version__
        result=subprocess.run(["git","rev-parse","HEAD"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,text=True)
        if result.returncode==0:receipt["checkedOutSourceCommit"]=result.stdout.strip()
        scratch=evidence/"unit-scratch";scratch.mkdir()
        candidate=restored/relative(CANDIDATE_PREFIX)
        declared_source={name:value for name,value in before.items()
            if PurePosixPath(name).parent.as_posix()==CANDIDATE_PREFIX
            and PurePosixPath(name).suffix in (".py",".json") and PurePosixPath(name).name!="candidate-index.json"}
        declared_source.update(load(candidate/"candidate-index.json")["runtimeDependencies"])
        run=run_child("unit-31",[sys.executable,"-B",str(candidate/"test_profile.py")],restored,child_environment(scratch),evidence)
        receipt["runs"].append(run)
        unit_paths=list(scratch.glob("*/test-receipt.json"))
        if len(unit_paths)!=1:raise ValueError("Expected one new actual unit receipt")
        unit=load(unit_paths[0],131072);run["receipt"]=unit_paths[0].relative_to(evidence).as_posix()
        run["receiptBinding"]=binding(unit_paths[0]);run["actualTests"]=unit["tests"]
        if (run.get("exitCode")!=0 or unit["tests"]!=EXPECTED_TESTS or not unit["passed"]
                or unit["skipped"] or unit["actualFilesystemExecution"] is not True
                or unit["actualMockExecution"] is not True or unit["actualDatabaseExecution"] is not False
                or unit["sourceBindingsBefore"]!=unit["sourceBindingsAfter"]
                or unit["sourceBindingsAfter"]!=declared_source):
            raise ValueError("Actual unit gate failed; database was not run")
        for name,value in unit["sourceBindingsAfter"].items():
            if before.get(name)!=value:raise ValueError("Unit dependency binding differs")
        run["passed"]=True;receipt["actualFilesystemTests"]=True
        pg_output=evidence/"postgres"  # Producer itself creates it, no overwrite.
        run=run_child("postgres-7",[sys.executable,"-B",str(candidate/"postgres.py"),"--output",str(pg_output)],
                      restored,child_environment(scratch,args.fixture_port),evidence)
        receipt["runs"].append(run)
        pg=load(pg_output/"postgres-receipt.json",262144)
        run["receipt"]="postgres/postgres-receipt.json";run["receiptBinding"]=binding(pg_output/"postgres-receipt.json")
        receipt["actualDatabaseExecution"]=pg["actualDatabaseExecution"] is True
        run["actualScenarios"]=len(pg["cases"])
        if (run.get("exitCode")!=0 or not pg["passed"] or not pg["actualDatabaseExecution"]
                or pg.get("serverVersion")!=180006 or tuple(case["name"] for case in pg["cases"])!=EXPECTED_CASES
                or pg["sourceBindingsBefore"]!=pg["sourceBindingsAfter"]
                or pg["sourceBindingsAfter"]!=declared_source):
            raise ValueError("Actual PostgreSQL gate failed")
        for name,value in pg["sourceBindingsAfter"].items():
            if before.get(name)!=value:raise ValueError("PG dependency binding differs")
        for case in pg["cases"]:
            if not case["passed"] or case["coreProofImplemented"] is not False or case["formalEligible"] is not False:
                raise ValueError("Unexpected scenario claim")
            diagnostic=case["name"] in ("not-null-error","unsupported-sql","ledger-overflow")
            if case["rawJournal"]["valid"] is not True or case["rawJournal"]["complete"]!=(not diagnostic):
                raise ValueError("Scenario closure/gap expectation changed")
            if case["sourceLog"]["complete"] is not True:raise ValueError("Source byte log did not close")
            case_root=pg_output/relative(case["name"])
            if load(case_root/"case-receipt.json",131072)!=case:raise ValueError("Embedded/standalone scenario receipts differ")
            actual_files={p.relative_to(case_root).as_posix() for p in case_root.rglob("*")
                          if p.is_file() and p.name!="case-receipt.json"}
            if actual_files!=set(case["rawFileBindings"]):raise ValueError("A scenario raw file was omitted or added")
            for name,value in case["rawFileBindings"].items():
                if binding(case_root/relative(name),64*1024*1024)!=value:
                    raise ValueError("Actual raw-file binding differs")
        run["passed"]=True;receipt["passed"]=True
    except Exception as error:receipt["failures"].append({"class":type(error).__name__,"message":str(error)})
    finally:
        try:
            after={name:binding(restored/relative(name)) for name in before if (restored/relative(name)).is_file()}
            receipt["restoredFilesAfter"]=after;receipt["sourceBindingsUnchanged"]=bool(before) and before==after
            receipt["passed"]=receipt["passed"] and receipt["sourceBindingsUnchanged"]
            receipt["rawEvidenceBindings"]=raw_files(evidence)
        except Exception as error:
            receipt["passed"]=False;receipt["failures"].append({"class":type(error).__name__,"phase":"final-bindings"})
        receipt["finished"]=datetime.now(timezone.utc).isoformat()
        with (evidence/"execution-receipt.json").open("x",encoding="utf-8",newline="\n") as stream:
            json.dump(receipt,stream,ensure_ascii=True,indent=2);stream.write("\n")
    print(json.dumps({"passed":receipt["passed"],"runs":len(receipt["runs"]),
                      "actualDatabaseExecution":receipt["actualDatabaseExecution"],"coreProofImplemented":False,
                      "receipt":str(evidence/"execution-receipt.json")}))
    return 0 if receipt["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
