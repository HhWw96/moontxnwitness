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
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_source_v2 import install_configured_source_v2, SourceInstallPolicy
from moontxnwitness_capture.configured_sql_v2 import (
    SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2, ColumnConfig, TEXT_COMPARISON)
from moontxnwitness_capture.configured_point_capture_v2 import PointCaptureV2
from moontxnwitness_capture.configured_point_projection_v2 import PointProjectionOptionsV2
from moontxnwitness_capture.configured_window_v2 import (
    ConfiguredCaptureWindowV2, SourceInputsV2, observe_source_snapshot_v2)


def q(name): return '"' + name.replace('"', '""') + '"'
def lit(value): return "'" + value.replace("'", "''") + "'"
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def eq(actual, expected):
    if actual != expected: raise AssertionError((actual, expected))


def analysis_fixtures(control, connect_writer, config, policy, installation, output, key, fresh, other_key):
    """Run original SQL through wrappers; no model histories are constructed here."""
    import psycopg
    target=q(config.table.schema)+'.'+q(config.table.table)
    select='SELECT identity,balance,enabled FROM '+target+' WHERE identity=%s'
    insert='INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled'
    cases=[]
    def window(name):return ConfiguredCaptureWindowV2(output/name,config,control,policy,installation,opt_in=True)
    w=window('crud');c=w.wrap_connection(connect_writer())
    eq(c.execute(select,(fresh,)).fetchall(),[])
    eq(c.execute(insert,(fresh,30,True)).fetchone(),(fresh,30,True))
    c.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s',(31,fresh))
    eq(c.execute(select,(fresh,)).fetchone(),(fresh,31,True))
    eq(c.execute('DELETE FROM '+target+' WHERE identity=%s RETURNING balance',(fresh,)).fetchone(),(31,))
    eq(c.execute(select,(fresh,)).fetchall(),[])
    c.commit()
    c.execute(select,(key,)).fetchone();c.commit();c.close()
    path=w.seal();cases.append({'name':'crud','bundle':str(path),'expected':'compatible','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path)})
    def reset():
        with connect_writer() as c:
            for identity in (key,other_key):c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(True,identity))
    reset();w=window('rr-write-skew');barrier=threading.Barrier(2)
    def participant(identity):
        raw=connect_writer();raw.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ;c=w.wrap_connection(raw)
        try:
            before=[c.execute(select,(v,)).fetchone() for v in (key,other_key)]
            eq(all(r[2] for r in before),True);barrier.wait(timeout=20)
            c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(False,identity));c.commit()
            return {'committed':True,'rows':len(before)}
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(participant,(key,other_key)))
    eq(control.execute('SELECT count(*) FROM '+target+' WHERE identity IN (%s,%s) AND enabled',(key,other_key)).fetchone()[0],0)
    path=w.seal();cases.append({'name':'rr-write-skew','bundle':str(path),'expected':'refuted','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path),'participants':results})
    reset();w=window('serializable-ordered')
    for identity in (key,other_key):
        raw=connect_writer();raw.isolation_level=psycopg.IsolationLevel.SERIALIZABLE;c=w.wrap_connection(raw)
        try:
            before=[c.execute(select,(v,)).fetchone() for v in (key,other_key)]
            if all(r[2] for r in before):c.execute('UPDATE '+target+' SET enabled=%s WHERE identity=%s',(False,identity))
            c.commit()
        finally:c.close()
    eq(control.execute('SELECT count(*) FROM '+target+' WHERE identity IN (%s,%s) AND enabled',(key,other_key)).fetchone()[0],1)
    path=w.seal();cases.append({'name':'serializable-ordered','bundle':str(path),'expected':'compatible','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path)})
    # No-op writes are observations too: dropping the two zero-row UPDATEs
    # below would incorrectly turn this nonserializable history into two
    # independent inserts. This protocol deliberately reports it as unknown.
    missing = fresh+100 if isinstance(fresh,int) else fresh+'-missing' if isinstance(fresh,str) else uuid.UUID(int=fresh.int+100)
    w=window('zero-write-skew');barrier=threading.Barrier(2)
    def no_op_participant(pair):
        own,other=pair
        raw=connect_writer();raw.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ;c=w.wrap_connection(raw)
        try:
            eq(c.execute('UPDATE '+target+' SET balance=%s WHERE identity=%s RETURNING identity,balance,enabled',(40,own)).fetchall(),[])
            barrier.wait(timeout=20)
            eq(c.execute(insert,(other,40,True)).fetchone(),(other,40,True));c.commit()
            return {'zeroRowWrite':True,'committed':True}
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(no_op_participant,((fresh,missing),(missing,fresh))))
    path=w.seal();cases.append({'name':'zero-write-skew','bundle':str(path),'expected':'unknown','expectedReason':'unsupported:window-zero-row-write','config':config.to_dict(),'policy':policy.to_dict(),'bundleSha256':sha(path),'participants':results})
    return cases


def suite(admin, connect, work, *, with_window=False, with_analysis=False):
    records = []
    for index, kind in enumerate(('int64', 'text', 'uuid')):
        owner, writer, schema = 'source_owner_'+str(index), 'source_writer_'+str(index), 'app_'+str(index)
        password = secrets.token_hex(20)
        admin.execute('CREATE ROLE '+q(owner)+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        admin.execute('CREATE ROLE '+q(writer)+' LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '+lit(password))
        admin.execute('GRANT CREATE ON DATABASE '+q(admin.info.dbname)+' TO '+q(owner))
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
            capture_path=work/('capture-'+str(index))
            window=None
            if with_window:
                window=ConfiguredCaptureWindowV2(work/('window-'+str(index)),config,control,policy,
                    SourceInputsV2.from_directory(work/('install-'+str(index))),opt_in=True)
                capture=window.observer;capture_path=window.output/'capture'
            else:capture = PointCaptureV2(capture_path,config,opt_in=True)
            raw = connect(user=writer,password=password)
            backend_pid = raw.info.backend_pid
            connection = window.wrap_connection(raw) if window else capture.wrap(raw)
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
            connection.rollback(); connection.close()
            ledger = control.execute('SELECT version,base_version,operation,writer_login,writer_pid,row_key::text,row_values::text FROM '+q(policy.namespace)+'.effects ORDER BY version').fetchall()
            eq([r[2] for r in ledger],['INITIAL','INSERT','UPDATE','DELETE'])
            eq(len({r[0] for r in ledger}),4)
            eq(all(r[3]==writer and r[4]==backend_pid for r in ledger[1:]),True)
            eq(ledger[1][1],None)
            eq(ledger[2][1],ledger[1][0]); eq(ledger[3][1],ledger[2][0])
            eq(json.loads(ledger[3][5]),str(fresh) if kind=='uuid' else fresh)
            eq(ledger[3][6],None)
            eq(control.execute('SELECT balance,enabled,identity FROM '+target).fetchall(),[(17,True,key)])
            window_check=None
            if window:
                slow_key=101 if kind=='int64' else '慢提交🙂' if kind=='text' else uuid.UUID(int=101)
                fast_key=102 if kind=='int64' else '快提交🙂' if kind=='text' else uuid.UUID(int=102)
                slow=window.wrap_connection(connect(user=writer,password=password))
                fast=window.wrap_connection(connect(user=writer,password=password))
                statement='INSERT INTO '+target+'(identity,balance,enabled) VALUES(%s,%s,%s) RETURNING identity,balance,enabled'
                eq(slow.execute(statement,(slow_key,20,True)).fetchone(),(slow_key,20,True))
                eq(fast.execute(statement,(fast_key,21,True)).fetchone(),(fast_key,21,True))
                fast.commit();fast.close()
                middle_path=observe_source_snapshot_v2(control,work/('middle-'+str(index)),config,policy,
                    window.installation,opt_in=True)
                middle=json.loads(middle_path.read_text('utf8'))
                slow.commit();slow.close()
                bundle_path=window.seal();bundle=json.loads(bundle_path.read_text('utf8'))
                start=json.loads(json.loads(bundle['startInputText'])['receiptText'])
                end=json.loads(json.loads(bundle['endInputText'])['receiptText'])
                missed=set(end['effectVersions'])-set(middle['effectVersions'])
                eq(len(missed),1)
                late=next(iter(missed));eq(int(late)<max(map(int,middle['effectVersions'])),True)
                eq(set(start['effectVersions']).issubset(end['effectVersions']),True)
                eq(len(set(end['effectVersions'])-set(start['effectVersions'])),5)
                eq(end['rowsObserved'],3)
                # All three inputs are raw retained observations; no model
                # coverage flag is inferred from successful durability checks.
                eq(json.loads((window.output/'window-receipt.json').read_text('utf8'))['completeWindow'],False)
                window_check={'passed':True,'bundleSha256':sha(bundle_path),'startEffects':len(start['effectVersions']),
                    'endEffects':len(end['effectVersions']),'lateCommittedLowVersion':late,
                    'middleMaximumVersion':str(max(map(int,middle['effectVersions']))),
                    'fullLedgerDifferenceIncludesLateVersion':True,'completeWindow':False,'modelCoverageAccepted':False}
            else:capture.close()
            retained = [json.loads(line) for line in (capture_path/'lifecycle.jsonl').read_text('utf8').splitlines()]
            probes = [json.loads(event['frameText']) for event in retained if event['kind']=='configured-point-writer']
            eq(len(probes),5 if window else 3)
            eq(all(json.loads(p['deliveredText'])['login']==writer for p in probes),True)
            analysis=[]
            if with_analysis:
                if not with_window:raise ValueError('Analysis fixtures also require --with-window')
                analysis=analysis_fixtures(control,lambda:connect(user=writer,password=password),config,policy,window.installation,work/('analysis-'+str(index)),key,fresh,slow_key)
            records.append({'keyType':kind,'passed':True,'initialRows':1,'committedEffects':3,'analysisFixtures':analysis,
                'sourceInstallationReceiptSha256':sha(work/('install-'+str(index))/'receipt-v2.json'),
                'sourceInstallationLogSha256':sha(work/('install-'+str(index))/'source-install-v2.jsonl'),
                'captureLogSha256':sha(capture_path/'lifecycle.jsonl'),
                'ledger':ledger,'writerCheckpoints':len(probes),'windowCheck':window_check,
                'sourceFactsProduced':False,'completeWindow':False,'modelCoverageAccepted':False})
    return records


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    target=cli.add_mutually_exclusive_group(required=True)
    target.add_argument('--bin',type=Path,help='PostgreSQL 18.6 binaries for a new owned local cluster')
    target.add_argument('--dsn-env',help='Environment variable for an isolated PostgreSQL 18.6 test service')
    cli.add_argument('--owned-database',action='store_true',help='Acknowledge the selected service is disposable and may receive test roles and tables')
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--with-window',action='store_true',help='Also seal raw window inputs and verify out-of-order commit visibility')
    cli.add_argument('--with-analysis',action='store_true',help='Also run committed CRUD, real RR write skew and ordered Serializable business windows')
    args=cli.parse_args()
    if args.with_analysis and not args.with_window:cli.error('--with-analysis requires --with-window')
    if args.dsn_env and not args.owned_database:cli.error('--dsn-env requires --owned-database')
    if args.dsn_env and not os.environ.get(args.dsn_env):cli.error('the selected DSN environment variable is empty')
    work=args.output.resolve()
    if os.name=='nt':assert work.is_relative_to(Path(r'D:\CodexScratch').resolve())
    work.mkdir(parents=True,exist_ok=False)
    for name,version in [('psycopg','3.3.6'),('sqlglot','30.26.0')]:eq(importlib.metadata.version(name),version)
    if args.dsn_env:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        service=conninfo_to_dict(os.environ[args.dsn_env])
        def connect(**kwargs):return psycopg.connect(**dict(service,**kwargs))
        receipt={'format':'configured-source-v2-native-installation-validation/v1','passed':False,'actualDatabaseExecution':False,
            'actualV2InstallationExecuted':False,'formalPerformanceMeasurement':False,'windowProducerRequested':args.with_window,
            'analysisFixturesRequested':args.with_analysis,'sourceSha256':{str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))}}
        try:
            with connect(autocommit=True) as admin:
                eq(int(admin.execute('SHOW server_version_num').fetchone()[0]),180006)
                receipt['postgresVersion']='postgres (PostgreSQL) 18.6';receipt['actualDatabaseExecution']=True
                receipt['records']=suite(admin,connect,work,with_window=args.with_window,with_analysis=args.with_analysis)
                receipt['actualV2InstallationExecuted'],receipt['passed']=True,True
        except BaseException:receipt['error']=traceback.format_exc()
        (work/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'passed':receipt['passed'],'layouts':len(receipt.get('records',[])),'receipt':str(work/'receipt.json')}))
        if not receipt['passed']:print(receipt.get('error',''),file=sys.stderr)
        return 0 if receipt['passed'] else 1
    binaries=args.bin.resolve()
    version=subprocess.check_output([str(binaries/('postgres.exe' if os.name=='nt' else 'postgres')),'--version'],text=True).strip();eq(version,'postgres (PostgreSQL) 18.6')
    password=secrets.token_hex(20);(work/'password.txt').write_text(password+'\n',encoding='ascii')
    data,started=work/'data',False
    environment=dict(os.environ,TEMP=str(work),TMP=str(work));flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    receipt={'format':'configured-source-v2-native-installation-validation/v1','passed':False,'actualDatabaseExecution':False,
        'actualV2InstallationExecuted':False,'postgresVersion':version,'sourceFactsProduced':False,'completeWindow':False,
        'modelCoverageAccepted':False,'formalPerformanceMeasurement':False,'windowProducerRequested':args.with_window,'analysisFixturesRequested':args.with_analysis,
        'sourceSha256':{str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__).resolve(),ROOT/'integrations/python/moontxnwitness_capture/configured_source_v2.py',ROOT/'integrations/python/moontxnwitness_capture/configured_point_capture_v2.py',ROOT/'integrations/python/moontxnwitness_capture/configured_window_v2.py']}}
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
                receipt['actualDatabaseExecution']=True;receipt['records']=suite(admin,connect,work,with_window=args.with_window,with_analysis=args.with_analysis)
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
