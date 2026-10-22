"""Static closure seal only. Does not run JavaScript, SDKs or review assertions."""
from pathlib import Path
import ast
import hashlib
import json
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
module=(HERE/"execution-checks.mjs").read_bytes()
assert b"const capsules=new Map();" in module
assert b"canon=x=>JSON.stringify(x,null,2)+'"+bytes([92,110])+b"'" in module
assert b"old.inspectExecutionFailuresV3" not in module
assert b"'version-future':x=>x.engineVersion='99.0.0'" in module
for p in HERE.glob("*.py"):ast.parse(p.read_text(encoding="utf-8"),filename=p.name)
files=[]
for p in sorted(HERE.rglob("*")):
    if p.is_file() and not p.name.startswith("preparation-manifest") and "runs" not in p.relative_to(HERE).parts:
        data=p.read_bytes();files.append({"file":p.relative_to(HERE).as_posix(),"bytes":len(data),"sha256":SHA(data)})
result={"schema":1,"kind":"actual17-independent-review-preparation-only","revision":2,"actual17Executed":False,"SDKImported":False,"newCoreBuild":False,"actualDatabaseExecution":False,"networkUsed":False,"formalPerformanceMeasurement":False,"rootActual17FreezeStillRequired":True,"frozenInputCases":11,"legacyCapsules":4,"firstStaticPreparationSnapshotPreserved":"preparation-manifest.json","preExecutionStaticRepair":"Added the capsule Map declaration omitted when extracting the original checker environment. No SDK was executed, no semantic expectation changed.","files":files}
with (HERE/"preparation-manifest.v2.json").open("x",encoding="utf-8",newline="\n") as f:json.dump(result,f,indent=2);f.write("\n")
print(json.dumps({"prepared":True,"actual17Executed":False,"SDKImported":False,"files":len(files),"manifestSha256":SHA((HERE/"preparation-manifest.v2.json").read_bytes())}))
