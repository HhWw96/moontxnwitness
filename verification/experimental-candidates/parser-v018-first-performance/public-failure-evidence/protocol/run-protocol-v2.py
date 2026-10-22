"""No core import/timing until root supplies an explicit exclusive-machine authorization."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,data):
    with Path(path).open("x",encoding="utf-8",newline="\n") as f:json.dump(data,f,indent=2);f.write("\n")
def p95(values):return sorted(values)[math.ceil(len(values)*.95)-1]
def median(values):return statistics.median(values)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--authorization",type=Path,required=True)
    parser.add_argument("--authorization-sha256",required=True)
    args=parser.parse_args()
    # These guards perform no measurement and import no product code.
    auth_bytes=args.authorization.read_bytes()
    assert SHA(auth_bytes)==args.authorization_sha256
    auth=json.loads(auth_bytes)
    assert auth["schema"]==1 and auth["kind"]=="root-exclusive-v018-performance-authorization"
    assert auth["signal"]=="root-authorized-exclusive-v018-performance"
    assert auth["runPerformanceNow"] is True and auth["exclusiveMachine"] is True
    assert auth["operatorAttestation"] and "ROOT_MUST" not in auth["operatorAttestation"]
    prepared_bytes=(HERE/"preparation-manifest.v2.json").read_bytes()
    assert SHA(prepared_bytes)==auth["preparationManifestSha256"]
    prepared=json.loads(prepared_bytes)
    assert prepared["formalPerformanceMeasured"] is False
    for row in prepared["files"]:
        data=(HERE/row["file"]).read_bytes()
        assert len(data)==row["bytes"] and SHA(data)==row["sha256"],row["file"]
    node=Path(auth["nodeExecutable"]).resolve()
    assert SHA(node.read_bytes())==auth["nodeExecutableSha256"]
    scratch=Path(auth["scratchRoot"]).resolve()
    assert scratch.drive.upper()=="D:","Large temporary measurements must stay on authorized D scratch"
    scratch.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix="moontxnwitness-v018-measure-",dir=scratch))
    receipt={"schema":1,"kind":"ascii-parser-candidate-formal-local-comparison","passed":False,"measurementExecuted":False,"createdAt":datetime.now(timezone.utc).isoformat(),"authorizationSha256":args.authorization_sha256,"preparationManifestSha256":SHA(prepared_bytes),"exclusiveMachineAttestation":auth["operatorAttestation"],"exclusiveMachineIndependentlyProven":False,"protocol":{"warmups":5,"samples":30,"independentProcessBatches":3,"order":"AB, BA, AB per input/phase","coldProcess":"Separate fresh process, one call, no warmup","controlThreshold":"candidate minus baseline <= max(10% baseline, 2ms) for warm median/P95 and cold process median"},"fullOutputEquivalence":[],"results":[],"newCoreBuild":False,"formal18Build":False,"networkUsed":False,"databaseExecuted":False}
    try:
        engines={}
        for name,row in prepared["engines"].items():
            source=ROOT/row["file"]
            raw=source.read_bytes()
            assert SHA(raw)==row["sha256"] and len(raw)==row["bytes"]
            target=output/(name+".mjs")
            target.write_bytes(raw)
            assert SHA(target.read_bytes())==row["sha256"]
            engines[name]={**row,"copy":str(target)}
        candidate_freeze=ROOT/"artifacts/v018-parser-candidate/freeze.json"
        assert SHA(candidate_freeze.read_bytes())==prepared["candidateFreezeSha256"]
        receipt["engines"]=engines
        receipt["measurementExecuted"]=True
        def run(engine,case,phase,mode,batch,expected=None):
            stem=case["name"]+"-"+phase+"-"+mode+"-"+str(batch)+"-"+engine
            job={"authorized":True,"engine":engine,"batch":batch,"mode":mode,"phase":phase,"warmups":5,"samples":30,"corePath":engines[engine]["copy"],"coreSha256":engines[engine]["sha256"],"inputPath":str(HERE/case["inputFile"]),"inputSha256":case["inputSha256"],"expectedStatus":case["expectedStatus"],"expectedOutputSha256":expected,"fullOutputPath":str(output/(stem+".full-output.txt")),"resultPath":str(output/(stem+".json"))}
            job_path=output/(stem+".job.json")
            save(job_path,job)
            started=time.perf_counter_ns()
            result=subprocess.run([str(node),str(HERE/"worker-v2.mjs"),str(job_path),SHA(job_path.read_bytes())],capture_output=True,text=True,encoding="utf-8",timeout=240)
            wall_ms=(time.perf_counter_ns()-started)/1e6
            (output/(stem+".stdout.log")).write_text(result.stdout,encoding="utf-8")
            (output/(stem+".stderr.log")).write_text(result.stderr,encoding="utf-8")
            assert result.returncode==0,stem+": "+result.stderr
            row=load(job["resultPath"])
            assert row["passed"] is True and row["version"]=="0.1.5"
            row["externalProcessWallMs"]=wall_ms
            save(output/(stem+".parent.json"),row)
            return row,Path(job["fullOutputPath"])
        for case in prepared["cases"]:
            for phase in ["parse","full"]:
                original,before_path=run("baseline",case,phase,"equivalence",-1)
                candidate,after_path=run("candidate",case,phase,"equivalence",-1)
                assert before_path.read_bytes()==after_path.read_bytes(),"Complete output differs: "+case["name"]+"/"+phase
                expected=original["fullOutputSha256"]
                receipt["fullOutputEquivalence"].append({"case":case["name"],"phase":phase,"passed":True,"outputSha256":expected,"outputBytes":original["outputBytes"]})
                observed={"baseline":[],"candidate":[]}
                cold={"baseline":[],"candidate":[]}
                for batch in range(3):
                    for engine in (["baseline","candidate"] if batch%2==0 else ["candidate","baseline"]):
                        row,_=run(engine,case,phase,"warm",batch,expected)
                        assert row["warmups"]==5 and len(row["timesMs"])==30
                        observed[engine].append(row)
                    for engine in (["baseline","candidate"] if batch%2==0 else ["candidate","baseline"]):
                        row,_=run(engine,case,phase,"cold",batch,expected)
                        assert row["measuredSamples"]==0
                        cold[engine].append(row)
                summary={}
                for engine in ["baseline","candidate"]:
                    values=[x for row in observed[engine] for x in row["timesMs"]]
                    assert len(values)==90
                    summary[engine]={"medianMs":median(values),"p95Ms":p95(values),"samples":90,"batchMediansMs":[x["medianMs"] for x in observed[engine]],"batchP95Ms":[x["p95Ms"] for x in observed[engine]],"lifetimePeakRssKiBByBatch":[x["lifetimePeakRssKiB"] for x in observed[engine]],"medianLifetimePeakRssKiB":median([x["lifetimePeakRssKiB"] for x in observed[engine]]),"maxObservedRssBytesByBatch":[x["maxObservedRssBytes"] for x in observed[engine]],"coldImportMs":[x["importMs"] for x in cold[engine]],"coldFirstCallMs":[x["firstCallMs"] for x in cold[engine]],"coldExternalProcessWallMs":[x["externalProcessWallMs"] for x in cold[engine]],"coldExternalProcessMedianMs":median([x["externalProcessWallMs"] for x in cold[engine]]),"inputBytes":original["inputBytes"],"outputBytes":original["outputBytes"]}
                controls={}
                for metric in ["medianMs","p95Ms","coldExternalProcessMedianMs"]:
                    baseline=summary["baseline"][metric];after=summary["candidate"][metric];limit=max(2,baseline*.1)
                    controls[metric]={"baseline":baseline,"candidate":after,"deltaMs":after-baseline,"allowedRegressionMs":limit,"passed":after-baseline<=limit}
                receipt["results"].append({"case":case["name"],"group":case["group"],"phase":phase,"inputSha256":case["inputSha256"],"completeOutputSha256":expected,"summary":summary,"controlRegression":controls if case["group"]=="control" else None,"rawWarm":observed,"rawCold":cold})
        receipt["correctnessPassed"]=True
        receipt["protocolCompleted"]=True
        receipt["controlRegressionPassed"]=all(c["passed"] for row in receipt["results"] if row["controlRegression"] for c in row["controlRegression"].values())
        receipt["passed"]=receipt["correctnessPassed"] and receipt["protocolCompleted"] and receipt["controlRegressionPassed"]
        receipt["performanceImprovementClaim"]=False
        receipt["interpretation"]="Local measurements only. A control threshold pass is not evidence of a speedup; inspect complete raw batches and uncertainty before adoption."
        for row in prepared["files"]:assert SHA((HERE/row["file"]).read_bytes())==row["sha256"]
        for name,row in engines.items():assert SHA((ROOT/row["file"]).read_bytes())==row["sha256"] and SHA(Path(row["copy"]).read_bytes())==row["sha256"]
    except Exception as error:
        receipt.update(errorClass=type(error).__name__,error=str(error))
    save(output/"receipt.json",receipt)
    print(json.dumps({"passed":receipt["passed"],"measurementExecuted":receipt["measurementExecuted"],"receipt":str(output/"receipt.json"),"performanceImprovementClaim":False}))
    return 0 if receipt["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
