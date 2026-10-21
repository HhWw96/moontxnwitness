"""Read-only review of actual artifacts and independent fresh-runtime receipts."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'artifacts/orm-integrated-public-download-39602851503'
COMMIT = '41a63635eb23add596051f939c57b8f6c315feeb'
SOURCE = 'ec35d4a61267af9c5600baf6e62197219aa979fdc1f36ca17a9a4bc40f1d9787'
checks = []


def demand(value, label):
    checks.append({'name': label, 'passed': bool(value)})
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bind(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while data := stream.read(65536):
            size += len(data)
            digest.update(data)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def load(path):
    return json.loads(path.read_bytes())


result = {'schema': 1, 'kind': 'independent-AI-actual-main-runtime-compatibility-checkpoint', 'passed': False,
          'sourceCommit': COMMIT, 'sourceSha256': SOURCE, 'run': 39602851503,
          'originalRunOverallPassed': False, 'originalLinuxPackageStagePassed': False,
          'new73695PackageAccepted': False, 'freshArchiveInstallExecuted': False,
          'localDatabaseCompileJvmPerformanceExecuted': False, 'humanAcceptance': False,
          'stableReleaseAccepted': False, 'platforms': [], 'checks': checks}
try:
    meta = load(BASE / 'attempt-2/artifacts.json')['artifacts']
    run = load(BASE / 'attempt-2/run.json')
    jobs = load(BASE / 'attempt-2/jobs.json')['jobs']
    demand(run['id'] == 39602851503 and run['head_sha'] == COMMIT and run['conclusion'] == 'failure', 'Original overall failure retained')
    demand({j['name']: j['conclusion'] for j in jobs} == {'verify (ubuntu-24.04)': 'failure', 'verify (windows-2022)': 'success'}, 'Original platform states retained')
    listing = subprocess.check_output(['git', '--no-optional-locks', 'ls-tree', '-r', '-z', COMMIT], cwd=ROOT)
    objects = {}
    for line in listing.split(b'\0'):
        if not line:
            continue
        header, name = line.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        if kind == 'blob':
            objects[name.decode('utf8')] = oid
    proc = subprocess.Popen(['git', '--no-optional-locks', 'cat-file', '--batch'], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    git_hashes = {}
    try:
        for origin, zip_path, fresh, replay in [
            ('windows', BASE/'attempt-2/evidence-windows-2022.zip', BASE/'fresh-public-windows-origin-r2', BASE/'orm-windows-official-origin'),
            ('linux', BASE/'linux-transfer-extended/evidence-ubuntu-24.04.zip', BASE/'fresh-public-linux-origin-r2', BASE/'orm-linux-official-identity-r3'),
        ]:
            name = 'evidence-windows-2022' if origin == 'windows' else 'evidence-ubuntu-24.04'
            metadata = next(m for m in meta if m['name'] == name)
            actual_zip = bind(zip_path)
            demand(actual_zip == {'bytes': metadata['size_in_bytes'], 'sha256': metadata['digest'][7:]}, origin+' original official artifact bytes')
            with zipfile.ZipFile(zip_path) as archive:
                summary = json.loads(archive.read('verification/summary.json'))
                manifest = json.loads(archive.read('dist/build-manifest.json'))
                demand(summary['coreTestsPerTarget'] == 616 and summary['executedTargets'] == ['js', 'wasm-gc', 'wasm'] and summary['passed'] is True, origin+' actual core616 three targets')
                demand(manifest == summary['buildManifest'] and manifest['sourceSha256'] == SOURCE, origin+' actual source/build binding')
                tested = summary['testedFileSha256']
                demand(len(tested) == 366, origin+' actual366 tested files')
                for path, expected in tested.items():
                    if path.startswith('dist/'):
                        actual = sha(archive.read(path))
                    else:
                        oid = objects[path]
                        if oid not in git_hashes:
                            proc.stdin.write((oid+'\n').encode())
                            proc.stdin.flush()
                            header = proc.stdout.readline().split()
                            demand(len(header) == 3 and header[1] == b'blob', origin+' actual Git blob response '+path)
                            git_hashes[oid] = sha(proc.stdout.read(int(header[2])))
                            demand(proc.stdout.read(1) == b'\n', 'Git response framing '+path)
                        actual = git_hashes[oid]
                    demand(actual == expected, origin+' tested original source/runtime '+path)
                independent = load(fresh / 'independent-public-applicable.json')
                demand(independent['passed'] is True and independent['complete'] is True and independent['actualRuntime']['checks'] == 332 and independent['runtimeStillMatchesDownload'] is True, origin+' original332 fresh runtime checks')
                for path, row in independent['runtimeBindings'].items():
                    raw = archive.read('dist/'+path)
                    demand({'bytes': len(raw), 'sha256': sha(raw)} == row == bind(fresh/'dist'/path), origin+' actual downloaded runtime '+path)
                for label, stdout_name in [('journal', 'journal.stdout'), ('runtimeProcess', 'runtime.stdout')]:
                    demand(independent[label]['exitCode'] == 0 and independent[label]['stdout'] == bind(fresh/stdout_name), origin+' retained actual process '+label)
                demand(independent['runtimeResultBinding'] == bind(fresh/'audit-output/fresh-result.json'), origin+' actual332 result payload')
                actual_replay = load(replay/'independent-replay.json')
                demand(actual_replay['complete'] is True and actual_replay['semantic24Passed'] is True and actual_replay['valid4OutputBytesPassed'] is True and actual_replay['strict24OutputBytesPassed'] is False and actual_replay['passed'] is False, origin+' original semantic24/strict failure retained')
                differences = [row['name'] for row in actual_replay['checks'] if not row['fullOutputBytesEqual']]
                demand(len(differences) == 1, origin+' exact23/24 reports')
                result['platforms'].append({'origin': origin, 'artifact': actual_zip, 'testsPerTarget': 616, 'testedFileCount': 366,
                    'runtimeChecks': 332, 'originalOrmSemanticChecks': 24, 'originalOrmStrictByteChecksPassed': 23,
                    'strictByteDifferenceCases': differences, 'originalStrictReceiptStillFailed': True,
                    'runtimeReceipt': bind(fresh/'independent-public-applicable.json'),
                    'ormReceipt': bind(replay/'independent-replay.json'), 'actualBuildManifest': manifest})
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait(timeout=15)
    result['passed'] = True
except Exception as error:
    result['error'] = {'class': type(error).__name__, 'message': str(error)}
finally:
    result['auditorSha256'] = bind(Path(__file__))['sha256']
    (HERE/'receipt.json').write_bytes(json.dumps(result, indent=2).encode()+b'\n')
print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'platforms': len(result['platforms'])}))
raise SystemExit(0 if result['passed'] else 1)
