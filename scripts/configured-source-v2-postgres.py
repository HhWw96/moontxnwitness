"""Check explicit V2 source installation in a new owned PostgreSQL 18.6 cluster."""
from __future__ import annotations
import argparse
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
sys.path.insert(0, str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_source_v2 import install_configured_source_v2, SourceInstallPolicy
from moontxnwitness_capture.configured_sql_v2 import (
    SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2, ColumnConfig, TEXT_COMPARISON)
from moontxnwitness_capture.configured_point_capture_v2 import PointCaptureV2
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2


def q(name): return '"' + name.replace('"', '""') + '"'
def lit(value): return "'" + value.replace("'", "''") + "'"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def eq(actual, expected):
    if actual != expected: raise AssertionError((actual, expected))


def suite(admin, connect, work):
    records = []
    for index, kind in enumerate(('int64', 'text', 'uuid')):
        owner, writer, schema = 'source_owner_'+str(index), 'source_writer_'+str(index), 'app_'+str(index)
        password = secrets.token_hex(20)
        admin.execute('CREATE ROLE '+q(owner)+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        admin.execute('CREATE ROLE '+q(writer)+' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '+lit(password))
        admin.execute('GRANT CREATE ON DATABASE postgres TO '+q(owner))
        admin.execute('CREATE SCHEMA '+q(schema)+' AUTHORIZATION '+q(owner))
        table = TableConfigV2(schema, 'rows', PrimaryKeyConfigV2('identity', kind, TEXT_COMPARISON if kind=='text' else None),
            (ColumnConfig('balance','int64'),ColumnConfig('enabled','bool')))
        config, target = SQLCaptureConfigV2(table), q(schema)+'."rows"'
        key = 7 if kind=='int64' else '客户🙂' if kind=='text' else uuid.UUID('a8098c1a-f86e-11da-bd1a-00112444be1e')
        fresh = 9 if kind=='int64' else '新客户🙂' if kind=='text' else uuid.UUID('00000000-0000-0000-0000-000000000009')
        pk_type = {'int64':'bigint','text':'text COLLATE pg_catalog."C"','uuid':'uuid'}[kind]
        with connect(autocommit=True) as control:
            control.execute('SET ROLE '+q(owner))
            # PK deliberately last physically: explicit projection is name-based.
            control.execute('CREATE TABLE '+target+' (balance bigint NOT NULL, enabled boolean NOT NULL, identity '+pk_type+' PRIMARY KEY)')
            control.execute('INSERT INTO '+target+' VALUES(17,true,%s)',(key,))
            control.execute('GRANT USAGE ON SCHEMA '+q(schema)+' TO '+q(writer))
            control.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON '+target+' TO '+q(writer))
            policy = SourceInstallPolicy('mtw_source_v2_'+str(index),(writer,))
            installation = install_configured_source_v2(control,work/('install-'+str(index)),config,policy,opt_in=True).to_dict()
            eq(installation['status'],'installed-components-only')
            for field in ('catalogComponentsChecked','initialSnapshotComponentsChecked','initialLedgerComponentsChecked','actualCommitConfirmed'):
                eq(installation[field],True)
            for field in ('sourceFactsProduced','sourceAuthenticated','moonbitCatalogVerified','completeWindow','modelCoverageAccepted'):
                eq(installation[field],False)
            eq(installation['initialRows'],1)
            capture = PointCaptureV2(work/('capture-'+str(index)),config,opt_in=True)
            raw = connect(user=writer,password=password)
            backend_pid = raw.info.backend_pid
            connection = capture.wrap(raw)
            cursor = connection.execute('INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled',(fresh,10,True))
            eq(cursor.fetchone(),(fresh,10,True)); connection.commit()
            cursor = connection.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s RETURNING identity,balance,enabled',(11,fresh))
            eq(cursor.fetchone(),(fresh,11,True)); connection.commit()
            cursor = connection.execute('DELETE FROM '+target+' WHERE identity=%s RETURNING identity,balance,enabled',(fresh,))
            eq(cursor.fetchone(),(fresh,11,True)); connection.commit()
            # Out-of-grammar PK mutation is rejected by the explicit source scope.
            import psycopg
            try: connection.execute('UPDATE '+target+' SET identity=%s WHERE identity=%s',(fresh,key))
            except psycopg.errors.CheckViolation as error: eq(error.sqlstate,'23514')
            else: raise AssertionError('Installed V2 key guard did not reject a changed key')
            connection.rollback(); connection.close(); capture.close()
            ledger = control.execute('SELECT version,base_version,operation,writer_login,writer_pid,row_key::text,row_values::text FROM '+q(policy.namespace)+'.effects ORDER BY version').fetchall()
            eq([r[2] for r in ledger],['INITIAL','INSERT','UPDATE','DELETE'])
            eq(len({r[0] for r in ledger}),4)
            eq(all(r[3]==writer and r[4]==backend_pid for r in ledger[1:]),True)
            eq(ledger[1][1],None)
            eq(ledger[2][1],ledger[1][0]); eq(ledger[3][1],ledger[2][0])
            eq(json.loads(ledger[3][5]),str(fresh) if kind=='uuid' else fresh)
            eq(ledger[3][6],None)
            eq(control.execute('SELECT balance,enabled,identity FROM '+target).fetchall(),[(17,True,key)])
            retained = [json.loads(line) for line in (work/('capture-'+str(index))/'lifecycle.jsonl').read_text('utf8').splitlines()]
            probes = [json.loads(event['frameText']) for event in retained if event['kind']=='configured-point-writer']
            eq(len(probes),3)
            eq(all(json.loads(p['deliveredText'])['login']==writer for p in probes),True)
            records.append({'keyType':kind,'passed':True,'initialRows':1,'committedEffects':3,
                'sourceInstallationReceiptSha256':sha(work/('install-'+str(index))/'receipt-v2.json'),
                'sourceInstallationLogSha256':sha(work/('install-'+str(index))/'source-install-v2.jsonl'),
                'captureLogSha256':sha(work/('capture-'+str(index))/'lifecycle.jsonl'),
                'ledger':ledger,'writerCheckpoints':3,'sourceFactsProduced':False,'completeWindow':False,'modelCoverageAccepted':False})
    return records


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--bin',type=Path,required=True);cli.add_argument('--output',type=Path,required=True)
    args=cli.parse_args();binaries,work=args.bin.resolve(),args.output.resolve()
    assert work.is_relative_to(Path(r'D:\CodexScratch').resolve())
    work.mkdir(parents=True,exist_ok=False)
    for name,version in [('psycopg','3.3.6'),('sqlglot','30.26.0')]:eq(importlib.metadata.version(name),version)
    version=subprocess.check_output([str(binaries/'postgres.exe'),'--version'],text=True).strip();eq(version,'postgres (PostgreSQL) 18.6')
    password=secrets.token_hex(20);(work/'password.txt').write_text(password+'\n',encoding='ascii')
    data,started=work/'data',False
    environment=dict(os.environ,TEMP=str(work),TMP=str(work));flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    receipt={'format':'configured-source-v2-native-installation-validation/v1','passed':False,'actualDatabaseExecution':False,
        'actualV2InstallationExecuted':False,'postgresVersion':version,'sourceFactsProduced':False,'completeWindow':False,
        'modelCoverageAccepted':False,'formalPerformanceMeasurement':False,
        'sourceSha256':{str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__).resolve(),ROOT/'integrations/python/moontxnwitness_capture/configured_source_v2.py',ROOT/'integrations/python/moontxnwitness_capture/configured_point_capture_v2.py']}}
    with (work/'control.log').open('xb') as log:
        def run(parts):subprocess.run([str(p) for p in parts],env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,creationflags=flags)
        try:
            run([binaries/'initdb.exe','-D',data,'-U','mtw','--locale=C','--encoding=UTF8','--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
            with socket.socket() as endpoint:endpoint.bind(('127.0.0.1',0));port=endpoint.getsockname()[1]
            run([binaries/'pg_ctl.exe','-D',data,'-l',work/'server.log','-o','-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10','-w','start']);started=True
            import psycopg
            def connect(**kwargs):
                options=dict(host='127.0.0.1',port=port,dbname='postgres',user='mtw',password=password);options.update(kwargs)
                return psycopg.connect(**options)
            with connect(autocommit=True) as admin:
                receipt['actualDatabaseExecution']=True;receipt['records']=suite(admin,connect,work)
                receipt['actualV2InstallationExecuted'],receipt['passed']=True,True
        except BaseException:receipt['error']=traceback.format_exc()
        finally:
            if started and (data/'postmaster.pid').exists():
                actual=Path((data/'postmaster.pid').read_text('utf8').splitlines()[1]).resolve();assert actual==data
                run([binaries/'pg_ctl.exe','-D',data,'-m','fast','-w','stop'])
    (work/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':receipt['passed'],'layouts':len(receipt.get('records',[])),'receipt':str(work/'receipt.json')}))
    if not receipt['passed']:print(receipt.get('error',''),file=sys.stderr)
    return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
