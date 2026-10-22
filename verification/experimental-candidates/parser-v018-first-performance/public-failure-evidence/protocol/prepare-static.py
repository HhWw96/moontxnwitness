"""Freeze fixtures/code only. Never import a core or invoke a timed worker."""
from pathlib import Path
import ast
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
def put(name,data):
    path=HERE/name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:f.write(data)
def encoded(data):return (json.dumps(data,ensure_ascii=False,separators=(",",":"))+"\n").encode()
fixed=ROOT/"verification/fixtures/v010-comparison/manifest.json"
original=json.loads(fixed.read_bytes())
cases=[]
for name in ["small-positive","dense-rt-192","small-cycle-noise-64"]:
    row=next(x for x in original["cases"] if x["name"]==name)
    source=ROOT/row["file"]
    raw=source.read_bytes()
    assert SHA(raw)==row["fixtureSha256"]
    put("frozen-source-fixtures/"+name+".json",raw)
    value=json.loads(raw)
    data=encoded(value["history"])
    target="inputs/"+name+".json"
    put(target,data)
    cases.append({"name":name,"group":"control","expectedStatus":value["status"],"inputFile":target,"inputSha256":SHA(data),"inputBytes":len(data),"sourceFixture":row["file"],"sourceFixtureSha256":row["fixtureSha256"],"operation":"analyze_options_json","optionsText":"{}"})
for name,key,version,tx_prefix in [
    ("parser-known-ascii","key","version","T"),
    ("parser-custom-ascii","customer_key_001","custom_initial_version_001","custom_transaction_"),
    ("parser-escaped-ascii",'q"\\_key','v"\\_initial','T"\\_'),
    ("parser-unicode","业务键😀","初始版本𝄞","事务"),
]:
    # 256 transactions x16 operations =4096; fixed below balanced parser limits.
    history={"schemaVersion":1,"model":"serializable","initial":{key:version},"transactions":[{"id":tx_prefix+f"{i:04d}","status":"committed","ops":[{"type":"read","key":key,"version":version} for _ in range(16)]} for i in range(256)]}
    assert len(history["transactions"])==256
    assert len({x["id"] for x in history["transactions"]})==256
    assert sum(len(x["ops"]) for x in history["transactions"])==4096
    for identifier in [key,version,*[x["id"] for x in history["transactions"]]]:
        assert 0<len(identifier.encode("utf-16-le"))//2<=256
        assert not any(ord(c)<32 or ord(c)==127 for c in identifier)
    data=encoded(history);target="inputs/"+name+".json";put(target,data)
    cases.append({"name":name,"group":"parser-heavy","expectedStatus":"consistent","inputFile":target,"inputSha256":SHA(data),"inputBytes":len(data),"transactions":256,"operations":4096,"validity":"Schema/identifier/size construction assertions only; runtime validity and full-output equivalence are mandatory gates when measurement is later authorized.","operation":"analyze_options_json","optionsText":"{}"})
engines={}
for name,file,expected in [
    ("baseline","artifacts/v018-parser-candidate/baseline-runtime/core.mjs","a42c29e0ffcb516d6b6cd84ee273d50aa99ad6c989ad4d3e6f97d6c433ec0cef"),
    ("candidate","artifacts/v018-parser-candidate/actual-isolated-runtime/core.mjs","5d5d87c2b9c283822d32a343e406d687e2c3944a15adc32dd6ceaf5391531b8e"),
]:
    data=(ROOT/file).read_bytes();assert SHA(data)==expected
    engines[name]={"file":file,"bytes":len(data),"sha256":expected,"version":"0.1.5","noImportPerformed":True}
freeze=ROOT/"artifacts/v018-parser-candidate/freeze.json"
assert SHA(freeze.read_bytes())=="5dafbcb445a121cf7e0ed88b0ef3ddb28e167deaa90b3f06824aadd36329d716"
put("input-provenance.json",(json.dumps({"fixedFixtureManifestSha256":SHA(fixed.read_bytes()),"cases":cases,"candidateFreezeSha256":SHA(freeze.read_bytes()),"engines":engines,"coreImported":False,"measurementsRun":False},ensure_ascii=False,indent=2)+"\n").encode())
for path in HERE.glob("*.py"):ast.parse(path.read_text(encoding="utf-8"),filename=path.name)
files=[]
for path in sorted(HERE.rglob("*")):
    if path.is_file() and path.name!="preparation-manifest.json":
        raw=path.read_bytes();files.append({"file":path.relative_to(HERE).as_posix(),"bytes":len(raw),"sha256":SHA(raw)})
manifest={"schema":1,"kind":"v018-parser-performance-preparation-only","formalPerformanceMeasured":False,"coreImported":False,"newCoreBuild":False,"databaseExecuted":False,"networkUsed":False,"formal18Build":False,"exclusiveRootAuthorizationStillRequired":True,"warmups":5,"samplesPerProcess":30,"independentProcessBatches":3,"cases":cases,"engines":engines,"candidateFreezeSha256":SHA(freeze.read_bytes()),"files":files}
put("preparation-manifest.json",(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode())
print(json.dumps({"prepared":True,"formalPerformanceMeasured":False,"coreImported":False,"cases":len(cases),"files":len(files),"inputBytes":sum(x["inputBytes"] for x in cases),"manifestSha256":SHA((HERE/"preparation-manifest.json").read_bytes())}))
