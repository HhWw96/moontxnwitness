"""Build source/runtime ZIPs, then verify both from fresh extraction directories."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", VERSION), "Release version must be stable x.y.z"
NAME = "MoonTxnWitness-v" + VERSION
ARTIFACTS = ROOT / "artifacts"
NODE = os.environ.get("MTW_NODE", "node")
SUMMARY = json.loads((ROOT / "verification/summary.json").read_text(encoding="utf-8"))
assert SUMMARY["passed"] is True and SUMMARY["version"] == VERSION, "Run npm test before packaging"
assert (ROOT / "dist/core.mjs").is_file(), "Build the runtime before packaging"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(files, path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for relative in sorted(files):
            content = (ROOT / relative).read_bytes()
            # A local compiler/checkout path must never leak into shared artifacts.
            if relative.endswith((".mjs", ".json", ".mbt", ".md", ".mbti", ".txt")):
                for private in (str(ROOT), ROOT.as_posix(), str(Path.home()), Path.home().as_posix()):
                    assert private.encode("utf-8") not in content, "Local path found in " + relative
            info = zipfile.ZipInfo(NAME + "/" + relative, date_time=(2026, 10, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            output.writestr(info, content)
    with zipfile.ZipFile(path) as built:
        assert built.testzip() is None, "ZIP integrity failure"
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path), "files": len(files)}


excluded_dirs = {".git", "_build", ".mooncakes", "node_modules", "artifacts", "dist", "__pycache__"}
excluded_names = {".local-toolchain.json", ".DS_Store"}
source = []
for item in ROOT.rglob("*"):
    relative = item.relative_to(ROOT)
    if not item.is_file() or any(part in excluded_dirs or part.startswith('moontxnwitness-demo-') for part in relative.parts) or item.name in excluded_names:
        continue
    if item.suffix in {".log", ".pyc"} or relative.as_posix() == "verification/package.json":
        continue
    source.append(relative.as_posix())
portable = ["README.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY.md", "run-demo.cmd"]
for folder in ("dist", "docs", "examples", "verification"):
    for item in (ROOT / folder).rglob("*"):
        if item.is_file() and "__pycache__" not in item.parts and item.name != "package.json":
            portable.append(item.relative_to(ROOT).as_posix())

ARTIFACTS.mkdir(exist_ok=True)
archives = [archive(source, ARTIFACTS / (NAME + "-source.zip")), archive(portable, ARTIFACTS / (NAME + "-portable.zip"))]
current_sums = "".join(item["sha256"] + "  " + item["file"] + "\n" for item in archives)
(ARTIFACTS / (NAME + "-SHA256SUMS.txt")).write_text(current_sums, encoding="utf-8")
all_releases = [path for path in sorted(ARTIFACTS.glob("MoonTxnWitness-v*-*.zip")) if re.fullmatch(r"MoonTxnWitness-v[0-9]+\.[0-9]+\.[0-9]+-(source|portable)\.zip", path.name)]
(ARTIFACTS / "SHA256SUMS").write_text("".join(sha256(path) + "  " + path.name + "\n" for path in all_releases), encoding="utf-8")

# All work is created below the project. No existing directory is reset or removed.
consumer_parent = ARTIFACTS / "consumer-work"
consumer_parent.mkdir(exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="run-", dir=consumer_parent)).resolve()
assert work.is_relative_to(consumer_parent.resolve())
env = dict(os.environ)
home = env.get("MTW_TOOLCHAIN_HOME")
if home:
    env["MOON_HOME"] = home

checks = []


def run(args, cwd, expected=0):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert result.returncode == expected, "Consumer command failed:\n" + result.stdout + result.stderr
    return result.stdout


fixtures = [("consistent", "consistent", 0), ("write-skew", "violation", 1), ("information-cycle", "violation", 1), ("unknown-order", "consistent", 0), ("lost-update", "violation", 1), ("aborted-read", "violation", 1), ("strict-realtime", "violation", 1), ("fractured-observation", "violation", 1)]
for kind in ("portable", "source"):
    destination = work / kind
    with zipfile.ZipFile(ARTIFACTS / (NAME + "-" + kind + ".zip")) as packed:
        for member in packed.infolist():
            target = (destination / member.filename).resolve()
            assert target.is_relative_to(destination.resolve()), "Unsafe ZIP path"
        packed.extractall(destination)
    consumer = destination / NAME
    assert not (consumer / ".local-toolchain.json").exists(), "Source must not depend on private toolchain config"
    if kind == "source":
        assert not (consumer / "dist").exists()
        run([NODE, "scripts/build.mjs"], consumer)
        checks.append("source rebuilt using external MoonBit installation, no local config")
        core_tests = run([NODE, "scripts/moon.mjs", "test", "--target", "js", "--deny-warn"], consumer)
        test_count = SUMMARY["coreTestsPerTarget"]
        assert f"Total tests: {test_count}, passed: {test_count}, failed: 0." in core_tests
        checks.append(f"source fresh JS core tests: {test_count} passed")
    assert run([NODE, "dist/moontxnwitness.mjs", "--version"], consumer).strip() == VERSION
    checks.append(kind + " version")
    for filename, status, exit_code in fixtures:
        report = json.loads(run([NODE, "dist/moontxnwitness.mjs", "check", "examples/" + filename + ".json", "--format", "json"], consumer, exit_code))
        assert report["status"] == status
        checks.append(kind + " fixture: " + filename)
    run([NODE, "dist/moontxnwitness.mjs", "check", "examples/write-skew.json", "--format", "json", "--output", "new-report.json", "--witness", "new-witness.json", "--capsule", "new-case.capsule.json"], consumer, 1)
    checks.append(kind + " combined artifact export")
    assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "verify", "examples/write-skew.json", "new-witness.json"], consumer))["valid"] is True
    checks.append(kind + " certificate verification")
    assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "verify", "examples/write-skew.json", "examples/legacy-v0.0.1.witness.json"], consumer))["valid"] is True
    checks.append(kind + " legacy v0.0.1 certificate")
    assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "replay", "new-case.capsule.json"], consumer))["valid"] is True
    checks.append(kind + " self-contained replay")
    run([NODE, "dist/moontxnwitness.mjs", "shrink", "examples/noisy-write-skew.json", "--output", "new-reduction.json", "--history", "new-mini.json"], consumer)
    reduction = json.loads((consumer / "new-reduction.json").read_text(encoding="utf-8"))
    assert reduction["oneMinimal"] is True and len(reduction["reducedHistory"]["transactions"]) == 2
    checks.append(kind + " transaction reduction 7 to 2")
    assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "check", "new-mini.json", "--format", "json"], consumer, 1))["status"] == "violation"
    checks.append(kind + " reduced history reanalysis")
    assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "compare-models", "examples/strict-realtime.json"], consumer))["classification"] == "realtime-only-violation"
    checks.append(kind + " model comparison")
    demo = json.loads(run([NODE, "dist/demo.mjs", "--json"], consumer))
    assert demo["passed"] is True and demo["replayValid"] is True and demo["version"] == VERSION
    assert all((consumer / demo["outputDirectory"] / name).is_file() for name in demo["files"])
    checks.append(kind + " one-command demo and artifacts")
    sdk = run([NODE, "--input-type=module", "-e", "import {analyze,version,shrink,compareModels,replayReport} from './dist/sdk.mjs'; import {readFileSync} from 'node:fs'; const h=readFileSync('examples/consistent.json','utf8'); const r=analyze(h); console.log(JSON.stringify({version:version(),status:r.status,replay:replayReport(h,r).valid,oneMinimal:shrink(readFileSync('examples/noisy-write-skew.json','utf8')).oneMinimal,models:compareModels(readFileSync('examples/strict-realtime.json','utf8')).classification}));"], consumer)
    assert json.loads(sdk) == {"version": VERSION, "status": "consistent", "replay": True, "oneMinimal": True, "models": "realtime-only-violation"}
    checks.append(kind + " SDK import")

receipt = {"tool": "MoonTxnWitness", "version": VERSION, "passed": True, "archives": archives, "freshConsumerChecks": len(checks), "checks": checks, "sourceRebuilt": True, "portableRequires": "Node.js >=20 (tested with current installed Node)", "node": run([NODE, "--version"], ROOT).strip(), "nativeExecutableIncluded": False, "publiclyPublished": False}
(ROOT / "verification/package.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / "release-index.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / (NAME + "-release.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Packaged " + NAME + ": source + portable; " + str(len(checks)) + " fresh-consumer checks passed.")
for item in archives:
    print(item["file"] + "  " + str(item["bytes"]) + " bytes  " + item["sha256"])
