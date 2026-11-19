"""Compare uncaptured, source-only and fully sealed point CRUD on an owned database."""

from __future__ import annotations

import argparse
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
sys.path.insert(0, str(ROOT / 'integrations' / 'python'))

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from moontxnwitness_capture.configured_source_v2 import SourceInstallPolicy, install_configured_source_v2
from moontxnwitness_capture.configured_sql_v2 import ColumnConfig, PrimaryKeyConfigV2, SQLCaptureConfigV2, TableConfigV2
from moontxnwitness_capture.configured_window_v2 import ConfiguredCaptureWindowV2, SourceInputsV2


def percentile(samples, fraction):
    return sorted(samples)[math.ceil(len(samples) * fraction) - 1]


def write_cell(output, options, schema, role, writer, password, phase, keys, keys_for_transactions):
    path = output / f'{schema}-{phase}'
    path.mkdir()
    schema_name = f'{schema}_{phase.lower()}'
    target = sql.Identifier(schema_name, 'business_rows')
    native = {**options, 'user': writer, 'password': password}
    with psycopg.connect(**options, autocommit=True) as control:
        control.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(schema_name), sql.Identifier(role)))
        control.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        control.execute(sql.SQL('CREATE TABLE {} (id bigint PRIMARY KEY, value bigint NOT NULL)').format(target))
        control.execute(sql.SQL('INSERT INTO {} SELECT k, 0 FROM pg_catalog.generate_series(1, %s) AS k').format(target), (keys,))
        control.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema_name), sql.Identifier(writer)))
        control.execute(sql.SQL('GRANT SELECT, UPDATE ON {} TO {}').format(target, sql.Identifier(writer)))

        config = SQLCaptureConfigV2(TableConfigV2(schema_name, 'business_rows',
            PrimaryKeyConfigV2('id', 'int64'), (ColumnConfig('value', 'int64'),)))
        policy = SourceInstallPolicy('mtw_source_' + schema_name, (writer,))
        installation = None
        if phase != 'A':
            installation = path / 'installation'
            install_configured_source_v2(control, installation, config, policy, opt_in=True)
        window = None
        select = sql.SQL('SELECT id, value FROM {} WHERE id=%s').format(target).as_string(control)
        modify = sql.SQL('UPDATE {} SET value=%s WHERE id=%s RETURNING id, value').format(target).as_string(control)

        def connect():
            return psycopg.connect(**native)

        start = time.perf_counter_ns()
        if installation is not None and phase == 'C':
            window = ConfiguredCaptureWindowV2(path / 'capture', config, control, policy,
                SourceInputsV2.from_directory(installation), opt_in=True, snapshot_profile='paged-v1')
        acquire = window.psycopg_factory(connect) if window is not None else connect
        samples = []
        begin_business = time.perf_counter_ns()
        with acquire() as connection:
            for key in keys_for_transactions:
                begin = time.perf_counter_ns()
                row = connection.execute(select, (key,)).fetchone()
                if row is None or row[0] != key:
                    raise ValueError('Control workload did not deliver the requested key')
                updated = connection.execute(modify, (row[1] + 1, key)).fetchone()
                if updated != (key, row[1] + 1):
                    raise ValueError('Control workload did not deliver the expected update')
                connection.commit()
                samples.append(time.perf_counter_ns() - begin)
        end_business = time.perf_counter_ns()
        bundle = window.seal() if window is not None else None
        end = time.perf_counter_ns()
        final = control.execute(sql.SQL('SELECT id,value FROM {} ORDER BY id').format(target)).fetchall()
        expected = dict.fromkeys(range(1, keys + 1), 0)
        for key in keys_for_transactions:
            expected[key] += 1
        if final != list(expected.items()):
            raise ValueError('Final business data differ')

        row = {'phase': phase, 'commits': len(samples), 'transactionSamplesNs': samples,
               'medianTransactionNs': statistics.median(samples), 'p95TransactionNs': percentile(samples, .95),
               'windowOpenNs': begin_business - start, 'businessNs': end_business - begin_business,
               'windowSealNs': end - end_business, 'windowNs': end - start,
               'finalBusinessSha256': hashlib.sha256(json.dumps(final).encode('utf8')).hexdigest()}
        if bundle is not None:
            digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
            row.update(bundle=str(bundle), bundleSha256=digest, config=config.to_dict(), policy=policy.to_dict(),
                       producerReceipt=str(bundle.with_name('window-receipt.json')))
        return row


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dsn-env', required=True, help='Environment variable for a disposable PostgreSQL database')
    cli.add_argument('--owned-database', action='store_true', help='Allow creation of isolated roles and tables')
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--keys', type=int, choices=range(8, 65), default=24, metavar='8..64')
    cli.add_argument('--transactions', type=int, choices=range(1, 33), default=24, metavar='1..32')
    args = cli.parse_args()
    if not args.owned_database or not os.environ.get(args.dsn_env):
        cli.error('An explicit disposable database and populated DSN variable are required')
    if psycopg.__version__ != '3.3.6':
        cli.error('Use psycopg 3.3.6')
    options = conninfo_to_dict(os.environ[args.dsn_env])
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    run_id = secrets.token_hex(4)
    role, writer, password = 'mtw_cost_owner_' + run_id, 'mtw_cost_writer_' + run_id, secrets.token_hex(20)
    report = {'format': 'configured-source-window-cost-pilot/v1', 'passed': False,
              'formalPerformanceMeasurement': False, 'actualDatabaseExecution': False,
              'keys': args.keys, 'transactionsPerPhase': args.transactions, 'batches': [],
              'environment': {'system': platform.system(), 'machine': platform.machine(),
                              'python': platform.python_version(), 'psycopg': psycopg.__version__},
              'producerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        with psycopg.connect(**options, autocommit=True) as admin:
            if admin.info.server_version != 180006:
                raise ValueError('This pilot requires PostgreSQL 18.6')
            report['actualDatabaseExecution'] = True
            admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(writer), sql.Literal(password)))
            admin.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO {}').format(sql.Identifier(admin.info.dbname), sql.Identifier(role)))
        workload = [(i * 17 % args.keys) + 1 for i in range(args.transactions)]
        for index, order in enumerate(('ABC', 'BCA', 'CAB')):
            batch = {'order': order, 'cells': {}}
            report['batches'].append(batch)
            for phase in order:
                batch['cells'][phase] = write_cell(output, options, f'mtw_cost_{run_id}_{index}',
                    role, writer, password, phase, args.keys, workload)
            a, b, c = (batch['cells'][phase] for phase in 'ABC')
            if len({a['finalBusinessSha256'], b['finalBusinessSha256'], c['finalBusinessSha256']}) != 1:
                raise ValueError('Business outcomes differ across phases')
            batch['completeWindowThroughputRatioCA'] = a['windowNs'] / c['windowNs']
            batch['transactionP95RatioCA'] = c['p95TransactionNs'] / a['p95TransactionNs']
        report['passed'] = True
    finally:
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': report['passed'], 'batches': len(report['batches']), 'output': str(output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
