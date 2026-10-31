"""Owned PG18 original-SQL delivery observations; no source installation claim."""
from __future__ import annotations
import argparse,asyncio,hashlib,json,os,secrets,socket,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig
from moontxnwitness_capture.configured_fetch import ConfiguredInstrumentation,StoredColumnObservation

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def q(name):return '"'+name.replace('"','""')+'"'
def config():
    def c(name,kind):return ColumnConfig(name,kind,comparison='postgres-c-utf8-v1' if kind=='text' else None)
    return SQLCaptureConfig((
      TableConfig('ledger','accounts','account_no',(c('account_no','int64'),c('balance','int64'),c('active','bool'),c('version','text'))),
      TableConfig('Feature-X','Flag.Store','Feature Key',(c('Feature Key','text'),c('enabled','bool'),c('source id','text'))),
      TableConfig('业务','Object Space','Key',(c('Key','int64'),c('note','text'),c('score','int64'),c('flag','bool'),c('region','text'),c('revision','text')))),default_schema='ledger')


def collect(observer,configuration,output):
    observer.close()
    records=[json.loads(line) for line in (observer.output/'lifecycle.jsonl').read_text(encoding='utf8').splitlines()]
    frames=[(r['kind'],json.loads(r['frameText'])) for r in records if 'frameText' in r]
    executions={f['statementSeq']:f for kind,f in frames if kind=='configured-execution'}
    cases=[]
    for kind,native in frames:
        if kind!='configured-native-result':continue
        deliveries=[f for k,f in frames if k=='configured-delivery' and f['resultId']==native['resultId']]
        cases.append({'config':configuration.to_dict(),'execution':executions[native['statementSeq']],'native':native,'deliveries':deliveries})
    output.write_text(json.dumps({'format':'configured-fetch-actual-postgres/v1','cases':cases,'actualDatabaseExecution':True,
        'sourceFactsProduced':False,'installationVerified':False,'writerWindowVerified':False,
        'lifecycleSha256':sha(observer.output/'lifecycle.jsonl')},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return len(cases)


def run_database(private,work):
    import psycopg
    values=json.loads(private.read_text(encoding='utf8'))
    configuration=config();tables=configuration.tables
    initial=[(17,100,True,'version-α'),('feature🙂',True,'version-β'),(19,'𐀀与\ue000',23,False,'东','version-γ')]
    with psycopg.connect(**values,autocommit=True) as setup:
        for table,row in zip(tables,initial):
            setup.execute('CREATE SCHEMA '+q(table.schema))
            target=q(table.schema)+'.'+q(table.table)
            types={'int64':'bigint','bool':'boolean','text':'text COLLATE "C"'}
            setup.execute('CREATE TABLE '+target+'('+','.join(q(c.name)+' '+types[c.type]+(' PRIMARY KEY' if c.name==table.primary_key else '') for c in table.columns)+')')
            setup.execute('INSERT INTO '+target+' VALUES('+','.join('%s' for _ in row)+')',row)
        actual=setup.execute('SHOW server_version_num').fetchone()[0]
        if not 180000<=int(actual)<190000:raise AssertionError('PG18 required')
        encoding=setup.execute('SHOW server_encoding').fetchone()[0]
        assert encoding=='UTF8'
        byte_order=setup.execute('SELECT %s COLLATE "C" > %s COLLATE "C"',('𐀀','\ue000')).fetchone()[0]
        assert byte_order is True
    declarations=tuple(StoredColumnObservation(t.schema,t.table,t.columns[-1].name) for t in tables)
    observer=ConfiguredInstrumentation(work/'sync-observer',configuration,stored_columns=declarations)
    raw=psycopg.connect(**values);connection=observer.wrap(raw)
    assert observer.wrap(raw) is connection
    try:
        for index,(table,row) in enumerate(zip(tables,initial)):
            target=q(table.schema)+'.'+q(table.table);fields=','.join(q(c.name) for c in table.columns)
            cursor=connection.cursor()
            query='SELECT '+fields+' FROM '+target+' WHERE '+q(table.primary_key)+'=%(who)s'
            assert cursor.execute(query,{'who':row[0]}) is cursor
            assert cursor.rownumber==0  # native buffer observation did not consume a business row
            if index==0:
                assert cursor.fetchone()==row;assert cursor.fetchone() is None
            elif index==1:
                assert cursor.fetchmany(1)==[row];assert cursor.fetchall()==[]
            else:assert list(cursor)==[row]
            cursor.close()
            # Original return list omitting the version remains diagnostic.
            cursor=connection.cursor();cursor.execute('SELECT '+q(table.primary_key)+' FROM '+target+' WHERE '+q(table.primary_key)+'=%s',(row[0],))
            assert cursor.fetchall()==[(row[0],)];cursor.close()
        # Native empty SELECT has no source-version/tombstone invention.
        cursor=connection.cursor();cursor.execute('SELECT account_no,version FROM ledger.accounts WHERE account_no=%s',(-1,));assert cursor.fetchall()==[];cursor.close()
        connection.rollback()
    finally:connection.close()
    sync_count=collect(observer,configuration,work/'sync-cases.json')
    async def asynchronous():
        aobserver=ConfiguredInstrumentation(work/'async-observer',configuration,stored_columns=declarations)
        araw=await psycopg.AsyncConnection.connect(**values);aconn=aobserver.wrap_async(araw)
        try:
            for index,(table,row) in enumerate(zip(tables,initial)):
                target=q(table.schema)+'.'+q(table.table);fields=','.join(q(c.name) for c in table.columns)
                cursor=aconn.cursor();query='SELECT '+fields+' FROM '+target+' WHERE '+q(table.primary_key)+'=%s'
                await cursor.execute(query,(row[0],));assert cursor.rownumber==0
                if index==0:assert await cursor.fetchall()==[row]
                elif index==1:
                    assert await cursor.fetchmany(1)==[row];assert await cursor.fetchone() is None
                else:assert [item async for item in cursor]==[row]
                await cursor.close()
            await aconn.rollback()
        finally:await aconn.close()
        return collect(aobserver,configuration,work/'async-cases.json')
    if os.name=='nt':
        import selectors
        with asyncio.Runner(loop_factory=lambda:asyncio.SelectorEventLoop(selectors.SelectSelector())) as runner:
            async_count=runner.run(asynchronous())
    else:async_count=asyncio.run(asynchronous())
    return {'synchronousCases':sync_count,'asynchronousCases':async_count,'tableStructures':[len(t.columns) for t in tables],
        'actualServerVersionNum':actual,'serverEncoding':encoding,'actualCUnicodeComparison':byte_order,
        'originalSQLExecutedUnchanged':True,'resultPrefetchPerformed':False,'sourceFactsProduced':False,
        'catalogInstallationVerified':False,'writerWindowVerified':False,'driverVersion':psycopg.__version__}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bin',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    work=Path(args.output).resolve();work.mkdir(parents=True,exist_ok=False)
    binaries=Path(args.bin).resolve();suffix='.exe' if os.name=='nt' else ''
    for name in ('initdb','pg_ctl','postgres'):
        if not (binaries/(name+suffix)).is_file():raise ValueError('Complete preinstalled PG18 bin required')
    data=work/'data';private=work/'connection.json';password=secrets.token_hex(20)
    (work/'password.txt').write_text(password+'\n',encoding='ascii')
    env={**os.environ,'TEMP':str(work),'TMP':str(work),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
    receipt={'format':'configured-fetch-owned-postgres/v1','status':'started','actualDatabaseExecution':False,
      'formalPerformanceMeasurement':False,'sourceFactsProduced':False,'wrapperSha256':sha(__file__),
      'binarySha256':{name:sha(binaries/(name+suffix)) for name in ('initdb','pg_ctl','postgres')},
      'sourceSha256':{name:sha(ROOT/name) for name in ('integrations/python/moontxnwitness_capture/configured_fetch.py','integrations/python/moontxnwitness_capture/configured_sql.py')}}
    started=False;code=1
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (work/'control.log').open('xb') as log:
        def run(parts):return subprocess.run([str(x) for x in parts],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=120,creationflags=flags)
        try:
            run([binaries/('initdb'+suffix),'-D',data,'-U','mtw','--locale=C','--encoding=UTF8','--auth-host=scram-sha-256','--auth-local=trust','--pwfile='+str(work/'password.txt')])
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            run([binaries/('pg_ctl'+suffix),'-D',data,'-l',work/'server.log','-o','-h 127.0.0.1 -p '+str(port)+' -c shared_buffers=32MB -c max_connections=10 -c work_mem=2MB','-w','start'])
            started=True;receipt['actualDatabaseExecution']=True
            private.write_text(json.dumps({'host':'127.0.0.1','port':port,'dbname':'postgres','user':'mtw','password':password}),encoding='utf8')
            receipt.update(run_database(private,work));receipt['status']='passed';code=0
        except BaseException as error:
            import traceback
            (work/'failure.txt').write_text(traceback.format_exc(),encoding='utf8')
            receipt.update(status='failed',errorClass=type(error).__name__)
        finally:
            if started:
                pid=data/'postmaster.pid'
                if pid.exists():
                    actual=Path(pid.read_text(encoding='utf8').splitlines()[1]).resolve()
                    if actual!=data.resolve() or data.parent!=work:raise ValueError('Refuse to stop unrelated server')
                    run([binaries/('pg_ctl'+suffix),'-D',data,'-m','fast','-w','stop']);receipt['ownedClusterStopped']=True
            (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('binarySha256',)}))
    return code
if __name__=='__main__':raise SystemExit(main())
