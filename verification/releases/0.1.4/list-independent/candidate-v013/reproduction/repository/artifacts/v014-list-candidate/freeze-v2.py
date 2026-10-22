"""Freeze the corrected candidate and retain the complete first snapshot."""
from pathlib import Path
import difflib
import hashlib
import json
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

initial = HERE / "freezes/initial"
manifest = json.loads((initial / "candidate-manifest.json").read_text(encoding="utf8"))
assert binding(initial / "candidate-manifest.json")["sha256"] == "6e8f09f49c3ad4f2f2f9e2ff68d6c473ac3d63d7fa4131fc68bc739119dd5577"
assert all(binding(initial / name) == value for name, value in manifest["files"].items())
patches = []
for path in sorted((HERE / "payload").rglob("*")):
    if not path.is_file():
        continue
    name = path.relative_to(HERE / "payload").as_posix()
    old = ROOT / name
    before = old.read_text(encoding="utf8").splitlines(keepends=True) if old.is_file() else []
    after = path.read_text(encoding="utf8").splitlines(keepends=True)
    patches.append(f"diff --git a/{name} b/{name}\n")
    if not old.is_file(): patches.append("new file mode 100644\n")
    patches.extend(difflib.unified_diff(before, after, fromfile="a/" + name if old.is_file() else "/dev/null", tofile="b/" + name))
with (HERE / "candidate-v2.patch").open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(patches))
checked = subprocess.run(["git", "apply", "--check", str(HERE / "candidate-v2.patch")], cwd=ROOT, capture_output=True, text=True)
write("patch-v2-check.json", {"passed": checked.returncode == 0, "exitCode": checked.returncode, "stdout": checked.stdout, "stderr": checked.stderr, "applied": False})
assert checked.returncode == 0, checked.stderr
before = json.loads((HERE / "baseline-inputs.json").read_text(encoding="utf8"))
after = {name: binding(ROOT / name) for name in before}
assert before == after
write("mainline-v2-unchanged.json", {"unchanged": True, "before": before, "after": after})
final = json.loads((HERE / "runs/run-zsYDKm/receipt.json").read_text(encoding="utf8"))
assert final["passed"] is True and len(final["checks"]) == 92
files = ["prepare.py", "freeze-v2.py", "README.md", "list-sdk-additions.mjs", "baseline-inputs.json", "prior-artifacts-review.json", "candidate-v2.patch", "patch-v2-check.json", "mainline-v2-unchanged.json", "first-malformed-trace-failure.json", "runs/run-zsYDKm/receipt.json"]
files += [p.relative_to(HERE).as_posix() for p in sorted((HERE / "payload").rglob("*")) if p.is_file()]
files += [p.relative_to(HERE).as_posix() for p in sorted((HERE / "runtime").iterdir()) if p.is_file()]
files += [p.relative_to(HERE).as_posix() for p in sorted(initial.rglob("*")) if p.is_file()]
frozen = {"schema": 1, "revision": 2, "kind": "v014-fixed-list-sdk-candidate", "mainlineModified": False,
          "newCoreBuild": False, "actualDatabaseExecution": False, "performanceMeasurement": False,
          "testChecks": 92, "frozenManualCases": 71, "firstRevisionPreserved": True,
          "files": {name: binding(HERE / name) for name in files}}
write("candidate-manifest-v2.json", frozen)
with (HERE / "SHA256SUMS-v2").open("x", encoding="utf8", newline="\n") as stream:
    stream.write("".join(value["sha256"] + "  " + name + "\n" for name, value in frozen["files"].items()))
print(json.dumps({"frozen": True, "files": len(frozen["files"]), "manifest": binding(HERE / "candidate-manifest-v2.json"), "patchPassed": True, "checks": 92}))
