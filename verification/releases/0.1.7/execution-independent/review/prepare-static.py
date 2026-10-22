"""Only stage static inputs and checker source. Never import any product runtime."""
from pathlib import Path
import ast
import hashlib
import json
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
OLD=ROOT/"artifacts/v017-execution-independent"
CANDIDATE=ROOT/"artifacts/v017-execution-candidate"
SHA=lambda b:hashlib.sha256(b).hexdigest()
def put(name,raw):
    path=HERE/name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:f.write(raw)
def jsonput(name,data):put(name,(json.dumps(data,ensure_ascii=False,indent=2)+"\n").encode())
origin=json.loads((OLD/"pre-execution-freeze.json").read_bytes())
frozen_runner=(OLD/"review.mjs").read_bytes()
assert SHA(frozen_runner)==next(x["sha256"] for x in origin["reviewBindings"] if x["file"]=="review.mjs")
input_bytes=(OLD/"independent-inputs.json").read_bytes()
assert SHA(input_bytes)==next(x["sha256"] for x in origin["reviewBindings"] if x["file"]=="independent-inputs.json")
put("inputs/independent-inputs.json",input_bytes)
rows=json.loads(input_bytes)
expected={}
bindings=[]
def copy(source,target):
    raw=source.read_bytes()
    put(target,raw)
    bindings.append({"from":source.relative_to(ROOT).as_posix(),"to":target,"bytes":len(raw),"sha256":SHA(raw)})
for row in rows:
    source=OLD/"runs/independent-WiOcJ2"/(row["id"]+".replay.json")
    raw=source.read_bytes();record=json.loads(raw)
    assert record["valid"] is True and record["traceSha256"]==SHA(row["traceText"].encode())
    expected[row["id"]]=record["diagnostic"]
    bindings.append({"from":source.relative_to(ROOT).as_posix(),"targetExpectedDiagnostic":row["id"],"bytes":len(raw),"sha256":SHA(raw)})
jsonput("inputs/expected-diagnostics.json",expected)
for label in ["before","fixed"]:
    source=CANDIDATE/"source-inputs/verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c"/label
    for name in ["capture.json","receipt.json","sql-executions.jsonl","final-rows.json","journal/journal-index.json","journal/segment-000001.jsonl"]:copy(source/name,"inputs/mlflow/"+label+"/"+name)
    replay=OLD/"runs/independent-WiOcJ2"/("actual-"+label+".execution-replay.json")
    model=OLD/"runs/independent-WiOcJ2"/("actual-"+label+".model-report.json")
    copy(replay,"inputs/mlflow/"+label+"/expected-execution-replay.json")
    copy(model,"inputs/mlflow/"+label+"/original-model-report.json")
legacy=[]
for ident,source_name in [
    ("v1-v007","examples/legacy-v0.0.7.capsule.json"),
    ("v2-v015","verification/releases/0.1.5/postgres/mini.capsule.json"),
    ("v3-list-v014","verification/releases/0.1.4/list-independent/run14-fcXM9U/example/case.capsule.json"),
    ("v3-relation-v015","verification/releases/0.1.5/relation-independent/actual-v015/run/reduced-capsule.json"),
]:
    source=ROOT/source_name
    target="inputs/legacy/"+ident+".capsule.json"
    copy(source,target)
    capsule=json.loads(source.read_bytes());report=json.loads(capsule["reportText"])
    legacy.append({"id":ident,"file":target,"format":capsule["format"],"schemaVersion":capsule["schemaVersion"],"engineVersion":capsule["engineVersion"],"reportVersion":report["version"],"algorithm":report.get("algorithm"),"reportStatus":report["status"],"bytes":source.stat().st_size,"sha256":SHA(source.read_bytes()),"originalSource":source_name})
jsonput("inputs/legacy-index.json",legacy)
old_sdk=(CANDIDATE/"runtime/generic-sdk.mjs").read_text(encoding="utf-8")
exports=set(re.findall(r"export function ([A-Za-z0-9_]+)",old_sdk))
for group in re.findall(r"export\s*\{([^}]+)\}",old_sdk):
    exports.update(x.strip().split(" as ")[-1] for x in group.split(",") if x.strip())
