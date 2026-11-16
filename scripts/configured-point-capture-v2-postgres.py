"""Exercise local V2 point wrappers against a new owned PostgreSQL cluster."""
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
    ColumnConfig, PrimaryKeyConfigV2, TableConfigV2, SQLCaptureConfigV2, TEXT_COMPARISON)
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2
from moontxnwitness_capture.configured_point_capture_v2 import PointCaptureV2


def q(name): return '"' + name.replace('"', '""') + '"'
def lit(value): return "'" + value.replace("'", "''") + "'"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def suite(admin, connect, work):
    records, receipts = [], []
    def checked(name, body):
        body()
        records.append({'name': name, 'passed': True})
    text = lambda name: ColumnConfig(name, 'text', TEXT_COMPARISON)
    layouts = (
        TableConfigV2('bank', 'accounts', PrimaryKeyConfigV2('number', 'int64'),
                      (ColumnConfig('balance', 'int64'), ColumnConfig('enabled', 'bool'), text('label'))),
        TableConfigV2('App-Table', 'Contact.List', PrimaryKeyConfigV2('Key ID', 'text', TEXT_COMPARISON),
                      (ColumnConfig('quota', 'int64'), text('address'))),
        TableConfigV2('业务', '使用者', PrimaryKeyConfigV2('编号', 'uuid'),
                      (text('邮箱'), ColumnConfig('已启用', 'bool'))),
    )
    for index, table in enumerate(layouts):
        config = SQLCaptureConfigV2(table)
        target = q(table.schema) + '.' + q(table.table)
        names = ', '.join(q(c.name) for c in table.columns)
        types = {'int64': 'bigint', 'bool': 'boolean', 'text': 'text COLLATE pg_catalog."C"', 'uuid': 'uuid'}
        admin.execute('CREATE SCHEMA ' + q(table.schema))
        admin.execute('CREATE TABLE ' + target + ' (' + ', '.join(q(c.name) + ' ' + types[c.type] +
            ' NOT NULL' + (' PRIMARY KEY' if c.name == table.primary_key else '') for c in table.columns) + ')')
        key = 7 if table.key.type == 'int64' else '用户🙂' if table.key.type == 'text' else uuid.UUID('a8098c1a-f86e-11da-bd1a-00112444be1e')
        fresh = 9 if table.key.type == 'int64' else '新增🙂' if table.key.type == 'text' else uuid.UUID('00000000-0000-0000-0000-000000000009')
        def values(identity):
            return tuple(identity if c.name == table.primary_key else 17 if c.type == 'int64' else True if c.type == 'bool' else '原始🙂' for c in table.columns)
        original = values(key)
        insert = 'INSERT INTO ' + target + '(' + names + ') VALUES (' + ', '.join('%s' for _ in table.columns) + ')'
        admin.execute(insert, original)
        # Preserve a true preinstallation baseline for SELECT * and errors.
        with connect() as raw:
            before = raw.execute('SELECT * FROM ' + target + ' WHERE ' + q(table.primary_key) + '=%s', (key,))
            expected_description = [(c.name, c.type_code) for c in before.description]
            assert before.fetchone() == original
            try:
                raw.execute(insert, original)
            except Exception as error:
                duplicate_error = type(error), error.sqlstate
            else:
                raise AssertionError('Baseline duplicate INSERT did not fail')
        sequence = q(table.schema) + '."versions"'
        admin.execute('CREATE SEQUENCE ' + sequence + ' AS bigint')
        admin.execute('ALTER TABLE ' + target + ' ADD COLUMN "__mtw_source_version" bigint')
        admin.execute('UPDATE ' + target + ' SET "__mtw_source_version"=nextval(' + lit(sequence) + ')')
        admin.execute('ALTER TABLE ' + target + ' ALTER COLUMN "__mtw_source_version" SET NOT NULL')
        function = q(table.schema) + '."assign_version"'
        admin.execute('CREATE FUNCTION ' + function + '() RETURNS trigger LANGUAGE plpgsql AS ' + lit(
            'BEGIN NEW."__mtw_source_version" := nextval(' + lit(sequence) + '); RETURN NEW; END;'))
        admin.execute('CREATE TRIGGER "assign_version" BEFORE INSERT OR UPDATE ON ' + target +
                      ' FOR EACH ROW EXECUTE FUNCTION ' + function + '()')
        options = PointProjectionOptionsV2(config, star_contract='preinstallation-business-schema/v1',
            business_star_columns=tuple(c.name for c in table.columns))
        output = work / ('capture-' + str(index))
        observer = PointCaptureV2(output, config, projection_options=options, opt_in=True)
        wrapped = observer.psycopg_factory(connect)
        connection = wrapped()
        select = 'SELECT * FROM ' + target + ' WHERE ' + q(table.primary_key) + '=%s'
        cursor = connection.execute(select, (key,))
        checked(str(index) + '-description-before-fetch', lambda: eq([(c.name, c.type_code) for c in cursor.description], expected_description))
        checked(str(index) + '-no-eager-fetch', lambda: eq(cursor.rownumber, 0))
        checked(str(index) + '-cursor-connection-wrapper', lambda: eq(cursor.connection is connection, True))
        checked(str(index) + '-fetchmany-zero-uses-arraysize', lambda: eq(cursor.fetchmany(0), [original]))
        cursor = connection.execute(select, (key,))
        checked(str(index) + '-fetchone-business', lambda: eq(cursor.fetchone(), original))
        checked(str(index) + '-fetchone-eof', lambda: eq(cursor.fetchone(), None))
        connection.rollback()
        cursor = connection.execute(select, (key,))
        cursor.arraysize = 1
        checked(str(index) + '-arraysize-default', lambda: eq(cursor.fetchmany(), [original]))
        connection.rollback()
        cursor = connection.execute(select, (key,))
        checked(str(index) + '-nextset-none-keeps-projection', lambda: eq(cursor.nextset(), None))
        checked(str(index) + '-nextset-none-description', lambda: eq([(c.name, c.type_code) for c in cursor.description], expected_description))
        checked(str(index) + '-nextset-none-business-fetch', lambda: eq(cursor.fetchone(), original))
        connection.rollback()
        cursor = connection.execute(select, (key,))
        checked(str(index) + '-results-yields-wrapper', lambda: eq(next(cursor.results()) is cursor, True))
        checked(str(index) + '-set-result-returns-wrapper', lambda: eq(cursor.set_result(0) is cursor, True))
        checked(str(index) + '-result-helpers-hide-metadata', lambda: eq(cursor.fetchone(), original))
        cursor.scroll(0, mode='absolute')
        checked(str(index) + '-scroll-keeps-business-projection', lambda: eq(cursor.fetchone(), original))
        connection.rollback()
        cursor = connection.execute(select, (key,))
        def failed_many():
            try: cursor.executemany('SELECT 1', 3)
            except TypeError: pass
            else: raise AssertionError('Invalid executemany iterable was accepted')
        checked(str(index) + '-invalid-batch-raises-original-error', failed_many)
        checked(str(index) + '-invalid-batch-keeps-projection', lambda: eq(cursor.fetchone(), original))
        connection.rollback()
        cursor = connection.execute(select, (fresh,))
        checked(str(index) + '-negative-read', lambda: eq(cursor.fetchall(), []))
        connection.rollback()
        cursor = connection.execute(insert + ' RETURNING *', values(fresh))
        checked(str(index) + '-insert-returning-business', lambda: eq(cursor.fetchall(), [values(fresh)]))
        connection.commit()
        cursor = connection.execute(select, (fresh,))
        checked(str(index) + '-committed-refresh', lambda: eq(cursor.fetchone(), values(fresh)))
        connection.rollback()
        changed = table.business_columns[0]
        value = 23 if changed.type == 'int64' else '更新🙂'
        update = 'UPDATE ' + target + ' SET ' + q(changed.name) + '=%s WHERE ' + q(table.primary_key) + '=%s'
        cursor = connection.execute(update, (value, fresh))
        checked(str(index) + '-no-returning-description', lambda: eq(cursor.description, None))
        checked(str(index) + '-no-returning-rowcount', lambda: eq(cursor.rowcount, 1))
        def no_records():
            import psycopg
            try: cursor.fetchone()
            except psycopg.ProgrammingError as error: eq(error.sqlstate, None)
            else: raise AssertionError('Hidden RETURNING leaked as business records')
        checked(str(index) + '-hidden-result-not-fetchable', no_records)
        checked(str(index) + '-no-returning-nextset-none', lambda: eq(cursor.nextset(), None))
        checked(str(index) + '-no-returning-nextset-hidden', no_records)
        checked(str(index) + '-no-returning-results-wrapper', lambda: eq(next(cursor.results()) is cursor, True))
        checked(str(index) + '-no-returning-set-result-wrapper', lambda: eq(cursor.set_result(0) is cursor, True))
        checked(str(index) + '-no-returning-helpers-hidden', no_records)
        closed_command = connection.execute(update, (value, fresh))
        closed_command.close()
        def closed_fetch():
            import psycopg
            try: closed_command.fetchone()
            except psycopg.InterfaceError: pass
            else: raise AssertionError('Closed cursor did not raise its native InterfaceError')
        checked(str(index) + '-closed-no-result-native-error', closed_fetch)
        cursor = connection.execute(select, (fresh,))
        self_read = list(values(fresh)); self_read[1] = value
        checked(str(index) + '-transaction-self-read', lambda: eq(cursor.fetchall(), [tuple(self_read)]))
        connection.rollback()
        cursor = connection.execute('DELETE FROM ' + target + ' WHERE ' + q(table.primary_key) + '=%s RETURNING *', (fresh,))
        checked(str(index) + '-delete-old-returning', lambda: eq(list(cursor), [values(fresh)]))
        connection.commit()
        cursor = connection.execute(select, (fresh,))
        checked(str(index) + '-deleted-negative-read', lambda: eq(cursor.fetchall(), []))
        connection.rollback()
        def original_error():
            try: connection.execute(insert, original)
            except Exception as error: eq((type(error), error.sqlstate), duplicate_error)
            else: raise AssertionError('Duplicate INSERT did not fail')
        checked(str(index) + '-original-driver-error', original_error)
        connection.rollback()
        # Force the observer's own query to fail in PostgreSQL. Its private
        # savepoint must preserve the application's preceding write at COMMIT.
        import moontxnwitness_capture.configured_effects as effects
        old_probe = effects.WRITER_PROBE_SQL
        connection.execute(update, (value, key))
        try:
            effects.WRITER_PROBE_SQL = 'SELECT 1/0'
            connection.commit()
        finally:
            effects.WRITER_PROBE_SQL = old_probe
        expected_after_probe_failure = list(original); expected_after_probe_failure[1] = value
        checked(str(index) + '-failed-checkpoint-preserves-commit', lambda: eq(connection.execute(select, (key,)).fetchone(), tuple(expected_after_probe_failure)))
        connection.rollback()
        # Unrecognized SQL must retain its original result and record a gap.
        cursor = connection.execute('SELECT 123')
        checked(str(index) + '-unknown-sql-unchanged', lambda: eq(cursor.fetchone(), (123,)))
        connection.rollback()
        cursor = connection.execute(select, (key,))
        checked(str(index) + '-partial-result-before-close', lambda: eq(cursor.rownumber, 0))
        cursor.close()
        connection.close()
        observer.close()
        lines = (output/'lifecycle.jsonl').read_bytes().splitlines(keepends=True)
        events = [json.loads(line) for line in lines]
        eq(events[-1]['kind'], 'seal')
        eq(events[-1]['prefixSha256'], hashlib.sha256(b''.join(lines[:-1])).hexdigest())
        frames = [(e['kind'], json.loads(e['frameText'])) for e in events if 'frameText' in e]
        writers = [frame for kind, frame in frames if kind == 'configured-point-writer']
        eq(len(writers), 2)
        eq(all(json.loads(w['deliveredText'])['xid'] is not None for w in writers), True)
        eq(all(frame.get('sourceFactsProduced') is False for _, frame in frames), True)
        receipts.append({'layout': index, 'logSha256': sha(output/'lifecycle.jsonl'), 'logRecords': len(events),
                         'writerCheckpoints': len(writers), 'frames': [{'kind': k, 'payload': p} for k, p in frames]})
    return records, receipts


