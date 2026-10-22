"""Download public bytes, verify hashes, and exercise a registry-only consumer."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from publication_download import MAX_MANIFEST_BYTES, download_file, extract_zip, sha256_file
from publication_ci import wait_for_successful_run_list

ROOT = Path(__file__).resolve().parent.parent
CURRENT_VERSION = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
VERSION = sys.argv[1] if len(sys.argv) == 2 else CURRENT_VERSION
assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', VERSION)
MODULE = 'HhWw96/moontxnwitness'
REPOSITORY = 'https://github.com/' + MODULE
NAME = 'MoonTxnWitness-v' + VERSION
WORK_PARENT = ROOT / 'artifacts/public-verification'
WORK_PARENT.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix='run-', dir=WORK_PARENT))
ENV = dict(os.environ)
HOME = ENV.get('MOON_HOME')
if not HOME:
    config = ROOT / '.local-toolchain.json'
    HOME = json.loads(config.read_text(encoding='utf-8'))['moonHome'] if config.exists() else None
if HOME:
    ENV['MOON_HOME'] = HOME
    ENV['PATH'] = str(Path(HOME) / 'bin') + os.pathsep + ENV.get('PATH', '')
MOON = str(Path(HOME) / 'bin' / ('moon.exe' if os.name == 'nt' else 'moon')) if HOME else 'moon'
NODE = shutil.which('node')
assert NODE, 'Node.js is required'
RECEIPT = {'tool': 'MoonTxnWitness', 'version': VERSION, 'account': 'HhWw96', 'passed': False, 'startedAt': datetime.now(timezone.utc).isoformat(), 'github': {'repository': REPOSITORY, 'release': REPOSITORY + '/releases/tag/v' + VERSION}, 'mooncakes': {'module': MODULE, 'version': VERSION, 'page': 'https://mooncakes.io/docs/' + MODULE}}


def run(args, cwd=ROOT, expected=0, timeout=240):
    result = subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode != expected:
        print(result.stdout, result.stderr)
        raise RuntimeError('Verification command failed: ' + Path(args[0]).name)
    return result.stdout


def download(url, name, **options):
    return download_file(url, WORK / name,
                         user_agent='MoonTxnWitness-public-verification/' + VERSION, **options)


def digest(path):
    return sha256_file(path)


def history(name):
    return json.dumps((ROOT / ('examples/' + name + '.json')).read_text(encoding='utf-8'), ensure_ascii=True)


try:
    # No Authorization header, saved browser session or GitHub token is used here.
    prefix = REPOSITORY + '/releases/download/v' + VERSION + '/'
    sums = download(prefix + NAME + '-SHA256SUMS.txt', 'SHA256SUMS', max_bytes=MAX_MANIFEST_BYTES)
    assets = []
    for line in sums.read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        assert re.fullmatch(r'[0-9a-f]{64}', expected) and Path(name).name == name
        assert name in {NAME + '-source.zip', NAME + '-portable.zip'}
        path = download(prefix + name, name, expected_sha256=expected)
        assets.append({'name': name, 'url': prefix + name, 'bytes': path.stat().st_size, 'sha256': expected, 'anonymousDownload': True})
    assert len(assets) == 2
    RECEIPT['github']['assets'] = assets
    destination = WORK / 'portable'
    extraction = extract_zip(WORK / (NAME + '-portable.zip'), destination)
    RECEIPT['github']['portableExtraction'] = {key: extraction[key] for key in ('entries', 'files', 'uncompressedBytes')}
    portable = destination / NAME
    assert run([NODE, 'dist/moontxnwitness.mjs', '--version'], portable).strip() == VERSION
    assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'check', 'examples/write-skew.json', '--format', 'json'], portable, 1))['status'] == 'violation'
    demo = json.loads(run([NODE, 'dist/demo.mjs', '--json'], portable))
    assert demo['passed'] is True and demo['replayValid'] is True
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 0):
        assert demo['profile'] == 'balanced' and demo['reportSchemaVersion'] == 2
    assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay', str(portable / demo['outputDirectory'] / 'case.capsule.json')], portable))['valid'] is True
    RECEIPT['github']['downloadedRuntimeChecks'] = ['exact version', 'write-skew diagnosis', 'one-command demo', 'exported capsule replay']
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 11):
        for case in ('rr', 'serial', 'mini'):
            capsule = 'verification/releases/' + VERSION + '/postgres/' + case + '.capsule.json'
            assert json.loads(run([NODE, 'dist/moontxnwitness.mjs', 'replay', capsule], portable))['valid']
            RECEIPT['github']['downloadedRuntimeChecks'].append('actual PostgreSQL ' + case + ' capsule replay')
    print('Anonymous GitHub downloads, SHA-256 and downloaded runtime passed.', flush=True)

    registry_url = 'https://download.mooncakes.io/user/' + MODULE + '/' + VERSION + '.zip'
    registry_zip = download(registry_url, 'registry.zip')
    uploaded = ROOT / ('_build/publish/HhWw96-moontxnwitness-' + VERSION + '.zip')
    assert uploaded.is_file() and digest(registry_zip) == digest(uploaded), 'Registry bytes differ from uploaded package'
    RECEIPT['mooncakes'].update({'download': registry_url, 'sha256': digest(registry_zip), 'bytes': registry_zip.stat().st_size, 'uploadedBytesMatchPublicDownload': True})

    consumer = WORK / 'consumer'
    consumer.mkdir()
    (consumer / 'moon.mod').write_text('name = "local/published_consumer"\nversion = "0.0.0"\nlicense = "Apache-2.0"\n', encoding='utf-8')
    (consumer / 'moon.pkg').write_text('import { "HhWw96/moontxnwitness" @txn, "moonbitlang/core/json" }\n', encoding='utf-8')
    (consumer / 'consumer.mbt').write_text('///|\npub fn installed_version() -> String { @txn.version() }\n\n///|\npub fn analyze_history(text : String) -> Json {\n  @json.parse(@txn.analyze_json(text)) catch { _ => abort("Unexpected report JSON") }\n}\n', encoding='utf-8')
    test = f'''///|
fn load(text : String) -> @txn.History {{
  match @txn.parse_history(text) {{
    Ok(h) => h
    Err(_) => abort("Published fixture parse failed")
  }}
}}

///|
test "published exact version and positive history" {{
  assert_eq(installed_version(), "{VERSION}")
  assert_true(@txn.analyze(load({history('consistent')})).outcome == @txn.Consistent)
}}

///|
test "published shortest cycle provenance" {{
  let h = load({history('write-skew')})
  let r = @txn.analyze(h)
  assert_true(r.outcome == @txn.Violation)
  assert_eq(r.witness.length(), 2)
  assert_true(@txn.verify_cycle(h, r.witness))
}}

///|
test "published missing-order completion and exhaustive failure" {{
  assert_true(@txn.analyze(load({history('unknown-order')})).outcome == @txn.Consistent)
  let r = @txn.analyze(load({history('fractured-observation')}))
  assert_true(r.outcome == @txn.Violation)
  assert_eq(r.search.status, "exhausted")
  assert_true(r.witness.is_empty())
}}

///|
test "published transaction reduction" {{
  let r = @txn.reduce_history(load({history('noisy-write-skew')}))
  assert_true(r.one_minimal)
  assert_eq(r.history.transactions.length(), 2)
  assert_true(r.report.outcome == @txn.Violation)
}}

///|
test "published model comparison" {{
  let j = @txn.compare_models(load({history('strict-realtime')}))
  assert_true(j is Object(m) && m.get("classification") == Some("realtime-only-violation".to_json()))
}}

///|
test "published semantic report replay" {{
  let text = {history('write-skew')}
  let r = @txn.analyze(load(text))
  let j = @json.parse(@txn.replay_report_json(text, @txn.report_json(r).stringify()))
  assert_true(j is Object(m) && m.get("valid") == Some(true.to_json()))
}}
'''
    expected_tests = 6
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 9):
        test += f'''\n///|\ntest "published balanced profile and v2 replay" {{
  let text = {history('fractured-observation')}
  let result = @txn.analyze_with_options(load(text))
  assert_true(result.report.outcome == @txn.Violation)
  assert_eq(result.report.search.status, "exhausted")
  let j = @txn.analysis_result_json(result)
  let replay = @json.parse(@txn.replay_report_json(text, j.stringify()))
  assert_true(replay is Object(m) && m.get("valid") == Some(true.to_json()))
}}
'''
        expected_tests += 1
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 10):
        test += f'''\n///|\ntest "published balanced reduction" {{
  let result = @txn.reduce_with_options(load({history('noisy-write-skew')}))
  assert_true(result.reduction.one_minimal)
  assert_eq(result.reduction.history.transactions.length(), 2)
  assert_true(result.analysis.report.outcome == @txn.Violation)
}}
'''
        expected_tests += 1
    if tuple(map(int, VERSION.split('.'))) >= (0, 1, 1):
        complete_capture = json.loads((ROOT / 'examples/capture-complete.json').read_text(encoding='utf-8'))
        incomplete_capture = json.loads(json.dumps(complete_capture))
        incomplete_capture['events'].pop()
        test += f'''\n///|\ntest "published complete capture normalizes to analyzable history" {{
  let result = @json.parse(@txn.normalize_capture_json({json.dumps(json.dumps(complete_capture), ensure_ascii=True)}))
  match result {{
    Object(fields) => {{
      assert_eq(fields.get("status"), Some("ready".to_json()))
      assert_true(fields.get("coverage") is Some(Object(coverage)) && coverage.get("complete") == Some(true.to_json()))
      let h = load(fields.at("history").stringify())
      assert_true(@txn.analyze(h).outcome == @txn.Violation)
    }}
    _ => abort("Normalized capture object required")
  }}
}}

///|
test "published incomplete capture refuses a history" {{
  let result = @json.parse(@txn.normalize_capture_json({json.dumps(json.dumps(incomplete_capture), ensure_ascii=True)}))
  match result {{
    Object(fields) => {{
      assert_eq(fields.get("status"), Some("inconclusive".to_json()))
      assert_eq(fields.get("history"), Some(Json::null()))
      assert_true(fields.get("coverage") is Some(Object(coverage)) && coverage.get("complete") == Some(false.to_json()))
    }}
    _ => abort("Normalized capture object required")
  }}
}}
'''
        expected_tests += 2
    (consumer / 'consumer_wbtest.mbt').write_text(test, encoding='utf-8')
    run([MOON, 'add', MODULE + '@' + VERSION], consumer)
    assert not (consumer / 'moon.work').exists()
    installed = consumer / '.mooncakes' / MODULE / 'moon.mod'
    assert installed.is_file() and 'version = "' + VERSION + '"' in installed.read_text(encoding='utf-8')
    targets = []
    for target in ('js', 'wasm-gc'):
        output = run([MOON, 'test', '--target', target, '--deny-warn'], consumer)
        assert f'Total tests: {expected_tests}, passed: {expected_tests}, failed: 0.' in output
        targets.append({'target': target, 'tests': expected_tests, 'passed': True})
    RECEIPT['mooncakes']['registryOnlyConsumer'] = {'passed': True, 'workspaceOverride': False, 'targets': targets}
    print(f'Registry-only JS and Wasm GC consumers: {expected_tests} tests each passed.', flush=True)

    tag_sha = run(['git', 'rev-list', '-n', '1', 'v' + VERSION]).strip()
    runs = json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', tag_sha, '--workflow', 'ci.yml', '--json', 'databaseId,conclusion,headSha', '--limit', '10']))
    successful = [item for item in runs if item['headSha'] == tag_sha and item['conclusion'] == 'success']
    assert successful, 'No successful CI run for the exact release commit'
    ci = json.loads(run(['gh', 'run', 'view', str(successful[0]['databaseId']), '--repo', MODULE, '--json', 'conclusion,headSha,url,jobs']))
    assert ci['conclusion'] == 'success'
    RECEIPT['github']['ci'] = {'url': ci['url'], 'headSha': ci['headSha'], 'conclusion': ci['conclusion'], 'jobs': [{'name': job['name'], 'conclusion': job['conclusion']} for job in ci['jobs']], 'linuxNativeExecuted': any(step['name'] == 'Execute Native core on Linux' and step['conclusion'] == 'success' for job in ci['jobs'] for step in job['steps'])}
    assert RECEIPT['github']['ci']['linuxNativeExecuted'], 'Native execution must actually pass'
    if tuple(map(int, VERSION.split('.'))) >= (0, 0, 11):
        successful = wait_for_successful_run_list(
            lambda remaining: json.loads(run(['gh', 'run', 'list', '--repo', MODULE, '--commit', tag_sha, '--workflow', 'postgres.yml', '--json', 'databaseId,status,conclusion,headSha', '--limit', '10'], timeout=min(240, remaining))),
            tag_sha)
        repaired = False
        repair_path = ROOT / 'verification/releases' / VERSION / 'postgres-ci-repair.json'
        if not successful and repair_path.exists():
            repair = json.loads(repair_path.read_text(encoding='utf-8'))
            assert repair['sourceCommit'] == tag_sha
            candidate = json.loads(run(['gh', 'run', 'view', str(repair['runId']), '--repo', MODULE, '--json', 'conclusion,headSha']))
            assert candidate['conclusion'] == 'success' and candidate['headSha'] == repair['workflowCommit']
            successful = [{'databaseId': repair['runId']}]
            repaired = True
        assert successful, 'No successful independent PostgreSQL CI for this release source'
        pg_ci = json.loads(run(['gh', 'run', 'view', str(successful[0]['databaseId']), '--repo', MODULE, '--json', 'conclusion,headSha,url']))
        pg_dir = WORK / 'postgres-ci'
        run(['gh', 'run', 'download', str(successful[0]['databaseId']), '--repo', MODULE, '--name', 'actual-postgresql-evidence', '--dir', str(pg_dir)])
        candidates = list(pg_dir.rglob('postgres.json'))
        assert len(candidates) == 1
        pg_receipt = json.loads(candidates[0].read_text(encoding='utf-8'))
        assert pg_receipt['version'] == VERSION and pg_receipt['passed'] and pg_receipt['actualDatabaseExecution']
        assert pg_receipt['roundsPerScenario'] == 20 and len(pg_receipt['cases']) == 2
        assert all(case['rounds'] == 20 and len(case['results']) == 20 for case in pg_receipt['cases'])
        assert pg_receipt['server'].startswith('PostgreSQL 18.') and 'linux' in pg_receipt['server'].lower()
        attestations = list(pg_dir.rglob('postgres-ci-source.json'))
        assert len(attestations) == 1
        source = json.loads(attestations[0].read_text(encoding='utf-8'))
        assert source['sourceCommit'] == tag_sha and source['workflowCommit'] == pg_ci['headSha']
        cases = {case['isolation']: case for case in pg_receipt['cases']}
        assert all(row['initialConcurrentCommits'] == 2 and row['initialConcurrentAborts'] == 0 and row['finalOnCallCount'] == 0 for row in cases['REPEATABLE READ']['results'])
        assert all(row['initialConcurrentCommits'] == 1 and row['initialConcurrentAborts'] == 1 and row['sqlstates'] == ['40001'] and row['finalOnCallCount'] == 1 for row in cases['SERIALIZABLE']['results'])
        history_files = [path for path in pg_dir.rglob('rr-history.json')
                         if path.parent.name == 'postgres' and path.parent.parent.name == VERSION]
        assert len(history_files) == 1
        for name, expected in pg_receipt['files'].items():
            assert Path(name).name == name and digest(history_files[0].parent / name) == expected
        assert pg_receipt['oneMinimal'] and pg_receipt['minimalTransactions'] == 2 and pg_receipt['v2CapsulesReplayed'] == 3
        logs = list(pg_dir.rglob('postgres-server.log'))
        assert len(logs) == 1 and logs[0].stat().st_size > 0
        RECEIPT['github']['postgresCi'] = {**pg_ci, **source, 'workflowRepair': repaired, 'actualDatabaseExecution': True, 'roundsPerScenario': 20, 'server': pg_receipt['server'], 'receiptSha256': digest(candidates[0]), 'serverLogSha256': digest(logs[0]), 'oneMinimal': True, 'minimalTransactions': 2, 'v2CapsulesReplayed': 3}
        destination = ROOT / 'verification/releases' / VERSION
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'postgres-linux.json').write_text(json.dumps(pg_receipt, indent=2) + '\n', encoding='utf-8')
        (destination / 'postgres-linux-server.txt').write_bytes(logs[0].read_bytes())
    RECEIPT['passed'] = True
except Exception as error:
    RECEIPT['failure'] = type(error).__name__
    raise
finally:
    RECEIPT['finishedAt'] = datetime.now(timezone.utc).isoformat()
    destination = ROOT / 'verification/releases' / VERSION
    destination.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(RECEIPT, ensure_ascii=False, indent=2) + '\n'
    (destination / ('publication-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')).write_text(serialized, encoding='utf-8')
    (destination / 'publication.json').write_text(serialized, encoding='utf-8')
    if VERSION == CURRENT_VERSION:
        (ROOT / 'verification/publication.json').write_text(serialized, encoding='utf-8')
    print('Public verification: ' + ('passed' if RECEIPT['passed'] else 'incomplete'))