jsonput("inputs/expected-exports.json",sorted(exports|{"explainRegisterCycleV3","verifyRegisterCycleExplanationV3","makeExecutionCapsuleV3","replayExecutionCapsuleV3"}))
lines=frozen_runner.decode().splitlines(keepends=True)
begin=next(i for i,line in enumerate(lines) if "for(const row of rows)check('independent-fixture-'" in line)
end=next(i for i,line in enumerate(lines) if "check('15-old-exports-retained-new-exports-only-two'" in line)
body="".join(lines[begin:end])
old_call="old.inspectExecutionFailuresV3(row.traceText)"
assert body.count(old_call)==1
body=body.replace(old_call,"expectedDiagnostics[row.id]")
old_future="'version-future':x=>x.engineVersion='0.1.7'"
assert body.count(old_future)==1
body=body.replace(old_future,"'version-future':x=>x.engineVersion='99.0.0'")
header="""// Exact diagnostic behavior assertions extracted from the frozen candidate81 runner.
// Environment checks are separate. No product code runs when this file is staged.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const sha=b=>createHash('sha256').update(b).digest('hex'),canon=x=>JSON.stringify(x,null,2)+'\\n',clone=x=>structuredClone(x);
const reject=(sdk,text,reason)=>{const result=sdk.replayExecutionCapsuleV3(text);assert.equal(result.valid,false);assert.equal(result.scope.actualDatabaseExecution,false);if(reason)assert.equal(result.reason,reason);return result.reason;};
const reseal=x=>{x.traceSha256=sha(x.traceText);x.diagnosticSha256=sha(x.diagnosticText);return canon(x);};
export function runExecutionChecks({sdk,rows,expectedDiagnostics,check,retain}) {
  const capsules=new Map();
"""
put("execution-checks.mjs",(header+body+"\n  return {capsules,base};\n}\n").encode())
jsonput("expectation-adaptation.json",{"originalRunnerSha256":SHA(frozen_runner),"originalPreExecutionFreezeSha256":SHA((OLD/"pre-execution-freeze.json").read_bytes()),"originalResultChecks":81,"behaviorSourceLineStart":begin+1,"behaviorSourceLineEnd":end,"expectationSource":"Frozen complete diagnostics and original input facts; no actual17 output has been read.","explicitAdaptations":[{"from":old_call,"to":"expectedDiagnostics[row.id]","reason":"Same complete frozen diagnostic, with no baseline runtime import."},{"from":old_future,"to":"'version-future':x=>x.engineVersion='99.0.0'","reason":"Actual17 version is verified explicitly in its own engine header; unknown future engine remains a negative case. This touches only generated envelope metadata tampering, never business data."}],"environmentChecksReplaced":["live mainline must equal15","copy15 append composition","copy15 export count"],"oldInputsOrExpectationsModified":False,"actual17Executed":False,"SDKImported":False,"sourceBindings":bindings})
for path in HERE.glob("*.py"):ast.parse(path.read_text(encoding="utf-8"),filename=path.name)
files=[]
for path in sorted(HERE.rglob("*")):
    if path.is_file() and path.name!="preparation-manifest.json" and "runs" not in path.relative_to(HERE).parts:
        raw=path.read_bytes();files.append({"file":path.relative_to(HERE).as_posix(),"bytes":len(raw),"sha256":SHA(raw)})
jsonput("preparation-manifest.json",{"schema":1,"kind":"actual17-independent-review-preparation-only","actual17Executed":False,"SDKImported":False,"newCoreBuild":False,"actualDatabaseExecution":False,"networkUsed":False,"formalPerformanceMeasurement":False,"rootActual17FreezeStillRequired":True,"frozenInputCases":len(rows),"legacyCapsules":len(legacy),"files":files})
print(json.dumps({"prepared":True,"actual17Executed":False,"SDKImported":False,"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.json").read_bytes())}))
