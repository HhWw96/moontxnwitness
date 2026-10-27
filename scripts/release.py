"""Publish already-tested packages under the explicitly bound repository owner."""
import json
import hashlib
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from package_archive import sha256
from publication_ci import ci_details_ready

ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
MODULE = 'HhWw96/moontxnwitness'
ENV = dict(os.environ)


def validate_scoped_acceptance(acceptance, manifest):
    """Validate the declared stable profiles, without promoting preview goals."""
    assert acceptance['policy'] in ('scoped-stable-v1', 'scoped-stable-v2')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 2):
        assert acceptance['policy'] == 'scoped-stable-v2'
    assert acceptance['version'] == VERSION and acceptance['passed'] is True and acceptance['releaseReady'] is True
    profiles = ['register-v1', 'register-v2', 'postgres-point-capture-v1']
    if acceptance['policy'] == 'scoped-stable-v2':
        profiles.append('postgres-fixed-key-presence-v2')
    assert acceptance['supportedProfiles'] == profiles
    assert acceptance['buildManifest'] == manifest
    summary = json.loads((ROOT / 'verification/summary.json').read_text(encoding='utf8'))
    package = json.loads((ROOT / 'verification/package.json').read_text(encoding='utf8'))
    assert summary['passed'] and summary['version'] == VERSION
    assert {'js', 'wasm-gc', 'wasm'}.issubset(summary['executedTargets'])
    assert package['passed'] and package['version'] == VERSION and package['sourceRebuilt']
    assert package['freshConsumerChecks'] == len(package['checks'])
    assert 'source fresh JS core tests: ' + str(summary['coreTestsPerTarget']) + ' passed' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 3):
        assert summary['ormPlanUnitTests']['passed'] and summary['ormPlanUnitTests']['tests'] > 0
        for kind in ('source', 'portable'):
            assert kind + ' standalone ORM package construction without optional dependencies or experiments' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 4):
        assert summary['appendListSdkTests']['passed'] is True
        assert summary['appendListSdkTests']['checks'] > 0 and summary['appendListSdkTests']['manualCases'] > 0
        for kind in ('source', 'portable'):
            assert kind + ' append-list SDK and source-closed example round trip' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 5):
        assert summary['relationSdkTests']['passed'] is True
        assert summary['relationSdkTests']['checks'] > 0 and summary['relationSdkTests']['manualCases'] > 0
        for kind in ('source', 'portable'):
            assert kind + ' relation-set SDK and source-closed example round trip' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 6):
        cycle = summary['registerCycleSdkTests']
        assert cycle['passed'] is True and cycle['checks'] > 0
        assert cycle['runtimeVersion'] == VERSION and cycle['frozenHistoryCases'] == 132
        assert cycle['handwrittenCases'] == 13
        for kind in ('source', 'portable'):
            assert kind + ' verified register-cycle SDK and original-capsule derived-explanation round trip' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 7):
        execution = summary['executionCapsuleSdkTests']
        assert execution['passed'] is True and execution['checks'] >= 54
        assert execution['runtimeVersion'] == VERSION and execution['originalCandidateAssertions'] == 54
        assert execution['handwrittenCases'] == 10 and execution['recordedMlflowCases'] == 2
        for kind in ('source', 'portable'):
            assert kind + ' execution diagnostic capsule and recorded-MLflow offline comparison round trip' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 8):
        compatibility = summary['executionCapsuleCompatibilityTests']
        assert compatibility['passed'] is True and compatibility['checks'] >= 18
        assert compatibility['runtimeVersion'] == VERSION
        assert compatibility['producerEngineVersion'] == '0.1.7' and compatibility['capsuleCount'] == 2
        for kind in ('source', 'portable'):
            assert kind + ' actual-v017 execution-capsule compatibility' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 1):
        for field, capsules, checks in (
                ('publicV020CompatibilityTests', 6, 59),
                ('publicV020InvalidCompatibilityTests', 8, 96)):
            compatibility = summary[field]
            assert compatibility['passed'] and compatibility['runtimeVersion'] == VERSION
            assert compatibility['actualPublishedProducer'] and compatibility['producerEngineVersion'] == '0.2.0'
            assert compatibility['capsules'] == capsules and compatibility['checks'] == checks
        for kind in ('source', 'portable'):
            assert kind + ' actual-public-v020 model, execution and invalid-diagnostic capsule compatibility' in package['checks']
            assert kind + ' pinned public20 performance baseline and full common-input closure' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 2):
        original21 = summary['publicV021CompatibilityTests']
        assert original21['passed'] and original21['runtimeVersion'] == VERSION
        assert original21['actualPublishedProducer'] and original21['producerEngineVersion'] == '0.2.1'
        assert original21['capsules'] == 8 and original21['checks'] >= 100
        for kind in ('source', 'portable'):
            assert kind + ' actual-public-v021 model, execution and invalid-diagnostic capsule compatibility' in package['checks']
        argument_validation = summary['instrumentationArgumentResourceTests']
        assert argument_validation['passed'] and argument_validation['tests'] == 4
        assert argument_validation['failures'] == argument_validation['errors'] == 0
        instrumentation = summary['instrumentationAdapterUnitTests']
        assert instrumentation['passed'] and instrumentation['tests'] >= 38
        assert instrumentation['failures'] == instrumentation['errors'] == instrumentation['skipped'] == 0
        for kind in ('source', 'portable'):
            assert kind + ' standalone automatic instrumentation without optional dependencies and with explicit diagnostic gaps' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 3):
        original22=summary['publicV022CompatibilityTests']
        assert original22['passed'] and original22['actualPublishedProducer'] and original22['runtimeVersion']==VERSION
        assert original22['producerEngineVersion']=='0.2.2' and original22['capsules']==8 and original22['checks']>=100
        for kind in ('source','portable'):
            assert kind + ' actual-public-v022 model, execution and invalid-diagnostic capsule compatibility' in package['checks']
        persistence = summary['groupedPersistenceUnitTests']
        assert persistence['passed'] and persistence['testsRun'] > 0
        assert persistence['failures'] == persistence['errors'] == 0
        for kind in ('source', 'portable'):
            assert kind + ' standalone grouped source durability and legacy source compatibility' in package['checks']
    tested = json.loads(run(['node', '--input-type=module', '-e',
        "import {verificationFingerprint} from './scripts/verification-fingerprint.mjs'; console.log(JSON.stringify(verificationFingerprint(process.cwd())));" ]))
    assert tested == summary['testedFileSha256'], 'Current executable files differ from tested release'
    source = run(['node', '--input-type=module', '-e',
        "import {sourceFingerprint} from './scripts/build-fingerprint.mjs'; console.log(sourceFingerprint(process.cwd()));"])
    assert source == manifest['sourceSha256'] and summary['buildManifest'] == manifest
    for name, field in (('core.mjs', 'coreSha256'), ('capture-core.mjs', 'captureCoreSha256')):
        assert sha256(ROOT / 'dist' / name) == manifest[field], 'Runtime differs from tested build'
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 4):
        original23 = summary['publicV023CompatibilityTests']
        assert original23['passed'] and original23['actualPublishedProducer'] and original23['runtimeVersion'] == VERSION
        assert original23['producerEngineVersion'] == '0.2.3' and original23['capsules'] == 8 and original23['checks'] >= 100
        configured = summary['configuredOrmProfileHostTests']
        assert configured['passed'] and configured['checks'] >= 50
        driver = summary['configuredOrmProfileDriverTests']
        assert driver['passed'] and driver['testsRun'] == 18
        for kind in ('source', 'portable'):
            assert kind + ' actual-public-v023 model, execution and invalid-diagnostic capsule compatibility' in package['checks']
            assert kind + ' configured ORM explicit-profile source binding, closed reduction and capsule replay' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 5):
        categories = summary['categoryClassificationHostTests']
        assert categories['passed'] and categories['version'] == VERSION and categories['checks'] >= 60
        assert categories['coreSha256'] == manifest['coreSha256']
        assert categories['hostSha256'] == sha256(ROOT / 'dist/classification.mjs')
        original24 = summary['publicV024CompatibilityTests']
        assert original24['passed'] and original24['currentRuntimeVersion'] == VERSION
        assert original24['checks'] >= 107 and original24['originalProducerFamilies'] == 15
        assert original24['expectedRegenerated'] is False
        assert original24['normalAnalysisLegacyModulesLoaded'] == 0 and original24['oldOrmLegacyModulesLoaded'] == 2
        for kind in ('source', 'portable'):
            assert kind + ' category-specific source-closed reduction and exact classification capsule replay' in package['checks']
            assert kind + ' actual public24 fifteen-family SDK/CLI and synchronous lazy ORM replay' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 6):
        models = summary['modelClassificationHostTests']
        assert models['passed'] and models['version'] == VERSION and models['checks'] >= 62
        assert models['coreSha256'] == manifest['coreSha256']
        assert models['hostSha256'] == sha256(ROOT / 'dist/classification-models.mjs')
        assert models['sourceManifestSha256'] == sha256(ROOT / 'fixtures/classification-models-v3/manifest.json')
        assert models['newDatabaseExecution'] is False and models['syntheticStrictEvidence'] is True
        original25 = summary['publicV025CompatibilityTests']
        assert original25['passed'] and original25['currentRuntimeVersion'] == VERSION
        assert original25['checkCount'] == 173 and original25['originalProducerFamilies'] == 21
        assert original25['normalAnalysisHistoricalWorkersStarted'] == 0
        assert original25['inProcessObservedHistoricalWorkerLaunches'] == 143
        assert original25['expectedRegenerated'] is False
        assert original25['originalFixtureManifestSha256'] == sha256(ROOT / 'fixtures/compat-v025/manifest.json')
        protocol = summary['historicalWorkerProtocolTests']
        assert protocol['passed'] and protocol['checks'] == 23 and protocol['frameworkOnly'] is True
        for kind in ('source', 'portable'):
            assert kind + ' explicit model definitions, raw sidecar bindings, applicability gaps and exact model capsule replay' in package['checks']
            assert kind + ' actual public25 21-family ESM worker exact compatibility and tamper controls' in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 8):
        # These are the actual summary shapes. In particular model-profile has
        # core/host bindings, not an invented runtimeVersion field, and the
        # public27 receipt binds its original manifest through its pinned runner.
        configured_model = summary['configuredModelProfileHostTests']
        assert configured_model['passed'] is True and configured_model['cases'] >= 50
        assert configured_model['failures'] == []
        assert configured_model['compiledCoreSha256'] == manifest['coreSha256']
        assert configured_model['hostSourceSha256'] == sha256(ROOT / 'dist/model-profile.mjs')
        assert configured_model['actualDatabaseExecution'] is False
        assert configured_model['formalPerformanceMeasurement'] is False
        assert configured_model['sourceClosedReductionClaimed'] is False
        model_driver = summary['configuredModelProfileDriverTests']
        assert model_driver['passed'] is True and model_driver['actualDatabaseExecution'] is False
        original26 = summary['publicV026CompatibilityTests']
        assert original26['format'] == 'genuine-public026-current-consumer/v1'
        assert original26['passed'] is True and original26['currentRuntimeVersion'] == VERSION
        assert original26['currentCoreSha256'] == manifest['coreSha256']
        assert original26['originalFixtureManifestSha256'] == sha256(ROOT / 'fixtures/compat-v026/manifest.json')
        assert original26['originalProducerFamilies'] == 35 and original26['originalModelFamilies'] == 14
        original27 = summary['publicV027CompatibilityTests']
        assert original27['format'] == 'genuine-public027-current-consumer/v1'
        assert original27['passed'] is True and original27['currentRuntimeVersion'] == VERSION
        assert original27['originalProducerFamilies'] == 46 and original27['originalModelProfileFamilies'] == 11
        assert sha256(ROOT / 'fixtures/compat-v027/manifest.json') == 'f196ee5fc21e3fe78ea75ee3c73e904206e1a0f24dd8e847a0e6fe504461eba8'
        for compatibility, minimum in ((original26, 623), (original27, 418)):
            assert compatibility['expectedRegenerated'] is False
            assert compatibility['normalAnalysisHistoricalWorkersStarted'] == 0
            assert compatibility['originalReportsAndCapsulesRemainByteIdentical'] is True
            assert compatibility['verificationResponseOnlyCurrentEngineDeltaAllowedFor'] == ['v1', 'v2']
            assert compatibility['checkCount'] >= minimum
            assert len(compatibility['checks']) == compatibility['checkCount']
            assert all(row['passed'] is True for row in compatibility['checks'])
        assert any(row['name'] == 'actual current runtime version core and capture manifest bindings'
                   for row in original27['checks'])
        for label in ('026', '027'):
            worker = summary['historicalWorker' + label + 'ProtocolTests']
            assert worker['format'] == 'synthetic-public' + label.lstrip('0') + '-worker-framework-tests/v1'
            assert worker['passed'] is True and worker['checks'] > 0 and worker['frameworkOnly'] is True
            assert worker['actualPublicFixturesExecuted'] is False and worker['realSdkImported'] is False
        diagnosis = summary['diagnosisHostTests']
        assert diagnosis['passed'] is True and diagnosis['version'] == VERSION and diagnosis['checks'] >= 66
        assert len(diagnosis['cases']) == diagnosis['checks'] and all(row['passed'] is True for row in diagnosis['cases'])
        assert diagnosis['coreSha256'] == manifest['coreSha256']
        assert diagnosis['captureCoreSha256'] == manifest['captureCoreSha256']
        assert diagnosis['diagnosisHostSha256'] == sha256(ROOT / 'dist/diagnosis.mjs')
        assert diagnosis['newDatabaseExecution'] is False and diagnosis['newMoonCompilation'] is False
        assert diagnosis['formalPerformanceMeasured'] is False
        assert diagnosis['originalSerialAndModelReportsAndCapsulesPreserved'] is True
        assert diagnosis['syntheticCases'] == 7
        assert diagnosis['frozenOriginalCases'] == [
            {'id': name, 'sha256': sha256(ROOT / ('fixtures/diagnosis-v3/' + name + '.json'))}
            for name in ('register-0', 'register-4', 'register-80')]
        for kind in ('source', 'portable'):
            for description in (
                    'actual public26 35-family fixed-runtime exact compatibility and tamper controls',
                    'exact genuine public027 full46 compatibility and configured model-profile replay',
                    'configured list/relation original-source model projection and complete capsule replay',
                    'combined diagnosis preserves original unknown analysis and verifies direct INT evidence'):
                assert kind + ' ' + description in package['checks']
    if tuple(map(int, VERSION.split('.'))) >= (0, 3, 0):
        original28 = summary['publicV028CompatibilityTests']
        assert original28['passed'] and original28['currentRuntimeVersion'] == VERSION
        assert original28['producerCases'] == 156 and original28['variants'] == 3 and original28['cliCases'] == 24
        assert original28['expectedRegenerated'] is False and original28['originalReportsAndCapsulesRewritten'] is False
        assert original28['runtimeManifestSha256'] == sha256(ROOT / 'cmd/legacy/v028/manifest.json')
        worker28 = summary['historicalWorker028ProtocolTests']
        assert worker28['passed'] and worker28['checkCount'] == 17 and worker28['actualPublic028Runtime']
        assert worker28['syntheticResponsesUsed'] is False
        for kind in ('source', 'portable'):
            assert kind + ' genuine public028 three-context 156 original cases and 24 CLI replays' in package['checks']
            assert kind + ' native HTTP same623 real observations, deadlock diagnosis and exact offline replay' in package['checks']

    expected_names = {'MoonTxnWitness-v' + VERSION + '-' + kind + '.zip' for kind in ('source', 'portable')}
    assert {item['file'] for item in package['archives']} == expected_names
    for item in package['archives']:
        path = ROOT / 'artifacts' / item['file']
        assert path.stat().st_size == item['bytes'] and sha256(path) == item['sha256'], 'Archive differs from fresh consumer input'
        with zipfile.ZipFile(path) as packed:
            assert len(packed.infolist()) == item['files']
    expected_sums = ''.join(item['sha256'] + '  ' + item['file'] + '\n' for item in package['archives'])
    assert (ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + '-SHA256SUMS.txt')).read_text(encoding='utf8') == expected_sums, 'Public digest manifest differs from tested archives'
    actual = json.loads((ROOT / 'verification/releases' / VERSION / acceptance['databaseEvidence']).read_text(encoding='utf8'))
    assert actual['passed'] is True and actual['actualDatabaseExecution'] is True
    assert actual['buildManifestBefore'] == manifest and actual['buildManifestAfter'] == manifest
    assert actual['exitCode'] == 0
    if acceptance['policy'] == 'scoped-stable-v2':
        assert actual['testedFileSha256Before'] == actual['testedFileSha256After'] == tested
        for label in ('presence', 'initialization'):
            reference = actual['receipts'][label]
            path = (ROOT / 'verification' / reference['path'] / reference['receiptFile']).resolve()
            assert path.is_relative_to((ROOT / 'verification').resolve())
            assert sha256(path) == reference['sha256'], 'Database receipt changed: ' + label
        presence_root = ROOT / 'verification' / actual['receipts']['presence']['path']
        presence = json.loads((presence_root / 'presence-receipt.json').read_text(encoding='utf8'))
        assert presence['passed'] and presence['actualDatabaseExecution'] and presence['coreVersion'] == VERSION
        assert len(presence['scenarios']) == 6 and presence['replayedCapsules'] == 3
        expected_implementation = {
            'integrations/python/moontxnwitness_capture/' + name for name in (
                '__init__.py', 'capture.py', '_provenance.py', '_column_profile.py',
                '_initialization_guard.py', '_source_inventory.py', 'presence.py')}
        assert set(presence['captureSource']['implementationFiles']) == expected_implementation
        for name, expected in presence['captureSource']['implementationFiles'].items():
            assert sha256(ROOT / name) == expected, 'Presence implementation differs: ' + name
        for name, expected in presence['captureSource']['files'].items():
            assert sha256(ROOT / name) == expected, 'Presence fixture/runtime differs: ' + name
        initialization_root = ROOT / 'verification' / actual['receipts']['initialization']['path']
        initialization = json.loads((initialization_root / 'initialization-receipt.json').read_text(encoding='utf8'))
        assert initialization['passed'] and initialization['actualDatabaseExecution']
        assert initialization['packageVersion'] == VERSION and initialization['analyzerExecuted'] is False
        assert len(initialization['cases']) == 4 and all(case['passed'] for case in initialization['cases'])
        sources = initialization['implementationSources']
        assert sources['unchanged'] is True and sources['before'] == sources['after']
        assert {'integrations/python/' + name for name in sources['after']} == expected_implementation
        for name, observed in sources['after'].items():
            path = ROOT / 'integrations/python' / name
            assert sha256(path) == observed['sha256'] and path.stat().st_size == observed['bytes']
        fixture = initialization['fixtureSources']
        assert fixture['unchanged'] is True and fixture['before'] == fixture['after']
        assert fixture['after'] == sha256(ROOT / 'experiments/provenance/initialization_postgres.py')
    capture = json.loads((ROOT / 'verification/capture-postgres.json').read_text(encoding='utf8'))
    assert capture['version'] == VERSION and capture['passed'] and capture['actualDatabaseExecution']
    for field, name in (
        ('adapterSha256', 'integrations/python/moontxnwitness_capture/capture.py'),
        ('captureCoreSha256', 'dist/capture-core.mjs'), ('analysisCoreSha256', 'dist/core.mjs'),
        ('fixtureSha256', 'scripts/capture-postgres-test.py'), ('e2eSha256', 'scripts/capture-postgres-e2e.mjs')):
        assert capture['captureSource'][field] == sha256(ROOT / name), 'Capture evidence differs from release: ' + name


