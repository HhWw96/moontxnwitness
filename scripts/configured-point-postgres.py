"""Run configured point analysis in a disposable PostgreSQL 18 test database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('MTW_POINT_RUNTIME_DIR', ROOT / 'dist')).resolve()
sys.path.insert(0, str(ROOT / 'integrations/python'))

from moontxnwitness_capture.configured_session import ConfiguredPointWindow, InstallationInputs, canonical, write_new
from moontxnwitness_capture.configured_source import SourceInstallPolicy, identifier, install_configured_source
from moontxnwitness_capture.configured_sql import SQLCaptureConfig


def run_case(base, output, scenario):
    import psycopg
    from psycopg.conninfo import make_conninfo

    suffix = secrets.token_hex(6)
    owner, writer, schema = ('mtw_point_' + name + '_' + suffix for name in ('owner', 'writer', 'data'))
    password = secrets.token_hex(24)
    q = identifier
    target = q(schema) + '.roster'
    policy = SourceInstallPolicy('mtw_source_point_' + suffix, (writer,))
    config = SQLCaptureConfig.from_json(json.dumps({
        'format': 'moontxnwitness-configured-sql/v1',
        'defaultSchema': schema,
        'tables': [{
            'schema': schema, 'table': 'roster', 'primaryKey': 'id', 'model': 'relation-set-v1',
            'columns': [{'name': 'id', 'type': 'int64'}, {'name': 'active', 'type': 'bool'}],
        }],
    }))
    isolation = psycopg.IsolationLevel.REPEATABLE_READ if scenario == 'skew' else psycopg.IsolationLevel.SERIALIZABLE
    actor = {**base, 'user': writer, 'password': password}
    with psycopg.connect(make_conninfo(**base), autocommit=True) as control:
        control.execute(f'CREATE ROLE {q(owner)} NOLOGIN')
        control.execute(f"CREATE ROLE {q(writer)} LOGIN PASSWORD '{password}'")
        database = control.execute('SELECT current_database()').fetchone()[0]
        control.execute(f'GRANT CREATE ON DATABASE {q(database)} TO {q(owner)}')
        control.execute(f'SET ROLE {q(owner)}')
        control.execute(f'CREATE SCHEMA {q(schema)}')
        control.execute(f'CREATE TABLE {target}(id bigint PRIMARY KEY, active boolean NOT NULL)')
        control.execute(f'INSERT INTO {target} VALUES (1,true),(2,true)')
        control.execute(f'GRANT USAGE ON SCHEMA {q(schema)} TO {q(writer)}')
        control.execute(f'GRANT SELECT, UPDATE(active) ON {target} TO {q(writer)}')
        install = output / 'installation'
        install_configured_source(control, install, config, policy, opt_in=True)
        capture = ConfiguredPointWindow(output / 'capture', config, control, policy,
                                        InstallationInputs.from_attempt(install, policy), opt_in=True,
                                        automatic_writer_checkpoints=True)
        columns = 'id,active,__mtw_source_version'
        select_columns = 'id,active' if scenario == 'missing-version' else columns
        query = f'SELECT {select_columns} FROM {target} WHERE id=%s'
        update = f'UPDATE {target} SET active=%s WHERE id=%s RETURNING {columns}'

        def attempt(key, barrier=None):
            raw = psycopg.connect(make_conninfo(**actor))
            raw.isolation_level = isolation
            conn = capture.wrap_connection(raw)
            evidence = {'key': key, 'rows': [], 'outcome': 'unknown'}
            try:
                with conn.cursor() as cursor:
                    for candidate in (1, 2):
                        cursor.execute(query, (candidate,))
                        evidence['rows'].extend(cursor.fetchall())
                    if barrier is not None:
                        barrier.wait(timeout=15)
                    if all(row[1] for row in evidence['rows']):
                        cursor.execute(update, (False, key))
                        evidence['updated'] = cursor.fetchall()
                        cursor.execute(query, (key,))
                        evidence['ownRead'] = cursor.fetchall()
                        assert evidence['updated'][0][:2] == evidence['ownRead'][0][:2]
                        if scenario != 'missing-version':
                            assert evidence['updated'] == evidence['ownRead']
                # The enrolled connection records its identity immediately
                # before COMMIT; business code does not issue a probe.
                conn.commit()
                evidence['outcome'] = 'committed'
            except psycopg.errors.SerializationFailure as error:
                evidence['sqlstate'] = error.sqlstate
                conn.rollback()
                evidence['outcome'] = 'rolled-back'
            finally:
                conn.close()
            return evidence

        if scenario in ('ordered', 'unobserved-write', 'missing-version'):
            results = [attempt(1), attempt(2)]
            assert results[0]['updated'][0][:2] == results[1]['rows'][0][:2]
            if scenario != 'missing-version':
                assert results[0]['updated'][0] == results[1]['rows'][0]
            if scenario == 'unobserved-write':
                with psycopg.connect(make_conninfo(**actor)) as unobserved:
                    assert unobserved.execute(update, (False, 2)).fetchall()
        else:
            barrier = Barrier(2)
            with ThreadPoolExecutor(2) as workers:
                left, right = [workers.submit(attempt, key, barrier) for key in (1, 2)]
                results = [left.result(timeout=35), right.result(timeout=35)]
            if scenario == 'retry':
                failures = [value for value in results if value.get('sqlstate') == '40001']
                assert len(failures) == 1 and failures[0]['outcome'] == 'rolled-back'
                results.append(attempt(failures[0]['key']))
                assert results[-1]['outcome'] == 'committed'
        session = capture.seal()
        final = control.execute(f'SELECT id,active FROM {target} ORDER BY id').fetchall()
        assert sum(row[1] for row in final) == (0 if scenario in ('skew', 'unobserved-write') else 1)
        write_new(output / 'database-result.json', canonical({
            'scenario': scenario, 'serverVersion': control.info.server_version,
            'isolation': isolation.name, 'attempts': results, 'final': final,
        }) + '\n')
    return [capture.start_path, capture.end_path, session]


def cli(command, inputs, expected):
    child = subprocess.run([os.environ.get('MTW_NODE', 'node'), str(RUNTIME / 'moontxnwitness.mjs'),
                            command, *map(str, inputs)], capture_output=True, encoding='utf-8', timeout=60)
    if child.returncode != expected:
        raise AssertionError(child.stdout + child.stderr)
    return json.loads(child.stdout)


def check_negative(inputs, output):
    start, end, path = inputs
    def analyze(session_path, expected, *flags):
        return cli('analyze-configured-point-window-v4', [start, end, session_path, *flags], expected)

    def altered(name, kind, change):
        session = json.loads(path.read_text('utf-8'))
        records = list(map(json.loads, session['lifecycleText'].splitlines()))
        event = next(item for item in records if item['kind'] == kind)
        frame = json.loads(event['frameText'])
        change(frame)
        event['frameText'] = canonical(frame)
        prefix = ''.join(canonical(record) + '\n' for record in records[:-1])
        records[-1]['prefixSha256'] = hashlib.sha256(prefix.encode('utf-8')).hexdigest()
        session['lifecycleText'] = prefix + canonical(records[-1]) + '\n'
        mutated = output / (name + '.json')
        write_new(mutated, canonical(session) + '\n')
        return mutated

    partial = altered('partial', 'configured-delivery',
                      lambda frame: frame.update(complete=False, method='fetchone'))
    assert not analyze(partial, 3)['coverageComplete']
    forged = altered('forged-boundary', 'configured-point-start', lambda frame: frame.update(sha256='0' * 64))
    assert not analyze(forged, 2)['coverageComplete']
    forged = altered('forged-delivery', 'configured-delivery',
                     lambda frame: frame['rows'][0][1].update(value=False))
    assert not analyze(forged, 2)['coverageComplete']
    budget = output / 'point-budget.json'
    write_new(budget, '{"maxPointChecks":0}\n')
    assert not analyze(path, 3, '--options', budget)['coverageComplete']


def run_cases(base, output, repetitions=5):
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for attempt in range(repetitions):
        for scenario, status, code in [('skew', 'refuted', 1), ('ordered', 'checked-compatible', 0), ('retry', 'unknown', 3)]:
            folder = output / f'{attempt + 1}-{scenario}'
            folder.mkdir()
            inputs = run_case(base, folder, scenario)
            report = cli('analyze-configured-point-window-v4', inputs, code)
            assert report['status'] == status
            assert report['coverageComplete'] == (scenario != 'retry')
            if scenario == 'skew':
                assert report['itemCategory']['judgment']['status'] == 'refuted'
            if scenario == 'ordered':
                rules = report['model']['models'][0]['rules']
                proof = next(rule for rule in rules if rule['rule'] == 'completion/original-row-serial/data-only')
                assert proof['status'] == 'checked-compatible' and proof['evidence']['certificate']
            report_path = folder / 'point-report.json'
            write_new(report_path, canonical(report) + '\n')
            assert cli('verify-configured-point-window-v4', [*inputs, report_path], 0)['valid']
            if attempt == 0 and scenario in ('ordered', 'skew'):
                explained = folder / 'point-explanation.html'
                rendered = subprocess.run([os.environ.get('MTW_NODE', 'node'),
                    str(RUNTIME / 'moontxnwitness.mjs'), 'explain-configured-point-window-v4',
                    *map(str, inputs), str(report_path), '--output', str(explained)],
                    capture_output=True, encoding='utf8', timeout=60)
                assert rendered.returncode == 0, rendered.stdout + rendered.stderr
                html = explained.read_text('utf8')
                assert html.startswith('<!doctype html>') and f'>{status}</p>' in html
            if attempt == 0 and scenario == 'ordered':
                check_negative(inputs, folder)
            cases.append({'attempt': attempt + 1, 'scenario': scenario, 'status': status,
                          'reportSha256': hashlib.sha256(report_path.read_bytes()).hexdigest()})
    for scenario in ('missing-version', 'unobserved-write'):
        folder = output / scenario
        folder.mkdir()
        inputs = run_case(base, folder, scenario)
        report = cli('analyze-configured-point-window-v4', inputs, 3)
        assert not report['coverageComplete']
        write_new(folder / 'point-report.json', canonical(report) + '\n')
    receipt = {'passed': True, 'repetitions': repetitions, 'cases': cases,
               'negativeChecks': 6, 'build': json.loads((RUNTIME / 'build-manifest.json').read_text('utf8'))}
    write_new(output / 'receipt.json', canonical(receipt) + '\n')
    return receipt


if __name__ == '__main__':
    from psycopg.conninfo import conninfo_to_dict

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-database', action='store_true', required=True)
    parser.add_argument('--dsn-env', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_cases(conninfo_to_dict(os.environ[args.dsn_env]), args.output)))
