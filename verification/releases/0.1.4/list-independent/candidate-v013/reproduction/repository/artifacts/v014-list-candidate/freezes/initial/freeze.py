"""Bind only the candidate and prior read-only evidence; do not edit mainline."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def binding(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha(raw)}
def write(name, value):
    with (HERE / name).open("x", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

paths = [
    "src/list_v3.mbt", "src/list_v3_wbtest.mbt", "src/api_v3.mbt", "scripts/list-v3-oracle.py",
    "fixtures/list-v3/manifest.json", "fixtures/list-v3/extension-unique.json",
    "verification/list-v3/acceptance-2026-10-21T03-20-46-369Z/receipt.json",
    "verification/list-v3/acceptance-2026-10-22T11-38-04-456Z/receipt.json",
    "verification/list-v3/postgres-2de835316d5f40d6b7e4bfeab4e4b8e4/database-receipt.json",
    "verification/list-v3/postgres-offline-recheck-20261021-0340/model-receipt.json",
]
review = {"schema": 1, "kind": "read-only-existing-list-work-inventory", "actualDatabaseExecution": False,
          "newCoreBuild": False, "fullFrozenCorpusRerun": False, "files": {p: binding(ROOT / p) for p in paths}}
manifest = json.loads((ROOT / paths[4]).read_text(encoding="utf8"))
extension = json.loads((ROOT / paths[5]).read_text(encoding="utf8"))
inputs = manifest["files"] + extension["files"]
for item in inputs:
    assert binding(ROOT / item["file"]) == {"bytes": item["bytes"], "sha256": item["sha256"]}
review["frozenInputFilesVerified"] = inputs
review["moonBitListBoundaryTests"] = len(re.findall(r'^test "', (ROOT / paths[1]).read_text(encoding="utf8"), flags=re.M))
current = json.loads((ROOT / paths[7]).read_text(encoding="utf8"))
review["latestExistingAcceptance"] = {key: current.get(key) for key in ["passed", "complete", "inputCases", "distinctInputHashes", "tamperCases", "build", "differences"]}
assert current["passed"] is True and not current["differences"]
database = json.loads((ROOT / paths[8]).read_text(encoding="utf8"))
offline = json.loads((ROOT / paths[9]).read_text(encoding="utf8"))
review["priorDatabaseReceipt"] = {"passed": database["passed"], "actualDatabaseExecution": database["actualDatabaseExecution"], "roundsPerScenario": database["roundsPerScenario"], "cases": len(database["cases"]), "allCasesPassed": all(case["passed"] for case in database["cases"]), "scope": database["mappingScope"]}
review["priorOfflineRecheck"] = {"passed": offline["passed"], "actualDatabaseExecution": offline["actualDatabaseExecution"], "cases": len(offline["cases"]), "allCasesPassed": all(case["passed"] for case in offline["cases"]), "build": offline["build"]}
write("prior-artifacts-review.json", review)

patches = []
for path in sorted((HERE / "payload").rglob("*")):
    if not path.is_file():
        continue
    name = path.relative_to(HERE / "payload").as_posix()
    old = ROOT / name
    before = old.read_text(encoding="utf8").splitlines(keepends=True) if old.is_file() else []
    after = path.read_text(encoding="utf8").splitlines(keepends=True)
    patches.append(f"diff --git a/{name} b/{name}\n")
    if not old.is_file():
        patches.append("new file mode 100644\n")
    patches.extend(difflib.unified_diff(before, after, fromfile="a/" + name if old.is_file() else "/dev/null", tofile="b/" + name))
(HERE / "candidate.patch").write_text("".join(patches), encoding="utf8", newline="\n")
checked = subprocess.run(["git", "apply", "--check", str(HERE / "candidate.patch")], cwd=ROOT, capture_output=True, text=True)
write("patch-check.json", {"passed": checked.returncode == 0, "exitCode": checked.returncode, "stdout": checked.stdout, "stderr": checked.stderr, "applied": False})
assert checked.returncode == 0, checked.stderr
baseline = json.loads((HERE / "baseline-inputs.json").read_text(encoding="utf8"))
after = {name: binding(ROOT / name) for name in baseline}
assert after == baseline, "Do not change the frozen mainline inputs"
write("mainline-unchanged.json", {"unchanged": True, "before": baseline, "after": after})
final = json.loads((HERE / "runs/run-TunYYE/receipt.json").read_text(encoding="utf8"))
assert final["passed"] is True and len(final["checks"]) == 91
files = ["prepare.py", "freeze.py", "README.md", "list-sdk-additions.mjs", "baseline-inputs.json", "prior-artifacts-review.json", "candidate.patch", "patch-check.json", "mainline-unchanged.json"]
files += [p.relative_to(HERE).as_posix() for p in sorted((HERE / "payload").rglob("*")) if p.is_file()]
files += [p.relative_to(HERE).as_posix() for p in sorted((HERE / "runtime").iterdir()) if p.is_file()]
files += ["runs/run-10GQaH/receipt.json", "runs/run-wmqIR0/receipt.json", "runs/run-pUNIMx/receipt.json", "runs/run-TunYYE/receipt.json"]
frozen = {"schema": 1, "kind": "v014-fixed-list-sdk-candidate", "mainlineModified": False,
          "newCoreBuild": False, "actualDatabaseExecution": False, "performanceMeasurement": False,
          "testChecks": 91, "frozenManualCases": 71, "files": {name: binding(HERE / name) for name in files}}
write("candidate-manifest.json", frozen)
with (HERE / "SHA256SUMS").open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(value["sha256"] + "  " + name + "\n" for name, value in frozen["files"].items()))
print(json.dumps({"frozen": True, "files": len(frozen["files"]), "manifest": binding(HERE / "candidate-manifest.json"), "patchPassed": True, "checks": 91}))