def run(args, timeout=300, capture=True):
    result = subprocess.run(args, cwd=ROOT, env=ENV, capture_output=capture, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        if capture:
            print(result.stdout, result.stderr)
        raise RuntimeError('Release operation failed: ' + args[0])
    return result.stdout.strip() if capture else ''


def wait_for_ci(sha):
    workflows = ['ci.yml'] + (['postgres.yml'] if tuple(map(int, VERSION.split('.'))) >= (0, 0, 11) else [])
    for workflow in workflows:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            runs = json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', sha, '--workflow', workflow, '--json', 'databaseId,status,conclusion,headSha,event', '--limit', '10'], timeout=min(300, deadline - time.monotonic())))
            if time.monotonic() >= deadline:
                continue
            # workflow_dispatch may check out a different inputs.source_ref.
            # A normal push always tests this commit under the pinned workflow.
            runs = [r for r in runs if r['headSha'] == sha and r['event'] == 'push']
            successes = [r for r in runs if r['conclusion'] == 'success']
            if successes:
                if workflow == 'ci.yml':
                    ci = json.loads(run(['gh', 'run', 'view', str(successes[0]['databaseId']), '--repo', MODULE, '--json', 'headSha,conclusion,jobs'], timeout=min(300, deadline - time.monotonic())))
                    if time.monotonic() >= deadline:
                        continue
                    if not ci_details_ready(ci, sha):
                        # Workflow metadata can precede the final job response.
                        # Keep the original deadline; no incomplete state passes.
                        time.sleep(min(15, max(0, deadline - time.monotonic())))
                        continue
                print('Exact-commit CI passed: ' + workflow, flush=True)
                break
            if runs and all(r['status'] == 'completed' for r in runs):
                raise RuntimeError('Public CI failed: ' + workflow + '; preserve the failed run and repair')
            time.sleep(min(15, max(0, deadline - time.monotonic())))
        else:
            raise TimeoutError('CI did not finish within the observation window: ' + workflow)


def publish():
    # The account can be switched by other desktop tasks; never use its implicit selection.
    token = run(['gh', 'auth', 'token', '--hostname', 'github.com', '--user', 'HhWw96'])
    ENV['GH_TOKEN'] = token
    assert run(['gh', 'api', 'user', '--jq', '.login']) == 'HhWw96'
    assert not run(['git', 'status', '--porcelain']), 'Commit the tested release first'
    for name in ('summary', 'package'):
        receipt = json.loads((ROOT / ('verification/' + name + '.json')).read_text(encoding='utf-8'))
        assert receipt['passed'] and receipt['version'] == VERSION
    prefix = 'MoonTxnWitness-v' + VERSION + '/'
    with zipfile.ZipFile(ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + '-source.zip')) as source:
        for member in source.infolist():
            assert member.filename.startswith(prefix)
            relative = Path(member.filename[len(prefix):])
            assert (ROOT / relative).resolve().is_relative_to(ROOT.resolve())
            with source.open(member) as archived, (ROOT / relative).open('rb') as current:
                while True:
                    chunk = archived.read(65536)
                    assert chunk == current.read(65536), 'Source archive is stale: ' + relative.as_posix()
                    if not chunk:break
    scoped = False
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 0):
        acceptance = json.loads((ROOT / 'verification/releases' / VERSION / 'acceptance.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'dist/build-manifest.json').read_text(encoding='utf-8'))
        assert acceptance['passed']
        scoped = acceptance.get('policy') in ('scoped-stable-v1', 'scoped-stable-v2')
        if scoped:
            validate_scoped_acceptance(acceptance, manifest)
        else:
            performance = json.loads((ROOT / 'verification/releases' / VERSION / acceptance['performanceReceipt']).read_text(encoding='utf-8'))
        if not scoped and tuple(map(int, VERSION.split('.'))) >= (0, 1, 1):
            assert acceptance['releaseReady'] and acceptance['existingBusinessIntegration']['passed']
            assert performance['formalReleaseGatePassed'] and performance['correctnessPassed'] and not performance['smokeOnly']
            current = performance['provenance']['currentBuildManifest']
            assert current['sourceSha256'] == manifest['sourceSha256'] and current['coreSha256'] == manifest['coreSha256']
            capture = json.loads((ROOT / 'verification/capture-postgres.json').read_text(encoding='utf-8'))
            assert capture['version'] == VERSION and capture['passed'] and capture['actualDatabaseExecution']
            for field, path in (
                ('adapterSha256', 'integrations/python/moontxnwitness_capture/capture.py'),
                ('captureCoreSha256', 'dist/capture-core.mjs'),
                ('analysisCoreSha256', 'dist/core.mjs'),
                ('fixtureSha256', 'scripts/capture-postgres-test.py'),
                ('e2eSha256', 'scripts/capture-postgres-e2e.mjs'),
            ):
                assert capture['captureSource'][field] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), 'Actual capture receipt is stale: ' + path
        elif not scoped:
            assert performance['performanceTargetsMet']
            assert performance['sourceSha256'] == manifest['sourceSha256'] and performance['currentSha256'] == manifest['coreSha256']
        postgres = json.loads((ROOT / 'verification/postgres.json').read_text(encoding='utf-8'))
        assert postgres['version'] == VERSION and postgres['passed'] and postgres['actualDatabaseExecution']
    sha = run(['git', 'rev-parse', 'HEAD'])
    tag = 'v' + VERSION
    assert run(['git', 'rev-list', '-n', '1', tag]) == sha
    run(['git', '-c', 'core.longpaths=true', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', 'HEAD:refs/heads/main'])
    print('Release candidate pushed; waiting for actual CI before package publication: ' + tag, flush=True)
    wait_for_ci(sha)
    assert run(['git', 'rev-parse', 'HEAD']) == sha and not run(['git', 'status', '--porcelain'])
    # Publishing reads the current source, so finish this step before another version is edited.
    assert run(['node', 'scripts/moon.mjs', 'whoami']).endswith('HhWw96')
    run(['node', 'scripts/moon.mjs', 'publish'], capture=False)
    print('Mooncakes upload completed: ' + VERSION, flush=True)
    run(['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', tag])
    notes = ROOT / ('artifacts/release-notes-v' + VERSION + '.md')
    notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
                     '- PostgreSQL point-read/write capture for psycopg sync/async connections, with explicit version columns and SQL mappings.\n'
                     '- MoonBit coverage validation preserves unknown commits and incomplete observations.\n'
                     '- Lower allocation in graph/report/search paths; v1/v2 analysis and replay remain compatible.\n\n'
                     'Supported: versioned point registers, bounded analysis/reduction, v1/v2 replay and traceSchema1 capture. '
                     'v3 models and ordinary-table/ORM adapters remain opt-in previews; v3 capsules require their original engine version.\n\n'
                     'Install: `moon add HhWw96/moontxnwitness@' + VERSION + '`, or download the portable ZIP (Node.js >=20). '
                     'PostgreSQL capture needs its optional Python driver.\n\n'
                     'Cross-target tests, real PostgreSQL scenarios and fresh source/portable consumers are checked for this scope. '
                     'See CHANGELOG.md for details.\n', encoding='utf-8')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 2):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Standalone Python presence capture for controlled PostgreSQL 18 two-column tables: generated synchronous point CRUD, negative reads and tombstone sources.\n'
            '- Bounded initialization, explicit server COMMIT confirmation, failed/unknown initialization lockout and legacy import compatibility.\n'
            '- Smaller source/portable downloads retain current reproduction evidence and required fixtures; full historical evidence remains in Git.\n\n'
            'Existing v1/v2 analysis/reduction/replay and schema-1 sync/async capture remain supported. '
            'See docs/presence-capture.md for installation changes and the fixed-key scope. '
            'Extended persistence, v3 models and ORM integrations continue as previews.\n\n'
            'Install: `moon add HhWw96/moontxnwitness@' + VERSION + '`, or download portable ZIP (Node.js >=20). '
            'Python capture uses the optional psycopg driver. See CHANGELOG.md for validation and compatibility.\n', encoding='utf8')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 3):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Standalone Python ORM SQL-plan and bounded-cache API for the fixed FastAPI Users SQLAlchemy 7.0.0 base-user point CRUD profile.\n'
            '- Reuse constructor-compiled SQL plans instead of compiling each shape again on first execution; keep parameters, results and transaction state out of the cache.\n'
            '- Expose the MoonBit local ORM-source diagnostic with explicit partial coverage; preserve released v1/v2 and compatible v3 replay.\n\n'
            'Use `moontxnwitness_capture.orm` and see docs/orm-plans.md. Basic imports need no driver or SQLAlchemy; template compilation uses optional SQLAlchemy 2.0.55. '
            'Source observers and their installation remain experimental; local source proof does not establish complete ORM transaction coverage.\n\n'
            'Install: `moon add HhWw96/moontxnwitness@' + VERSION + '`, or download the portable ZIP (Node.js >=20). '
            'Existing register analysis/reduction, PostgreSQL capture and ordinary-table fixed-key CRUD remain available. See CHANGELOG.md for compatibility and validation.\n', encoding='utf8')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 4):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Explicit append-list SDK entries for normalization, analysis, reduction, verification and replay capsules, with fixed-model guards.\n'
            '- Runnable synthetic example: identify a two-list serializability violation, remove an unrelated transaction and replay the reduced two-transaction evidence.\n'
            '- Preserve exact capture text, source gaps, unknown outcomes and bounded-search results; keep generic v3 and released v1/v2 and compatible v3 replay.\n\n'
            'Import the list-specific functions from `dist/sdk.mjs`; run `node examples/list-roundtrip.mjs` and see docs/list-sdk.md. '
            'The precise-search scope remains 6 committed transactions and 128 append/read operations, with at most 100,000 states, 1,000,000 semantic checks and 256 reduction candidates. '
            'Budget exhaustion and insufficient sources remain inconclusive. Replay validity means reproducible diagnostics, including invalid or inconclusive results; inspect the reported status.\n\n'
            'The example is synthetic and does not connect to a database. This release adds no arbitrary-SQL list capture, mixed-model transactions, full isolation-level classification or new performance claim. '
            'Existing PostgreSQL fixtures, actual release checks and fresh-consumer evidence are recorded separately in CHANGELOG.md and verification/.\n\n'
            'Install the MoonBit core: `moon add HhWw96/moontxnwitness@' + VERSION + '`, or download the portable ZIP for the Node.js SDK (Node.js >=20). '
            'Existing register, presence and optional ORM-plan APIs remain available.\n', encoding='utf8')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 5):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Six relation-model SDK entries for analysis, source-preserving reduction and replay.\n'
            '- A runnable example removes an unrelated transaction and retains the version source needed by the counterexample.\n'
            '- Existing register/list APIs and explicitly supported released v3 replay remain compatible.\n\n'
            'Run `node examples/relation-roundtrip.mjs`; see [the SDK guide](docs/relation-sdk.md) for usage, supported queries, budgets and diagnostic status. '
            'Arbitrary SQL instrumentation and complete isolation-level classification remain outside this scope.\n\n'
            'Install: `moon add HhWw96/moontxnwitness@' + VERSION + '` for the MoonBit core, or use the portable ZIP for Node.js SDK. '
            'See CHANGELOG.md and verification/ for actual validation and retained failures.\n', encoding='utf8')
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 6):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Explain the type and original sources of an already verified point-register dependency cycle.\n'
            '- Recompute the separate explanation while preserving the original report and v3 capsule.\n'
            '- Preserve generic, list and relation APIs; explicitly retain released-engine replay compatibility through v0.1.5.\n\n'
            'Run `node examples/register-cycle-roundtrip.mjs`. See [the SDK guide](https://github.com/' + MODULE + '/blob/' + tag + '/docs/cycle-explanation-v3.md) '
            'for input limits, diagnostic states and witness-only scope. This does not search all anomaly classes or accept an isolation model.\n\n'
            'Install the MoonBit core with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for the Node.js SDK. '
            'Actual verification, installation and download receipts remain in verification/; see CHANGELOG.md for details.\n', encoding='utf8')

    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 7):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Seal exact capture text and its execution diagnostic, then recompute the complete diagnostic on replay.\n'
            '- Compare two existing recorded MLflow component executions offline while retaining faults, unknown outcomes and coverage gaps.\n'
            '- Preserve cycle, list, relation and generic APIs; explicitly retain released model-capsule compatibility through v0.1.6.\n\n'
            'Run `node examples/execution-roundtrip.mjs`. See [the SDK guide](https://github.com/' + MODULE + '/blob/' + tag + '/docs/execution-capsule-v3.md) '
            'for the distinct execution format, fixed budgets and the meaning of valid replay. This does not run a database, certify failure absence or prove an application repair.\n\n'
            'Install the MoonBit core with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for the Node.js SDK. '
            'Actual verification and public download receipts are recorded separately in verification/.\n', encoding='utf8')

    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 8):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Replay genuine v0.1.7 execution capsules while retaining original engine, capture text, diagnostic and model compatibility.\n'
            '- Keep the published v0.1.7 production parser byte-for-byte and retain nine unchanged parser boundary tests with the experimental helper in test-only code.\n'
            '- Preserve the first rejected optimization comparison; its correctness passed but performance controls did not. No stable18 performance or RSS success is claimed.\n\n'
            'See CHANGELOG.md and [the execution-capsule guide](https://github.com/' + MODULE + '/blob/' + tag + '/docs/execution-capsule-v3.md). '
            'Performance results and actual release verification are recorded separately; this note makes no speedup or memory claim.\n\n'
            'Install with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for Node.js.\n', encoding='utf8')

    if tuple(map(int, VERSION.split('.'))) >= (0, 2, 0):
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- One bounded support matrix for registers, fixed-key presence, SQL templates/cache, append lists, relation facts, selected-cycle explanation and execution capsules.\n'
            '- Preserve explicit budgets, source gaps and replay rules, including v0.1.8 model and v0.1.7/v0.1.8 execution capsules.\n'
            '- Keep full automatic SQL/ORM, six-model classification and complete production integrations on the future roadmap.\n\n'
            'See the [stable scope and examples](https://github.com/' + MODULE + '/blob/' + tag + '/docs/stable-scope.md). '
            'Actual regression, database, independent review, fresh installation and public download receipts are recorded separately; no unmeasured performance figure is claimed here.\n\n'
            'Install with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for Node.js.\n', encoding='utf8')

    if VERSION == '0.2.8':
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Add `diagnoseV3` / `verifyDiagnosisV3` and CLI diagnosis/verification, combining the original serial analysis and model checks with independently verifiable direct evidence. Unknown analysis remains visible; INT does not become G2 or a PL3 refutation.\n'
            '- Reuse parsed relation-reduction candidates while retaining full semantic revalidation, sources and budgets. Fixed relation-candidate workloads measured 1.124x speedup; this is not an overall v0.2.8 SDK or database-throughput claim.\n'
            '- Replay all 46 genuine public v0.2.7 fixture families through the fixed original runtime, including configured model profiles, and retain the full toolchain licences and NOTICE.\n\n'
            'Configured register/list/relation profiles, explicit model checks, missing-source gaps and existing budgets remain as documented. '
            'The MLflow case remains a component-level reproduction; the original HTTP log_batch repair comparison is unfinished.\n\n'
            'See the [support matrix](https://github.com/' + MODULE + '/blob/' + tag + '/docs/stable-scope.md), '
            '[diagnosis guide](https://github.com/' + MODULE + '/blob/' + tag + '/docs/diagnosis-sdk.md) and '
            '[measured performance scope](https://github.com/' + MODULE + '/blob/' + tag + '/docs/performance-v0.2.8-relation.md). '
            'Actual release, database, fresh-consumer and public-download receipts remain separate from human feedback and organizer decisions.\n\n'
            'Install with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for Node.js.\n', encoding='utf8')

    if VERSION == '0.3.0':
        notes.write_text('## MoonTxnWitness v' + VERSION + '\n\n'
            '- Deliver the native MLflow HTTP log-batch repair case: 30 fixed seed pairs, actual 40P01 evidence, 1000-to-623 key reduction and three fixed-side reruns of the identical final case. `oneMinimal` remains false.\n'
            '- Run `node examples/mlflow-http-roundtrip.mjs` to diagnose and replay two unchanged real captures without a database. Source gaps and inconclusive model results remain visible.\n'
            '- Add explicit bounded source-write buffering to configured user/model profiles while preserving legacy defaults, tail synchronization and refusal of incomplete seals.\n'
            '- Replay 156 original public v0.2.8 cases across three genuine build contexts with fixed runtime identity checks and unchanged original expectations.\n\n'
            'Formal capture-cost experiments completed, but the throughput/P95 targets were not met; failed CRUD cells remain ineligible. '
            'The measured scope and raw evidence identities are in the [capture-cost report](https://github.com/' + MODULE + '/blob/' + tag + '/docs/performance-v0.3.0-capture.md).\n\n'
            'See the [HTTP case and new-run instructions](https://github.com/' + MODULE + '/blob/' + tag + '/docs/mlflow-http-case.md) and '
            '[support matrix](https://github.com/' + MODULE + '/blob/' + tag + '/docs/stable-scope.md). '
            'Install with `moon add HhWw96/moontxnwitness@' + VERSION + '` or use the portable ZIP for Node.js.\n', encoding='utf8')

    performance_path = ROOT / 'verification/releases' / VERSION / 'release-gate-v1.json'
    if performance_path.exists() and not scoped:
        groups = json.loads(performance_path.read_text(encoding='utf-8'))['groups']
        with notes.open('a', encoding='utf-8') as output:
            output.write('\nFull-report local comparison with v0.0.6: graph %.2fx, bounded search %.2fx, reduction %.2fx; graph peak RSS %.2f%% lower (group geometric means).\n' % (groups['graph']['geometricMeanSpeedup'], groups['search']['geometricMeanSpeedup'], groups['reduction']['geometricMeanSpeedup'], (1-groups['graph']['geometricMeanPeakMemoryRatio'])*100))
            output.write('Actual PostgreSQL 18: 20 RR write-skew rounds + 20 Serializable abort/fresh-retry rounds on Windows and independent Linux CI, with 2-transaction reduction and three replay capsules.\n')
            output.write('See docs/performance.md, docs/project-brief.md and docs/human-acceptance.md. Participant explanation/registration and organizer acceptance remain separate.\n')
    assets = [str(ROOT / ('artifacts/MoonTxnWitness-v' + VERSION + suffix)) for suffix in ('-source.zip', '-portable.zip', '-SHA256SUMS.txt')]
    run(['gh', 'release', 'create', tag, '--repo', MODULE, '--target', sha, '--title', 'MoonTxnWitness ' + tag, '--notes-file', str(notes), *assets], timeout=900)
    print('Public GitHub Release created: ' + tag, flush=True)
    run([sys.executable, 'scripts/verify_publication.py', VERSION], timeout=900, capture=False)
    print('Public download, exact-commit CI and registry-only consumers passed: ' + tag, flush=True)


if __name__ == '__main__':
    publish()
