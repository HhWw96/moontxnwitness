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
from binding_guard_v3 import stage_bound_engines

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
    parser.add_argument("--binding",type=Path,required=True)
    parser.add_argument("--binding-sha256",required=True)
    args=parser.parse_args()
    # These guards perform no measurement and import no product code.
    auth_bytes=args.authorization.read_bytes()
    assert SHA(auth_bytes)==args.authorization_sha256
    auth=json.loads(auth_bytes)
    assert auth["schema"]==1 and auth["kind"]=="root-exclusive-v018-performance-authorization"
    assert auth["signal"]=="root-authorized-exclusive-v018-performance"
    assert auth["runPerformanceNow"] is True and auth["exclusiveMachine"] is True
    assert auth["allAgentsStopped"] is True and auth["runningNonMeasurementAgents"]==[]
    assert auth["agentShutdownAttestation"] and "ROOT_MUST" not in auth["agentShutdownAttestation"]
    binding_bytes=args.binding.read_bytes()
    assert SHA(binding_bytes)==args.binding_sha256==auth["runtimeSourceBindingSha256"]
    binding=json.loads(binding_bytes)
    assert auth["operatorAttestation"] and "ROOT_MUST" not in auth["operatorAttestation"]
    prepared_bytes=(HERE/"preparation-manifest.v3.json").read_bytes()
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
        engines=stage_bound_engines(binding,output)
        receipt["engines"]=engines
        receipt["runtimeSourceBindingSha256"]=args.binding_sha256
        receipt["baselineVersion"]="0.1.7"
        receipt["currentVersion"]="0.1.8"
        receipt["allAgentsStoppedAttestation"]=auth["agentShutdownAttestation"]
        receipt["allAgentsStoppedIndependentlyProven"]=False
        receipt["baselinePublicationReceipt"]=binding["baselinePublicationReceipt"]
        receipt["projectionPolicy"]="Validate actual core.version and each native /version header, tool/schema/algorithm; project only those two root JSON string spans. Every other character remains exact."
        projection_check=subprocess.run([str(node),str(HERE/"projection-self-check-v3.mjs")],capture_output=True,text=True,encoding="utf-8",timeout=30)
        (output/"projection-self-check.stdout.log").write_text(projection_check.stdout,encoding="utf-8")
        (output/"projection-self-check.stderr.log").write_text(projection_check.stderr,encoding="utf-8")
        assert projection_check.returncode==0,projection_check.stderr
        receipt["measurementExecuted"]=True
        def run(engine,case,phase,mode,batch,expected=None,raw_expected=None):
            stem=case["name"]+"-"+phase+"-"+mode+"-"+str(batch)+"-"+engine
            job={"authorized":True,"engine":engine,"batch":batch,"mode":mode,"phase":phase,"warmups":5,"samples":30,"corePath":engines[engine]["copy"],"coreSha256":engines[engine]["sha256"],"inputPath":str(HERE/case["inputFile"]),"inputSha256":case["inputSha256"],"expectedStatus":case["expectedStatus"],"expectedOutputSha256":expected,"expectedRawOutputSha256":raw_expected,"expectedVersion":engines[engine]["version"],"projectedOutputPath":str(output/(stem+".projected-output.txt")),"firstFailureOutputPath":str(output/(stem+".first-failure-output.txt")),"fullOutputPath":str(output/(stem+".full-output.txt")),"resultPath":str(output/(stem+".json"))}
            job_path=output/(stem+".job.json")
            save(job_path,job)
            started=time.perf_counter_ns()
            result=subprocess.run([str(node),str(HERE/"worker-v3.mjs"),str(job_path),SHA(job_path.read_bytes())],capture_output=True,text=True,encoding="utf-8",timeout=240)
            wall_ms=(time.perf_counter_ns()-started)/1e6
            (output/(stem+".stdout.log")).write_text(result.stdout,encoding="utf-8")
            (output/(stem+".stderr.log")).write_text(result.stderr,encoding="utf-8")
            assert result.returncode==0,stem+": "+result.stderr
            row=load(job["resultPath"])
            assert row["passed"] is True and row["version"]==engines[engine]["version"]
            row["externalProcessWallMs"]=wall_ms
            save(output/(stem+".parent.json"),row)
            return row,Path(job["projectedOutputPath"])
        for case in prepared["cases"]:
            for phase in ["parse","full"]:
                original,before_path=run("baseline",case,phase,"equivalence",-1)
                candidate,after_path=run("current",case,phase,"equivalence",-1)
                assert before_path.read_bytes()==after_path.read_bytes(),"Complete output differs: "+case["name"]+"/"+phase
                expected=original["fullOutputSha256"]
                raw_expected={"baseline":original["rawFullOutputSha256"],"current":candidate["rawFullOutputSha256"]}
                receipt["fullOutputEquivalence"].append({"case":case["name"],"phase":phase,"passed":True,"outputSha256":expected,"outputBytes":original["outputBytes"],"baselineRawOutputSha256":original["rawFullOutputSha256"],"currentRawOutputSha256":candidate["rawFullOutputSha256"],"projectionPolicy":receipt["projectionPolicy"]})
                observed={"baseline":[],"current":[]}
                cold={"baseline":[],"current":[]}
                for batch in range(3):
                    for engine in (["baseline","current"] if batch%2==0 else ["current","baseline"]):
                        row,_=run(engine,case,phase,"warm",batch,expected,raw_expected[engine])
                        assert row["warmups"]==5 and len(row["timesMs"])==30
                        observed[engine].append(row)
                    for engine in (["baseline","current"] if batch%2==0 else ["current","baseline"]):
                        row,_=run(engine,case,phase,"cold",batch,expected,raw_expected[engine])
                        assert row["measuredSamples"]==0
                        cold[engine].append(row)
                summary={}
                for engine in ["baseline","current"]:
                    values=[x for row in observed[engine] for x in row["timesMs"]]
                    assert len(values)==90
                    summary[engine]={"medianMs":median(values),"p95Ms":p95(values),"samples":90,"batchMediansMs":[x["medianMs"] for x in observed[engine]],"batchP95Ms":[x["p95Ms"] for x in observed[engine]],"lifetimePeakRssKiBByBatch":[x["lifetimePeakRssKiB"] for x in observed[engine]],"medianLifetimePeakRssKiB":median([x["lifetimePeakRssKiB"] for x in observed[engine]]),"maxObservedRssBytesByBatch":[x["maxObservedRssBytes"] for x in observed[engine]],"coldImportMs":[x["importMs"] for x in cold[engine]],"coldFirstCallMs":[x["firstCallMs"] for x in cold[engine]],"coldExternalProcessWallMs":[x["externalProcessWallMs"] for x in cold[engine]],"coldExternalProcessMedianMs":median([x["externalProcessWallMs"] for x in cold[engine]]),"inputBytes":original["inputBytes"],"outputBytes":original["outputBytes"]}
                controls={}
                for metric in ["medianMs","p95Ms","coldExternalProcessMedianMs"]:
                    baseline=summary["baseline"][metric];after=summary["current"][metric];limit=max(2,baseline*.1)
                    controls[metric]={"baseline":baseline,"current":after,"deltaMs":after-baseline,"allowedRegressionMs":limit,"passed":after-baseline<=limit}
                receipt["results"].append({"case":case["name"],"group":case["group"],"phase":phase,"inputSha256":case["inputSha256"],"completeOutputSha256":expected,"summary":summary,"controlRegression":controls if case["group"]=="control" else None,"rawWarm":observed,"rawCold":cold})
        receipt["correctnessPassed"]=True
        receipt["protocolCompleted"]=True
        receipt["controlRegressionPassed"]=all(c["passed"] for row in receipt["results"] if row["controlRegression"] for c in row["controlRegression"].values())
        receipt["passed"]=receipt["correctnessPassed"] and receipt["protocolCompleted"] and receipt["controlRegressionPassed"]
        receipt["performanceImprovementClaim"]=False
        receipt["interpretation"]="Local measurements only. A control threshold pass is not evidence of a speedup; inspect complete raw batches and uncertainty before adoption."
        for row in prepared["files"]:assert SHA((HERE/row["file"]).read_bytes())==row["sha256"]
        for name,row in engines.items():assert SHA((ROOT/row["file"]).read_bytes())==row["sha256"] and SHA(Path(row["copy"]).read_bytes())==row["sha256"]
        for row in engines.values():
            for source_file in row["sourceFiles"]:assert SHA((Path(row["sourceRoot"])/source_file["file"]).read_bytes())==source_file["sha256"]
            assert SHA(Path(row["buildManifest"]["path"]).read_bytes())==row["buildManifest"]["sha256"]
    except Exception as error:
        receipt.update(errorClass=type(error).__name__,error=str(error))
    save(output/"receipt.json",receipt)
    print(json.dumps({"passed":receipt["passed"],"measurementExecuted":receipt["measurementExecuted"],"receipt":str(output/"receipt.json"),"performanceImprovementClaim":False}))
    return 0 if receipt["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
