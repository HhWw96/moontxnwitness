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
from package_archive import sha256, write_archive


ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", VERSION), "Release version must be stable x.y.z"
NAME = "MoonTxnWitness-v" + VERSION
ARTIFACTS = ROOT / "artifacts"
NODE = os.environ.get("MTW_NODE", "node")
SUMMARY = json.loads((ROOT / "verification/summary.json").read_text(encoding="utf-8"))
assert SUMMARY["passed"] is True and SUMMARY["version"] == VERSION, "Run npm test before packaging"
assert (ROOT / "dist/core.mjs").is_file(), "Build the runtime before packaging"
MANIFEST = json.loads((ROOT / 'dist/build-manifest.json').read_text(encoding='utf-8'))
assert SUMMARY.get('buildManifest') == MANIFEST, 'Run all tests against this exact runtime before packaging'
tested_files = json.loads(subprocess.check_output([NODE, '--input-type=module', '-e',
    "import {verificationFingerprint} from './scripts/verification-fingerprint.mjs'; console.log(JSON.stringify(verificationFingerprint(process.cwd())));"],
    cwd=ROOT, text=True))
assert SUMMARY.get('testedFileSha256') == tested_files, 'Executable sources or wrappers changed after tests; rerun verification'
current_source = subprocess.check_output([NODE, '--input-type=module', '-e',
    "import {sourceFingerprint} from './scripts/build-fingerprint.mjs'; console.log(sourceFingerprint(process.cwd()));"],
    cwd=ROOT, text=True).strip()
assert current_source == MANIFEST['sourceSha256'], 'MoonBit source changed after the verified build'
for runtime, field in (('core.mjs', 'coreSha256'), ('capture-core.mjs', 'captureCoreSha256')):
    assert hashlib.sha256((ROOT / 'dist' / runtime).read_bytes()).hexdigest() == MANIFEST[field], 'Compiled runtime changed after build'
for runtime in ('moontxnwitness.mjs', 'sdk.mjs', 'evidence.mjs', 'demo.mjs', 'postgres-demo.mjs'):
    assert (ROOT / 'cmd' / runtime).read_bytes() == (ROOT / 'dist' / runtime).read_bytes(), 'Runtime wrapper changed after build: ' + runtime


def archive(files, path):
    return write_archive(ROOT, files, path, NAME,
                         (str(ROOT), ROOT.as_posix(), str(Path.home()), Path.home().as_posix()))


excluded_dirs = {".git", "_build", ".mooncakes", "node_modules", "artifacts", "dist", "__pycache__", ".venv-pg"}
excluded_names = {".local-toolchain.json", ".DS_Store"}
# Match the public source inventory, including uncommitted public additions.
# Ignored diagnostics and draft work must not enter a source or portable export.
public_names = set(filter(None, subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
    cwd=ROOT).decode('utf-8').split('\0')))
source = []
for name in sorted(public_names):
    relative = Path(name)
    item = ROOT / relative
    if not item.is_file() or any(part in excluded_dirs or part.startswith(('moontxnwitness-demo-', 'moontxnwitness-postgres-')) for part in relative.parts) or item.name in excluded_names:
        continue
    if item.suffix in {".log", ".pyc"} or relative.as_posix() == "verification/package.json":
        continue
    source.append(relative.as_posix())
portable = ["README.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY.md", "run-demo.cmd"]
for folder in ("dist", "docs", "examples", "verification", "integrations", "experiments"):
    for item in (ROOT / folder).rglob("*"):
        relative = item.relative_to(ROOT).as_posix()
        if item.is_file() and "__pycache__" not in item.parts and item.name != "package.json" and (folder == 'dist' or relative in public_names):
            portable.append(item.relative_to(ROOT).as_posix())

ARTIFACTS.mkdir(exist_ok=True)
archives = [archive(source, ARTIFACTS / (NAME + "-source.zip")), archive(portable, ARTIFACTS / (NAME + "-portable.zip"))]
current_sums = "".join(item["sha256"] + "  " + item["file"] + "\n" for item in archives)
(ARTIFACTS / (NAME + "-SHA256SUMS.txt")).write_text(current_sums, encoding="utf-8")
all_releases = [path for path in sorted(ARTIFACTS.glob("MoonTxnWitness-v*-*.zip")) if re.fullmatch(r"MoonTxnWitness-v[0-9]+\.[0-9]+\.[0-9]+-(source|portable)\.zip", path.name)]
(ARTIFACTS / "SHA256SUMS").write_text("".join(sha256(path) + "  " + path.name + "\n" for path in all_releases), encoding="utf-8")

