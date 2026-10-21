from __future__ import annotations
# Candidate only: derived from a preserved 8f audit; no existing tool is modified.
from transport import guard_environment, child_environment, file_binding, file_sha, read_bounded, immutable, safe_extract, fetch, run_bounded, JSON_MAX
PROFILE = None
PROFILE_SHA256 = "6808bb9ef987816cc096f2ab9e245d2ad9bc8cffd9fbcb5bd4f3806888a81000"
"""Independent fixed-commit transport, executable-byte and fresh-runtime audit.

Read-only GitHub APIs; no workflow dispatch, build, database or benchmark.
Only new scratch/evidence paths are written. Credentials never enter receipts.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
REPO = 'HhWw96/moontxnwitness'
COMMIT = '78635505e4c189c402ba70600632aeaef71ef206'
ROOT = Path(__file__).resolve().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(read_bounded(path))

def audit(work):
    transport = load(work / 'transport-audit.json')
    assert transport['sourceCommit'] == COMMIT
    for item in transport['downloads']:
        actual = file_binding(work / item['file'])
        assert actual == {'bytes': item['bytes'], 'sha256': item['sha256']}
        if item['githubDigest']:
            assert item['githubDigest'] == 'sha256:' + actual['sha256']
    source_dir = work / 'source'
    assert source_dir.is_dir(), 'Use the independently safety-checked pre-extracted source archive'
    roots = list(source_dir.iterdir())
    assert len(roots) == 1 and roots[0].is_dir()
    source = roots[0]
    names = sorted(['moon.mod'] + [p.relative_to(source).as_posix() for p in (source / 'src').rglob('*') if p.is_file() and (p.suffix == '.mbt' or p.name == 'moon.pkg')])
    fingerprint = hashlib.sha256()
    for name in names:
        fingerprint.update(name.encode() + b'\x00')
        fingerprint.update(read_bounded(source / name))
        fingerprint.update(b'\x00')
    source_hash = fingerprint.hexdigest()
    assert source_hash == PROFILE['sourceSha256'], 'Fixed source fingerprint required'
    member_bindings, core_results = ({}, [])

    def digest_file(path):
        return file_binding(path)
    for os_name in ('ubuntu-24.04', 'windows-2022'):
        folder = work / ('artifact-' + os_name)
        assert folder.is_dir(), 'Use the independently safety-checked pre-extracted artifact'
        summary, package = (load(folder / 'verification/summary.json'), load(folder / 'verification/package.json'))
        assert summary['passed'] and package['passed']
        assert summary['coreTestsPerTarget'] == 563 and summary['executedTargets'] == ['js', 'wasm-gc', 'wasm']
        assert (summary['oracleHistories'], summary['verifiedCycleCertificates'], summary['parserDifferentialInputs'], summary['cliChecks'], summary['captureCliChecks'], summary['experimentalPresenceCliChecks']) == (10320, 6373, 2542, 75, 14, 26)
        bindings = summary['testedFileSha256']
        assert len(bindings) == PROFILE['testedBindings'] == 347
        non_dist = {name: expected for name, expected in bindings.items() if not name.startswith('dist/')}
        assert len(non_dist) == 339, '339 fixed-commit non-runtime tested-source bindings required'
        for name, expected in non_dist.items():
            actual = digest_file(source / name)
            assert actual['sha256'] == expected, 'Public source does not match tested bytes: ' + name
            member_bindings[os_name + ':source:' + name] = actual
        for name, expected in bindings.items():
            if name.startswith('dist/'):
                actual = digest_file(folder / name)
                assert actual['sha256'] == expected
                member_bindings[os_name + ':runtime:' + name] = actual
        manifest = load(folder / 'dist/build-manifest.json')
        assert manifest == summary['buildManifest'] and manifest['sourceSha256'] == source_hash
        assert manifest['coreSha256'] == file_sha(folder / 'dist/core.mjs')
        assert manifest['captureCoreSha256'] == file_sha(folder / 'dist/capture-core.mjs')
        for name in ('sdk.mjs', 'evidence.mjs', 'moontxnwitness.mjs'):
            assert read_bounded(folder / 'dist' / name) == read_bounded(source / 'cmd' / name)
            assert read_bounded(folder / 'cmd' / name) == read_bounded(source / 'cmd' / name)
        v3 = summary['experimentalV3']
        assert not v3['foundationOnly'] and v3['experimentalOnly'] and (not v3['v011v012JointReleaseReady']) and (not v3['fullBusinessLifecycle']) and (not v3['formalPerformanceMeasured'])
        assert v3['independentReference']['passed'] and v3['independentReference']['cases'] == 57
        assert v3['acceptance']['passed'] and v3['acceptance']['checks'] == 167
        assert v3['journal']['passed'] and v3['journal']['testsRun'] == 64
        skipped = v3['journal']['skipped']
        assert len(skipped) <= (2 if os_name == 'windows-2022' else 0)
        if skipped:
            assert all(('symlink' in item['test'] and item['reason'] for item in skipped))
        assert v3['independentStorageAudit']['passed'] and v3['independentStorageAudit']['checks'] == 10
        for key in ('acceptance', 'independentStorageAudit'):
            nested = v3[key]
            assert file_sha(folder / nested['receipt']) == nested['sha256']
        assert package['sourceRebuilt'] and package['freshConsumerChecks'] == len(package['checks']) == 76
        job = next((job for job in transport['jobs'] if os_name in job['name']))
        log_raw = read_bounded(work / f'job-{job['id']}.log')
        log = re.sub('\\x1b\\[[0-9;]*m', '', log_raw.decode('utf8'))
        assert COMMIT in log
        counts = re.findall('Total tests: 563, passed: 563, failed: 0\\.', log)
        assert len(counts) >= (4 if os_name == 'ubuntu-24.04' else 3)
        assert re.search('Ran 62 tests in', log)
        native = next((step for step in job['steps'] if step['name'] == 'Execute Native core on Linux'))
        assert native['conclusion'] == ('success' if os_name == 'ubuntu-24.04' else 'skipped')
        if os_name == 'ubuntu-24.04':
            start = log.index('##[group]Run node scripts/moon.mjs test --target native --deny-warn')
            end = log.index('##[group]', start + len('##[group]'))
            assert 'Total tests: 563, passed: 563, failed: 0.' in log[start:end]
        core_results.append({'os': os_name, 'job': job['html_url'], 'sourceBindingsMatched': len(non_dist), 'manifest': manifest, 'executedTargets': summary['executedTargets'], 'coreTestsPerTarget': 563, 'actualRuntimeFilesDownloaded': True, 'nativeExecuted': os_name == 'ubuntu-24.04', 'jobLogSha256': sha(log_raw), 'v3Counts': {'reference': 57, 'acceptance': 167, 'journal': 64, 'storageAudit': 10}, 'freshPackageChecks': 76, 'journalSkipped': v3['journal']['skipped']})
    pg = work / 'artifact-postgres'
    assert pg.is_dir(), 'Use the independently safety-checked pre-extracted PostgreSQL artifact'
    pg_base = pg / 'verification' if (pg / 'verification/postgres.json').exists() else pg
    assert set(load(pg_base / 'postgres-ci-source.json').values()) == {COMMIT}
    pg_manifest = load(pg / 'dist/build-manifest.json')
    assert pg_manifest['sourceSha256'] == source_hash
    assert pg_manifest['coreSha256'] == file_sha(pg / 'dist/core.mjs')
    assert pg_manifest['captureCoreSha256'] == file_sha(pg / 'dist/capture-core.mjs')
    legacy, capture = (load(pg_base / 'postgres.json'), load(pg_base / 'capture-postgres.json'))
    assert legacy['passed'] and legacy['actualDatabaseExecution'] and (legacy['roundsPerScenario'] == 20)
    assert len(legacy['cases']) == 2 and all((len(c['results']) == c['rounds'] == 20 for c in legacy['cases']))
    assert legacy['observedTransactions'] == 100 and legacy['oneMinimal'] and (legacy['minimalTransactions'] == 2)
    for case in legacy['cases']:
        for result in case['results']:
            expected = (2, 0, 0, []) if case['isolation'] == 'REPEATABLE READ' else (1, 1, 1, ['40001'])
            assert case['isolation'] in ('REPEATABLE READ', 'SERIALIZABLE')
            assert (result['initialConcurrentCommits'], result['initialConcurrentAborts'], result['finalOnCallCount'], result['sqlstates']) == expected
    for filename, expected in legacy['files'].items():
        assert file_sha(pg_base / 'releases/0.1.1/postgres' / filename) == expected
    assert capture['passed'] and capture['actualDatabaseExecution'] and (len(capture['scenarios']) == 7) and (capture['replayedCapsules'] == 4)
    assert capture['captureSource']['analysisCoreSha256'] == pg_manifest['coreSha256']
    assert capture['captureSource']['captureCoreSha256'] == pg_manifest['captureCoreSha256']
    for key, path in (('adapterSha256', 'integrations/python/moontxnwitness_capture/capture.py'), ('fixtureSha256', 'scripts/capture-postgres-test.py'), ('e2eSha256', 'scripts/capture-postgres-e2e.mjs')):
        assert capture['captureSource'][key] == file_sha(source / path)
    profile = load(pg_base / 'provenance-profile/ci/profile-receipt.json')
    assert profile['passed'] and len(profile['scenarios']) == 4 and (len(profile['rejections']) == 11) and (profile['replayedCapsules'] == 2)
    dislock = load(pg_base / 'business/dislock/ci/business-receipt.json')
    presence = load(pg_base / 'provenance-presence/ci/presence-receipt.json')
    assert dislock['passed'] and dislock['actualDatabaseExecution']
    assert presence['passed'] and presence['actualDatabaseExecution']
    lifecycle_dir = pg_base / 'v3/postgres-ci'
    database, modeled = (load(lifecycle_dir / 'database-receipt.json'), load(lifecycle_dir / 'model-receipt.json'))
    assert database['passed'] and database['actualDatabaseExecution'] and (len(database['cases']) == 6)
    assert database['sourceSha256'] == file_sha(source / 'experiments/lifecycle_v3/postgres.py')
    assert modeled['passed'] and (not modeled['actualDatabaseExecution']) and (len(modeled['cases']) == 6)
    assert modeled['rawDatabaseExecutionReceipt']['sha256'] == file_sha(lifecycle_dir / 'database-receipt.json')
    assert modeled['sourceSha256'] == file_sha(source / 'experiments/lifecycle_v3/e2e.mjs')
    for binding in modeled['bindings']:
        data = read_bounded(lifecycle_dir / binding['file'])
        assert len(data) == binding['bytes'] and sha(data) == binding['sha256']
    for case in database['cases']:
        trace_raw = read_bounded(lifecycle_dir / case['trace'])
        assert sha(trace_raw) == case['sha256'] and case['serverFinalVersion'] == 'x0'
        events = [json.loads(line) for line in read_bounded(lifecycle_dir / (case['name'] + '.events.jsonl')).splitlines()]
        assert events == json.loads(trace_raw)['events']
        report = load(lifecycle_dir / (case['name'] + '.report.json'))
        assert report['status'] == 'inconclusive' and report['normalized']['observations'] == events
        assert any((gap['code'] == 'unmapped_statement' for gap in report['coverage']['gaps']))
        capsule = load(lifecycle_dir / (case['name'] + '.capsule.json'))
        for field in ('trace', 'normalized', 'report', 'evidence'):
            assert sha(capsule[field + 'Text'].encode()) == capsule[field + 'Sha256']
        assert json.loads(capsule['traceText']) == json.loads(trace_raw) and json.loads(capsule['reportText']) == report
    assert next((c for c in database['cases'] if c['name'] == 'cursor-position-survives'))['delivered'][2]['rows'] == [[1]]
    assert next((c for c in database['cases'] if c['name'] == 'cursor-position-survives'))['delivered'][4]['rows'] == [[2]]
    immutable(work / 'member-bindings.json', member_bindings)
    static = {'passed': True, 'sourceCommit': COMMIT, 'computedMoonBitSourceSha256': source_hash, 'core': core_results, 'remoteDatabaseExecutionVerified': True, 'legacyPgRoundsPerScenario': 20, 'captureScenarios': 7, 'ordinaryProfile': {'cases': 4, 'rejections': 11, 'capsules': 2}, 'dislockCases': len(dislock['scenarios']), 'presenceCases': len(presence['scenarios']), 'v3DatabaseCases': [case['name'] for case in database['cases']], 'v3ModelStatuses': [case['status'] for case in modeled['cases']], 'v3BindingsVerified': len(modeled['bindings']), 'actualCompiledBytesVerified': True}
    immutable(work / 'static-audit.json', static)
    return (source, pg_base, static)

def extra_audit(work, source, pg_base):
    checked = []

    def bind(path, expected):
        raw = read_bounded(path)
        expected = {'sha256': expected} if isinstance(expected, str) else expected
        assert sha(raw) == expected['sha256'], str(path)
        if 'bytes' in expected:
            assert len(raw) == expected['bytes'], str(path)
        checked.append({'file': str(path.relative_to(work)), 'sha256': sha(raw), 'bytes': len(raw)})

    def source_bindings(mapping):
        for name, expected in mapping.items():
            bind(work / 'artifact-postgres' / name if name.startswith('dist/') else source / name, expected)

    def bindings(base, items):
        for item in items:
            bind(base / item['file'], item)

    def nested_sources(base, document):
        mapping = document.get('sourceBindings', {})
        if isinstance(mapping, dict):
            for name, expected in mapping.items():
                if isinstance(expected, (str, dict)) and name.startswith(('scripts/', 'fixtures/', 'cmd/', 'integrations/', 'experiments/', 'verification/', 'dist/')):
                    assert '..' not in Path(name).parts and (not Path(name).is_absolute())
                    bind(base / name if name.startswith('dist/') else source / name, expected)

    def nested(base, value):
        if isinstance(value, dict):
            receipt = value.get('receipt')
            if isinstance(receipt, dict):
                bind(base / receipt['path'], receipt)
                assert load(base / receipt['path'])['passed']
                nested_sources(base, load(base / receipt['path']))
            elif isinstance(receipt, str) and receipt.startswith('verification/'):
                raw = read_bounded(base / receipt)
                if value.get('sha256'):
                    bind(base / receipt, value['sha256'])
                assert load(base / receipt)['passed']
                nested_sources(base, load(base / receipt))
            for key, child in value.items():
                if key != 'receipt':
                    nested(base, child)
        elif isinstance(value, list):
            for child in value:
                nested(base, child)
    for os_name in ('ubuntu-24.04', 'windows-2022'):
        folder = work / ('artifact-' + os_name)
        v = load(folder / 'verification/summary.json')['experimentalV3']
        nested(folder, v)
        assert v['appendList']['independentReference']['cases'] == 20071
        assert v['appendList']['acceptance']['inputCases'] == 20071 and v['appendList']['acceptance']['differences'] == 0
        assert (v['appendList']['acceptance']['checks'], v['appendList']['acceptance']['tamperCases']) == (45, 31)
        assert (v['boundedProtocolCollector']['testsRun'], v['postCloseIndependentAudit']['checks']) == (35, 42)
        assert (v['fixedSqlDiagnostic']['originals'], v['fixedSqlDiagnostic']['mutations'], v['fixedSqlDiagnostic']['checks']) == (7, 64, 86)
        assert (v['explicitSqlPolicy']['cases'], v['explicitSqlPolicy']['tamper'], v['explicitSqlPolicy']['checks']) == (7, 36, 199)
        assert v['boundedProtocolCollector']['sourceSha256'] == file_sha(source / 'integrations/python/moontxnwitness_capture/capture_v3.py')
    d = pg_base / 'list-v3/postgres-ci'
    db, model = (load(d / 'database-receipt.json'), load(d / 'model-receipt.json'))
    assert db['passed'] and db['actualDatabaseExecution'] and (db['roundsPerScenario'] == 20) and (not db['smokeOnly'])
    assert model['passed'] and (not model['actualDatabaseExecution']) and (not model['automaticG2OrPLClassification'])
    assert model['rawDatabaseExecutionReceipt']['sha256'] == file_sha(d / 'database-receipt.json')
    assert len(db['cases']) == len(model['cases']) == 120
    assert len({(c['name'], c['round']) for c in db['cases']}) == 120
    assert len({c['name'] for c in db['cases']}) == 6
    source_bindings(model['sourceBindings'])
    bindings(d, model['bindings'])
    for case in db['cases']:
        assert case['passed']
        folder = d / case['directory']
        bindings(folder, case['files'])
        trace = load(folder / 'trace.json')
        events = [json.loads(line) for line in read_bounded(folder / 'events.jsonl').splitlines()]
        assert trace['events'] == events
        report = load(folder / 'report.json')
        assert report['status'] == case['expectedModelStatus']
        assert report['normalized']['observations'] == events
        capsule = load(folder / 'capsule.json')
        assert json.loads(capsule['traceText']) == trace and json.loads(capsule['reportText']) == report
        for field in ('trace', 'normalized', 'report', 'evidence'):
            assert sha(capsule[field + 'Text'].encode()) == capsule[field + 'Sha256']
    d = pg_base / 'business/dislock/v3-ci'
    db, model = (load(d / 'database-receipt.json'), load(d / 'model-receipt.json'))
    assert db['passed'] and db['actualDatabaseExecution'] and (len(db['cases']) == 7)
    assert db['sourceBindings'] == db['sourceBindingsAfter'] and db['sourceBindingsUnchanged']
    assert model['passed'] and (not model['actualDatabaseExecution']) and (len(model['cases']) == 7)
    assert model['databaseReceiptSha256'] == file_sha(d / 'database-receipt.json')
    source_bindings(db['sourceBindings'])
    source_bindings(model['sourceBindings'])
    bindings(d, model['inputBindings'])
    bindings(d, model['outputBindings'])
    positive = {'schedule-and-server-clock', 'acquire-heartbeat-cleanup', 'body-exception-cleanup'}
    for case in model['cases']:
        assert case['passed'] and case['status'] == 'inconclusive'
        assert case['explicitSqlPolicy']['policy'] == 'dislock-f9946f0-sql-proof-1'
        assert case['explicitSqlPolicy']['status'] == ('consistent' if case['name'] in positive else 'inconclusive')
        assert case['explicitSqlPolicy']['coverageComplete'] == (case['name'] in positive)
    d = pg_base / 'business/dislock/v3-commit-ci'
    db, model = (load(d / 'commit-receipt.json'), load(d / 'model-receipt.json'))
    assert db['passed'] and db['actualDatabaseExecution'] and db['sourceBindingsUnchanged']
    assert db['sourceBindings'] == db['sourceBindingsAfter']
    source_bindings(db['sourceBindings'])
    assert model['passed'] and (model['committed'], model['aborted'], model['unknown']) == (1, 1, 0)
    assert model['databaseReceiptSha256'] == file_sha(d / 'commit-receipt.json')
    bindings(d, model['bindings'])
    aborted = next((x for x in db['outcomes'] if x['outcome'] == 'server-confirmed-aborted'))
    assert aborted['sqlstate'] == aborted['diagnosticSqlstate'] == '40001'
    assert aborted['pgresultPresent'] and aborted['originalExceptionIdentityPreserved']
    assert aborted['transactionStatus'] == 'IDLE' and aborted['idleRollbackAddedEvents'] == 0
    assert db['rollbackProof'] == model['rollbackProof']
    immutable(work / 'expanded-member-bindings.json', checked)
    return {'passed': True, 'newBindingChecks': len(checked), 'listDatabaseCases': 120, 'listScenarios': 6, 'listRoundsEach': 20, 'listInputRecordCount': 20071, 'listDistinctInputCount': 10118, 'dislockDefaultInconclusive': 7, 'dislockExplicitConsistent': 3, 'dislockExplicitInconclusive': 4, 'realCommitConfirmedAborted': 1, 'fullBusinessLifecycle': False, 'formalPerformanceMeasured': False}

def extra_relation_audit(work, source, pg_base):
    verified = []

    def bind(path, expected):
        raw = read_bounded(path)
        value = {'sha256': expected} if isinstance(expected, str) else expected
        assert sha(raw) == value['sha256'], str(path)
        if 'bytes' in value:
            assert len(raw) == value['bytes']
        verified.append({'file': str(path.relative_to(work)), 'bytes': len(raw), 'sha256': sha(raw)})
    for os_name in ('ubuntu-24.04', 'windows-2022'):
        d = work / ('artifact-' + os_name)
        v = load(d / 'verification/summary.json')['experimentalV3']
        reference, acceptance = (v['relationSet']['independentReference'], v['relationSet']['acceptance'])
        assert reference['passed'] and reference['cases'] == 1170 and (reference['generatedUniqueInputSha256Count'] == 1000)
        assert reference['normalizationCases'] == 1138 and reference['budgetCases'] == 10
        assert (acceptance['inputCases'], acceptance['differences'], acceptance['checks'], acceptance['tamperCases'], acceptance['witnesses'], acceptance['cliCases']) == (1170, 0, 57, 35, 704, 8)
        failure = v['executionFailures']['independentAudit']
        assert failure['passed'] and failure['checks'] == 24
        assert not v['executionFailures']['certifiesFailureAbsence']
        bind(source / 'scripts/relation-v3-oracle.py', reference['sourceSha256'])
    corpus = load(source / 'fixtures/relation-v3/manifest.json')
    for name, b in corpus['files'].items():
        bind(source / 'fixtures/relation-v3' / name, b)
    promoted = load(source / 'verification/relation-v3/frozen-corpus-promotion.json')
    for archive in promoted['archives']:
        bind(source / archive['file'], archive)
        with zipfile.ZipFile(source / archive['file']) as zipped:
            assert set(zipped.namelist()) == {m['file'] for m in archive['members']}
            for member in archive['members']:
                raw = zipped.read(member['file'])
                assert len(raw) == member['bytes'] and sha(raw) == member['sha256']
    d = pg_base / 'relation-v3/postgres-ci'
    m = pg_base / 'relation-v3/postgres-ci-model'
    database, model = (load(d / 'database-receipt.json'), load(m / 'model-receipt.json'))
    assert database['passed'] and database['actualDatabaseExecution'] and (database['roundsPerScenario'] == 20) and (database['scenarioCount'] == 8)
    assert len(database['scenarios']) == 160 and len({(c['name'], c['round']) for c in database['scenarios']}) == 160
    assert not database['completeAutomaticSqlCapture']
    assert database['sourceBindings'] == database['sourceBindingsAfter'] and database['sourceBindingsUnchanged']
    for name, b in database['sourceBindings'].items():
        bind(source / 'experiments/relation_v3' / name, b)
    assert model['passed'] and (not model['actualDatabaseExecution']) and (len(model['cases']) == 160)
    bind(d / 'database-receipt.json', model['sourceDatabaseExecutionReceipt'])
    bind(m / 'independent-oracle-executed.py', model['oracleSnapshot'])
    assert read_bounded(m / 'independent-oracle-executed.py') == read_bounded(source / 'scripts/relation-v3-oracle.py')
    assert model['productionBuild'] == load(work / 'artifact-postgres/dist/build-manifest.json')
    expected = {(c['name'], c['round']): c for c in database['scenarios']}
    for c in model['cases']:
        rawcase = expected[c['name'], c['round']]
        assert c['passed'] and c['status'] == c['independentOracleStatus'] == rawcase['expectedVerdict']
        for b in rawcase['artifacts']:
            bind(d / rawcase['path'] / b['path'], b)
        for name, b in c['artifactBindings'].items():
            bind(m / rawcase['path'] / name, b)
        trace = load(d / rawcase['path'] / 'trace.json')
        report = load(m / rawcase['path'] / 'report.json')
        capsule = load(m / rawcase['path'] / 'capsule.json')
        assert report['status'] == c['status'] and report['modelDefinition']['id'] == 'relation-set-serializable-v1'
        assert report['normalized']['observations'] == trace['events']
        assert json.loads(capsule['traceText']) == trace and json.loads(capsule['reportText']) == report
        for field in ('trace', 'normalized', 'report', 'evidence'):
            assert sha(capsule[field + 'Text'].encode()) == capsule[field + 'Sha256']
    raw_driver = "import importlib.util,json,sys\nfrom pathlib import Path\nsource,base=map(Path,sys.argv[1:])\nspec=importlib.util.spec_from_file_location('downloaded_independent_raw',source/'verification/relation-v3/independent-raw-chain-audit.py')\nmodule=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\nmodule.ROOT=source;module.BASE=base\nraise SystemExit(module.main())\n"
    command = [os.environ.get('MTW_PYTHON') or os.environ.get('PYTHON') or 'python', '-B', '-c', raw_driver, str(source), str(d)]
    process = run_bounded(command, cwd=source, env=child_environment(), output_prefix=work / 'relation-raw-chain', timeout=60)
    immutable(work / 'relation-ci-raw-chain-process.json', {'exitCode': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr, 'driverSha256': sha(raw_driver.encode()), 'downloadedImplementationSha256': file_sha(source / 'verification/relation-v3/independent-raw-chain-audit.py')})
    assert process.returncode == 0, 'Independent downloaded relation raw-chain audit failed'
    raw_result = json.loads(process.stdout.strip().splitlines()[-1])
    assert raw_result['passed'] and raw_result['complete'] and (raw_result['cases'] == 160)
    raw_receipt = source / raw_result['receipt']
    assert file_sha(raw_receipt) == raw_result['sha256']
    bind(raw_receipt, raw_result['sha256'])
    d = pg_base / 'faults/mlflow/ci'
    m = pg_base / 'faults/mlflow/ci-model'
    database, model = (load(d / 'receipt.json'), load(m / 'receipt.json'))
    assert database['passed'] and database['actualDatabaseExecution'] and (len(database['cases']) == 2)
    assert model['passed'] and len(model['cases']) == 2 and all((c['passed'] for c in model['checks']))
    assert model['sourceDatabaseExecutionRetained'] and (not model['actualDatabaseExecution'])
    for name, b in model['sourceBindings'].items():
        bind(work / 'artifact-postgres' / name if name.startswith('dist/') else source / name, b)
    for label, committed, faults in [('before', 1, 1), ('fixed', 2, 0)]:
        native = load(d / label / 'receipt.json')
        assert native['committed'] == committed and native['passed']
        assert native['runtimeSourceBindings'] == native['runtimeSourceBindingsAfter'] and native['runtimeSourceUnchanged']
        for name, b in native['runtimeSourceBindings'].items():
            bind(source / name, b)
            assert gzip.decompress(read_bounded(d / label / 'source-snapshots' / (Path(name).name + '.gz'))) == read_bounded(source / name)
        for filename, key in [('capture.json', 'captureSha256'), ('final-rows.json', 'finalRowsSha256'), ('sql-executions.jsonl', 'sqlExecutionsSha256')]:
            bind(d / label / filename, native[key])
        diagnostic = load(m / (label + '.faults.json'))
        report = load(m / (label + '.report.json'))
        assert diagnostic['observedFaultCount'] == faults and (not diagnostic['modelViolationClaim']) and (not diagnostic['databaseAuthenticityVerified']) and (not diagnostic['certifiesFailureAbsence'])
        assert report['status'] == 'inconclusive' and report['evidence'] is None and (not report['coverage']['complete'])
    performance = source / 'verification/releases/0.1.1/performance-v010-formal-2026-10-21T08-26-01-638Z.checkpoints/000038-7acd1520-065d-4bb0-bd78-bab0c880170a.json'
    bind(performance, '361dda5d6e52689583dc5040811e72753c1ecabd9ef1b151d2d7eb8fa1a7beee')
    perf = load(performance)
    assert perf['formalReleaseGatePassed'] and perf['complete'] and (len(perf['results']) == 20) and (len(perf['phases']) == 15)
    assert perf['provenance']['currentBuildManifest']['sourceSha256'] == load(work / 'artifact-postgres/dist/build-manifest.json')['sourceSha256']
    targets = perf['groups']
    thresholds = PROFILE['optimizationThresholds']
    measured_targets = {
        'graphSpeed': targets['graph']['geometricMeanSpeedup'] >= thresholds['graphSpeedMinimum'],
        'graphRss': targets['graph']['geometricMeanPeakMemoryRatio'] <= thresholds['graphRssRatioMaximum'],
        'searchLarge': targets['search-large']['geometricMeanSpeedup'] >= thresholds['searchLargeMinimum'],
        'reductionLarge': targets['reduction-large']['geometricMeanSpeedup'] >= thresholds['reductionLargeMinimum']}
    assert measured_targets == PROFILE['expectedOptimizationTargets']
    assert all(measured_targets.values()) == PROFILE['finalOptimizationGateExpectedPassed']
    immutable(work / 'relation-and-fault-bindings.json', verified)
    return {'passed': True, 'bindingChecks': len(verified), 'relationIndependentInputs': 1170, 'relationDatabaseScenarios': 8, 'relationRoundsEach': 20, 'relationDatabaseCases': 160, 'mlflowAffectedComponentCases': 2, 'mlflowFullApplicationExecuted': False, 'formalRegressionGatePassed': True, 'finalOptimizationTargetsPassed': all(measured_targets.values()), 'optimizationTargetResults': measured_targets, 'optimizationThresholds': thresholds, 'measuredPerformanceGroups': targets, 'relationRawChainIndependentCases': 160, 'relationRawChainReceiptSha256': raw_result['sha256'], 'packageArchivesDownloaded': False, 'packageLimitation': 'CI uploaded actual runtime bytes and package receipts/checksums, but not the generated source/portable ZIP archives themselves.'}
NODE_DRIVER = "\nimport assert from 'node:assert/strict';\nimport {readFileSync as nativeReadFileSync,writeFileSync,mkdirSync,statSync} from 'node:fs';\nconst readFileSync=(path,...args)=>{assert(statSync(path).size<=32*1024*1024,'Consumer input byte limit');return nativeReadFileSync(path,...args);};\nimport {resolve} from 'node:path';\nimport {spawnSync} from 'node:child_process';\nimport * as sdk from './dist/sdk.mjs';\nimport * as evidence from './dist/evidence.mjs';\nconst base=process.cwd(), pg=process.argv[2], cases=[];\nconst load=p=>JSON.parse(readFileSync(p,'utf8'));\nconst output=resolve('audit-output');mkdirSync(output);\nconst check=(name,fn)=>{try{fn();cases.push({name,passed:true});}catch(e){cases.push({name,passed:false,error:String(e.message).replaceAll(base,'<fresh>').replaceAll(pg,'<downloaded-pg>')});}};\nconst trace=load('fixtures/v3/write-skew-safe-projection.json');\nlet report,proof;\ncheck('v3-real-runtime-import-and-analysis',()=>{assert.equal(sdk.version(),'0.1.1');report=sdk.analyzeV3(trace);assert.equal(report.status,'violation');assert.equal(report.normalized.status,'ready');});\ncheck('v3-report-verification',()=>assert.equal(sdk.verifyV3(trace,report).valid,true));\ncheck('v3-capsule-and-replay',()=>{proof=sdk.makeCapsuleV3(trace,report);assert.equal(sdk.replayCapsuleV3(proof).valid,true);});\ncheck('v3-recomputed-digest-forged-conclusion-rejected',()=>{const c=JSON.parse(proof),r=JSON.parse(c.reportText);r.status='consistent';c.reportText=JSON.stringify(r);c.reportSha256=(awaitHash(c.reportText));assert.equal(sdk.replayCapsuleV3(JSON.stringify(c)).valid,false);});\nfunction awaitHash(text){return createHash('sha256').update(text).digest('hex');}\nimport {createHash} from 'node:crypto';\ncheck('v3-own-read-before-rollback-observation-retained',()=>{const t=load('fixtures/v3/read-of-later-reverted-own-write.json'),n=sdk.normalizeCaptureV3(t);assert.equal(n.status,'ready');assert.deepEqual(n.observations,t.events);assert.notEqual(n.effects[0].revertedBy,null);assert.deepEqual(n.history.transactions[0].ops,[]);});\ncheck('v3-own-read-after-rollback-remains-incomplete',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/read-after-rollback-revoked-own-write.json'));assert.equal(n.status,'inconclusive');assert.equal(n.history,null);assert.ok(n.coverage.gaps.some(g=>g.code==='own_read_mismatch'));});\ncheck('v3-release-does-not-commit',()=>{const n=sdk.normalizeCaptureV3(load('fixtures/v3/release-is-not-commit.json'));assert.equal(n.status,'inconclusive');assert.equal(n.transactions[0].status,'unknown');});\ncheck('v3-unknown-commit-not-cured-by-rollback',()=>{const r=sdk.analyzeV3(load('fixtures/v3/rollback-after-request-not-proof.json'));assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);});\ncheck('v3-source-closure-and-budget',()=>{const t=load('fixtures/v3/reduction-source-closure.json'),z=sdk.reduceV3(t,{maxChecks:0}),r=sdk.reduceV3(t,{maxChecks:256});assert.equal(z.oneMinimal,false);assert.equal(z.checks,0);assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['noise']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['source','A','B']);});\ncheck('v3-disk-journal-export-runtime-analysis',()=>{const r=sdk.analyzeV3(load('journal-export.json'));assert.equal(r.status,'consistent');assert.equal(r.normalized.status,'ready');});\nconst old=load('examples/write-skew.json');let r1,p1,r2,p2;\ncheck('legacy-v1-actual-core-analysis',()=>{r1=sdk.analyze(old);assert.equal(r1.status,'violation');});\ncheck('legacy-v1-capsule-replay',()=>{p1=evidence.makeCapsule(JSON.stringify(old),r1);assert.equal(JSON.parse(p1).format,'moontxnwitness-replay/v1');assert.equal(evidence.replayCapsule(p1).valid,true);});\ncheck('legacy-v2-balanced-actual-core-analysis',()=>{r2=sdk.analyzeWithOptions(old);assert.equal(r2.schemaVersion,2);assert.equal(r2.status,'violation');});\ncheck('legacy-v2-capsule-replay',()=>{p2=evidence.makeCapsule(JSON.stringify(old),r2);assert.equal(JSON.parse(p2).format,'moontxnwitness-replay/v2');assert.equal(evidence.replayCapsule(p2).valid,true);});\ncheck('capsule-generations-do-not-mix',()=>{assert.equal(sdk.replayCapsuleV3(p1).valid,false);assert.equal(sdk.replayCapsuleV3(p2).valid,false);assert.equal(evidence.replayCapsule(proof).valid,false);});\nfor(const name of ['read-before-rollback','read-after-rollback','released-child-parent-rollback','duplicate-name-reveal','repeated-rollback-target','cursor-position-survives'])check('downloaded-postgres-v3-'+name,()=>{const path=resolve(pg,'v3/postgres-ci',name),t=load(path+'.trace.json'),r=load(path+'.report.json');assert.equal(sdk.verifyV3(t,r).valid,true);const replay=sdk.replayCapsuleV3(readFileSync(path+'.capsule.json','utf8'));assert.equal(replay.valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.deepEqual(r.normalized.observations,t.events);assert.ok(r.coverage.gaps.some(g=>g.code==='unmapped_statement'));});\nfor(const name of ['rr','serial','mini'])check('downloaded-postgres-v2-'+name,()=>assert.equal(evidence.replayCapsule(readFileSync(resolve(pg,'releases/0.1.1/postgres',name+'.capsule.json'),'utf8')).valid,true));\nwriteFileSync(resolve(output,'v3-report.json'),JSON.stringify(report));writeFileSync(resolve(output,'v3-capsule.json'),proof);writeFileSync(resolve(output,'v1-capsule.json'),p1);writeFileSync(resolve(output,'v2-capsule.json'),p2);\nfunction cli(name,args,code,predicate){check(name,()=>{const p=spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:base,encoding:'utf8',windowsHide:true,timeout:30000,maxBuffer:8*1024*1024});const actual={args,exitCode:p.status,stdout:p.stdout,stderr:p.stderr,error:p.error?.name||null};writeFileSync(resolve(output,name+'.process.json'),JSON.stringify(actual,null,2));assert.equal(p.error,undefined);assert.equal(p.status,code,p.stderr);predicate(JSON.parse(p.stdout));});}\ncli('cli-v3-ingest',['ingest-v3','fixtures/v3/write-skew-safe-projection.json'],0,r=>assert.equal(r.status,'ready'));\ncli('cli-v3-analysis',['check-v3','fixtures/v3/write-skew-safe-projection.json'],1,r=>assert.equal(r.status,'violation'));\ncli('cli-v3-verify',['verify-v3','fixtures/v3/write-skew-safe-projection.json','audit-output/v3-report.json'],0,r=>assert.equal(r.valid,true));\ncli('cli-v3-replay',['replay-v3','audit-output/v3-capsule.json'],0,r=>assert.equal(r.valid,true));\ncli('cli-v3-reduce',['reduce-v3','fixtures/v3/reduction-source-closure.json'],0,r=>assert.equal(r.oneMinimal,true));\ncli('cli-v3-unknown',['check-v3','fixtures/v3/rollback-after-request-not-proof.json'],3,r=>assert.equal(r.status,'inconclusive'));\ncli('cli-v3-invalid',['ingest-v3','fixtures/v3/wrong-schema.json'],2,r=>assert.equal(r.status,'invalid'));\ncli('cli-v1-replay',['replay','audit-output/v1-capsule.json'],0,r=>assert.equal(r.valid,true));\ncli('cli-v2-replay',['replay','audit-output/v2-capsule.json'],0,r=>assert.equal(r.valid,true));\n\nconst listDB=load(resolve(pg,'list-v3/postgres-ci/database-receipt.json'));\nfor(const c of listDB.cases)check('downloaded-list-'+c.name+'-'+c.round,()=>{\n const folder=resolve(pg,'list-v3/postgres-ci',c.directory),t=load(resolve(folder,'trace.json')),r=load(resolve(folder,'report.json'));\n assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(folder,'capsule.json'),'utf8')).valid,true);\n assert.equal(r.status,c.expectedModelStatus);assert.equal(r.modelDefinition.id,'append-list-serializable-v1');\n});\nconst policy='dislock-f9946f0-sql-proof-1';\nconst sqlDB=load(resolve(pg,'business/dislock/v3-ci/model-receipt.json'));\nfor(const c of sqlDB.cases)check('downloaded-business-default-and-policy-'+c.name,()=>{\n const d=resolve(pg,'business/dislock/v3-ci',c.name),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json')),s=load(resolve(d,'sql-proof-report.json'));\n assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);\n assert.equal(sdk.verifyV3(t,s).valid,true);assert.equal(s.status,c.explicitSqlPolicy.status);\n assert.deepEqual(sdk.normalizeCaptureV3(t,{sqlProof:policy}),s.normalized);\n assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'sql-proof-capsule.json'),'utf8')).valid,true);\n});\ncheck('downloaded-real-commit-40001-source-proof',()=>{\n const d=resolve(pg,'business/dislock/v3-commit-ci'),t=load(resolve(d,'capture.json')),r=load(resolve(d,'model-report.json'));\n assert.equal(sdk.verifyV3(t,r).valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.normalized.transactions.filter(x=>x.status==='aborted').length,1);\n assert.equal(r.normalized.transactions.filter(x=>x.status==='unknown').length,0);assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(d,'capsule.json'),'utf8')).valid,true);\n});\ncheck('explicit-sql-source-closure-reduction',()=>{\n const t=load('verification/v3/synthetic-dislock-source-closure-v1/trace.json'),r=sdk.reduceV3(t,{analysisOptions:{sqlProof:policy},maxChecks:256});\n assert.equal(r.status,'reduced');assert.equal(r.oneMinimal,true);assert.deepEqual(r.removed,['N']);assert.deepEqual(r.report.normalized.transactions.map(t=>t.id),['P','A','B']);\n assert.equal(sdk.verifyV3(r.reducedCapture,r.report).valid,true);\n});\nconst sqlTrace=resolve(pg,'business/dislock/v3-ci/schedule-and-server-clock/capture.json');\ncli('cli-explicit-sql-ingest',['ingest-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'ready'));\ncli('cli-explicit-sql-check',['check-v3',sqlTrace,'--sql-proof',policy],0,r=>assert.equal(r.status,'consistent'));\ncli('cli-default-sql-stays-incomplete',['check-v3',sqlTrace],3,r=>assert.equal(r.status,'inconclusive'));\nconst listTrace=resolve(pg,'list-v3/postgres-ci/duplicate-business-values-00/trace.json');\ncli('cli-append-list-check',['check-v3',listTrace],0,r=>assert.equal(r.status,'consistent'));\n\n\nconst relationDb=load(resolve(pg,'relation-v3/postgres-ci/database-receipt.json'));\nfor(const c of relationDb.scenarios)check('downloaded-relation-'+c.name+'-'+c.round,()=>{\n const d=resolve(pg,'relation-v3/postgres-ci',c.path),m=resolve(pg,'relation-v3/postgres-ci-model',c.path),t=load(resolve(d,'trace.json')),r=load(resolve(m,'report.json'));\n assert.equal(r.status,c.expectedVerdict);assert.equal(r.modelDefinition.id,'relation-set-serializable-v1');assert.equal(sdk.verifyV3(t,r).valid,true);\n assert.equal(sdk.replayCapsuleV3(readFileSync(resolve(m,'capsule.json'),'utf8')).valid,true);assert.deepEqual(r.normalized.observations,t.events);\n});\nconst relationTrace=resolve(pg,'relation-v3/postgres-ci/insert-phantom-01/trace.json');\ncheck('relation-source-backed-reduction',()=>{const t=load(relationTrace),r=sdk.reduceV3(t,{maxChecks:256});assert.equal(r.oneMinimal,true);assert.equal(r.report.status,'violation');assert.equal(sdk.verifyV3(r.reducedCapture,r.report).valid,true);});\ncli('cli-relation-violation',['check-v3',relationTrace],1,r=>assert.equal(r.modelDefinition.id,'relation-set-serializable-v1'));\ncli('cli-relation-consistent',['check-v3',resolve(pg,'relation-v3/postgres-ci/empty-result-01/trace.json')],0,r=>assert.equal(r.status,'consistent'));\nfor(const label of ['before','fixed'])check('actual-fault-channel-'+label+'-cannot-certify-isolation-or-authenticity',()=>{\n const d=resolve(pg,'faults/mlflow/ci',label),t=load(resolve(d,'capture.json')),f=sdk.inspectExecutionFailuresV3(t),r=sdk.analyzeV3(t);\n assert.equal(f.valid,true);assert.equal(f.observedFaultCount,label==='before'?1:0);assert.equal(f.databaseAuthenticityVerified,false);assert.equal(f.certifiesFailureAbsence,false);assert.equal(f.modelViolationClaim,false);\n assert.equal(r.status,'inconclusive');assert.equal(r.evidence,null);assert.equal(sdk.replayCapsuleV3(sdk.makeCapsuleV3(t,r)).valid,true);\n});\ncli('cli-execution-fault-valid-input',['failures-v3',resolve(pg,'faults/mlflow/ci/before/capture.json')],0,r=>{assert.equal(r.valid,true);assert.equal(r.faults[0].kind,'deadlock');assert.equal(r.databaseAuthenticityVerified,false);assert.equal(r.captureCoverage.complete,false);});\n\nconst result={passed:cases.every(c=>c.passed),checks:cases.length,cases,node:process.version,platform:process.platform,localDatabaseExecution:false,localBuild:false,authorRuntimeOrCacheUsed:false};writeFileSync(resolve(output,'fresh-result.json'),JSON.stringify(result,null,2)+'\\n');console.log(JSON.stringify(result));if(!result.passed)process.exitCode=1;\n"
JOURNAL_DRIVER = "\nimport hashlib,json,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path.cwd()/'integrations/python'))\nfrom moontxnwitness_capture.journal_v3 import SegmentedJournal,JournalReader\ntrace=json.loads(Path('fixtures/v3/initial-read-commit.json').read_bytes())\nw=SegmentedJournal('fresh-journal')\nfor event in trace['events']:\n    assert w.append(event).accepted\nassert w.close(source_closed=True).complete\nresult=JournalReader('fresh-journal').export('journal-export.json',clock_domain=trace['clockDomain'],exclusive_writers=True)\nraw=Path('journal-export.json').read_bytes()\nassert result['bytes']==len(raw) and result['sha256']==hashlib.sha256(raw).hexdigest()\nassert json.loads(raw)==trace\nprint(json.dumps({'passed':True,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'actualDatabaseExecution':False}))\n"

def fresh(work, source, pg_base):
    results = []
    for os_name in ('ubuntu-24.04', 'windows-2022'):
        directory = work / ('fresh-' + os_name)
        shutil.copytree(source, directory)
        assert not any(((directory / name).exists() for name in ('dist', '_build', 'node_modules', '.local-toolchain.json')))
        shutil.copytree(work / ('artifact-' + os_name) / 'dist', directory / 'dist')
        immutable(directory / 'independent-driver.mjs', NODE_DRIVER.encode())
        immutable(directory / 'independent-journal.py', JOURNAL_DRIVER.encode())
        env = child_environment()
        env['MTW_JOURNAL_SCRATCH'] = str(work)
        python = os.environ.get('MTW_PYTHON') or os.environ.get('PYTHON') or 'python'
        downloaded_database = directory / 'verification/faults/mlflow/downloaded-public-ci'
        shutil.copytree(pg_base / 'faults/mlflow/ci', downloaded_database)
        copies = []
        for original in sorted((pg_base / 'faults/mlflow/ci').rglob('*')):
            if original.is_file():
                name = original.relative_to(pg_base / 'faults/mlflow/ci')
                actual = file_binding(original)
                assert file_binding(downloaded_database / name) == actual
                copies.append({'file': name.as_posix(), **actual})
        immutable(work / ('fresh-' + os_name + '-copied-inputs.json'), copies)
        processes = []
        for name, command in (('journal', [python, '-B', 'independent-journal.py']), ('runtime', ['node', 'independent-driver.mjs', str(pg_base)]), ('mlflow-independent', [python, '-B', 'verification/v3/tools/mlflow_execution_audit.py', '--database', str(downloaded_database)])):
            process = run_bounded(command, cwd=directory, env=env, output_prefix=directory / (name + '-output'), timeout=120)
            value = {'name': name, 'exitCode': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr, 'command': [str(item).replace(str(directory), '<fresh>') for item in command]}
            immutable(directory / (name + '-process.json'), value)
            processes.append({'name': name, 'exitCode': process.returncode, 'stdoutSha256': sha(process.stdout.encode()), 'stderrSha256': sha(process.stderr.encode())})
            if not process.returncode and name == 'mlflow-independent':
                summary = json.loads(process.stdout.strip().splitlines()[-1])
                assert summary['passed'] and summary['complete'] and (summary['checks'] == PROFILE['freshMlflowChecksPerArtifact'] == 24)
                assert file_sha(directory / summary['receipt']) == summary['sha256']
            if process.returncode:
                results.append({'artifactOrigin': os_name, 'passed': False, 'processes': processes})
                print(json.dumps({'progress': 'fresh-first-failure', 'artifactOrigin': os_name, 'process': name, 'exitCode': process.returncode}), flush=True)
                break
        else:
            result = load(directory / 'audit-output/fresh-result.json')
            assert result['passed'] and result['checks'] == PROFILE['freshRuntimeChecksPerArtifact'] == 332
            results.append({'artifactOrigin': os_name, 'passed': True, 'processes': processes, 'checks': result['checks'], 'node': result['node'], 'hostPlatform': result['platform'], 'resultSha256': file_sha(directory / 'audit-output/fresh-result.json'), 'extraMlflowIndependentChecks': 24, 'actualCoreSha256': file_sha(directory / 'dist/core.mjs'), 'actualCaptureCoreSha256': file_sha(directory / 'dist/capture-core.mjs'), 'nodeDriverSha256': sha(NODE_DRIVER.encode()), 'journalDriverSha256': sha(JOURNAL_DRIVER.encode()), 'cases': result['cases']})
            print(json.dumps({'progress': 'fresh-complete', 'artifactOrigin': os_name, 'checks': result['checks'], 'passed': True}), flush=True)
    immutable(work / 'fresh-audit.json', results)
    return results


def read_profile(path):
    raw = read_bounded(path, 8192)
    assert sha(raw) == PROFILE_SHA256, 'Only the independently reviewed fixed profile is accepted'
    value = json.loads(raw)
    assert value['repository'] == 'HhWw96/moontxnwitness' and value['sourceCommit'] == COMMIT
    assert (value['coreTestsPerTarget'], value['nativeTests'], value['testedBindings'], value['nonDistBindings'],
            value['freshPackageConsumers'], value['freshRuntimeChecksPerArtifact'], value['freshMlflowChecksPerArtifact']) == (563, 563, 347, 339, 76, 332, 24)
    return value


def main():
    global PROFILE
    parser = argparse.ArgumentParser(description='Explicit GitHub Actions independent public-artifact audit candidate')
    parser.add_argument('--mode', choices=['github-actions'], required=True)
    parser.add_argument('--phase', choices=['fetch', 'audit'], required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        PROFILE = read_profile(args.profile)
        guard_environment(need_token=args.phase == 'fetch')
        if args.phase == 'audit' and os.environ.get('GITHUB_TOKEN'):
            raise ValueError('Run the audit in a separate step without a GITHUB_TOKEN environment variable')
    except Exception as error:
        print(json.dumps({'passed': False, 'complete': False, 'phase': args.phase,
                          'errorClass': type(error).__name__, 'error': str(error),
                          'checks': 'not-executed'}), flush=True)
        return 2
    if args.phase == 'fetch':
        try:
            fetch(args.work, PROFILE)
            print(json.dumps({'passed': True, 'complete': True, 'phase': 'fetch', 'downloadedFiles': 7,
                              'nextPhase': 'not-executed', 'tokenPersisted': False, 'signedUrlPersisted': False}), flush=True)
            return 0
        except Exception as error:
            print(json.dumps({'passed': False, 'complete': False, 'phase': 'fetch',
                              'errorClass': type(error).__name__, 'checks': 'not-executed'}), flush=True)
            return 1
    if args.output is None:
        parser.error('--output is required for the audit phase')
    names = ['download-integrity', 'fixed-source-and-core-ci', 'legacy-v3-db-evidence',
             'relation-and-failure-evidence', 'fresh-downloaded-runtime']
    receipt = {
        'schema': 1, 'scope': 'Independent AI public development-checkpoint acceptance on a separate Linux runner',
        'authenticationMode': 'explicit-repository-workflow-token-fetch-only', 'sourceCommit': COMMIT,
        'independentAIAcceptance': True, 'humanAcceptance': False, 'stableReleasePublished': False,
        'fullApplicationIntegration': False, 'localBuild': False, 'localDatabaseExecution': False,
        'formalPerformanceExecuted': False, 'authorRuntimeOrCacheUsed': False,
        'complete': False, 'passed': False, 'profileSha256': PROFILE_SHA256,
        'auditScriptSha256': file_sha(__file__), 'transportScriptSha256': file_sha(Path(__file__).with_name('transport.py')),
        'independentWorkflowRun': {'id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')},
        'stages': [{'name': n, 'status': 'not-executed'} for n in names]}
    sequence = 0

    def stage(index, operation):
        nonlocal sequence
        row = receipt['stages'][index]
        row.update(status='running', startedAt=datetime.now(timezone.utc).isoformat())
        sequence += 1
        immutable(args.work / ('audit-stage-' + str(sequence).zfill(3) + '.json'), row)
        try:
            value = operation()
            row.update(status='passed', finishedAt=datetime.now(timezone.utc).isoformat())
            return value
        except Exception as error:
            row.update(status='failed', errorClass=type(error).__name__, finishedAt=datetime.now(timezone.utc).isoformat())
            raise
        finally:
            sequence += 1
            immutable(args.work / ('audit-stage-' + str(sequence).zfill(3) + '.json'), row)
            print(json.dumps({'stage': row['name'], 'status': row['status']}), flush=True)

    try:
        def transport_check():
            marker = load(args.work / 'fetch-complete.json')
            assert marker == {'complete': True, 'files': 7, 'extractions': 4}
            transport = load(args.work / 'transport-audit.json')
            assert transport['complete'] and transport['sourceCommit'] == COMMIT
            assert len(transport['downloads']) == 7 and len(transport['artifacts']) == len(transport['jobs']) == 3
            for item in transport['downloads']:
                actual = file_binding(args.work / item['file'])
                assert actual == {k: item[k] for k in ('bytes', 'sha256')}
                if item['githubDigest']:
                    assert item['githubDigest'] == 'sha256:' + actual['sha256']
            return transport
        transport = stage(0, transport_check)
        source, pg_base, static = stage(1, lambda: audit(args.work))
        static['expanded'] = stage(2, lambda: extra_audit(args.work, source, pg_base))
        static['relationAndFailures'] = stage(3, lambda: extra_relation_audit(args.work, source, pg_base))
        receipt['static'] = static
        def checked_fresh():
            results = fresh(args.work, source, pg_base)
            receipt['fresh'] = results
            assert len(results) == 2 and all(r['passed'] for r in results), 'Fresh runtime acceptance failed'
            return results
        receipt['fresh'] = stage(4, checked_fresh)
        receipt['workflowRuns'] = [{k: r[k] for k in ('id', 'html_url', 'head_sha', 'status', 'conclusion', 'run_attempt')}
                                   for r in load(args.work / 'completed-run-states.json')]
        receipt['downloadedFiles'] = transport['downloads']
        receipt['transportAuditSha256'] = file_sha(args.work / 'transport-audit.json')
        receipt['memberBindingsSha256'] = file_sha(args.work / 'member-bindings.json')
        receipt.update(complete=True, passed=True)
    except Exception as error:
        receipt['errorClass'] = type(error).__name__
        receipt['error'] = str(error).replace(str(args.work), '<work>').replace(str(ROOT), '<audit-tool>')
    receipt['finishedAt'] = datetime.now(timezone.utc).isoformat()
    receipt['limitations'] = [
        'Independent AI-operated acceptance; not participant/human or organizer acceptance.',
        'The Linux runner executes both downloaded JS artifact origins; Windows/Native execution is checked from their original CI logs.',
        'Actual CI runtime bytes are downloaded; generated source/portable release ZIPs were not uploaded by the original packaging workflow.',
        'Final RSS and reduction targets remain unmet; this is not a stable-release acceptance gate.',
        'No compilation, database workload, performance run or full application run is performed here.']
    immutable(args.output, receipt)
    print(json.dumps({'passed': receipt['passed'], 'complete': receipt['complete'], 'receiptSha256': file_sha(args.output),
                      'stages': receipt['stages'], 'errorClass': receipt.get('errorClass')}), flush=True)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
