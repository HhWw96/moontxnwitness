"""Interleave two source-pinned A/B/C producers on one disposable PostgreSQL 18.6 instance."""

import argparse
from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import zipfile

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


ENTRY = Path(__file__).resolve()
HARNESS = ENTRY.with_name('configured-window-cost-pilot.py')
ORDERS = ('ABC', 'BCA', 'CAB')
SEAL = 'original-v2'
WRITER = 'returning-v1'
SOURCE_FILES = ('configured_window_v2.py', 'configured_point_capture_v2.py',
                'configured_point_projection_v2.py')
SNAPSHOT_SOURCE_FILES = (*SOURCE_FILES, 'configured_source_v2.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_commit(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

    if git('status', '--porcelain'):
        raise ValueError(f'Use a clean producer checkout: {root}')
    return git('rev-parse', 'HEAD')


def send(process, value):
    process.stdin.write(json.dumps(value) + '\n')
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('A producer stopped before reporting its capture; see its worker log')
    return json.loads(line)


def retain_cell(output, scratch, schema, phase, cell):
    if phase == 'C':
        original = Path(cell['bundle']).resolve()
        if not original.is_relative_to(scratch):
            raise ValueError('Capture escaped the sample directory')
        packed = output / f'{schema}-{phase}.json.gz'
        with original.open('rb') as source, packed.open('xb') as stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        with gzip.open(packed, 'rb') as reopened:
            if hashlib.file_digest(reopened, 'sha256').hexdigest() != cell['bundleSha256']:
                raise ValueError('The archived capture differs from the sealed original')
        retained_receipt = output / f'{schema}-{phase}.receipt.json'
        shutil.copyfile(cell['producerReceipt'], retained_receipt)
        cell.update(bundle=str(packed), bundleEncoding='gzip', compressedSha256=digest(packed),
                    producerReceipt=str(retained_receipt))
    elif phase == 'B':
        installation = shutil.make_archive(str(output / f'{schema}-{phase}'), 'zip', root_dir=scratch)
        with zipfile.ZipFile(installation) as archived:
            if archived.testzip() is not None:
                raise ValueError('The archived source installation is damaged')
        cell.update(sourceInstallation=str(installation), sourceInstallationSha256=digest(Path(installation)))
    if scratch.parent != output or not scratch.name.startswith('.sample-'):
        raise ValueError('Refusing to clean a directory outside this worker')
    shutil.rmtree(scratch)


def worker(output):
    driver = runpy.run_path(str(HARNESS))
    actual = Path(sys.modules[driver['ConfiguredCaptureWindowV2'].__module__].__file__).resolve().parent
    expected = Path(os.environ['MTW_COST_PRODUCER_ROOT']) / 'integrations/python/moontxnwitness_capture'
    if actual != expected:
        raise ValueError('The imported producer is outside its pinned checkout')
    options = conninfo_to_dict(os.environ['MTW_PAIRED_COST_DSN'])
    loads = {name: (keys, connections, 0, transactions)
             for name, keys, connections, transactions in driver['FORMAL_LOADS']}
    multicolumn = os.environ['MTW_PAIRED_COST_MATRIX'] == 'multicolumn-v2'
    if multicolumn:
        keys, connections, _, transactions = loads['wide']
        loads['multicolumn'] = (keys, connections, 12, transactions)
    writer_profile = os.environ.get('MTW_PAIRED_COST_WRITER_PROFILE')
    snapshot_profile = os.environ['MTW_PAIRED_COST_SNAPSHOT_PROFILE']
    compact = os.environ.get('MTW_PAIRED_COST_ARTIFACTS') == 'gzip-original-capture/v1'
    for line in sys.stdin:
        request = json.loads(line)
        if request == 'describe':
            names = SNAPSHOT_SOURCE_FILES if multicolumn else SOURCE_FILES
            result = {'producerFilesSha256': {name: digest(actual / name) for name in names},
                      'loadShapes': {name: list(value[:3]) if multicolumn else list(value[:2])
                                     for name, value in loads.items()}}
        elif request == 'peak':
            result = {'peakProcessRssBytes': driver['peak_process_rss']()}
        else:
            keys, connections, payload_columns, transactions = loads[request['load']]
            result = {}
            for phase in request['order']:
                scratch = Path(tempfile.mkdtemp(prefix='.sample-', dir=output)).resolve() if compact else output
                cell = driver['write_cell'](
                    scratch, options, request['schema'], os.environ['MTW_PAIRED_COST_OWNER'],
                    os.environ['MTW_PAIRED_COST_WRITER'], os.environ['MTW_PAIRED_COST_WRITER_SECRET'],
                    phase, keys, transactions, workers=connections, coordinated=True,
                    seal_profile=SEAL, writer_proof_profile=writer_profile,
                    snapshot_profile=snapshot_profile, payload_columns=payload_columns,
                )
                if compact:
                    retain_cell(output, scratch, request['schema'], phase, cell)
                result[phase] = cell
        print(json.dumps(result), flush=True)


def summarize(batch):
    windows = batch['windows']
    def median(phase):
        return statistics.median(cells[phase]['windowNs'] for cells in windows)

    def p95(phase):
        samples = sorted(value for cells in windows for value in cells[phase]['transactionSamplesNs'])
        return samples[(95 * len(samples) + 99) // 100 - 1]

    batch['completeWindowThroughputRatioCA'] = median('A') / median('C')
    batch['transactionP95RatioCA'] = p95('C') / p95('A')


def validate_pair(pair):
    for cells in pair.values():
        if set(cells) != set('ABC') or any(cell['commits'] != 24 for cell in cells.values()):
            raise ValueError('A matched arm lacks a complete A/B/C set')
    if len({cell['finalBusinessSha256'] for cells in pair.values() for cell in cells.values()}) != 1:
        raise ValueError('Producer and control business outcomes differ')


def paired_trials(workers, reports, loads, run_id, warmups, samples, schedule):
    for workload, shape in loads.items():
        keys, connections = shape[:2]
        for order_index, order in enumerate(ORDERS):
            batches = {arm: {'workload': workload, 'keys': keys, 'connections': connections,
                             'order': order, 'warmup': [], 'windows': []} for arm in workers}
            for arm, batch in batches.items():
                if len(shape) == 3:
                    batch['payloadColumns'] = shape[2]
                reports[arm]['batches'].append(batch)
            for kind, prefix, count in (('warmup', 'w', warmups), ('windows', 'm', samples)):
                for index in range(count):
                    first = ('baseline', 'candidate') if (index + order_index) % 2 == 0 else ('candidate', 'baseline')
                    request = {'load': workload, 'order': order,
                               'schema': f'mtw_pair_{run_id}_{workload}_{order_index}_{prefix}{index}'}
                    pair = {arm: send(workers[arm], request) for arm in first}
                    validate_pair(pair)
                    for arm, cells in pair.items():
                        batches[arm][kind].append(cells)
                    schedule.append({'workload': workload, 'order': order, 'kind': kind, 'index': index, 'arms': first})
            for batch in batches.values():
                summarize(batch)
            print(f'{workload} {order}: {warmups} warmup pairs, {samples} measured pairs', flush=True)


def compare(args, dsn):
    if psycopg.__version__ != '3.3.6':
        raise ValueError('Use the pinned psycopg 3.3.6')
    roots = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    commits = {arm: clean_commit(root) for arm, root in roots.items()}
    if commits['baseline'] == commits['candidate']:
        raise ValueError('The paired protocols require distinct producer commits')
    output = args.output.resolve()
    output.mkdir()
    run_id = secrets.token_hex(4)
    role, writer = 'mtw_pair_owner_' + run_id, 'mtw_pair_writer_' + run_id
    password = secrets.token_hex(24)
    with psycopg.connect(dsn, autocommit=True) as admin:
        if admin.info.server_version != 180006:
            raise ValueError('Use an owned PostgreSQL 18.6 instance')
        admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(writer), sql.Literal(password)))
        admin.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO {}').format(sql.Identifier(admin.info.dbname), sql.Identifier(role)))
    env = {**os.environ, 'MTW_PAIRED_COST_DSN': dsn, 'MTW_PAIRED_COST_OWNER': role,
           'MTW_PAIRED_COST_WRITER': writer, 'MTW_PAIRED_COST_WRITER_SECRET': password}
    env.pop('MTW_PAIRED_COST_WRITER_PROFILE', None)
    warmups, samples = (5, 30) if args.formal else (0, 1)
    multicolumn = args.matrix == 'multicolumn-v2'
    common = {'format': 'configured-source-window-cost/v2' if multicolumn else 'configured-source-window-cost/v1',
              'passed': False,
              'formalPerformanceMeasurement': False, 'actualDatabaseExecution': True,
              'harnessSha256': digest(HARNESS), 'pairedRunnerSha256': digest(ENTRY),
              'sealProfileRequested': SEAL, 'transactionsPerPhase': 24,
              'warmupWindowsPerPhase': warmups, 'measuredWindowsPerPhase': samples,
              'environment': {'system': platform.system(), 'machine': platform.machine(),
                              'python': platform.python_version(), 'psycopg': psycopg.__version__,
                              'postgres': '18.6'}}
    workers, reports, descriptions, schedule = {}, {}, {}, []
    with ExitStack() as resources:
        try:
            for arm, root in roots.items():
                destination = output / arm
                destination.mkdir()
                log = resources.enter_context((destination / 'worker.log').open('xb'))
                producer_env = {**env, 'MTW_COST_PRODUCER_ROOT': str(root)}
                profile = WRITER if arm == 'candidate' and args.candidate_snapshot_profile is None else None
                snapshot = args.candidate_snapshot_profile if arm == 'candidate' else None
                snapshot = snapshot or 'paged-v1'
                producer_env['MTW_PAIRED_COST_MATRIX'] = args.matrix
                producer_env['MTW_PAIRED_COST_SNAPSHOT_PROFILE'] = snapshot
                producer_env['MTW_PAIRED_COST_ARTIFACTS'] = 'gzip-original-capture/v1' if args.compact_artifacts else ''
                if profile is not None:
                    producer_env['MTW_PAIRED_COST_WRITER_PROFILE'] = profile
                worker_process = subprocess.Popen([sys.executable, '-B', str(ENTRY), '--worker', str(destination)],
                    text=True, encoding='utf-8', env=producer_env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                workers[arm] = worker_process
                descriptions[arm] = description = send(worker_process, 'describe')
                sources = description['producerFilesSha256']
                reports[arm] = {**common, 'batches': [], 'sourceCommit': commits[arm],
                                'producerFilesSha256': sources,
                                'producerSha256': hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
                                'writerProofProfileRequested': profile}
                if multicolumn:
                    reports[arm]['snapshotProfileRequested'] = snapshot
                if args.compact_artifacts:
                    reports[arm]['artifactStorage'] = 'gzip-original-capture/v1'
            loads = descriptions['baseline']['loadShapes']
            if descriptions['candidate']['loadShapes'] != loads:
                raise ValueError('Producer workload shapes differ')
            paired_trials(workers, reports, loads, run_id, warmups, samples, schedule)
            for arm, process in workers.items():
                reports[arm].update(send(process, 'peak'))
                process.stdin.close()
                if process.wait(timeout=15) != 0:
                    raise RuntimeError(f'{arm} producer did not exit cleanly')
            for report in reports.values():
                report.update(passed=True, formalPerformanceMeasurement=args.formal)
        finally:
            for process in workers.values():
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
            for arm, report in reports.items():
                report['pairedSchedule'] = schedule
                with (output / arm / 'receipt.json').open('x', encoding='utf-8') as receipt:
                    json.dump(report, receipt, indent=2)
                    receipt.write('\n')
    print(json.dumps({'passed': True, 'formal': args.formal, 'matchedPairs': len(schedule), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn-env', required=True)
    parser.add_argument('--owned-database', action='store_true')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--formal', action='store_true', help='Run all 5+30 windows in each of three orders')
    parser.add_argument('--exclusive-host', action='store_true')
    parser.add_argument('--matrix', choices=('legacy-v1', 'multicolumn-v2'), default='legacy-v1')
    parser.add_argument('--candidate-snapshot-profile', choices=('paged-256-v1',),
                        help='Compare boundary pages instead of same-statement writer proofs')
    parser.add_argument('--compact-artifacts', action='store_true',
                        help='Compress original capture bytes after each timed window')
    args = parser.parse_args()
    dsn = os.environ.get(args.dsn_env)
    if not args.owned_database or not dsn:
        parser.error('Use an explicitly owned disposable database and a populated DSN environment variable')
    if args.formal and not args.exclusive_host:
        parser.error('--formal requires --exclusive-host')
    if args.candidate_snapshot_profile and args.matrix != 'multicolumn-v2':
        parser.error('Boundary-page comparisons use --matrix multicolumn-v2')
    compare(args, dsn)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        main()
