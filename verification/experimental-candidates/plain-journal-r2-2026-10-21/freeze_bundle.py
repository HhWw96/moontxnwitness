"""Copy exact reviewed bytes into a new static CI bundle. Does not run tests."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PREFIX="artifacts/plain-v3-journal-r2-draft"
EXPECTED="3a13b37fdf4324ceb8c899b3616d86c92e75aa256eca9d87668ddfcde46ee50a"


def binding(path):
    raw=path.read_bytes();return {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def main():
    source=ROOT/PREFIX
    assert binding(source/"candidate-index.json")["sha256"]==EXPECTED
    index=json.loads((source/"candidate-index.json").read_bytes())
    dependencies=json.loads((source/"repository-dependencies.json").read_bytes())
    files={PREFIX+"/"+name:value for name,value in index["fileBindings"].items()}
    files[PREFIX+"/candidate-index.json"]=binding(source/"candidate-index.json")
    files.update(index["runtimeDependencies"]);files.update(dependencies["driverRequirements"])
    assert len(files)<=128 and sum(value["bytes"] for value in files.values())<=4*1024*1024
    for name,expected in files.items():assert binding(ROOT/name)==expected,name
    bundle=HERE/"bundle";bundle.mkdir(exist_ok=False)
    copied={}
    for name,expected in sorted(files.items()):
        target=bundle/"repository"/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as file:file.write((ROOT/name).read_bytes())
        assert binding(target)==expected
        copied[name]={"bundleFile":"repository/"+name,**expected}
    manifest={"schema":1,"kind":"plain-journal-r2-static-ci-source-bundle","candidatePrefix":PREFIX,
              "candidateIndexSha256":EXPECTED,"files":copied,"executedLocally":False,
              "actualDatabaseExecution":False,"formalPerformanceMeasurement":False}
    with (bundle/"bundle-index.json").open("x",encoding="utf-8",newline="\n") as file:
        json.dump(manifest,file,indent=2,ensure_ascii=True);file.write("\n")
    print(json.dumps({"bundleIndex":binding(bundle/"bundle-index.json"),"files":len(files),"bytes":sum(v["bytes"] for v in files.values()),"testsExecuted":False}))


if __name__=="__main__":main()
