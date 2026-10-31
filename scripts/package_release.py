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
from evidence_json import load_receipt
from pathlib import Path
from package_archive import sha256, write_archive
from publication_privacy import private_home_paths
from distribution_manifest import select_distribution_files, assert_complete, relation034_available, predicate035_available


ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", VERSION), "Release version must be stable x.y.z"
RELATION034 = relation034_available(ROOT, VERSION)
PREDICATE035 = predicate035_available(ROOT, VERSION)
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
for runtime in ('moontxnwitness.mjs', 'sdk.mjs', 'evidence.mjs', 'orm-profile.mjs', 'model-profile.mjs', 'classification.mjs', 'classification-models.mjs', 'diagnosis.mjs', 'v4.mjs', 'demo.mjs', 'postgres-demo.mjs'):
    assert (ROOT / 'cmd' / runtime).read_bytes() == (ROOT / 'dist' / runtime).read_bytes(), 'Runtime wrapper changed after build: ' + runtime

if RELATION034:
    for runtime in ('relation-v4.mjs', 'relation-reduction-v4.mjs'):
        assert (ROOT/'cmd'/runtime).read_bytes() == (ROOT/'dist'/runtime).read_bytes(), 'Relation runtime wrapper changed after build: ' + runtime


assert (ROOT/'cmd/legacy-v024.mjs').read_bytes() == (ROOT/'dist/legacy-v024.mjs').read_bytes(), 'Frozen ORM dispatch changed after build'
subprocess.check_call([NODE,'--input-type=module','-e',
    "import{verifyFrozenLegacyV024}from'./scripts/legacy-v024-runtime.mjs';verifyFrozenLegacyV024(process.cwd());verifyFrozenLegacyV024(process.cwd(),process.cwd()+'/dist/legacy/v024');"],cwd=ROOT)

for helper in ('legacy-v026.mjs', 'legacy-v026-runtime.mjs', 'legacy-v026-worker.mjs', 'legacy-v026-binding.mjs'):
    assert (ROOT / 'cmd' / helper).read_bytes() == (ROOT / 'dist' / helper).read_bytes(), 'Fixed public26 helper changed after build: ' + helper
subprocess.check_call([NODE, '--input-type=module', '-e',
    "import{verifyPublicV026Runtime as source}from'./cmd/legacy-v026-runtime.mjs';import{verifyPublicV026Runtime as installed}from'./dist/legacy-v026-runtime.mjs';const a=source(),b=installed();if(a.manifestSha256!==b.manifestSha256||a.workerSha256!==b.workerSha256)throw Error('Copied public26 runtime differs');"], cwd=ROOT)

for helper in ('legacy-v027.mjs', 'legacy-v027-runtime.mjs', 'legacy-v027-worker.mjs', 'legacy-v027-binding.mjs'):
    assert (ROOT / 'cmd' / helper).read_bytes() == (ROOT / 'dist' / helper).read_bytes(), 'Fixed public27 helper changed after build: ' + helper
subprocess.check_call([NODE, '--input-type=module', '-e',
    "import{verifyPublicV027Runtime as source}from'./cmd/legacy-v027-runtime.mjs';import{verifyPublicV027Runtime as installed}from'./dist/legacy-v027-runtime.mjs';const a=source(),b=installed();if(a.manifestSha256!==b.manifestSha256||a.workerSha256!==b.workerSha256)throw Error('Copied public27 runtime differs');"], cwd=ROOT)

for helper in ('legacy-v028.mjs', 'legacy-v028-runtime.mjs', 'legacy-v028-worker.mjs', 'legacy-v028-policy.mjs', 'legacy-v028-dispatch.mjs','legacy-v030.mjs','legacy-v031.mjs','legacy-v031-binding.mjs', 'legacy-v028-binding.mjs'):
    assert (ROOT / 'cmd' / helper).read_bytes() == (ROOT / 'dist' / helper).read_bytes(), 'Fixed public28 helper changed after build: ' + helper
