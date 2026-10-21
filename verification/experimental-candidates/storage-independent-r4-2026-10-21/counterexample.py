"""Two preregistered protected-sync failures; execute only on an approved remote runner."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import traceback
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'moon.mod').is_file() and (p / 'integrations/python').is_dir())
INDEX_SHA = '223e61bcb41b64f2d47f0d96e8c8e99e88a1a9c1fed856467a7b01a45c920124'
PRIMARY = 'Independent r4 actual protected final data-sync IO failure'
SECONDARY = 'Independent r4 actual diagnostic marker persistence IO failure'


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def binding(path):
    path = Path(path)
    info = path.lstat()
    ensure(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_size <= 8 * 1024 * 1024,
           'Small regular bound file required')
    h, n = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while block := stream.read(65536):
            n += len(block)
            ensure(n <= 8 * 1024 * 1024, 'Bounded file grew')
            h.update(block)
    ensure(n == info.st_size, 'Bound file changed while reading')
    return {'bytes': n, 'sha256': h.hexdigest()}


def load(path):
    ensure(binding(path)['bytes'] <= 1024 * 1024, 'Small JSON metadata required')
    return json.loads(Path(path).read_bytes())


def save(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    Path(path).open('xb').write(raw)
    return binding(path)


def tree(root):
    files = sorted(p for p in root.rglob('*') if p.is_file())
    ensure(len(files) <= 128, 'Independent small-fixture file-count limit')
    return {p.relative_to(root).as_posix(): binding(p) for p in files}


def sources(candidate):
    ensure(candidate.parent == ROOT / 'artifacts', 'Restore the original candidate repository layout')
    index_path = candidate / 'candidate-index.json'
    ensure(binding(index_path)['sha256'] == INDEX_SHA, 'Only the frozen r4 candidate is accepted')
    index = load(index_path)
    bound = {'candidate/candidate-index.json': binding(index_path)}
    for group, base, prefix in [(index['fileBindings'], candidate, 'candidate/'),
                                (index['runtimeDependencies'], ROOT, 'repository/')]:
        for name, expected in group.items():
            rel = Path(name)
            ensure(not rel.is_absolute() and '..' not in rel.parts and '\\' not in name, 'Safe bound relative dependency')
            actual = binding(base / name)
            ensure(actual == expected, 'Frozen author dependency changed: ' + name)
            bound[prefix + name] = actual
    for name in ('contract-v1.json', 'preregistration-before-implementation.json', 'events-v1.json',
                 'contract-r4-stable-mutex-amendment.json', 'r4-callsite-binding.json', 'counterexample.py'):
        bound['independent/' + name] = binding(HERE / name)
    return bound


def author(candidate):
    sys.path.insert(0, str(candidate))
    import managed
    ensure(Path(managed.__file__).resolve() == candidate / 'managed.py', 'Unexpected author module')
    from moontxnwitness_capture.journal_v3 import SegmentedJournal
    return managed, SegmentedJournal


def native_probe(path, expected_nonce):
    """No author locking helper or ownership flag is used in this process."""
    evidence = {'phase': 'open', 'result': 'unexpected-error', 'platform': os.name}
    try:
        info = path.lstat()
        ensure(stat.S_ISREG(info.st_mode) and not path.is_symlink(), 'Regular permanent mutex required')
        with path.open('r+b') as stream:
            opened = os.fstat(stream.fileno())
            ensure((info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino), 'Probe mutex identity changed')
            raw = stream.read(4097)
            ensure(json.loads(raw) == {'kind': 'archive-coordination/1', 'nonce': expected_nonce}, 'Probe mutex authority')
            evidence.update(phase='native-lock', device=info.st_dev, inode=info.st_ino,
                            mutexSha256=hashlib.sha256(raw).hexdigest())
            stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                evidence.update(errorClass=type(error).__name__, errno=error.errno,
                                winerror=getattr(error, 'winerror', None))
                blocked = error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or getattr(error, 'winerror', None) == 33
                evidence['result'] = 'blocked' if blocked else 'unexpected-native-error'
                print(json.dumps(evidence), flush=True)
                return 17 if blocked else 2
            evidence['result'] = 'acquired-unexpectedly'
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        print(json.dumps(evidence), flush=True)
        return 0
    except BaseException as error:
        evidence.update(errorClass=type(error).__name__, message=str(error))
        print(json.dumps(evidence), flush=True)
        return 2


def probe(path, nonce):
    child = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--probe-coordination', str(path),
                            '--expected-nonce', nonce], capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    ensure(len(child.stdout.encode()) <= 65536 and len(child.stderr.encode()) <= 65536, 'Native probe output bound')
    value = json.loads(child.stdout.strip())
    ensure(child.returncode == 17 and value['phase'] == 'native-lock' and value['result'] == 'blocked',
           'Independent native mutex probe did not prove contention')
    return {'exitCode': child.returncode, 'stdout': value, 'stderr': child.stderr}


def caller(candidate, function, line):
    matches = [f for f in inspect.stack() if Path(f.filename).resolve() == candidate / 'managed.py']
    ensure(matches and matches[0].function == function and matches[0].lineno == line,
           'Fault must be at the exact frozen actual source callsite')
    return {'file': 'managed.py', 'function': matches[0].function, 'line': matches[0].lineno}


def prepared_child(candidate, store):
    sources(candidate)
    managed, _ = author(candidate)
    source = managed.ManagedSource(store)

    def stop(stage):
        if stage != 'after-manifest':
            return
        intent, state, owner = load(store / 'prune-intent.json'), load(store / 'manifest.json'), load(store / 'operation.lock')
        ensure(state['pending'] == intent['plan'] and state['generation'] == intent['baseGeneration'] + 1,
               'Actual manifest is not the prepared prune state')
        ensure(owner == {'kind': 'archive-operation/1', 'nonce': intent['nonce'], 'token': intent['operationToken']},
               'Actual prepared owner authority differs')
        held = probe(store / 'coordination.lock', intent['nonce'])
        save(store.parent / 'child-prepared-state.json', {'intent': intent, 'manifest': state, 'owner': owner,
              'permanentMutexProbe': held, 'bindings': {name: binding(store / name) for name in
                  ('prune-intent.json', 'manifest.json', 'operation.lock', 'coordination.lock')}})
        os._exit(73)

    source.fault = stop
    source.prune(before_seq=999)
    raise RuntimeError('The actual prepared crash boundary was not reached')


def scenario(candidate, work, marker_failure):
    work.mkdir(parents=True, exist_ok=False)
    result = {'name': 'protected-final-sync-and-marker-io-fail' if marker_failure else 'protected-final-sync-fails',
              'passed': False, 'executionComplete': False, 'checks': [], 'failures': []}

    def check(name, actual, expected):
        passed = actual == expected
        result['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'passed': passed})
        if not passed:
            result['failures'].append({'name': name, 'actual': actual, 'expected': expected})

    try:
        managed, SegmentedJournal = author(candidate)
        site = load(HERE / 'r4-callsite-binding.json')
        journal, store, archive = work / 'journal', work / 'store', work / 'original-source.zip'
        writer = SegmentedJournal(journal, segment_bytes=256, max_record_bytes=256, flush_bytes=128, max_queue_bytes=4096)
        for event in load(HERE / 'events-v1.json'):
            writer.append(event)
        ensure(writer.close(source_closed=True).complete, 'Actual source must first seal completely')
        original = managed.ManagedSource.adopt(store, journal, exclusive_source_ownership=True)
        original.archive_checkpoint('checkpoint', archive)
        immutable_paths = {'sourceIndex': journal / 'journal-index.json', 'transactionCache': journal / 'transactions.sqlite3',
                           'sourceFence': journal / 'writer.lock', 'originalArchive': archive}
        before_original = {name: binding(path) for name, path in immutable_paths.items()}
        mutex_info = (store / 'coordination.lock').lstat()
        mutex_before = {'device': mutex_info.st_dev, 'inode': mutex_info.st_ino, **binding(store / 'coordination.lock')}
        with (work / 'actual-prepared-child.log').open('xb') as log:
            child = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--candidate', str(candidate),
                                    '--child-prune', str(store)], stdout=log, stderr=subprocess.STDOUT, timeout=90,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        ensure(child.returncode == 73, 'Actual child did not reach the frozen prepared state')
        prepared = load(work / 'child-prepared-state.json')
        intent, owner = load(store / 'prune-intent.json'), load(store / 'operation.lock')
        ensure(prepared['intent'] == intent and prepared['owner'] == owner, 'Prepared authority changed after real crash')
        preserved = work / 'prepared-original-bytes'
        preserved.mkdir()
        for name in ('prune-intent.json', 'manifest.json', 'operation.lock', 'coordination.lock'):
            raw = (store / name).read_bytes()
            (preserved / name).open('xb').write(raw)
            ensure(binding(preserved / name) == binding(store / name), 'Prepared original bytes differ')
        prepared_fresh = managed.ManagedSource(store).verify()
        recovery = managed.ManagedSource(store)
        primary, secondary = [], []
        real_sync, real_open = managed.point.sync_directory, Path.open

        def qualifying_state():
            state, actual_owner = load(store / 'manifest.json'), load(store / 'operation.lock')
            ensure(state['pending'] is None and state.get('completedPlan') == intent['plan'], 'Finalized actual plan required')
            ensure(not (store / 'prune-intent.json').exists(), 'Actual intent has not been cleared')
            ensure(actual_owner == owner, 'Actual original owner authority must still exist')
            mutex = store / 'coordination.lock'
            ensure(load(mutex) == {'kind': 'archive-coordination/1', 'nonce': owner['nonce']}, 'Actual permanent mutex binding')
            return {'pending': state['pending'], 'completedPlan': state['completedPlan'], 'owner': actual_owner,
                    'ownerBinding': binding(store / 'operation.lock'), 'intentPresent': False,
                    'nativeProbe': probe(mutex, owner['nonce'])}

        def fail_final_sync(path):
            if Path(path).resolve() == store:
                frames = [f for f in inspect.stack() if Path(f.filename).resolve() == candidate / 'managed.py']
                if frames and frames[0].function == site['finalSync']['function'] and frames[0].lineno == site['finalSync']['line']:
                    ensure(not primary, 'Actual final-sync fault repeated')
                    primary.append({'callsite': caller(candidate, site['finalSync']['function'], site['finalSync']['line']),
                                    **qualifying_state()})
                    raise OSError(PRIMARY)
            return real_sync(path)

        def fail_marker(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if marker_failure and Path(path).resolve() == store / 'operation-failed.json' and mode == 'xb':
                ensure(len(primary) == 1 and not secondary, 'Diagnostic fault requires the first actual final-sync IO failure')
                secondary.append({'callsite': caller(candidate, site['secondaryMarkerIO']['function'], site['secondaryMarkerIO']['line']),
                                  **qualifying_state()})
                raise OSError(SECONDARY)
            return real_open(path, *args, **kwargs)

        actual_error = None
        with patch.object(managed.point, 'sync_directory', side_effect=fail_final_sync), patch.object(Path, 'open', new=fail_marker):
            try:
                recovery.recover(expected_plan=intent['plan'], exclusive_recovery=True)
            except BaseException as error:
                actual_error = {'class': type(error).__name__, 'message': str(error), 'isOSError': isinstance(error, OSError),
                                'trace': traceback.format_exc()}
        result.update(prepared=prepared, preparedFreshVerify=prepared_fresh, primaryFaults=primary,
                      secondaryFaults=secondary, actualRecoveryError=actual_error,
                      afterFailureFilesBeforeVerification=tree(work))
        lock = load(store / 'operation.lock') if (store / 'operation.lock').exists() else None
        marker = load(store / 'operation-failed.json') if (store / 'operation-failed.json').exists() else None
        expected_marker = {'kind': 'archive-operation-failed/1', 'nonce': owner['nonce'], 'operationToken': owner['token']}
        guard = lock == owner or (not marker_failure and marker == expected_marker)
        same, fresh = recovery.verify(), managed.ManagedSource(store).verify()
        after_original = {name: binding(path) for name, path in immutable_paths.items()}
        info = (store / 'coordination.lock').lstat()
        mutex_after = {'device': info.st_dev, 'inode': info.st_ino, **binding(store / 'coordination.lock')}
        result.update(afterFailureOwner=lock, afterFailureMarker=marker, sameInstanceVerify=same, freshInstanceVerify=fresh,
                      originalBindingsBefore=before_original, originalBindingsAfter=after_original,
                      permanentMutexBefore=mutex_before, permanentMutexAfter=mutex_after,
                      afterVerificationFiles=tree(work))
        check('actual-prepared-child-exit', child.returncode, 73)
        check('actual-prepared-fresh-incomplete', prepared_fresh['complete'], False)
        check('qualified-actual-final-sync-injected-once', len(primary), 1)
        check('permanent-native-mutex-actually-held-at-fault', primary[0]['nativeProbe']['exitCode'] if primary else None, 17)
        check('injected-primary-IO-preserved', actual_error is not None and actual_error['isOSError'] and actual_error['message'] == PRIMARY, True)
        check('actual-owner-bound-persistent-guard', guard and (not marker_failure or lock == owner), True)
        check('live-instance-permanently-poisoned', recovery.poisoned, True)
        check('same-instance-incomplete-after-real-failure', same['complete'], False)
        check('fresh-instance-incomplete-after-real-failure', fresh['complete'], False)
        check('original-index-cache-fence-and-archive-unchanged', after_original, before_original)
        check('permanent-mutex-inode-and-bytes-never-removed', mutex_after, mutex_before)
        if marker_failure:
            check('actual-diagnostic-marker-IO-failed-once', len(secondary), 1)
        result['executionComplete'] = True
        result['passed'] = not result['failures']
    except BaseException as error:
        result['fatalSetupOrPlacementError'] = True
        result['failures'].append({'class': type(error).__name__, 'message': str(error), 'trace': traceback.format_exc()})
    save(work / 'case-receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, default=ROOT / 'artifacts/source-window-v3-archive-r4-draft')
    parser.add_argument('--work', type=Path)
    parser.add_argument('--child-prune', type=Path)
    parser.add_argument('--probe-coordination', type=Path)
    parser.add_argument('--expected-nonce')
    args = parser.parse_args()
    if args.probe_coordination is not None:
        return native_probe(args.probe_coordination, args.expected_nonce)
    candidate = args.candidate.resolve()
    if args.child_prune is not None:
        prepared_child(candidate, args.child_prune.resolve())
        return 1
    ensure(args.work is not None, 'A new task-owned --work is required')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 1, 'kind': 'independent-r4-protected-final-sync-two-fault-cases', 'passed': False,
               'complete': False, 'cases': [], 'checks': [], 'candidateIndexSha256': INDEX_SHA,
               'localHostExecutionBeforeRemote': False, 'actualFilesystemExecution': True,
               'actualDatabaseExecution': False, 'nodeExecution': False, 'compilation': False,
               'formalPerformanceMeasurement': False, 'stableAcceptance': False,
               'oldR3FaultTarget': {'status': 'inapplicable-not-executed', 'passed': False, 'oldActualFailureChanged': False},
               'postCommitNativeAllDiagnosticIOFailure': 'Explicit unexecuted boundary; not a waiver for these two data-sync failures.',
               'platform': platform.platform(), 'python': sys.version,
               'started': datetime.now(timezone.utc).isoformat()}
    before = None
    try:
        before = sources(candidate)
        receipt['sourceBindingsBefore'] = before
        for flag, name in [(False, 'primary'), (True, 'primary-and-marker')]:
            result = scenario(candidate, work / name, flag)
            receipt['cases'].append(result)
            if result.get('fatalSetupOrPlacementError'):
                break
        after = sources(candidate)
        receipt['sourceBindingsAfter'] = after
        receipt['checks'].append({'name': 'candidate-and-independent-source-bytes-unchanged',
                                  'passed': before == after})
        receipt['complete'] = len(receipt['cases']) == 2 and all(c['executionComplete'] for c in receipt['cases'])
        receipt['passed'] = receipt['complete'] and all(c['passed'] for c in receipt['cases']) and before == after
    except BaseException as error:
        receipt['fatalError'] = {'class': type(error).__name__, 'message': str(error), 'trace': traceback.format_exc()}
    receipt['finished'] = datetime.now(timezone.utc).isoformat()
    receipt['checksCount'] = sum(len(c['checks']) for c in receipt['cases']) + len(receipt['checks'])
    bound = save(work / 'independent-r4-receipt.json', receipt)
    print(json.dumps({'passed': receipt['passed'], 'complete': receipt['complete'], 'cases': len(receipt['cases']),
                      'checks': receipt['checksCount'], 'receiptSha256': bound['sha256']}), flush=True)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
