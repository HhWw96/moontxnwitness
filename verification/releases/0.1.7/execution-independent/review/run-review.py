"""Guard every supplied actual17 byte before starting any production JavaScript."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
HEX=re.compile(r"^[0-9a-f]{64}$")

def safe(root,name):
    root=Path(root).resolve()
    result=(root/name).resolve()
    assert result.is_relative_to(root) and result!=root,name
    return result

def verify(row,path):
    assert HEX.fullmatch(row["sha256"]),str(path)
    raw=Path(path).read_bytes()
    assert len(raw)==row["bytes"] and SHA(raw)==row["sha256"],str(path)
    return raw

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--freeze",type=Path,required=True)
    parser.add_argument("--freeze-sha256",required=True)
    args=parser.parse_args()
    runs=HERE/"runs"
    runs.mkdir(exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix="actual17-",dir=runs))
    preflight={"schema":1,"kind":"actual17-independent-pre-import-guard","passed":False,"createdAt":datetime.now(timezone.utc).isoformat(),"productionImported":False,"actualDatabaseExecution":False,"newCoreBuild":False,"networkUsed":False,"formalPerformanceMeasurement":False,"checks":[]}
    try:
        assert HEX.fullmatch(args.freeze_sha256)
        frozen_bytes=args.freeze.read_bytes()
        assert SHA(frozen_bytes)==args.freeze_sha256,"Externally supplied root freeze SHA mismatch"
        frozen=json.loads(frozen_bytes)
        assert frozen["schema"]==1 and frozen["kind"]=="root-frozen-actual17-independent-review-input"
        assert frozen["executeReview"] is True and frozen["authorizationSignal"]=="actual-0.1.7-frozen-by-root"
        assert frozen["expectedVersion"]=="0.1.7"
        preflight["checks"].append({"name":"root-explicit-actual17-freeze-and-external-SHA","passed":True})
        prepared=json.loads((HERE/"preparation-manifest.v2.json").read_bytes())
        assert prepared["actual17Executed"] is False
        for row in prepared["files"]:verify(row,safe(HERE,row["file"]))
        preflight["checks"].append({"name":"review-source-and-all-frozen-inputs","passed":True,"files":len(prepared["files"])})
        source=frozen["source"]
        source_map={x["file"]:x for x in source["files"]}
        assert len(source_map)==len(source["files"])
        assert {"moon.mod","package.json"}.issubset(source_map)
        for name,row in source_map.items():verify(row,safe(source["root"],name))
        pkg=json.loads(safe(source["root"],"package.json").read_bytes())
        assert pkg["version"]=="0.1.7"
        source_names=sorted(["moon.mod"]+[name for name in source_map if name.startswith("src/") and (name.endswith(".mbt") or name.endswith("/moon.pkg"))])
        actual_names=sorted(p.relative_to(Path(source["root"])).as_posix() for p in (Path(source["root"])/"src").rglob("*") if p.is_file() and (p.suffix==".mbt" or p.name=="moon.pkg"))
        assert source_names==sorted(["moon.mod"]+actual_names),"Source list omits or adds compilation inputs"
        digest=hashlib.sha256()
        for name in source_names:digest.update(name.encode()+b"\0");digest.update(safe(source["root"],name).read_bytes());digest.update(b"\0")
        assert digest.hexdigest()==source["sourceFingerprint"]
        preflight["checks"].append({"name":"actual17-complete-source-fingerprint","passed":True,"sourceFingerprint":digest.hexdigest()})
        runtime=frozen["runtime"]
        runtime_map={x["file"]:x for x in runtime["files"]}
        assert len(runtime_map)==len(runtime["files"])
        assert {runtime["sdk"],runtime["evidence"],"core.mjs","capture-core.mjs","build-manifest.json","THIRD_PARTY_NOTICES.txt"}.issubset(runtime_map)
        runtime_bytes={name:verify(row,safe(runtime["root"],name)) for name,row in runtime_map.items()}
        build=json.loads(runtime_bytes["build-manifest.json"])
        assert build["version"]=="0.1.7" and build["sourceSha256"]==source["sourceFingerprint"]
        assert build["coreSha256"]==runtime_map["core.mjs"]["sha256"] and build["captureCoreSha256"]==runtime_map["capture-core.mjs"]["sha256"]
        # Only verified local modules and Node builtins may be imported. Runtime
        # dynamic imports are rejected so no later unbound module is loaded.
        imports=[]
        for name,raw in runtime_bytes.items():
            if not name.endswith(".mjs"):continue
            text=raw.decode("utf-8")
            assert not re.search(r"\bimport\s*\(",text),"Unbound dynamic import: "+name
            specs=re.findall(r"(?:\bfrom\s*|\bimport\s*)['\"]([^'\"]+)['\"]",text)
            for spec in specs:
                if spec.startswith("node:"):continue
                assert spec.startswith("."),"External runtime import: "+spec
                p=safe(runtime["root"],str(Path(name).parent/spec))
                local=p.relative_to(Path(runtime["root"]).resolve()).as_posix()
                assert local in runtime_map,"Runtime dependency not frozen: "+local
                imports.append({"from":name,"to":local})
        preflight["checks"].append({"name":"actual17-runtime-build-and-import-closure","passed":True,"files":len(runtime_map),"localImports":imports})
        assert {x["kind"] for x in frozen["packages"]}=={"source","portable"}
        for package in frozen["packages"]:
            verify(package,package["path"])
            covered=set()
            with zipfile.ZipFile(package["path"]) as archive:
                assert archive.testzip() is None
                assert len(archive.namelist())==len(set(archive.namelist())),"Duplicate ZIP names"
                for row in package["entries"]:
                    raw=archive.read(row["file"])
                    assert len(raw)==row["bytes"] and SHA(raw)==row["sha256"]
                    key="runtimeFile" if package["kind"]=="portable" else "sourceFile"
                    name=row[key]
                    original=runtime_map[name] if key=="runtimeFile" else source_map[name]
                    assert row["bytes"]==original["bytes"] and row["sha256"]==original["sha256"],"Package differs from frozen source/runtime: "+row["file"]
                    covered.add(name)
            expected=set(runtime_map if package["kind"]=="portable" else source_map)
            assert covered==expected,"Package entry binding is incomplete"
            preflight["checks"].append({"name":package["kind"]+"-ZIP-SHA-CRC-and-all-bound-members","passed":True,"members":len(covered)})
        copied=output/"runtime"
        copied.mkdir()
        for name,raw in runtime_bytes.items():
            target=safe(copied,name)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            verify(runtime_map[name],target)
        preflight.update(passed=True,rootFreezeSha256=args.freeze_sha256,runtimeCopiedOnlyAfterGuard=True,runtimeRoot=str(copied),runtimeFiles=runtime["files"],sdk=runtime["sdk"],evidence=runtime["evidence"],expectedVersion="0.1.7",sourceFingerprint=source["sourceFingerprint"],rootFreezeFile=str(args.freeze.resolve()))
    except Exception as error:
        preflight.update(errorClass=type(error).__name__,error=str(error))
    target=output/"preflight.json"
    target.write_text(json.dumps(preflight,indent=2)+"\n",encoding="utf-8")
    if not preflight["passed"]:
        print(json.dumps({"passed":False,"productionImported":False,"preflight":str(target),"error":preflight.get("error")}))
        return 1
    result=subprocess.run([frozen.get("nodeExecutable",r"D:\nodejs\node.exe"),str(HERE/"run-tests.mjs"),"--preflight",str(target),"--preflight-sha256",SHA(target.read_bytes())],capture_output=True,text=True,encoding="utf-8",timeout=180)
    (output/"stdout.log").write_text(result.stdout,encoding="utf-8")
    (output/"stderr.log").write_text(result.stderr,encoding="utf-8")
    print(result.stdout,end="")
    if result.stderr:print(result.stderr,end="")
    return result.returncode

if __name__=="__main__":raise SystemExit(main())