subprocess.check_call([NODE, '--input-type=module', '-e',
    "import{verifyPublicV028Runtime as source}from'./cmd/legacy-v028-runtime.mjs';import{verifyPublicV028Runtime as installed}from'./dist/legacy-v028-runtime.mjs';const a=source(),b=installed();if(a.manifestSha256!==b.manifestSha256)throw Error('Copied public28 runtime differs');"], cwd=ROOT)

if tuple(map(int, VERSION.split('.'))) >= (0, 3, 3):
    for helper in ('legacy-v032.mjs', 'legacy-v032-binding.mjs', 'compact-runtime.mjs'):
        assert (ROOT / 'cmd' / helper).read_bytes() == (ROOT / 'dist' / helper).read_bytes(), 'Fixed public32 helper changed after build: ' + helper

if tuple(map(int, VERSION.split('.'))) >= (0, 3, 4):
    for helper in ('legacy-v033.mjs', 'legacy-v033-binding.mjs'):
        assert (ROOT / 'cmd' / helper).read_bytes() == (ROOT / 'dist' / helper).read_bytes(), 'Fixed public33 helper changed after build: ' + helper


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
if (ROOT / 'scripts/frozen-inputs.json').is_file():
    env.setdefault('MTW_INPUT_CACHE', str(ROOT / 'artifacts/input-cache'))
home = env.get("MTW_TOOLCHAIN_HOME")
if home:
    env["MOON_HOME"] = home

checks = []
relation034_consumers = {}
predicate035_consumers = {}


