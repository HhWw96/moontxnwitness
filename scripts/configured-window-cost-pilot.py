"""Compare uncaptured, source-only and fully sealed point CRUD on an owned database."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_ROOT = Path(os.environ.get('MTW_COST_PRODUCER_ROOT', str(ROOT))).resolve()
sys.path.insert(0, str(PRODUCER_ROOT / 'integrations' / 'python'))

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from moontxnwitness_capture.configured_source_v2 import SourceInstallPolicy, install_configured_source_v2
from moontxnwitness_capture.configured_sql_v2 import ColumnConfig, PrimaryKeyConfigV2, SQLCaptureConfigV2, TableConfigV2
from moontxnwitness_capture.configured_window_v2 import ConfiguredCaptureWindowV2, SourceInputsV2
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2


def percentile(samples, fraction):
    return sorted(samples)[math.ceil(len(samples) * fraction) - 1]


def peak_process_rss():
    if sys.platform == 'win32':
        import ctypes as c
        from ctypes import wintypes as w

        class Counters(c.Structure):
            _fields_ = [('cb', w.DWORD), ('faults', w.DWORD)] + [
                (field, c.c_size_t) for field in (
                    'peak', 'working', 'peak_paged', 'paged', 'peak_nonpaged',
                    'nonpaged', 'pagefile', 'peak_pagefile')]

        current = c.windll.kernel32.GetCurrentProcess
        current.restype = w.HANDLE
        memory = c.windll.psapi.GetProcessMemoryInfo
        memory.argtypes = [w.HANDLE, c.POINTER(Counters), w.DWORD]
        memory.restype = w.BOOL
        result = Counters()
        result.cb = c.sizeof(result)
        if not memory(current(), c.byref(result), result.cb):
            raise c.WinError()
        return result.peak
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == 'darwin' else rss * 1024


def write_cell(output, options, schema, role, writer, password, phase, keys, keys_for_transactions,
               *, workers=1, coordinated=False, seal_profile=None, writer_proof_profile=None,
               snapshot_profile='paged-v1', payload_columns=0):
    path = output / f'{schema}-{phase}'
    path.mkdir()
    schema_name = f'{schema}_{phase.lower()}'
    target = sql.Identifier(schema_name, 'business_rows')
    native = {**options, 'user': writer, 'password': password}
    payload = tuple(f'p{index:02}' for index in range(1, payload_columns + 1))
    row_identifiers = [sql.Identifier(name) for name in ('id', 'value', *payload)]
    row_projection = sql.SQL(', ').join(row_identifiers)
    columns = sql.SQL(', ').join(
        [sql.SQL('id bigint PRIMARY KEY')] +
        [sql.SQL('{} bigint NOT NULL').format(column) for column in row_identifiers[1:]])
    initial_values = sql.SQL(', ').join(
        [sql.SQL('k'), sql.SQL('0')] +
        [sql.SQL('k + {}').format(sql.Literal(index)) for index in range(1, payload_columns + 1)])

    def expected_row(key, value):
        return (key, value, *(key + index for index in range(1, payload_columns + 1)))

    with psycopg.connect(**options, autocommit=True) as control:
        control.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(schema_name), sql.Identifier(role)))
        control.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        control.execute(sql.SQL('CREATE TABLE {} ({})').format(target, columns))
        control.execute(sql.SQL('INSERT INTO {} SELECT {} FROM pg_catalog.generate_series(1, %s) AS k')
                        .format(target, initial_values), (keys,))
        control.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema_name), sql.Identifier(writer)))
        control.execute(sql.SQL('GRANT SELECT, UPDATE ON {} TO {}').format(target, sql.Identifier(writer)))

        config = SQLCaptureConfigV2(TableConfigV2(schema_name, 'business_rows',
            PrimaryKeyConfigV2('id', 'int64'), tuple(ColumnConfig(name, 'int64') for name in ('value', *payload))))
        policy = SourceInstallPolicy('mtw_source_' + schema_name, (writer,))
        installation = None
        if phase != 'A':
            installation = path / 'installation'
            install_configured_source_v2(control, installation, config, policy, opt_in=True)
        window = None
        select = sql.SQL('SELECT {} FROM {} WHERE id=%s').format(
            row_projection, target).as_string(control)
        modify = sql.SQL('UPDATE {} SET value=%s WHERE id=%s RETURNING {}').format(
            target, row_projection).as_string(control)

        def connect():
            return psycopg.connect(**native)

        start = time.perf_counter_ns()
        if installation is not None and phase == 'C':
            capture = {} if seal_profile is None else {'seal_profile': seal_profile}
            if writer_proof_profile is not None:
                capture['projection_options'] = PointProjectionOptionsV2(config, writer_proof_profile=writer_proof_profile)
            window = ConfiguredCaptureWindowV2(path / 'capture', config, control, policy,
                SourceInputsV2.from_directory(installation), opt_in=True, snapshot_profile=snapshot_profile,
                **capture)
        acquire = window.psycopg_factory(connect) if window is not None else connect
        def execute(keys_for_worker):
            samples = []
            with acquire() as connection:
                for key in keys_for_worker:
                    begin = time.perf_counter_ns()
                    if coordinated:
                        # Lock through UPDATE first; the following read sees
                        # this transaction's own write even on a shared key.
                        updated = connection.execute(modify, (1, key)).fetchone()
                        row = connection.execute(select, (key,)).fetchone()
                        if row != expected_row(key, 1) or row != updated:
                            raise ValueError('Concurrent workload did not deliver its own write')
                    else:
                        row = connection.execute(select, (key,)).fetchone()
                        if row is None or row[0] != key:
                            raise ValueError('Control workload did not deliver the requested key')
                        updated = connection.execute(modify, (row[1] + 1, key)).fetchone()
                        if updated != expected_row(key, row[1] + 1):
                            raise ValueError('Control workload did not deliver the expected update')
                    connection.commit()
                    samples.append(time.perf_counter_ns() - begin)
            return samples
        begin_business = time.perf_counter_ns()
        if workers == 1:
            samples = execute(keys_for_transactions)
        else:
            assignments = [keys_for_transactions[offset::workers] for offset in range(workers)]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                samples = [sample for group in executor.map(execute, assignments) for sample in group]
        end_business = time.perf_counter_ns()
        bundle = window.seal() if window is not None else None
        end = time.perf_counter_ns()
        final = control.execute(sql.SQL('SELECT {} FROM {} ORDER BY id').format(row_projection, target)).fetchall()
        expected = dict.fromkeys(range(1, keys + 1), 0)
        for key in keys_for_transactions:
            expected[key] = 1 if coordinated else expected[key] + 1
        if final != [expected_row(key, value) for key, value in expected.items()]:
            raise ValueError('Final business data differ')

        row = {'phase': phase, 'commits': len(samples), 'transactionSamplesNs': samples,
               'medianTransactionNs': statistics.median(samples), 'p95TransactionNs': percentile(samples, .95),
               'windowOpenNs': begin_business - start, 'businessNs': end_business - begin_business,
               'windowSealNs': end - end_business, 'windowNs': end - start,
               'finalBusinessSha256': hashlib.sha256(json.dumps(final).encode('utf8')).hexdigest(),
               'connections': workers, 'outputBytes': 0}
        if bundle is not None:
            digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
            row.update(bundle=str(bundle), bundleSha256=digest, config=config.to_dict(), policy=policy.to_dict(),
                       outputBytes=bundle.stat().st_size,
                       producerReceipt=str(bundle.with_name('window-receipt.json')))
        if coordinated:
            if installation is not None:
                control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(policy.namespace)))
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema_name)))
        return row


FORMAL_LOADS = (
    ('small', 24, 1, tuple(range(1, 25))),
    ('wide', 1024, 4, tuple((i * 17 % 1024) + 1 for i in range(24))),
    ('hot', 32, 8, tuple(i % 4 + 1 for i in range(22)) + (5, 6)),
)


def formal_batches(report, output, options, run_id, role, writer, password, warmups, samples,
                   seal_profile, writer_proof_profile):
    report['warmupWindowsPerPhase'] = warmups
    report['measuredWindowsPerPhase'] = samples
    for workload, keys, workers, transactions in FORMAL_LOADS:
        for index, order in enumerate(('ABC', 'BCA', 'CAB')):
            batch = {'workload': workload, 'keys': keys, 'connections': workers, 'order': order,
                     'warmup': [], 'windows': []}
            report['batches'].append(batch)
            for kind, count, result in (('warmup', warmups, batch['warmup']),
                                         ('measured', samples, batch['windows'])):
                for number in range(count):
                    cells = {}
                    result.append(cells)
                    schema = f'mtw_{run_id}_{workload}_{index}_{kind[0]}{number}'
                    for phase in order:
                        cells[phase] = write_cell(output, options, schema, role, writer, password,
                            phase, keys, transactions, workers=workers, coordinated=True,
                            seal_profile=seal_profile, writer_proof_profile=writer_proof_profile)
                    if len({cell['finalBusinessSha256'] for cell in cells.values()}) != 1:
                        raise ValueError('Business outcomes differ across phases')
            medians = {phase: statistics.median(window[phase]['windowNs'] for window in batch['windows'])
                       for phase in order}
            p95s = {phase: percentile([value for window in batch['windows']
                                      for value in window[phase]['transactionSamplesNs']], .95)
                    for phase in order}
            batch['completeWindowThroughputRatioCA'] = medians['A'] / medians['C']
            batch['transactionP95RatioCA'] = p95s['C'] / p95s['A']


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dsn-env', required=True, help='Environment variable for a disposable PostgreSQL database')
    cli.add_argument('--owned-database', action='store_true', help='Allow creation of isolated roles and tables')
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--keys', type=int, choices=range(8, 65), default=24, metavar='8..64')
    cli.add_argument('--transactions', type=int, choices=range(1, 33), default=24, metavar='1..32')
    group = cli.add_mutually_exclusive_group()
    group.add_argument('--formal', action='store_true', help='Run the frozen 5+30-window protocol')
    group.add_argument('--formal-smoke', action='store_true', help='Exercise all formal loads once without a performance claim')
    cli.add_argument('--exclusive-host', action='store_true', help='Confirm that the formal run has exclusive use of the benchmark host')
    cli.add_argument('--seal-profile', choices=('original-v2', 'streamed-v1'),
                     help='Select a producer seal profile when supported by the tested source')
    cli.add_argument('--writer-proof-profile', choices=('returning-v1',),
                     help='Explicitly use the synchronous RETURNING client writer proof')
    args = cli.parse_args()
    if not args.owned_database or not os.environ.get(args.dsn_env):
        cli.error('An explicit disposable database and populated DSN variable are required')
    if psycopg.__version__ != '3.3.6':
        cli.error('Use psycopg 3.3.6')
    if args.formal and not args.exclusive_host:
        cli.error('Formal measurement requires --exclusive-host')
    options = conninfo_to_dict(os.environ[args.dsn_env])
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    run_id = secrets.token_hex(4)
    role, writer, password = 'mtw_cost_owner_' + run_id, 'mtw_cost_writer_' + run_id, secrets.token_hex(20)
    formal_shape = args.formal or args.formal_smoke
    producer = Path(sys.modules[ConfiguredCaptureWindowV2.__module__].__file__).parent
    producer_hashes = {name: hashlib.sha256((producer / name).read_bytes()).hexdigest()
        for name in ('configured_window_v2.py', 'configured_point_capture_v2.py', 'configured_point_projection_v2.py')}
    report = {'format': ('configured-source-window-cost/v1' if formal_shape
                         else 'configured-source-window-cost-pilot/v1'), 'passed': False,
              'formalPerformanceMeasurement': False, 'actualDatabaseExecution': False,
              'keys': args.keys, 'transactionsPerPhase': args.transactions, 'batches': [],
              'sealProfileRequested': args.seal_profile,
              'writerProofProfileRequested': args.writer_proof_profile,
              'environment': {'system': platform.system(), 'machine': platform.machine(),
                              'python': platform.python_version(), 'psycopg': psycopg.__version__},
              'harnessSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'producerFilesSha256': producer_hashes,
              'producerSha256': hashlib.sha256(json.dumps(producer_hashes,sort_keys=True).encode()).hexdigest()}
    try:
        with psycopg.connect(**options, autocommit=True) as admin:
            if admin.info.server_version != 180006:
                raise ValueError('This pilot requires PostgreSQL 18.6')
            report['actualDatabaseExecution'] = True
            admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(writer), sql.Literal(password)))
            admin.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO {}').format(sql.Identifier(admin.info.dbname), sql.Identifier(role)))
        workload = [(i * 17 % args.keys) + 1 for i in range(args.transactions)]
        if formal_shape:
            report.pop('keys')
            report['transactionsPerPhase'] = 24
            formal_batches(report, output, options, run_id, role, writer, password,
                           5 if args.formal else 0, 30 if args.formal else 1,
                           args.seal_profile, args.writer_proof_profile)
        for index, order in enumerate(() if formal_shape else ('ABC', 'BCA', 'CAB')):
            batch = {'order': order, 'cells': {}}
            report['batches'].append(batch)
            for phase in order:
                batch['cells'][phase] = write_cell(output, options, f'mtw_cost_{run_id}_{index}',
                    role, writer, password, phase, args.keys, workload, seal_profile=args.seal_profile,
                    writer_proof_profile=args.writer_proof_profile)
            a, b, c = (batch['cells'][phase] for phase in 'ABC')
            if len({a['finalBusinessSha256'], b['finalBusinessSha256'], c['finalBusinessSha256']}) != 1:
                raise ValueError('Business outcomes differ across phases')
            batch['completeWindowThroughputRatioCA'] = a['windowNs'] / c['windowNs']
            batch['transactionP95RatioCA'] = c['p95TransactionNs'] / a['p95TransactionNs']
        report['peakProcessRssBytes'] = peak_process_rss()
        report['formalPerformanceMeasurement'] = args.formal
        report['passed'] = True
    finally:
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': report['passed'], 'batches': len(report['batches']), 'output': str(output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