# All work is created below the project. No existing directory is reset or removed.
consumer_parent = Path(os.environ.get('MTW_CONSUMER_WORK_ROOT', str(ARTIFACTS / 'consumer-work'))).resolve()
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
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 9):
        advanced = json.loads(run([NODE, "dist/moontxnwitness.mjs", "check", "examples/fractured-observation.json", "--profile", "balanced", "--format", "json", "--capsule", "advanced.capsule.json"], consumer, 1))
        assert advanced['schemaVersion'] == 2 and advanced['search']['status'] == 'exhausted'
        assert json.loads(run([NODE, "dist/moontxnwitness.mjs", "replay", "advanced.capsule.json"], consumer))['valid'] is True
        checks.append(kind + " balanced v2 exhaustive proof and capsule")
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 10):
        reduced = json.loads(run([NODE, "dist/moontxnwitness.mjs", "shrink", "examples/noisy-write-skew.json", "--profile", "balanced"], consumer))
        assert reduced['oneMinimal'] is True and len(reduced['reducedHistory']['transactions']) == 2 and reduced['report']['schemaVersion'] == 2
        checks.append(kind + " balanced reduction and v2 report")
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
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 0):
        assert demo['profile'] == 'balanced' and demo['reportSchemaVersion'] == 2
    assert all((consumer / demo["outputDirectory"] / name).is_file() for name in demo["files"])
    checks.append(kind + " one-command demo and artifacts")
    sdk = run([NODE, "--input-type=module", "-e", "import {analyze,version,shrink,compareModels,replayReport} from './dist/sdk.mjs'; import {readFileSync} from 'node:fs'; const h=readFileSync('examples/consistent.json','utf8'); const r=analyze(h); console.log(JSON.stringify({version:version(),status:r.status,replay:replayReport(h,r).valid,oneMinimal:shrink(readFileSync('examples/noisy-write-skew.json','utf8')).oneMinimal,models:compareModels(readFileSync('examples/strict-realtime.json','utf8')).classification}));"], consumer)
    assert json.loads(sdk) == {"version": VERSION, "status": "consistent", "replay": True, "oneMinimal": True, "models": "realtime-only-violation"}
    checks.append(kind + " SDK import")
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 1):
        captured = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'ingest', 'examples/capture-complete.json', '--history', 'captured-history.json'], consumer))
        assert captured['status'] == 'ready' and captured['coverage']['complete']
        assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'check', 'captured-history.json', '--profile', 'balanced', '--format', 'json'], consumer, 1))['status'] == 'violation'
        assert (consumer / 'integrations/python/moontxnwitness_capture/capture.py').is_file()
        checks.append(kind + ' captured trace ingestion and packaged Python adapter')
        if (ROOT / 'experiments/provenance/capture_profile.py').exists():
            profile = run([sys.executable, '-c', "import sys; sys.path.insert(0,'experiments/provenance'); from capture_profile import ColumnPointProfile; print(ColumnPointProfile.__name__)"], consumer)
            assert profile.strip() == 'ColumnPointProfile'
            assert (consumer / 'experiments/provenance/CAPTURE_PROFILE.md').is_file()
            checks.append(kind + ' experimental ordinary-table profile and documentation import without database access')
        if (ROOT / 'experiments/provenance/returning_profile.py').exists():
            profile = run([sys.executable, '-c', "import sys; sys.path.insert(0,'experiments/provenance'); from returning_profile import ReturningPointProfile; print(ReturningPointProfile.__name__)"], consumer)
            assert profile.strip() == 'ReturningPointProfile'
            checks.append(kind + ' experimental existing-RETURNING profile import without database access')
        if (ROOT / 'experiments/provenance/presence_profile.py').exists():
            profile = run([sys.executable, '-c', "import sys; sys.path.insert(0,'experiments/provenance'); from presence_profile import PresencePointProfile; print(PresencePointProfile.__name__)"], consumer)
            assert profile.strip() == 'PresencePointProfile'
            assert (consumer / 'experiments/provenance/PRESENCE_PROFILE.md').is_file()
            assert json.loads(run([NODE, '--input-type=module', '-e', "import {normalizePresenceCapture} from './dist/sdk.mjs'; console.log(JSON.stringify(normalizePresenceCapture('{}')));"], consumer))['status'] == 'invalid'
            checks.append(kind + ' experimental presence adapter import and independent SDK rejection without database access')
        if (ROOT / 'experiments/business/dislock/business.py').exists():
            source = run([sys.executable, '-c', "import sys; sys.path.insert(0,'experiments/business/dislock'); from business import verify_sources; print(verify_sources()['commit'])"], consumer)
            assert source.strip() == 'f9946f07159054433d9071c3805e41223cb47856'
            checks.append(kind + ' frozen MIT upstream business source integrity without executing its code')
        if (consumer / 'verification/v3/synthetic-dislock-source-closure-v1/trace.json').is_file():
            v3_checks = json.loads(run([NODE, '--input-type=module', '-e', """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {analyzeV3,normalizeCaptureV3,reduceV3,verifyV3,makeCapsuleV3,replayCapsuleV3} from './dist/sdk.mjs';
const read = path => readFileSync(path,'utf8');
const policy = {sqlProof:'dislock-f9946f0-sql-proof-1'};
const trace = read('verification/v3/synthetic-dislock-source-closure-v1/trace.json');
const report = analyzeV3(trace,policy);
assert.equal(report.status,'violation'); assert(verifyV3(trace,report).valid);
assert(replayCapsuleV3(makeCapsuleV3(trace,report)).valid);
const reduced = reduceV3(trace,{analysisOptions:policy,maxChecks:256});
assert.equal(reduced.oneMinimal,true); assert.equal(reduced.report.status,'violation');
assert.equal(analyzeV3(trace).status,'inconclusive');
assert.equal(analyzeV3(trace,{sqlProof:null}).status,'invalid');
const actual = read('verification/business/dislock/v3-db5f87c5620c4f8e955172340023482c/acquire-heartbeat-cleanup/capture.json');
assert.equal(analyzeV3(actual,policy).status,'consistent');
const list = read('verification/list-v3/postgres-2de835316d5f40d6b7e4bfeab4e4b8e4/duplicate-business-values-00/trace.json');
const lr = analyzeV3(list); assert.equal(lr.status,'consistent');
assert(verifyV3(list,lr).valid); assert(replayCapsuleV3(makeCapsuleV3(list,lr)).valid);
assert.equal(normalizeCaptureV3(list).coverage.complete,true);
console.log(JSON.stringify({passed:true,groups:4}));
"""], consumer))
            assert v3_checks == {'passed': True, 'groups': 4}
            checks.extend(kind + ' v3 ' + entry for entry in (
                'explicit source proof and capsule', 'source-closed synthetic reduction',
                'default and invalid-policy compatibility', 'real stored list and dislock replay'))
        if tuple(map(int, VERSION.split('.'))) >= (0, 1, 1):
            assert (consumer / 'verification/relation-v3/postgres-2026-10-21/database').is_dir(), 'Relation evidence must be packaged'
            assert (consumer / 'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json').is_file(), 'Execution-fault evidence must be packaged'
            model_checks = json.loads(run([NODE, '--input-type=module', '-e', """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {analyzeV3,reduceV3,verifyV3,makeCapsuleV3,replayCapsuleV3,inspectExecutionFailuresV3} from './dist/sdk.mjs';
const read = path => readFileSync(path,'utf8');
for (const [name,status] of [['empty-result','consistent'],['insert-phantom','violation']]) {
  const trace=read('verification/relation-v3/postgres-2026-10-21/database/'+name+'-01/trace.json');
  const report=analyzeV3(trace); assert.equal(report.status,status);
  assert(verifyV3(trace,report).valid); assert(replayCapsuleV3(makeCapsuleV3(trace,report)).valid);
  if(status==='violation') {
    const mini=reduceV3(trace,{maxChecks:256});assert.equal(mini.oneMinimal,true);
    assert.equal(mini.report.status,'violation');assert(verifyV3(mini.reducedCapture,mini.report).valid);
  }
}
const fault=read('verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json');
const diagnostic=inspectExecutionFailuresV3(fault);assert.equal(diagnostic.valid,true);
assert.equal(diagnostic.faults.length,1);assert.equal(diagnostic.faults[0].kind,'deadlock');
assert.equal(diagnostic.modelViolationClaim,false);assert.equal(diagnostic.certifiesFailureAbsence,false);
const report=analyzeV3(fault);assert.equal(report.status,'inconclusive');assert.equal(report.evidence,null);
assert(replayCapsuleV3(makeCapsuleV3(fault,report)).valid);
console.log(JSON.stringify({passed:true,groups:3}));
"""], consumer))
            assert model_checks == {'passed': True, 'groups': 3}
            diagnostic = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'failures-v3',
                'verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json'], consumer))
            assert diagnostic['valid'] and diagnostic['faults'][0]['kind'] == 'deadlock'
            checks.extend(kind + ' v3 ' + entry for entry in (
                'real relation consistent and capsule', 'real relation violation reduction and capsule',
                'real execution fault with explicit coverage gap', 'diagnostic CLI valid-input exit semantics'))
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 11):
        old_python = env.get('MTW_PYTHON')
        try:
            env['MTW_PYTHON'] = str(work / 'absent-python')
            skipped = json.loads(run([NODE, 'dist/postgres-demo.mjs'], consumer, 3))
            assert skipped['status'] == 'not-executed' and not skipped['passed'] and not skipped['actualDatabaseExecution']
            checks.append(kind + ' optional PostgreSQL missing prerequisite is not executed')
        finally:
            if old_python is None:
                env.pop('MTW_PYTHON', None)
            else:
                env['MTW_PYTHON'] = old_python
        for case in ('rr', 'serial', 'mini'):
            capsule = 'verification/releases/' + VERSION + '/postgres/' + case + '.capsule.json'
            assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay', capsule], consumer))['valid']
            checks.append(kind + ' actual PostgreSQL bundled ' + case + ' capsule replay')

receipt = {"tool": "MoonTxnWitness", "version": VERSION, "passed": True, "archives": archives, "freshConsumerChecks": len(checks), "checks": checks, "sourceRebuilt": True, "portableRequires": "Node.js >=20 (tested with current installed Node)", "node": run([NODE, "--version"], ROOT).strip(), "nativeExecutableIncluded": False, "publiclyPublished": False}
(ROOT / "verification/package.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / "release-index.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / (NAME + "-release.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Packaged " + NAME + ": source + portable; " + str(len(checks)) + " fresh-consumer checks passed.")
for item in archives:
    print(item["file"] + "  " + str(item["bytes"]) + " bytes  " + item["sha256"])
