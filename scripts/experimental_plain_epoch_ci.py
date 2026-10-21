"""Fresh Linux unit/actual-PG experiment for the frozen two-epoch candidate."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'verification/experimental-candidates/plain-epoch-r1-2026-10-21'
EXPECTED_BUNDLE = 'd0401a607a6cb9640105f05bb7222be19584eb9c2bc8ac7348e8481c6c073cba'
EXPECTED_CANDIDATE = 'c585d2ac6d9968c98c10577a78a7b4adfd3a0127a9afa5d800f34b2f288d005d'
EXPECTED_RESTORE = '999a594b22dca95f1ee6ea6a854e065b12609ccd566a83db9fd26450f0f5c408'
EXPECTED_TESTS = 47


def binding(path, maximum=1048576):
    digest, size = hashlib.sha256(), 0
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular frozen source required')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError('Regular bounded frozen source required')
        while raw := stream.read(65536):
            size += len(raw)
            if size > maximum:
                raise ValueError('File exceeds binding budget')
            digest.update(raw)
        after = os.fstat(stream.fileno())
    current = path.stat()
    if (path.is_symlink() or not stat.S_ISREG(current.st_mode)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
               (after.st_dev, after.st_ino, size, after.st_mtime_ns)
            or (after.st_dev, after.st_ino, size, after.st_mtime_ns) !=
               (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)):
        raise ValueError('Frozen source changed during bounded reading')
    return {'bytes': size, 'sha256': digest.hexdigest()}


def load(path, maximum=1048576):
    expected = binding(path, maximum)
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum or {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} != expected:
        raise ValueError('Bounded JSON required')
    return json.loads(raw)


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--fixture-port', type=int, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_OS') != 'Linux':
        raise ValueError('Manual Linux experiment only')
    requested = os.environ['MTW_REQUESTED_REF']
    if not re.fullmatch('[0-9a-f]{40}', requested):
        raise ValueError('Immutable source commit required')
    if not 1 <= args.fixture_port <= 65535:
        raise ValueError('Fixture-only port')
    import subprocess
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if requested != head:
        raise ValueError('Actual source differs')
    work = args.work.resolve()
    if work.parent != Path(os.environ['RUNNER_TEMP']).resolve():
        raise ValueError('Fresh direct RUNNER_TEMP child required')
    work.mkdir(exist_ok=False)
    evidence = work / 'evidence'
    evidence.mkdir()
    restored, scratch = work / 'repository', work / 'scratch'
    restored.mkdir()
    scratch.mkdir()
    receipt = {'schema': 1, 'passed': False, 'sourceCommit': head,
               'workflowCommit': os.environ.get('GITHUB_SHA'), 'run': os.environ.get('GITHUB_RUN_ID'),
               'actualDatabaseExecution': False, 'formalPerformanceMeasured': False,
               'coreProofImplemented': False, 'sourceClosureVerified': False, 'formalEligible': False,
               'independentAcceptance': False, 'stages': []}
    files, helper, old_files, old_bundle = {}, None, {}, None
    try:
        index_path = PUBLIC / 'bundle-index.json'
        if binding(index_path)['sha256'] != EXPECTED_BUNDLE:
            raise ValueError('Exact reviewed bundle required')
        manifest = load(index_path)
        files = manifest['files']
        if not 1 <= len(files) <= 128 or sum(v['bytes'] for v in files.values()) > 4194304:
            raise ValueError('Bundle count/aggregate bound')
        for name, expected in files.items():
            relative = PurePosixPath(name)
            if ('\\' in name or ':' in name or relative.is_absolute() or '..' in relative.parts
                    or relative.as_posix() != name or not name.startswith('artifacts/plain-v3-epoch-r1/')):
                raise ValueError('Original candidate layout only')
            if binding(PUBLIC / 'bundle' / name) != expected:
                raise ValueError('Frozen source changed')
        if files['artifacts/plain-v3-epoch-r1/candidate-index.json']['sha256'] != EXPECTED_CANDIDATE:
            raise ValueError('Exact frozen candidate required')
        old = ROOT / 'verification/experimental-candidates/plain-journal-r2-2026-10-21/restore_and_run.py'
        if binding(old)['sha256'] != EXPECTED_RESTORE:
            raise ValueError('Original reviewed R2 restore helper required')
        spec = importlib.util.spec_from_file_location('frozen_r2_restore', old)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        old_bundle = ROOT / helper.PUBLIC_BUNDLE
        _, old_files = helper.verify_bundle(old_bundle)
        candidate_path = PUBLIC / 'bundle/artifacts/plain-v3-epoch-r1/candidate-index.json'
        candidate = load(candidate_path)
        expected_files = {'artifacts/plain-v3-epoch-r1/' + name: value for name, value in candidate['files'].items()}
        expected_files['artifacts/plain-v3-epoch-r1/candidate-index.json'] = binding(candidate_path)
        if expected_files != files or candidate['dependencies'] != manifest['dependencies']:
            raise ValueError('Candidate file/dependency inventory differs')
        if any(old_files.get(name) != value for name, value in candidate['dependencies'].items()):
            raise ValueError('Required runtime dependency differs from restored R2 bytes')
        prefix = 'artifacts/plain-v3-epoch-r1'
        declared_unit = {name: value for name, value in files.items()
                         if PurePosixPath(name).parent.as_posix() == prefix
                         and PurePosixPath(name).suffix in ('.py', '.json')
                         and PurePosixPath(name).name != 'candidate-index.json'}
        declared_unit.update({name: value for name, value in candidate['dependencies'].items()
                              if name not in ('examples/postgres-requirements.txt',
                                              'integrations/python/moontxnwitness_capture/__init__.py')})
        declared_pg = dict(declared_unit)
        init_name = 'integrations/python/moontxnwitness_capture/__init__.py'
        declared_pg[init_name] = candidate['dependencies'][init_name]
        helper.copy_files(old_bundle, restored, old_files)
        for name, expected in files.items():
            target = restored / name
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with (PUBLIC / 'bundle' / name).open('rb') as src, target.open('xb') as dst:
                while raw := src.read(min(65536, expected['bytes'] - size + 1)):
                    size += len(raw)
                    if size > expected['bytes']:
                        raise ValueError('Candidate grew during restoration')
                    dst.write(raw)
            if binding(target) != expected:
                raise ValueError('Restored candidate differs')
        receipt['allSourceBindingsBefore'] = {**old_files, **files}
        env = helper.child_environment(scratch, args.fixture_port)
        command = [sys.executable, '-B', 'artifacts/plain-v3-epoch-r1/test_epoch.py']
        stage = helper.run_child('unit-first', command, restored, env, evidence)
        receipt['stages'].append(stage)
        if stage.get('exitCode') != 0:
            raise ValueError('First unit run failed; preserve original output')
        log_path = evidence / 'unit-first.log'
        binding(log_path, 16 * 1024 * 1024)
        with log_path.open('rb') as stream:
            log_raw = stream.read(16 * 1024 * 1024 + 1)
        if len(log_raw) > 16 * 1024 * 1024:
            raise ValueError('Unit log read budget')
        log = log_raw.decode('utf8')
        matches = re.findall(r'^Epoch receipt: (.+)$', log, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('One actual unit receipt required')
        unit_path = Path(matches[0].strip()).resolve()
        if not unit_path.is_relative_to(scratch) or unit_path.name != 'test-receipt.json':
            raise ValueError('Unit receipt outside owned scratch')
        unit = load(unit_path)
        if not (unit['passed'] is True and unit['tests'] == EXPECTED_TESTS and unit['skipped'] == []
                and unit['sourceBindingsUnchanged'] is True and unit['actualDatabaseExecution'] is False
                and unit['sourceBindingsBefore'] == declared_unit and unit['sourceBindingsAfter'] == declared_unit
                and unit['actualFilesystemExecution'] is True and unit['actualNativeChildExecution'] is True
                and unit['actualMockExecution'] is True and unit['syntaxFiles'] == 5):
            raise ValueError('Actual unit/source obligations differ')
        stage['passed'] = True
        receipt['unitReceipt'] = {'path': str(unit_path.relative_to(work)), **binding(unit_path)}
        command = [sys.executable, '-B', 'artifacts/plain-v3-epoch-r1/postgres_epoch.py',
                   '--output', str(evidence / 'postgres')]
        stage = helper.run_child('postgres-first', command, restored, env, evidence)
        receipt['stages'].append(stage)
        pg_path = evidence / 'postgres/postgres-receipt.json'
        if pg_path.exists():
            pg = load(pg_path)
            receipt['actualDatabaseExecution'] = pg['actualDatabaseExecution']
            receipt['postgresReceipt'] = {'path': str(pg_path.relative_to(work)), **binding(pg_path)}
        else:
            pg = {}
        if stage.get('exitCode') != 0:
            raise ValueError('First actual PG run failed; preserve original output')
        names = ['two-epochs-same-value', 'rollback-and-savepoint', 'unsupported-statement', 'discarded-setup-commit-ack']
        if not (pg.get('passed') is True and pg.get('actualDatabaseExecution') is True and pg['serverVersion'] == 180006
                and pg['driver'] == '3.3.6' and pg['sourceBindingsUnchanged'] is True
                and pg['sourceBindingsBefore'] == declared_pg and pg['sourceBindingsAfter'] == declared_pg
                and [c['name'] for c in pg['cases']] == names and all(c['passed'] is True for c in pg['cases'])
                and all(pg[k] is False for k in ['coreProofImplemented', 'sourceClosureVerified', 'formalEligible'])):
            raise ValueError('Actual controlled PG obligations differ')
        for case in pg['cases']:
            case_root = evidence / 'postgres' / case['name']
            if load(case_root / 'case-receipt.json') != case:
                raise ValueError('Embedded and standalone actual scenario differ')
            if not (case['actualDatabaseExecution'] is True and case['coreProofImplemented'] is False
                    and case['formalEligible'] is False):
                raise ValueError('Unsupported scenario claim')
            chain_root = case_root / 'chain'
            actual, nodes, aggregate = {}, 0, 0
            for path in chain_root.rglob('*'):
                nodes += 1
                if nodes > 256 or path.is_symlink():
                    raise ValueError('Scenario raw tree type/count budget')
                if not path.is_file():
                    continue
                if len(actual) >= 128:
                    raise ValueError('Scenario raw file-count budget')
                item = binding(path, 16 * 1024 * 1024)
                aggregate += item['bytes']
                if aggregate > 32 * 1024 * 1024:
                    raise ValueError('Scenario raw aggregate budget')
                actual[path.relative_to(chain_root).as_posix()] = item
            if actual != case['rawFileBindings']:
                raise ValueError('Actual scenario raw files omitted, added or changed')
        stage['passed'] = True
        receipt['passed'] = True
    except Exception as error:
        receipt['failure'] = {'class': type(error).__name__, 'message': str(error)}
    finally:
        after = {}
        for name, expected in {**old_files, **files}.items():
            try:
                after[name] = binding(restored / name)
                if after[name] != expected:
                    raise ValueError('Source changed')
            except Exception as error:
                receipt['passed'] = False
                receipt.setdefault('sourceVerificationFailures', []).append({'path': name, 'class': type(error).__name__})
        receipt['allSourceBindingsAfter'] = after
        if helper is not None and old_bundle is not None:
            try:
                _, unchanged = helper.verify_bundle(old_bundle)
                if unchanged != old_files:
                    raise ValueError('R2 bundle changed')
            except Exception as error:
                receipt['passed'] = False
                receipt['priorBundleFailure'] = {'class': type(error).__name__}
        write_new(evidence / 'execution-receipt.json', receipt)
    print(json.dumps({'passed': receipt['passed'], 'actualDatabaseExecution': receipt['actualDatabaseExecution']}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