def run(args, cwd, expected=0, timeout=180):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
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
        run([sys.executable, "scripts/input_cache.py", "prepare", "--scope", "tests"], consumer)
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
    if tuple(map(int, VERSION.split('.'))) >= (0, 3, 2):
        public031 = json.loads(run([NODE, 'scripts/public031-compatibility-test.mjs',
            '--runtime', str(consumer / 'dist'), '--producer-runtime', str(consumer / 'dist/legacy/v031'),
            '--output-root', str(work / ('public031-' + kind))], consumer))
        assert public031['passed'] and public031['publicVersion'] == '0.3.1' and public031['currentVersion'] == VERSION
        assert public031['usesPublishedRuntimeOnly'] and not public031['historicalSourceSnapshotCreated']
        checks.append(kind + ' public031 original SDK/capsules and corrupted runtime refusal')
        typed_v4 = json.loads(run([NODE, 'scripts/v4-sdk-test.mjs'], consumer))
        assert typed_v4['passed'] and typed_v4['failed'] == 0 and typed_v4['legacyWorkers'] == 0
        checks.append(kind + ' v4 typed analysis, explicit reduction and independently budgeted replay')
        direct_category = json.loads(run([NODE, 'scripts/register-direct-v4-audit.mjs',
            '--runtime', str(consumer / 'dist'), '--output-root', str(work / ('direct-category-' + kind))], consumer))
        assert direct_category['passed'] is True and direct_category['checks'] >= 6 and direct_category['failed'] == 0
        checks.append(kind + ' independent direct-register category SDK reference and witness audit')
    if tuple(map(int, VERSION.split('.'))) >= (0, 3, 3):
        parts = []
        for group in ('core', 'capture', 'models', 'classification', 'profiles', 'v4', 'integrity'):
            destination = work / ('public032-' + kind) / group
            result = json.loads(run([NODE, 'scripts/public032-compatibility-test.mjs', '--group', group,
                                    '--runtime', str(consumer / 'dist'), '--output-root', str(destination)], consumer))
            assert result['passed'] is True and result['currentVersion'] == VERSION
            parts.append(str(destination / 'public032-compatibility-validation.json'))
            checks.append(kind + ' public032 original fixed compatibility group ' + group)
        public032 = json.loads(run([NODE, 'scripts/public032-compatibility-groups.mjs', *parts], consumer))
        assert public032['passed'] is True and public032['checks'] == 47 and public032['groups'] == 7
        assert public032['currentVersion'] == VERSION
        checks.append(kind + ' public032 all 47 original checks and 15 fixed method families')
        for script, label in (
                ('v033-sdk-test.mjs', 'source anomaly and G-single SDK with duplicate-key CLI guards'),
                ('lost-update-sdk-test.mjs', 'source-bound register lost-update and capsule replay'),
                ('list-effective-sdk-test.mjs', 'effective multi-append list classification and source replay'),
                ('v033-independent-anomalies-test.mjs', 'independent source-anomaly and effective-list counterexamples'),
                ('../examples/v4-anomalies-roundtrip.mjs', 'runnable G-single and lost-update example')):
            result = json.loads(run([NODE, 'scripts/' + script], consumer))
            assert result['passed'] is True and result['checks'] > 0
            checks.append(kind + ' ' + label)
    if tuple(map(int, VERSION.split('.'))) >= (0, 3, 4):
        parts = []
        for group in ('core', 'capture', 'models', 'classification', 'profiles', 'v4', 'integrity'):
            destination = work / ('public033-' + kind) / group
            result = json.loads(run([NODE, 'scripts/public033-compatibility-test.mjs', '--group', group,
                                    '--runtime', str(consumer / 'dist'), '--output-root', str(destination)], consumer))
            assert result['passed'] is True and result['currentVersion'] == VERSION
            parts.append(str(destination / 'public033-compatibility-validation.json'))
            checks.append(kind + ' public033 original fixed compatibility group ' + group)
        public033 = json.loads(run([NODE, 'scripts/public033-compatibility-groups.mjs', *parts], consumer))
        assert public033['passed'] is True and public033['checks'] == 47 and public033['groups'] == 7
        assert public033['currentVersion'] == VERSION
        checks.append(kind + ' public033 all 47 original checks and 15 fixed method families')
    if RELATION034:
        capability = {'sourceAuditPerformed': kind == 'source', 'runtimeOnlyPortableChecks': kind == 'portable',
                      'newIndependentReviewPerformed': False, 'actualDatabaseExecution': False, 'results': {}}
        if kind == 'source':
            for script, label in (
                    ('v034-source-rules-sdk-test.mjs', 'relation/source rules complete-source SDK and CLI audit'),
                    ('relation-category-reduction-sdk-test.mjs', 'relation category reduction complete-source SDK and CLI audit'),
                    ('v034-maintenance-bindings-test.mjs', 'current relation build-source binding guard tests'),
                    ('v034-public-boundary-independent-test.mjs', '84 maintained relation/source public-boundary semantic checks')):
                result = json.loads(run([NODE, 'scripts/' + script], consumer))
                assert result['passed'] is True and result['checks'] > 0
                if script == 'v034-public-boundary-independent-test.mjs':
                    assert result['executed'] is True and result['checks'] == 84 and result['failed'] == 0
                capability['results'][script] = {'passed': True, 'checks': result['checks']}
                checks.append(kind + ' ' + label)
        else:
            result = json.loads(run([NODE, 'scripts/v034-portable-runtime-test.mjs'], consumer))
            assert result['passed'] is True and result['checks'] >= 16 and result['failed'] == 0
            assert result['requiresSourceTree'] is False and result['requiresCommandSource'] is False
            assert result['sourceAuditPerformed'] is False and result['semantic84AuditClaimed'] is False
            assert result['version'] == VERSION
            capability['results']['runtimeProbe'] = {'passed': True, 'checks': result['checks'], 'sourceAuditPerformed': False}
            checks.append(kind + ' runtime-only relation/source SDK CLI and exact capsule replay without source audit')
        example = json.loads(run([NODE, 'examples/source-rules-v4-roundtrip.mjs'], consumer))
        assert [row['name'] for row in example] == ['relation', 'capture', 'internal']
        assert [row['status'] for row in example] == ['checked-compatible', 'refuted', 'refuted']
        assert all(row['replayValid'] is True and row['acceptsIsolationModels'] is False for row in example)
        capability['results']['sourceRulesExample'] = {'passed': True, 'cases': len(example)}
        checks.append(kind + ' runnable relation and captured-source example with exact capsule replay')
        example = json.loads(run([NODE, 'examples/relation-category-reduction.mjs'], consumer))
        assert example['category'] == 'G2-item' and example['oneMinimal'] is True and example['replay']['valid'] is True
        assert example['retainedTransactions'] == ['A', 'B'] and example['removedTransactions'] == ['noise']
        capability['results']['categoryReductionExample'] = {'passed': True, 'retainedTransactions': example['retainedTransactions']}
        checks.append(kind + ' runnable category-preserving relation reduction and explicit-option replay')
        relation034_consumers[kind] = capability
    if PREDICATE035:
        capability = {'sourceAuditPerformed': kind == 'source', 'runtimeOnlyPortableChecks': kind == 'portable',
                      'newIndependentReviewPerformed': False, 'actualDatabaseExecution': False,
                      'formalPerformanceMeasurement': False, 'results': {}}
        if kind == 'source':
            result = json.loads(run([NODE, 'scripts/relation-predicate-sdk-test.mjs'], consumer))
            assert result['passed'] is True and result['checks'] == 40 and result['failed'] == 0
            capability['results']['completeSourceSdk'] = result
            checks.append(kind + ' predicate all 40 complete-source SDK CLI and caller-budget replay checks')
            result = json.loads(run([NODE, 'scripts/v035-predicate-maintenance-test.mjs'], consumer))
            assert result['passed'] is True and result['checks'] == 513 and result['failed'] == 0
            assert result['semanticAssertions'] == 506 and result['currentBuildGuards'] == 7
            assert result['newIndependentReviewPerformed'] is False and result['sourceUnchanged'] is True
            capability['results']['maintainedPredicateRegression'] = result
            checks.append(kind + ' predicate 506 preserved semantic assertions and seven current-build integrity guards')
        else:
            result = json.loads(run([NODE, 'scripts/v035-portable-predicate-test.mjs'], consumer))
            assert result['passed'] is True and result['checks'] == 12 and result['failed'] == 0
            assert result['requiresSourceTree'] is False and result['requiresCommandSource'] is False
            assert result['sourceAuditPerformed'] is False and result['newIndependentReviewPerformed'] is False
            assert result['version'] == VERSION
            capability['results']['runtimeProbe'] = result
            checks.append(kind + ' predicate runtime-only SDK CLI and exact scoped capsule replay')
        example = json.loads(run([NODE, 'examples/relation-predicate-categories.mjs'], consumer))
        assert example == {'passed': True, 'predicate': 'refuted', 'item': 'checked-compatible',
                           'replayValid': True, 'acceptsIsolationModels': False}
        capability['results']['predicateExample'] = example
        checks.append(kind + ' runnable predicate versus item example and independent-option capsule replay')
        predicate035_consumers[kind] = capability
    public024 = json.loads(run([NODE,'scripts/compat-v024-test.mjs',str(consumer/'dist'),str(consumer/'fixtures/compat-v024'),str(work/('public024-'+kind))],consumer))
    assert public024['passed'] and public024['currentRuntimeVersion'] == VERSION and public024['checks'] == 107
    checks.append(kind + ' actual public24 fifteen-family SDK/CLI and synchronous lazy ORM replay')
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

    if (consumer / 'dist/orm-profile.mjs').is_file():
        profile_demo = json.loads(run([NODE, 'examples/orm-profile-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert profile_demo['passed'] and profile_demo['version'] == VERSION
        assert profile_demo['actualDatabaseExecution'] is False and profile_demo['syntheticAnomalyIsActualDatabaseExecution'] is False
        assert profile_demo['originalPacketsFromRetainedActualDatabaseRuns'] == 2
        assert profile_demo['syntheticOriginalTransactions'] == 4 and profile_demo['syntheticReducedTransactions'] == 3
        assert profile_demo['sourceClosureComplete'] and profile_demo['oneMinimal'] and profile_demo['originalDiagnosticsRemainPartial']
        assert profile_demo['semanticCandidateChecks'] <= profile_demo['maxSemanticCandidateChecks'] == 256
        assert profile_demo['candidateAttempts'] == profile_demo['semanticCandidateChecks'] + profile_demo['cachedCandidateLookups']
        assert profile_demo['verificationPasses']['finalCandidateAnalyses'] == profile_demo['verificationPasses']['finalReportReplays'] == 1
        directory = (work / profile_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        for item in profile_demo['files']:
            path = (directory / item['file']).resolve()
            assert path.is_relative_to(directory)
            assert sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-orm-profile-v3', str(directory / 'synthetic-closed.capsule.json')], consumer))
        assert replay['valid'] and replay['report']['result']['reduction']['sourceClosure']['complete']
        checks.append(kind + ' configured ORM explicit-profile source binding, closed reduction and capsule replay')

    if tuple(map(int, VERSION.split('.'))) >= (0, 3, 0):
        public28_output = work / ('public028-' + kind)
        run([NODE, 'scripts/compat-v028-test.mjs', str(consumer / 'dist'), str(consumer / 'fixtures/compat-v028'), str(public28_output)], consumer, timeout=900)
        public28 = json.loads((public28_output / 'receipt.json').read_text(encoding='utf8'))
        assert public28['passed'] and public28['currentRuntimeVersion'] == VERSION
        assert public28['producerCases'] == 156 and public28['variants'] == 3 and public28['cliCases'] == 24
        assert public28['expectedRegenerated'] is False and public28['originalReportsAndCapsulesRewritten'] is False
        checks.append(kind + ' genuine public028 three-context 156 original cases and 24 CLI replays')
        http_demo = json.loads(run([NODE, 'examples/mlflow-http-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert http_demo['passed'] and http_demo['runtimeVersion'] == VERSION
        assert http_demo['retainedActualDatabaseObservations'] is True and http_demo['actualDatabaseExecution'] is False
        assert http_demo['sameCaseSha256'] == '9fddccaffd9d300ab23c1cd5b1bdd1d5f6075a75eabdca13a8a2ec36f127d69d'
        assert http_demo['caseKeys'] == 623 and http_demo['oneMinimal'] is False
        assert http_demo['coverageRemainsIncomplete'] is True
        assert http_demo['observedDifference']['beforeFaults'] == 1 and http_demo['observedDifference']['afterFaults'] == 0
        checks.append(kind + ' native HTTP same623 real observations, deadlock diagnosis and exact offline replay')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 8):
        public27_output = work / ('public027-' + kind)
        public27 = json.loads(run([NODE, 'scripts/compat-v027-test.mjs', str(consumer / 'dist'), str(consumer / 'fixtures/compat-v027'), str(public27_output)], consumer, timeout=600))
        assert public27['passed'] and public27['families'] == 46 and public27['expectedRegenerated'] is False
        checks.append(kind + ' exact genuine public027 full46 compatibility and configured model-profile replay')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 7):
        assert (consumer / 'dist/model-profile.mjs').is_file(), 'Required model-profile runtime missing'
        assert (consumer / 'examples/model-profile-roundtrip.mjs').is_file(), 'Required model-profile example missing'

    if (consumer / 'dist/model-profile.mjs').is_file():
        configured_model_demo = json.loads(run([NODE, 'examples/model-profile-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert configured_model_demo['passed'] and configured_model_demo['version'] == VERSION
        assert configured_model_demo['actualDatabaseExecution'] is False and configured_model_demo['cases'] == 4
        assert configured_model_demo['originalDiagnosticsRemainPartial'] and configured_model_demo['fullOriginalSourcesRetained']
        assert configured_model_demo['sourceClosedReductionClaimed'] is False
        directory = (work / configured_model_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        for item in configured_model_demo['files']:
            path = (directory / item['file']).resolve()
            assert path.is_relative_to(directory)
            assert sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-model-profile-v3', str(directory / 'list-write-skew.capsule.json')], consumer))
        assert replay['valid'] and replay['status'] == 'violation' and replay['analysisCoverageAccepted']
        checks.append(kind + ' configured list/relation original-source model projection and complete capsule replay')

    if (consumer / 'dist/diagnosis.mjs').is_file():
        diagnostic = json.loads(run([NODE, '--input-type=module', '-e', "import assert from 'node:assert/strict'; import {readFileSync} from 'node:fs'; import {diagnoseV3,verifyDiagnosisV3} from './dist/sdk.mjs'; const source=readFileSync('fixtures/diagnosis-v3/register-0.json','utf8'); const report=diagnoseV3(source); assert.equal(report.analysis.status,'inconclusive'); assert(report.findings.some(f=>f.rule==='INT')); assert.equal(report.models.result.models['adya-pl-3-v1'].status,'inconclusive'); assert.equal(verifyDiagnosisV3(source,report).valid,true); console.log(JSON.stringify({passed:true,status:report.status,diagnosticOnly:report.scope.diagnosticOnly}));"], consumer))
        assert diagnostic == {'passed': True, 'status': 'findings', 'diagnosticOnly': True}
        checks.append(kind + ' combined diagnosis preserves original unknown analysis and verifies direct INT evidence')

    if (consumer / 'dist/classification-models.mjs').is_file():
        model_demo = json.loads(run([NODE, 'examples/classification-models-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert model_demo['passed'] and model_demo['version'] == VERSION
        assert model_demo['syntheticInputs'] and model_demo['actualDatabaseExecution'] is False
        assert model_demo['relationModelClassificationSupported'] is False and model_demo['modelPreservingReductionSupported'] is False
        assert model_demo['generalizedSI'] == 'checked-compatible' and model_demo['serial'] == 'refuted'
        assert model_demo['strictWithoutIntervals'] == 'inconclusive' and model_demo['strictBoundSynthetic'] == 'checked-compatible'
        directory = (work / model_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        for item in model_demo['files']:
            path = (directory / item['file']).resolve()
            assert path.is_relative_to(directory) and sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-models-classification-v3', str(directory / 'bound-synthetic.capsule.json')], consumer))
        assert replay['valid'] and replay['report']['result']['models']['strict-pl-ss-v1']['status'] == 'checked-compatible'
        checks.append(kind + ' explicit model definitions, raw sidecar bindings, applicability gaps and exact model capsule replay')

    if (consumer / 'dist/classification.mjs').is_file():
        classification_demo = json.loads(run([NODE, 'examples/classification-roundtrip.mjs', '--out-root', str(work)], consumer))
        assert classification_demo['passed'] and classification_demo['version'] == VERSION
        assert classification_demo['syntheticInputs'] and classification_demo['actualDatabaseExecution'] is False
        assert classification_demo['formalPerformanceMeasured'] is False
        assert classification_demo['originalTransactions'] == 4 and classification_demo['reducedTransactions'] == 3
        assert classification_demo['preservedCategory'] == 'G2-item' and classification_demo['sourceClosureComplete'] and classification_demo['oneMinimal']
        assert classification_demo['fixedCandidateChecks'] <= classification_demo['maxCandidateChecks'] == 256
        directory = (work / classification_demo['outputDirectory']).resolve()
        assert directory.is_relative_to(work.resolve())
        for item in classification_demo['files']:
            path = (directory / item['file']).resolve()
            assert path.is_relative_to(directory) and sha256(path) == item['sha256'] and path.stat().st_size == item['bytes']
        replay = json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay-classification-v3', str(directory / 'reduction.capsule.json')], consumer))
        assert replay['valid'] and replay['report']['sourceClosure']['complete'] and replay['report']['result']['category'] == 'G2-item'
        checks.append(kind + ' category-specific source-closed reduction and exact classification capsule replay')

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

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 7):
        original26 = json.loads(run([NODE, 'scripts/compat-v026-test.mjs', 'dist',
                                     'fixtures/compat-v026', str(work / ('public26-' + kind))], consumer, timeout=600))
        assert original26['passed'] and original26['currentRuntimeVersion'] == VERSION
        assert original26['originalProducerFamilies'] == 35 and original26['checks'] > 0
        assert original26['normalAnalysisHistoricalWorkersStarted'] == 0
        assert original26['expectedRegenerated'] is False
        checks.append(kind + ' actual public26 35-family fixed-runtime exact compatibility and tamper controls')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 6):
        original25 = json.loads(run([NODE, 'scripts/compat-v025-test.mjs', 'dist',
                                     'fixtures/compat-v025', str(work / ('public25-' + kind))], consumer))
        assert original25['passed'] and original25['currentRuntimeVersion'] == VERSION
        assert original25['checks'] == 173 and original25['originalProducerFamilies'] == 21
        assert original25['normalAnalysisHistoricalWorkersStarted'] == 0
        assert original25['inProcessObservedHistoricalWorkerLaunches'] == 143
        assert original25['expectedRegenerated'] is False
        checks.append(kind + ' actual public25 21-family ESM worker exact compatibility and tamper controls')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 4):
        original23 = json.loads(run([NODE, 'scripts/v023-compatibility-test.mjs'], consumer))
        assert original23['passed'] and original23['runtimeVersion'] == VERSION
        assert original23['producerEngineVersion'] == '0.2.3' and original23['actualPublishedProducer']
        assert original23['capsules'] == 8 and original23['checks'] >= 100
        checks.append(kind + ' actual-public-v023 model, execution and invalid-diagnostic capsule compatibility')
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 3):
        original22 = json.loads(run([NODE, 'scripts/v022-compatibility-test.mjs'], consumer))
        assert original22['passed'] and original22['runtimeVersion'] == VERSION
        assert original22['producerEngineVersion'] == '0.2.2' and original22['actualPublishedProducer']
        assert original22['capsules'] == 8 and original22['checks'] >= 100
        checks.append(kind + ' actual-public-v022 model, execution and invalid-diagnostic capsule compatibility')
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 2):
        original21 = json.loads(run([NODE, 'scripts/v021-compatibility-test.mjs'], consumer))
        assert original21['passed'] and original21['runtimeVersion'] == VERSION
        assert original21['producerEngineVersion'] == '0.2.1' and original21['actualPublishedProducer']
        assert original21['capsules'] == 8 and original21['checks'] >= 100
        checks.append(kind + ' actual-public-v021 model, execution and invalid-diagnostic capsule compatibility')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 1):
        for script, expected_capsules, expected_checks in (
                ('v020-compatibility-test.mjs', 6, 59),
                ('v020-invalid-compatibility-test.mjs', 8, 96)):
            original20 = json.loads(run([NODE, 'scripts/' + script], consumer))
            assert original20['passed'] and original20['runtimeVersion'] == VERSION
            assert original20['producerEngineVersion'] == '0.2.0' and original20['actualPublishedProducer']
            assert original20['capsules'] == expected_capsules and original20['checks'] == expected_checks
        checks.append(kind + ' actual-public-v020 model, execution and invalid-diagnostic capsule compatibility')
        baseline_path = consumer / 'verification/baselines/0.2.0/manifest.json'
        assert sha256(baseline_path) == '0b764ff214e1a5cf6732a7c783899c4bbfeec2dd13b7c0ecbeb0732757f68503'
        baseline = json.loads(baseline_path.read_text(encoding='utf8'))
        assert baseline['publicArchiveSha256'] == '92ffd79314841e09b7ba13209c7678d4626265d74c3c12dba2726089e9b490a3'
        for name, expected in baseline['files'].items():
            path = consumer / baseline['provider'] / name
            assert path.is_file() and path.stat().st_size == expected['bytes'] and sha256(path) == expected['sha256']
        assert sha256(consumer / baseline['anonymousDownloadReviewReceipt']) == baseline['anonymousDownloadReviewReceiptSha256']
        control = consumer / 'verification/fixtures/v010-comparison/manifest.json'
        assert sha256(control) == '208a86d4f19224b7bdea753e6380b677b52155bab557f734b2021f525f9056a6'
        assert len(json.loads(control.read_text(encoding='utf8'))['cases']) == 20
        if kind == 'source':
            baseline_fixtures = json.loads(run([NODE, '--input-type=module', '-e',
                "import{performanceFixturesV020}from'./scripts/performance-v020-fixtures.mjs';"
                "console.log(JSON.stringify({cases:performanceFixturesV020(process.cwd()).length}));"], consumer))
            assert baseline_fixtures['cases'] == 41
        checks.append(kind + ' pinned public20 performance baseline and full common-input closure')

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
        database = load_receipt(consumer / ('verification/releases/' + VERSION) / declaration['databaseEvidence'])
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
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 2):
        instrumentation_only = work / (kind + '-instrumentation-only')
        standalone_capture = instrumentation_only / 'moontxnwitness_capture'
        standalone_capture.mkdir(parents=True, exist_ok=False)
        for module in (consumer / 'integrations/python/moontxnwitness_capture').glob('*.py'):
            if not module.name.startswith('test_'):
                shutil.copyfile(module, standalone_capture / module.name)
        diagnostic = json.loads(run([sys.executable, '-I', '-S', '-B', '-c',
            'import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'from moontxnwitness_capture.instrumentation import instrument_psycopg;'
            'base=Path(sys.argv[1]);observer,connect=instrument_psycopg(lambda:None,base/"capture");'
            'observer.close();receipt=observer.export_diagnostic(base/"trace.json");'
            'trace=json.loads((base/"trace.json").read_text(encoding="utf8"));'
            'assert receipt["complete"] is False and receipt["diagnostic"] is True;'
            'assert any(g["code"]=="diagnostic_instrumentation_only" for g in trace["gaps"]);'
            'assert not any(e["kind"] in ("read","write","condition") for e in trace["events"]);'
            'assert "sqlalchemy" not in sys.modules and "psycopg" not in sys.modules;'
            'print(json.dumps({"passed":True,"complete":False,"optionalDependenciesImported":False}))',
            str(instrumentation_only)], instrumentation_only))
        assert diagnostic == {'passed': True, 'complete': False, 'optionalDependenciesImported': False}
        checks.append(kind + ' standalone automatic instrumentation without optional dependencies and with explicit diagnostic gaps')
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 3):
        grouped = json.loads(run([sys.executable, '-I', '-S', '-B', '-c',
            'import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
            'from moontxnwitness_capture.source_sink import GroupedSourceSink,verify_grouped_source;'
            'from moontxnwitness_capture._orm_source_sink import SourceSink,verify as verify_legacy;'
            'base=Path(sys.argv[1]);p=base/"grouped.jsonl";s=GroupedSourceSink(p);'
            'a=s.append({"kind":"source-batch","observation":{"opaque":"original"}});'
            'assert a.accepted;s.flush();sealed=s.close();'
            'assert sealed["storageSealed"] and verify_grouped_source(p)["storageSealed"];'
            'old=base/"legacy.jsonl";legacy=SourceSink(old);legacy.append({"kind":"source-batch","observation":{"opaque":"original"}});'
            'assert legacy.close()["storageSealed"];assert verify_legacy(p)==verify_legacy(old);assert p.read_bytes()==old.read_bytes();'
            'assert "sqlalchemy" not in sys.modules and "psycopg" not in sys.modules;'
            'print(json.dumps({"passed":True,"completeCapture":sealed["completeCapture"]}))',
            str(instrumentation_only)], instrumentation_only))
        assert grouped == {'passed': True, 'completeCapture': False}
        checks.append(kind + ' standalone grouped source durability and legacy source compatibility')
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
if RELATION034:
    receipt['relation034Consumers'] = relation034_consumers
if PREDICATE035:
    receipt['predicate035Consumers'] = predicate035_consumers
(ROOT / "verification/package.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / "release-index.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ARTIFACTS / (NAME + "-release.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Packaged " + NAME + ": source + portable; " + str(len(checks)) + " fresh-consumer checks passed.")
for item in archives:
    print(item["file"] + "  " + str(item["bytes"]) + " bytes  " + item["sha256"])
