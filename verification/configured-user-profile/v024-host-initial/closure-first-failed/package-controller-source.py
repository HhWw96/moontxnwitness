"""Build source/runtime ZIPs, then verify both from fresh extraction directories."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from package_archive import sha256, write_archive
from publication_privacy import private_home_paths
from distribution_manifest import select_distribution_files, assert_complete


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
for runtime in ('moontxnwitness.mjs', 'sdk.mjs', 'evidence.mjs', 'orm-profile.mjs', 'demo.mjs', 'postgres-demo.mjs'):
    assert (ROOT / 'cmd' / runtime).read_bytes() == (ROOT / 'dist' / runtime).read_bytes(), 'Runtime wrapper changed after build: ' + runtime


def archive(files, path):
    home_paths = private_home_paths(
        str(Path.home()), github_actions=os.environ.get('GITHUB_ACTIONS') == 'true',
        runner_environment=os.environ.get('RUNNER_ENVIRONMENT', ''))
    return write_archive(ROOT, files, path, NAME,
                         {str(ROOT), ROOT.as_posix(), *home_paths})


# Keep the existing source/runtime fingerprint and every consumer check intact.
# Only the exported file inventory changes; historical evidence stays in Git.
public_names = set(filter(None, subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
    cwd=ROOT).decode('utf-8').split('\0')))
selection = select_distribution_files(ROOT, public_names, tested_files, VERSION)
assert_complete(selection)
source = selection['source']
portable = selection['portable']

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
        # A clean source consumer links multiple test packages. Bound concurrent
        # compiler processes without changing test cases or compiler optimization.
        core_tests = run([NODE, "scripts/moon.mjs", "test", "--target", "js", "--deny-warn", "--jobs", "1"], consumer)
        test_count = SUMMARY["coreTestsPerTarget"]
        assert f"Total tests: {test_count}, passed: {test_count}, failed: 0." in core_tests
        checks.append(f"source fresh JS core tests: {test_count} passed")
    assert run([NODE, "dist/moontxnwitness.mjs", "--version"], consumer).strip() == VERSION
    checks.append(kind + " version")
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 4):
        demonstration = json.loads(run([NODE, 'examples/list-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert demonstration['passed'] and demonstration['version'] == VERSION
        assert demonstration['originalTransactions'] == 3 and demonstration['reducedTransactions'] == 2
        assert demonstration['oneMinimal'] and demonstration['replayValid']
        case = work / demonstration['outputDirectory'] / 'case.capsule.json'
        assert case.resolve().is_relative_to(work.resolve())
        for item in demonstration['files']:
            path = (case.parent / item['file']).resolve()
            assert path.is_relative_to(case.parent.resolve())
            assert sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-v3', str(case)], consumer))['valid']
        checks.append(kind + ' append-list SDK and source-closed example round trip')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 5):
        relation_demo = json.loads(run([NODE, 'examples/relation-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert relation_demo['passed'] and relation_demo['version'] == VERSION
        assert relation_demo['originalTransactions'] == 4 and relation_demo['reducedTransactions'] == 3
        assert relation_demo['oneMinimal'] and relation_demo['replayValid']
        case = work / relation_demo['outputDirectory'] / 'case.capsule.json'
        assert case.resolve().is_relative_to(work.resolve())
        for item in relation_demo['files']:
            path = (case.parent / item['file']).resolve()
            assert path.is_relative_to(case.parent.resolve())
            assert sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-v3', str(case)], consumer))['valid']
        checks.append(kind + ' relation-set SDK and source-closed example round trip')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 6):
        cycle_demo = json.loads(run([NODE, 'examples/register-cycle-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert cycle_demo['passed'] and cycle_demo['version'] == VERSION
        assert cycle_demo['sourceReportStatus'] == 'violation' and cycle_demo['selectedCycleSubtype'] == 'G2-item'
        assert cycle_demo['explanationVerified'] and cycle_demo['originalCapsuleReplayed']
        assert not cycle_demo['acceptsIsolationModels'] and not cycle_demo['searchesOtherCategories']
        directory = (work / cycle_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        for item in cycle_demo['files']:
            path = (directory / item['file']).resolve()
            assert path.is_relative_to(directory)
            assert sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-v3', str(directory / 'original-v3.capsule.json')], consumer))
        assert replay['valid']
        derived = json.loads(run([NODE, '--input-type=module', '-e',
            "import{readFileSync}from'node:fs';import{verifyRegisterCycleExplanationV3}from'./dist/sdk.mjs';"
            "const c=JSON.parse(readFileSync(process.argv[1],'utf8'));"
            "const e=JSON.parse(readFileSync(process.argv[2],'utf8'));"
            "console.log(JSON.stringify(verifyRegisterCycleExplanationV3(c.traceText,c.reportText,e)));",
            str(directory / 'original-v3.capsule.json'), str(directory / 'cycle-explanation.json')], consumer))
        assert derived['valid'] and derived['subtype'] == 'G2-item'
        checks.append(kind + ' verified register-cycle SDK and original-capsule derived-explanation round trip')

    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 7):
        execution_demo = json.loads(run([NODE, 'examples/execution-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert execution_demo['passed'] and execution_demo['runtimeVersion'] == VERSION
        assert execution_demo['actualDatabaseExecution'] is False
        directory = (work / execution_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        comparison = json.loads((directory / 'receipt.json').read_text(encoding='utf8'))
        assert comparison['passed'] and comparison['runtimeVersion'] == VERSION
        assert comparison['actualDatabaseExecution'] is False and comparison['databaseAuthenticityVerified'] is False
        assert comparison['fixesEverySchedule'] is False and comparison['modelViolationClaim'] is False
        assert comparison['certifiesFailureAbsence'] is False and comparison['fullApplicationIntegration'] is False
        assert comparison['observedDifference']['beforeFaults'] == 1 and comparison['observedDifference']['afterFaults'] == 0
        assert len(comparison['cases']) == 2
        for item in comparison['cases']:
            assert item['executionDiagnosticRecomputed'] and item['originalModelCapsuleReplayed']
            assert item['modelStatus'] == 'inconclusive' and not item['modelCoverage']['complete']
            assert not item['captureCoverage']['complete']
            for artifact in item['files']:
                path = (directory / artifact['file']).resolve()
                assert path.is_relative_to(directory)
                assert sha256(path) == artifact['sha256'] and path.stat().st_size == artifact['bytes']
            label = item['label']
            execution_replay = json.loads(run([NODE, '--input-type=module', '-e',
                "import{readFileSync}from'node:fs';import{replayExecutionCapsuleV3}from'./dist/sdk.mjs';"
                "console.log(JSON.stringify(replayExecutionCapsuleV3(readFileSync(process.argv[1],'utf8'))));",
                str(directory / (label + '.execution-capsule.json'))], consumer))
            assert execution_replay['valid'] and execution_replay['scope']['modelViolationClaim'] is False
            assert not execution_replay['diagnostic']['captureCoverage']['complete']
            model_replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-v3', str(directory / (label + '.model-capsule.json'))], consumer))
            assert model_replay['valid']
        assert comparison['cases'][0]['observedSqlstates'] == ['40P01']
        assert comparison['cases'][0]['observedFaultKinds'] == ['deadlock']
        checks.append(kind + ' execution diagnostic capsule and recorded-MLflow offline comparison round trip')

    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 8):
        previous_execution = json.loads(run([NODE, '--input-type=module', '-e',
            "import assert from'node:assert/strict';import{readFileSync}from'node:fs';import{createHash}from'node:crypto';"
            "import{replayExecutionCapsuleV3,makeExecutionCapsuleV3,version}from'./dist/sdk.mjs';"
            "const dir='fixtures/execution-v3/compat/v017/',o=JSON.parse(readFileSync(dir+'origin.json','utf8'));"
            "const sha=s=>createHash('sha256').update(s).digest('hex'),cases=[];"
            "assert.equal(o.obtainedFromGitHubPackage,false);assert.equal(o.producerEngineVersion,'0.1.7');"
            "for(const row of o.cases){const text=readFileSync(dir+row.file,'utf8'),c=JSON.parse(text);"
            "assert.equal(sha(text),row.sha256);assert.equal(Buffer.byteLength(text,'utf8'),row.bytes);"
            "assert.equal(c.engineVersion,'0.1.7');const r=replayExecutionCapsuleV3(text);"
            "assert.equal(r.valid,true);assert.equal(r.engineVersion,'0.1.7');assert.equal(r.traceSha256,c.traceSha256);"
            "assert.equal(JSON.stringify(r.diagnostic),c.diagnosticText);assert.equal(r.scope.modelViolationClaim,false);"
            "const n=JSON.parse(makeExecutionCapsuleV3(c.traceText));assert.equal(n.engineVersion,version());"
            "assert.equal(n.traceText,c.traceText);assert.equal(n.diagnosticText,c.diagnosticText);"
            "cases.push({id:row.id,valid:r.valid,engineVersion:r.engineVersion,capsuleSha256:sha(text)});}"
            "assert.equal(cases.length,2);console.log(JSON.stringify({passed:true,runtimeVersion:version(),producerEngineVersion:'0.1.7',cases}));"], consumer))
        assert previous_execution['passed'] and previous_execution['runtimeVersion'] == VERSION
        assert previous_execution['producerEngineVersion'] == '0.1.7' and len(previous_execution['cases']) == 2
        assert all(item['valid'] and item['engineVersion'] == '0.1.7' for item in previous_execution['cases'])
        checks.append(kind + ' actual-v017 execution-capsule compatibility')

    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 3):
        isolated = work / (kind + '-orm-only')
        copied = isolated / 'moontxnwitness_capture'
        copied.mkdir(parents=True, exist_ok=False)
        for name in ('__init__.py', 'capture.py', 'capture_v3.py', 'journal_v3.py',
                     'orm.py', '_orm_policy.py', '_orm_async.py', '_orm_raw_async.py', '_orm_source_sink.py'):
            shutil.copyfile(consumer / 'integrations/python/moontxnwitness_capture' / name, copied / name)
        imported = run([sys.executable, '-I', '-S', '-B', '-c',
            'import sys;sys.path.insert(0,sys.argv[1]);'
            'from moontxnwitness_capture.orm import UserScope,SQLContext,StructuredSQLCache;'
            's=UserScope("mtw_orm_v3_consumer","observed_user",("00000000-0000-4000-8000-000000000001",));'
            'c=StructuredSQLCache(context=SQLContext(registry_epoch=1));'
            'assert c.retained=={"entries":0,"bytes":0};'
            'assert "sqlalchemy" not in sys.modules and "psycopg" not in sys.modules;'
            'print("orm-standalone-ok")', str(isolated)], isolated)
        assert imported.strip() == 'orm-standalone-ok'
        checks.append(kind + ' standalone ORM package construction without optional dependencies or experiments')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 2):
        # A copied package imports and constructs without site packages, the
        # optional driver or an experiments directory on the Python import path.
        package_only = work / (kind + '-presence-only')
        installed_package = package_only / 'moontxnwitness_capture'
        installed_package.mkdir(parents=True, exist_ok=False)
        for name in ('__init__.py', 'capture.py', '_provenance.py', '_column_profile.py',
                     '_initialization_guard.py', '_source_inventory.py', 'presence.py'):
            shutil.copyfile(consumer / 'integrations/python/moontxnwitness_capture' / name,
                            installed_package / name)
        installed = json.loads(run([sys.executable, '-I', '-S', '-B', '-c',
            'import json,sys;sys.path.insert(0,sys.argv[1]);'
            'from moontxnwitness_capture.presence import PresenceCapture,PresencePointProfile,implementation_bindings;'
            'c=PresenceCapture(PresencePointProfile("mtw_provenance_consumer","items"),keys=("a","missing"));'
            'assert not c._initialized;assert "psycopg" not in sys.modules;'
            'print(json.dumps(implementation_bindings()))',
            str(package_only)], package_only))
        assert len(installed) == 7
        for path, observed in installed.items():
            assert observed['sha256'] == sha256(package_only / path)
        checks.append(kind + ' standalone presence package import without optional driver or experiments')
        declaration = json.loads((consumer / ('verification/releases/' + VERSION + '/acceptance.json')).read_text(encoding='utf8'))
        database = json.loads((consumer / ('verification/releases/' + VERSION) / declaration['databaseEvidence']).read_text(encoding='utf8'))
        presence_run = 'verification/' + database['receipts']['presence']['path']
        presence_receipt = json.loads((consumer / presence_run / 'presence-receipt.json').read_text(encoding='utf8'))
        ready = [row for row in presence_receipt['scenarios'] if row['expectedStatus'] == 'ready']
        assert len(ready) == 3
        for scenario in ready:
            for bound in scenario['artifactBindings'].values():
                path = (consumer / presence_run / bound['path']).resolve()
                assert path.is_relative_to((consumer / presence_run).resolve())
                assert sha256(path) == bound['sha256'] and path.stat().st_size == bound['bytes']
            normalized = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'ingest-presence', presence_run + '/' + scenario['trace']], consumer))
            original_history = json.loads((consumer / presence_run / scenario['artifactBindings']['history']['path']).read_text(encoding='utf8'))
            assert normalized['status'] == 'ready' and normalized['history'] == original_history
            capsule = presence_run + '/' + scenario['name'] + '.capsule.json'
            assert json.loads(json.loads((consumer / capsule).read_text(encoding='utf8'))['historyText']) == original_history
            assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay', capsule], consumer))['valid']
        checks.append(kind + ' actual ordinary-table CRUD, negative-read and lock-wait capsules')
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
        orm_fixture = 'verification/experimental-candidates/orm-source2-r3-2026-10-21/fixtures/'
        if (consumer / orm_fixture / 'diagnostic-trace.json').is_file():
            diagnostic = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'inspect-orm-source-v3',
                orm_fixture + 'diagnostic-trace.json', orm_fixture + 'source-observations.jsonl'], consumer))
            assert diagnostic['controlProfileComplete'] and len(diagnostic['provenFacts']) == 21
            assert diagnostic['analysisCoverageAccepted'] is False and diagnostic['history'] is None
            assert all(diagnostic[field] == [] for field in ('verifiedStatements', 'verifiedFacts', 'verifiedProfiles'))
            checks.append(kind + ' experimental ORM source CLI with complete global refusal')
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
