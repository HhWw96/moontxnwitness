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
    tested = json.loads(run(['node', '--input-type=module', '-e',
        "import {verificationFingerprint} from './scripts/verification-fingerprint.mjs'; console.log(JSON.stringify(verificationFingerprint(process.cwd())));" ]))
    assert tested == summary['testedFileSha256'], 'Current executable files differ from tested release'
    source = run(['node', '--input-type=module', '-e',
        "import {sourceFingerprint} from './scripts/build-fingerprint.mjs'; console.log(sourceFingerprint(process.cwd()));"])
    assert source == manifest['sourceSha256'] and summary['buildManifest'] == manifest
    for name, field in (('core.mjs', 'coreSha256'), ('capture-core.mjs', 'captureCoreSha256')):
        assert sha256(ROOT / 'dist' / name) == manifest[field], 'Runtime differs from tested build'
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
            runs = json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', sha, '--workflow', workflow, '--json', 'databaseId,status,conclusion,headSha,event', '--limit', '10']))
            # workflow_dispatch may check out a different inputs.source_ref.
            # A normal push always tests this commit under the pinned workflow.
            runs = [r for r in runs if r['headSha'] == sha and r['event'] == 'push']
            successes = [r for r in runs if r['conclusion'] == 'success']
            if successes:
                if workflow == 'ci.yml':
                    ci = json.loads(run(['gh', 'run', 'view', str(successes[0]['databaseId']), '--repo', MODULE, '--json', 'headSha,conclusion,jobs']))
                    assert ci['headSha'] == sha and ci['conclusion'] == 'success'
                    assert len(ci['jobs']) == 2 and all(job['conclusion'] == 'success' for job in ci['jobs'])
                    assert any(step['name'] == 'Execute Native core on Linux' and step['conclusion'] == 'success'
                               for job in ci['jobs'] for step in job['steps']), 'Linux Native must execute'
                print('Exact-commit CI passed: ' + workflow, flush=True)
                break
            if runs and all(r['status'] == 'completed' for r in runs):
                raise RuntimeError('Public CI failed: ' + workflow + '; preserve the failed run and repair')
            time.sleep(15)
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
    run(['git', '-c', 'core.longpaths=true', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', 'main'])
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
