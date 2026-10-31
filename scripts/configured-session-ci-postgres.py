"""Explicit owned-CI setup and original same-connection diagnostic execution.

No installation or connection happens on import. Credentials remain in memory.
The original consumer SQL is retained; no source-window authentication is granted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/python'))
from moontxnwitness_capture.configured_sql import SQLCaptureConfig
from moontxnwitness_capture.configured_source import identifier, SourceInstallPolicy, VERSION_COLUMN
from moontxnwitness_capture.configured_session import canonical, write_new


def source_policy(token, writer):
    """Validate the private namespace before any role or table is created."""
    if not re.fullmatch('[0-9a-f]{12}', token):
        raise ValueError('Owned fixture token must be twelve lowercase hexadecimal characters')
    return SourceInstallPolicy('mtw_source_cs_' + token, (writer,), 4096, 8388608)


def initial_request(table, key):
    fields = ','.join(identifier(column.name) for column in table.columns)
    fields += ',' + identifier(VERSION_COLUMN)
    return {'sql': 'SELECT ' + fields + ' FROM ' + identifier(table.schema) + '.' +
            identifier(table.table) + ' WHERE ' + identifier(table.primary_key) + '=%s',
            'parameters': [key]}


def retain_controller_result(out, completed, *, timed_out=False):
    """Keep exact owned-fixture streams; emit only allowlisted diagnostics.

    The raw streams are retained in the uploaded owned-CI attempt, never printed
    to the console. An untrusted exception message/DSN is not a safe log summary.
    """
    stdout = completed.stdout or b''; stderr = completed.stderr or b''
    if isinstance(stdout, str): stdout = stdout.encode('utf8')
    if isinstance(stderr, str): stderr = stderr.encode('utf8')
    write_new(out/'controller-stdout.json', stdout)
    write_new(out/'controller-stderr.json', stderr)
    diagnostic = {'format': 'configured-session-controller-diagnostic/v1',
                  'exitCode': completed.returncode, 'timedOut': timed_out,
                  'stdout': {'path': 'controller-stdout.json', 'bytes': len(stdout), 'sha256': hashlib.sha256(stdout).hexdigest()},
                  'stderr': {'path': 'controller-stderr.json', 'bytes': len(stderr), 'sha256': hashlib.sha256(stderr).hexdigest()},
                  'reasonCode': 'timeout' if timed_out else 'inspect-retained-controller-streams',
                  'sourceFactsProduced': False, 'isolationAnalysisReady': False}
    text = stderr[-65536:].decode('utf8', errors='replace')
    reasons = [('Explicit private mtw_source_* namespace required', 'invalid-private-source-namespace'),
               ('OptionalParserUnavailable', 'optional-sql-parser-unavailable'),
               ('No module named', 'python-module-unavailable'),
               ('Execution needs at least 1GiB', 'execution-resource-reserve'),
               ('Caller-pinned runtime bytes differ', 'diagnostic-runtime-digest-mismatch'),
               ('Self-contained compiled diagnostic bridge required', 'diagnostic-runtime-is-not-self-contained')]
    if not timed_out:
        for marker, code in reasons:
            if marker in text:
                diagnostic['reasonCode'] = code; break
    safe_errors = {'ValueError','TypeError','ImportError','ModuleNotFoundError','OptionalParserUnavailable',
                   'SourceInstallError','RecognitionError','OperationalError','ProgrammingError','RuntimeError',
                   'OSError','FileNotFoundError','PermissionError','AssertionError'}
    for line in reversed(text.splitlines()):
        first = line.split(':',1)[0].rsplit('.',1)[-1]
        if first in safe_errors:
            diagnostic['controllerErrorClass'] = first; break
        try: value = json.loads(line)
        except (ValueError, TypeError): continue
        if isinstance(value, dict):
            error_class = value.get('errorClass')
            if isinstance(error_class, str) and error_class in safe_errors: diagnostic['controllerErrorClass'] = error_class
            if value.get('failedStage') in ('connect','installation-and-original-initial-reads','independent-diagnostic-replay'):
                diagnostic['controllerFailedStage'] = value['failedStage']
            break
    write_new(out/'controller-diagnostic.json', canonical(diagnostic) + '\n')
    return diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--owned-database', action='store_true')
    parser.add_argument('--dsn-env', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not args.execute or not args.owned_database:
        raise ValueError('Explicit owned-database execution required')
    if not os.environ.get(args.dsn_env):
        raise ValueError('Explicit DSN environment missing')
    out = Path(args.output).resolve()
    if out.exists():
        raise ValueError('New independent attempt directory required')
    out.mkdir(parents=True)
    stage = 'setup'
    controller_diagnostic = None
    try:
        import psycopg
        base = SQLCaptureConfig.from_json(
            (ROOT / 'examples/configured-session/config.json').read_text('utf8'))
        token = secrets.token_hex(6)
        owner, writer = 'mtw_cs_owner_' + token, 'mtw_cs_writer_' + token
        stage = 'validate-owned-source-policy'
        validated_policy = source_policy(token, writer)
        config = replace(base, tables=tuple(
            replace(table, schema='mtw_cs_' + token + '_' + str(index))
            for index, table in enumerate(base.tables)),
            default_schema='mtw_cs_' + token + '_0')
        q = identifier
        rows = [(1, 100, True, 'seed-a'), ('feature-a', True, 'seed-b'),
                (1, 'row', 23, False, 'east', 'seed-c')]
        queries = []
        stage = 'create-owned-tables'
        with psycopg.connect(os.environ[args.dsn_env], autocommit=True) as admin:
            assert admin.execute('SHOW server_version_num').fetchone()[0].startswith('18')
            for role in (owner, writer):
                admin.execute('CREATE ROLE ' + q(role) +
                              (' NOLOGIN' if role == owner else ' LOGIN') +
                              ' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
            database = admin.execute('SELECT current_database()').fetchone()[0]
            admin.execute('GRANT CREATE ON DATABASE ' + q(database) + ' TO ' + q(owner))
            admin.execute('SET ROLE ' + q(owner))
            for table, values in zip(config.tables, rows):
                target = q(table.schema) + '.' + q(table.table)
                columns = ','.join(
                    q(column.name) + ' ' +
                    {'int64': 'bigint', 'bool': 'boolean', 'text': 'text COLLATE "C"'}[column.type] +
                    (' PRIMARY KEY' if column.name == table.primary_key else ' NOT NULL')
                    for column in table.columns)
                admin.execute('CREATE SCHEMA ' + q(table.schema))
                admin.execute('CREATE TABLE ' + target + '(' + columns + ')')
                admin.execute('INSERT INTO ' + target + ' VALUES(' +
                              ','.join('%s' for _ in values) + ')', values)
                admin.execute('GRANT USAGE ON SCHEMA ' + q(table.schema) + ' TO ' + q(writer))
                admin.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ' + target + ' TO ' + q(writer))
                queries.append(initial_request(table, values[0]))
        configuration, policy, requests = out/'config.json', out/'policy.json', out/'requests.json'
        write_new(configuration, canonical(config.to_dict()) + '\n')
        write_new(policy, canonical(validated_policy.to_dict()) + '\n')
        write_new(requests, canonical(queries) + '\n')
        runtime = ROOT/'dist/configured-session-core.mjs'
        runtime_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        stage = 'original-same-connection-controller'
        command = [sys.executable, '-B', str(ROOT/'scripts/configured-session-postgres.py'),
                   '--config', str(configuration), '--policy', str(policy), '--queries', str(requests),
                   '--output', str(out/'attempt'), '--execute', '--dsn-env', args.dsn_env,
                   '--owner-role', owner, '--runtime', str(runtime), '--runtime-sha256', runtime_sha,
                   '--node', os.environ.get('MTW_NODE', 'node')]
        try:
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as error:
            completed = subprocess.CompletedProcess([], 124, error.stdout or b'', error.stderr or b'')
            controller_diagnostic = retain_controller_result(out, completed, timed_out=True)
            raise RuntimeError('Configured execution controller timed out') from error
        controller_diagnostic = retain_controller_result(out, completed)
        if completed.returncode:
            raise RuntimeError('Configured execution controller failed')
        diagnosis = out/'attempt/diagnosis.json'
        report = json.loads(diagnosis.read_bytes())
        assert report['status'] == 'diagnostic-only'
        assert report['resultConsistency'] == 'consistent-observed-results'
        assert report['initialSourceStatus'] == 'consistent-initial-components'
        assert len(report['results']) == 3
        for field in ('sourceFactsProduced', 'writerWindowVerified', 'sourceAuthenticated',
                      'serverInstanceIdentityAuthenticated', 'isolationModelChecked', 'isolationAnalysisReady'):
            assert report[field] is False
        receipt = {'format': 'configured-session-owned-postgres-check/v1', 'passed': True,
                   'actualDatabaseExecution': True, 'configuredTables': 3, 'businessColumnCounts': [4, 3, 6],
                   'sourceFactsProduced': False, 'writerWindowVerified': False, 'sourceAuthenticated': False,
                   'isolationAnalysisReady': False, 'sameConnectionInitialDiagnosticOnly': True,
                   'runtimeSha256': runtime_sha, 'diagnosisSha256': hashlib.sha256(diagnosis.read_bytes()).hexdigest(),
                   'originalRequestsSha256': hashlib.sha256(requests.read_bytes()).hexdigest()}
        write_new(out/'receipt.json', canonical(receipt) + '\n')
        print(canonical(receipt))
        return 0
    except BaseException as error:
        failure = {'format': 'configured-session-owned-postgres-failure/v1', 'passed': False,
                   'stage': stage, 'errorClass': type(error).__name__, 'actualDatabaseExecution': None,
                   'sourceFactsProduced': False, 'writerWindowVerified': False,
                   'isolationAnalysisReady': False, 'retryPerformed': False}
        if controller_diagnostic is not None:
            failure['controllerDiagnostic'] = controller_diagnostic
        write_new(out/'failure.json', canonical(failure) + '\n')
        print(canonical(failure), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