def eq(actual, expected):
    if actual != expected: raise AssertionError((actual, expected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    binaries, work = args.bin.resolve(), args.output.resolve()
    assert work.is_relative_to(Path(r'D:\CodexScratch').resolve())
    work.mkdir(parents=True, exist_ok=False)
    for package, version in [('psycopg', '3.3.6'), ('sqlglot', '30.26.0')]:
        eq(importlib.metadata.version(package), version)
    import psycopg
    version = subprocess.check_output([str(binaries/'postgres.exe'), '--version'], text=True).strip()
    eq(version, 'postgres (PostgreSQL) 18.6')
    password = secrets.token_hex(20)
    (work/'password.txt').write_text(password+'\n', encoding='ascii')
    environment = dict(os.environ, TEMP=str(work), TMP=str(work))
    flags, data, started = getattr(subprocess, 'CREATE_NO_WINDOW', 0), work/'data', False
    receipt = {'format': 'configured-point-capture-driver-validation/v2', 'passed': False,
        'actualDatabaseExecution': False, 'actualDriverWrapperExecuted': False, 'postgresVersion': version,
        'sourceFactsProduced': False, 'completeWindow': False, 'modelCoverageAccepted': False,
        'formalPerformanceMeasurement': False, 'sourceSha256': {str(path.relative_to(ROOT)): sha(path) for path in [
            Path(__file__).resolve(), ROOT/'integrations/python/moontxnwitness_capture/configured_point_capture_v2.py',
            ROOT/'integrations/python/moontxnwitness_capture/configured_point_projection_v2.py']}}
    with (work/'control.log').open('xb') as log:
        def run(parts):
            subprocess.run([str(p) for p in parts], env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120, creationflags=flags)
        try:
            run([binaries/'initdb.exe', '-D', data, '-U', 'mtw', '--locale=C', '--encoding=UTF8',
                 '--auth-host=scram-sha-256', '--auth-local=trust', '--pwfile='+str(work/'password.txt')])
            with socket.socket() as endpoint:
                endpoint.bind(('127.0.0.1', 0)); port = endpoint.getsockname()[1]
            run([binaries/'pg_ctl.exe', '-D', data, '-l', work/'server.log', '-o',
                 '-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10', '-w', 'start'])
            started = True
            def connect(**kwargs):
                return psycopg.connect(host='127.0.0.1', port=port, dbname='postgres', user='mtw', password=password, **kwargs)
            with connect(autocommit=True) as admin:
                receipt['actualDatabaseExecution'] = True
                receipt['tests'], receipt['captures'] = suite(admin, connect, work)
                receipt['actualDriverWrapperExecuted'], receipt['passed'] = True, True
        except BaseException:
            receipt['error'] = traceback.format_exc()
        finally:
            if started and (data/'postmaster.pid').exists():
                actual = Path((data/'postmaster.pid').read_text('utf8').splitlines()[1]).resolve()
                assert actual == data, 'Refuse to stop an unrelated cluster'
                run([binaries/'pg_ctl.exe', '-D', data, '-m', 'fast', '-w', 'stop'])
    (work/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'passed': receipt['passed'], 'tests': len(receipt.get('tests', [])), 'receipt': str(work/'receipt.json')}))
    if not receipt['passed']: print(receipt.get('error', ''), file=sys.stderr)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
