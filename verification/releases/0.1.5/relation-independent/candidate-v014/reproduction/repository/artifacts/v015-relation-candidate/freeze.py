"""Freeze candidate, patch and read-only original evidence; no mainline writes."""
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

paths = ["src/relation_v3.mbt", "src/relation_v3_wbtest.mbt", "scripts/relation-v3-oracle.py",
         "fixtures/relation-v3/manifest.json", "fixtures/relation-v3/reduction-source-closure.json", "fixtures/relation-v3/reduction-source-closure.expected.json",
         "verification/relation-v3/acceptance-2026-10-22T12-25-49-427Z/receipt.json",
         "verification/relation-v3/postgres-2026-10-21/scheduler-receipt.json",
         "verification/relation-v3/postgres-2026-10-21/database/database-receipt.json",
         "verification/relation-v3/postgres-2026-10-21/model/model-receipt.json"]
inventory = {"schema": 1, "kind": "read-only-existing-relation-evidence-inventory", "actualDatabaseExecution": False,
             "newCoreBuild": False, "fullFrozenCorpusRerun": False, "files": {name: binding(ROOT / name) for name in paths}}
manifest = json.loads((ROOT / "fixtures/relation-v3/manifest.json").read_text(encoding="utf8"))
for name, value in manifest["files"].items():
    assert binding(ROOT / "fixtures/relation-v3" / name) == value
inventory["frozenInputFilesVerified"] = manifest["files"]
inventory["moonBitBoundaryTests"] = len(re.findall(r'^test "', (ROOT / paths[1]).read_text(encoding="utf8"), flags=re.M))
current = json.loads((ROOT / paths[6]).read_text(encoding="utf8"))
assert current["passed"] is True and current["differences"] == []
inventory["latestExistingAcceptance"] = {key: current.get(key) for key in ["passed", "complete", "inputCases", "normalizationCases", "sourceEvidenceCases", "budgetCases", "witnesses", "build", "differences"]}
inventory["latestExistingAcceptance"]["checks"] = len(current["checks"])
database = json.loads((ROOT / paths[8]).read_text(encoding="utf8"))
model = json.loads((ROOT / paths[9]).read_text(encoding="utf8"))
inventory["priorDatabase"] = {key: database.get(key) for key in ["passed", "actualDatabaseExecution", "roundsPerScenario", "scenarioCount", "completeAutomaticSqlCapture", "sourceBindingsUnchanged"]}
inventory["priorDatabase"]["cases"] = len(database["scenarios"])
inventory["priorOfflineModel"] = {key: model.get(key) for key in ["passed", "actualDatabaseExecution", "fixtureScope"]}
inventory["priorOfflineModel"]["cases"] = len(model["cases"])
write("prior-artifacts-review.json", inventory)

patches = []
for path in sorted((HERE / "payload").rglob("*")):
    if not path.is_file(): continue
    name = path.relative_to(HERE / "payload").as_posix()
    old = ROOT / name
    before = old.read_text(encoding="utf8").splitlines(keepends=True) if old.is_file() else []
    after = path.read_text(encoding="utf8").splitlines(keepends=True)
    patches.append(f"diff --git a/{name} b/{name}\n")
    if not old.is_file(): patches.append("new file mode 100644\n")
    patches.extend(difflib.unified_diff(before, after, fromfile="a/" + name if old.is_file() else "/dev/null", tofile="b/" + name))
with (HERE / "candidate.patch").open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(patches))
checked = subprocess.run(["git", "apply", "--check", str(HERE / "candidate.patch")], cwd=ROOT, capture_output=True, text=True)
write("patch-check.json", {"passed": checked.returncode == 0, "exitCode": checked.returncode, "stdout": checked.stdout, "stderr": checked.stderr, "applied": False})
assert checked.returncode == 0, checked.stderr
before = json.loads((HERE / "baseline-inputs.json").read_text(encoding="utf8"))
after = {name: binding(ROOT / name) for name in before}
assert before == after
write("mainline-unchanged.json", {"unchanged": True, "before": before, "after": after})
for run in ["run-013cPQ", "run-6ADwGa"]:
    receipt = json.loads((HERE / "runs" / run / "receipt.json").read_text(encoding="utf8"))
    assert receipt["passed"] is True and len(receipt["checks"]) == 194
    assert receipt["manualCases"] == 170 and receipt["preservedListManualCases"] == 71
files = ["prepare.py", "freeze.py", "README.md", "relation-sdk.md", "relation-sdk-additions.mjs", "extra-tests.mjs", "baseline-inputs.json", "prior-artifacts-review.json", "candidate.patch", "patch-check.json", "mainline-unchanged.json", "freeze-first-failure.json"]
for folder in ["templates", "payload", "runtime", "runtime-no-prior-sdk"]:
    files += [path.relative_to(HERE).as_posix() for path in sorted((HERE / folder).rglob("*")) if path.is_file()]
files += ["runs/" + name + "/receipt.json" for name in ["run-SSPSHA", "run-KZKzXl", "run-WF5OGe", "run-013cPQ", "run-6ADwGa"]]
frozen = {"schema": 1, "kind": "v015-fixed-relation-sdk-candidate", "mainlineModified": False,
          "newCoreBuild": False, "actualDatabaseExecution": False, "performanceMeasurement": False,
          "testChecksPerMode": 194, "relationBoundaryCases": 170, "preservedListCases": 71,
          "files": {name: binding(HERE / name) for name in files}}
write("candidate-manifest.json", frozen)
with (HERE / "SHA256SUMS").open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(value["sha256"] + "  " + name + "\n" for name, value in frozen["files"].items()))
print(json.dumps({"frozen": True, "files": len(frozen["files"]), "manifest": binding(HERE / "candidate-manifest.json"), "patchPassed": True, "checks": 194}))
