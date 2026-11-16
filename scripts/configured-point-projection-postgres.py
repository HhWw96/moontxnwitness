"""Compare point projection mappings in a new, retained PostgreSQL 18.6 cluster.

This runs SQL and projects returned fields explicitly. It does not exercise a
business driver wrapper, install a complete source ledger or accept model facts.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/python'))
from moontxnwitness_capture.configured_sql_v2 import (
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2,
    ConfiguredSQLParserV2, TEXT_COMPARISON,
)
from moontxnwitness_capture.configured_point_projection_v2 import (
    PointProjectionOptionsV2, build_point_projection,
)


def quote(value): return '"' + value.replace('"', '""') + '"'
def literal(value): return "'" + value.replace("'", "''") + "'"
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    kind = type(value).__module__ + '.' + type(value).__qualname__
    if type(value) is uuid.UUID: return {'pythonType': kind, 'value': str(value)}
    if type(value) is int: return {'pythonType': kind, 'value': str(value)}
    if type(value) is bool: return {'pythonType': kind, 'value': value}
    if type(value) is str: return {'pythonType': kind, 'value': value}
    if value is None: return {'pythonType': kind, 'value': None}
    raise TypeError('Unsupported observed scalar')


def observe(cursor):
    result = cursor.pgresult
    b64 = lambda value: None if value is None else base64.b64encode(value).decode('ascii')
    record = {'status': int(result.status), 'commandStatusBase64': b64(result.command_status),
              'commandTuples': result.command_tuples, 'fieldCount': int(result.nfields),
              'rowCount': int(result.ntuples), 'fields': [], 'rows': [],
              'clientEncodingBase64': b64(cursor.connection.pgconn.parameter_status(b'client_encoding')),
              'backendPid': cursor.connection.info.backend_pid,
              'transactionStatus': int(cursor.connection.info.transaction_status)}
    for index in range(result.nfields):
        record['fields'].append({'nameBase64': b64(result.fname(index)), 'oid': result.ftype(index),
            'format': result.fformat(index), 'typmod': result.fmod(index),
            'tableOid': result.ftable(index), 'tableColumn': result.ftablecol(index)})
    for row in range(result.ntuples):
        record['rows'].append([b64(result.get_value(row, column)) for column in range(result.nfields)])
    values = cursor.fetchall() if cursor.description is not None else None
    record['deliveryObservation'] = {
        'method': None if values is None else 'fetchall',
        'rowsContainerPythonType': None if values is None else type(values).__module__ + '.' + type(values).__qualname__,
        'rowPythonTypes': [] if values is None else [type(row).__module__ + '.' + type(row).__qualname__ for row in values],
        'requestedSize': None, 'effectiveSize': None,
        'exhaustedObserved': values is not None,
    }
    return record, values


def layouts():
    text = lambda name: ColumnConfig(name, 'text', TEXT_COMPARISON)
    return (
        TableConfigV2('ledger', 'accounts', PrimaryKeyConfigV2('account_no', 'int64'),
                      (ColumnConfig('balance', 'int64'), ColumnConfig('active', 'bool'), text('label'))),
        TableConfigV2('App-X', 'Customer.Space', PrimaryKeyConfigV2('User ID', 'text', TEXT_COMPARISON),
                      (ColumnConfig('quota', 'int64'), ColumnConfig('live', 'bool'), text('zone'))),
        TableConfigV2('业务', '成员', PrimaryKeyConfigV2('用户编号', 'uuid'),
                      (text('电子邮件'), ColumnConfig('启用', 'bool'))),
    )


def suite(connection):
    records = []
    for index, table in enumerate(layouts()):
        config = SQLCaptureConfigV2(table)
        parser = ConfiguredSQLParserV2(config)
        target = quote(table.schema) + '.' + quote(table.table)
        key = quote(table.primary_key)
        fields = ', '.join(quote(c.name) for c in table.columns)
        types = {'int64': 'bigint', 'bool': 'boolean', 'text': 'text COLLATE pg_catalog."C"', 'uuid': 'uuid'}
        connection.execute('CREATE SCHEMA ' + quote(table.schema))
        connection.execute('CREATE TABLE ' + target + ' (' + ', '.join(
            quote(c.name) + ' ' + types[c.type] + ' NOT NULL' + (' PRIMARY KEY' if c.name == table.primary_key else '')
            for c in table.columns) + ')')
        identity = 7 if table.key.type == 'int64' else '键🙂' if table.key.type == 'text' else uuid.UUID('a8098c1a-f86e-11da-bd1a-00112444be1e')
        missing = 8 if table.key.type == 'int64' else '另一个键' if table.key.type == 'text' else uuid.UUID('00000000-0000-0000-0000-000000000008')
        values = lambda key_value: tuple(key_value if c.name == table.primary_key else 17 if c.type == 'int64' else True if c.type == 'bool' else '原始🙂文本' for c in table.columns)
        slots = ', '.join('%s' for _ in table.columns)
        connection.execute('INSERT INTO ' + target + ' (' + fields + ') VALUES (' + slots + ')', values(identity))
        cases = [
            ('select-explicit', 'SELECT ' + fields + ' FROM ' + target + ' WHERE ' + key + '=%s', (identity,)),
            ('select-star', 'SELECT x.* FROM ' + target + ' x WHERE x.' + key + '=%s', (identity,)),
            ('select-empty', 'SELECT ' + fields + ' FROM ' + target + ' WHERE ' + key + '=%s', (missing,)),
            ('insert-returning', 'INSERT INTO ' + target + '(' + fields + ') VALUES (' + slots + ') RETURNING *', values(missing)),
            ('insert-no-returning', 'INSERT INTO ' + target + '(' + fields + ') VALUES (' + slots + ')', values(missing)),
            ('delete-returning', 'DELETE FROM ' + target + ' WHERE ' + key + '=%s RETURNING ' + key + ' AS "Business Key"', (identity,)),
            ('delete-no-returning', 'DELETE FROM ' + target + ' WHERE ' + key + '=%s', (identity,)),
            ('delete-empty', 'DELETE FROM ' + target + ' WHERE ' + key + '=%s RETURNING *', (missing,)),
        ]
        changed = table.business_columns[0]
        new_value = 23 if changed.type == 'int64' else 'new@example.invalid'
        for returning in (' RETURNING *', ' RETURNING ' + key, ''):
            cases.append(('update-' + str(len(cases)), 'UPDATE ' + target + ' SET ' + quote(changed.name) + '=%s WHERE ' + key + '=%s' + returning, (new_value, identity)))
        baseline = {}
        for name, sql, parameters in cases:
            connection.execute('BEGIN')
            try:
                cursor = connection.execute(sql, parameters)
                native, rows = observe(cursor)
                baseline[name] = {'native': native, 'rows': rows, 'rowcount': cursor.rowcount}
            finally:
                connection.execute('ROLLBACK')
        sequence = quote(table.schema) + '."versions"'
        connection.execute('CREATE SEQUENCE ' + sequence + ' AS bigint')
        connection.execute('ALTER TABLE ' + target + ' ADD COLUMN "__mtw_source_version" bigint')
        connection.execute('UPDATE ' + target + ' SET "__mtw_source_version"=nextval(' + literal(sequence) + ')')
        connection.execute('ALTER TABLE ' + target + ' ALTER COLUMN "__mtw_source_version" SET NOT NULL')
        function = quote(table.schema) + '."assign_version"'
        body = 'BEGIN NEW."__mtw_source_version" := pg_catalog.nextval(' + literal(sequence) + '); RETURN NEW; END;'
        connection.execute('CREATE FUNCTION ' + function + '() RETURNS trigger LANGUAGE plpgsql AS ' + literal(body))
        connection.execute('CREATE TRIGGER "assign_version" BEFORE INSERT OR UPDATE ON ' + target + ' FOR EACH ROW EXECUTE FUNCTION ' + function + '()')
        options = PointProjectionOptionsV2(config, star_contract='preinstallation-business-schema/v1',
                                          business_star_columns=tuple(c.name for c in table.columns))
        for name, sql, parameters in cases:
            projection = build_point_projection(parser.recognize(sql), parameters, options)
            description = projection.to_dict()
            connection.execute('BEGIN')
            try:
                cursor = connection.execute(projection.sql, projection.parameters)
                native, rows = observe(cursor)
                business = description['businessResult']
                indices = [c['nativeIndex'] for c in business['columns']]
                projected = None if business['mode'] == 'no-result' else [tuple(row[i] for i in indices) for row in rows]
                expected = baseline[name]
                assert projected == expected['rows'], (index, name, 'business rows')
                assert cursor.rowcount == expected['rowcount'], (index, name, 'rowcount')
                assert native['commandStatusBase64'] == expected['native']['commandStatusBase64'], (index, name, 'command tag')
                if projected is not None:
                    for out, position in enumerate(indices):
                        assert native['fields'][position]['nameBase64'] == expected['native']['fields'][out]['nameBase64']
                        assert native['fields'][position]['oid'] == expected['native']['fields'][out]['oid']
                for row in rows:
                    images = {image['image']: image for image in description['hiddenResults']}
                    for image in images.values():
                        assert type(row[image['version']['nativeIndex']]) is int
                        assert row[image['version']['nativeIndex']] > 0
                    if description['candidate']['operation'] == 'update':
                        assert row[images['old']['version']['nativeIndex']] != row[images['new']['version']['nativeIndex']]
                encode_rows = lambda data: None if data is None else [[scalar(value) for value in row] for row in data]
                records.append({'layout': index, 'case': name, 'passed': True, 'originalSql': sql,
                    'projection': description, 'baselineNative': expected['native'], 'projectedNative': native,
                    'baselineBusinessRows': encode_rows(expected['rows']), 'projectedBusinessRows': encode_rows(projected),
                    'testTransactionOutcome': 'rolled-back'})
            finally:
                connection.execute('ROLLBACK')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    binaries, work = args.bin.resolve(), args.output.resolve()
    assert work.is_relative_to(Path(r'D:\CodexScratch').resolve()), 'Use an owned D-drive output directory'
    work.mkdir(parents=True, exist_ok=False)
    for package, version in [('psycopg', '3.3.6'), ('sqlglot', '30.26.0')]:
        assert importlib.metadata.version(package) == version
    import psycopg
    version = subprocess.check_output([str(binaries / 'postgres.exe'), '--version'], text=True).strip()
    assert version == 'postgres (PostgreSQL) 18.6', version
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    password = secrets.token_hex(20)
    (work / 'password.txt').write_text(password + '\n', encoding='ascii')
    environment = dict(os.environ, TEMP=str(work), TMP=str(work))
    data, started = work / 'data', False
    receipt = {'format': 'configured-point-projection-native-comparison/v2', 'passed': False,
        'actualDatabaseExecution': False, 'postgresVersion': version, 'actualDriverWrapperExecuted': False,
        'sourceFactsProduced': False, 'closedWriterWindowVerified': False, 'modelCoverageAccepted': False,
        'formalPerformanceMeasurement': False, 'privateCredentialsPublished': False,
        'sourceSha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__).resolve(),
            ROOT/'integrations/python/moontxnwitness_capture/configured_point_projection_v2.py',
            ROOT/'integrations/python/moontxnwitness_capture/configured_sql_v2.py']}}
    with (work / 'control.log').open('xb') as log:
        def run(parts):
            subprocess.run([str(p) for p in parts], env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120, creationflags=flags)
        try:
            run([binaries/'initdb.exe', '-D', data, '-U', 'mtw', '--locale=C', '--encoding=UTF8',
                 '--auth-host=scram-sha-256', '--auth-local=trust', '--pwfile='+str(work/'password.txt')])
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1',0)); port = port_socket.getsockname()[1]
            run([binaries/'pg_ctl.exe','-D',data,'-l',work/'server.log','-o',
                 '-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10','-w','start'])
            started = True
            with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='mtw',password=password,autocommit=True) as connection:
                receipt['actualDatabaseExecution'] = True
                receipt['records'] = suite(connection)
                receipt['tests'] = len(receipt['records'])
                receipt['passed'] = True
        except BaseException:
            receipt['error'] = traceback.format_exc()
        finally:
            if started and (data/'postmaster.pid').exists():
                actual = Path((data/'postmaster.pid').read_text('utf8').splitlines()[1]).resolve()
                assert actual == data, 'Refuse to stop an unrelated cluster'
                run([binaries/'pg_ctl.exe','-D',data,'-m','fast','-w','stop'])
    (work/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':receipt['passed'],'tests':receipt.get('tests',0),
        'actualDatabaseExecution':receipt['actualDatabaseExecution'],'receipt':str(work/'receipt.json')}))
    if not receipt['passed']:
        print(receipt.get('error',''),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
