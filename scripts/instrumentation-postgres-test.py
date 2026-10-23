"""Bounded actual PostgreSQL checks for diagnostic instrumentation.

Uses an explicitly configured owned PG18 instance, no downloads/server startup.
No application table is migrated; all fixtures use a new retained schema.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import traceback
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.instrumentation import Instrumentation,instrument_engine


OBSERVERS=[]

def tracked(observer):
    OBSERVERS.append(observer)
    return observer


def events(observer):
    observer.flush()
    return [json.loads(line) for p in sorted(observer.journal.path.glob('segment-*.jsonl'))
            for line in p.read_text(encoding='utf8').splitlines()]


def no_delivery_yet(observer,sql):
    recorded=events(observer)
    seq=next(e['seq'] for e in reversed(recorded) if e['kind']=='statement' and e['sql']==sql)
    assert not any(e['kind']=='rows' and e['statement']==seq for e in recorded),'Result observed before business fetch'


def finish(observer,output):
    status=observer.close();assert status.valid and not status.complete
    observer.export_diagnostic(output/'trace.json')
    observer.export_call_intervals(output/'trace.json',output/'interval-evidence.json')
    trace=json.loads((output/'trace.json').read_text(encoding='utf8'))
    assert not any(e['kind'] in ('read','write','condition') for e in trace['events'])
    return {'validStorage':status.valid,'completeAnalysisCoverage':False,
            'events':len(trace['events']),'gaps':trace['gaps']}


def setup_table(setup,schema,name):
    target='"'+schema+'"."'+name+'"'
    setup.execute('CREATE TABLE '+target+'(id integer PRIMARY KEY,value text NOT NULL)')
    setup.execute('INSERT INTO '+target+' VALUES(1,\'one\'),(2,\'two\')')
    return target


def native_sync(psycopg,kwargs,setup,schema,output):
    target=setup_table(setup,schema,'native_sync')
    observer=tracked(Instrumentation(output))
    raw=psycopg.connect(**kwargs);conn=observer.wrap(raw)
    try:
        sql='SELECT id,value FROM '+target+' ORDER BY id'
        cursor=conn.execute(sql);no_delivery_yet(observer,sql)
        assert cursor.fetchone()==(1,'one');assert cursor.fetchall()==[(2,'two')]
        values=iter([(3,'three'),(4,'four')])
        assert conn.cursor().executemany('INSERT INTO '+target+' VALUES(%s,%s)',values) is None
        conn.commit()
        for sql in ['SAVEPOINT same','INSERT INTO '+target+' VALUES(5,\'outer\')','SAVEPOINT same',
                    'INSERT INTO '+target+' VALUES(6,\'inner\')','ROLLBACK TO same','RELEASE same','ROLLBACK TO same','RELEASE same']:
            conn.execute(sql)
        assert conn.execute('SELECT id FROM '+target+' WHERE id>=5').fetchall()==[]
        conn.commit()
        try:conn.execute('SELECT 1/0')
        except psycopg.errors.DivisionByZero:pass
        else:raise AssertionError('Expected native server error')
        conn.commit()  # Actual COMMIT in failed transaction returns ROLLBACK.
        current=events(observer)
        assert any(e['kind']=='commit_ok' for e in current)
        assert any(e['kind']=='rollback_ok' and e.get('commitResponse',{}).get('commandTag')=='ROLLBACK' for e in current)
        savepoints=[e for e in current if e['kind']=='savepoint']
        assert len(savepoints)==2 and savepoints[0]['instance']!=savepoints[1]['instance']
    finally:conn.close()
    return finish(observer,output)


async def native_async(psycopg,kwargs,setup,schema,output):
    target=setup_table(setup,schema,'native_async')
    observer=tracked(Instrumentation(output))
    raw=await psycopg.AsyncConnection.connect(**kwargs);conn=observer.wrap_async(raw)
    try:
        sql='SELECT id,value FROM '+target+' ORDER BY id'
        cursor=await conn.execute(sql);no_delivery_yet(observer,sql)
        assert await cursor.fetchone()==(1,'one');assert await cursor.fetchall()==[(2,'two')]
        assert await conn.cursor().executemany('INSERT INTO '+target+' VALUES(%s,%s)',[(3,'three'),(4,'four')]) is None
        await conn.commit()
        await conn.execute('SAVEPOINT same');await conn.execute('SAVEPOINT same')
        await conn.execute('ROLLBACK TO same');await conn.execute('RELEASE same');await conn.execute('ROLLBACK TO same')
        await conn.rollback()
        try:await conn.execute('SELECT 1/0')
        except psycopg.errors.DivisionByZero:pass
        else:raise AssertionError('Expected native async server error')
        await conn.commit()
        recorded=events(observer)
        assert any(e['kind']=='commit_ok' for e in recorded)
        assert any(e['kind']=='rollback_ok' and e.get('commitResponse',{}).get('commandTag')=='ROLLBACK' for e in recorded)
    finally:await conn.close()
    return finish(observer,output)


def engine_sync(psycopg,kwargs,setup,schema,output):
    from sqlalchemy import create_engine
    target=setup_table(setup,schema,'engine_sync')
    engine=create_engine('postgresql+psycopg://',creator=lambda:psycopg.connect(**kwargs),pool_size=1,max_overflow=0)
    observer=tracked(instrument_engine(engine,output))
    try:
        with engine.connect() as conn:
            sql='SELECT id,value FROM '+target+' ORDER BY id'
            result=conn.exec_driver_sql(sql);no_delivery_yet(observer,sql)
            assert result.fetchone()==(1,'one');assert result.fetchall()==[(2,'two')]
            conn.exec_driver_sql('INSERT INTO '+target+' VALUES(%s,%s)',[(3,'three'),(4,'four')]);conn.commit()
            with conn.begin():
                nested=conn.begin_nested();conn.exec_driver_sql('INSERT INTO '+target+' VALUES(5,\'reverted\')');nested.rollback()
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT id FROM '+target+' WHERE id=5').fetchall()==[]
            conn.rollback()
        with engine.connect() as conn:
            conn.exec_driver_sql('SELECT 1').fetchall();conn.invalidate()
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT 2').scalar_one()==2
        observer.lifecycle.file.flush()
        notes=[json.loads(line) for line in (observer.output/'lifecycle.jsonl').read_text(encoding='utf8').splitlines()]
        assert sum(e['kind']=='pool-checkout' for e in notes)==4
        assert any(e['kind']=='pool-invalidate' for e in notes)
        assert len({e['connection'] for e in notes if e['kind']=='pool-connect'})==2
    finally:engine.dispose()
    return finish(observer,output)


async def engine_async(psycopg,kwargs,setup,schema,output):
    from sqlalchemy.ext.asyncio import create_async_engine
    target=setup_table(setup,schema,'engine_async')
    engine=create_async_engine('postgresql+psycopg://',async_creator=lambda:psycopg.AsyncConnection.connect(**kwargs),pool_size=1,max_overflow=0)
    observer=tracked(instrument_engine(engine,output))
    try:
        async with engine.connect() as conn:
            sql='SELECT id,value FROM '+target+' ORDER BY id'
            result=await conn.exec_driver_sql(sql);no_delivery_yet(observer,sql)
            assert result.fetchone()==(1,'one');assert result.fetchall()==[(2,'two')]
            await conn.exec_driver_sql('INSERT INTO '+target+' VALUES(%s,%s)',[(3,'three'),(4,'four')]);await conn.commit()
            async with conn.begin():
                nested=await conn.begin_nested();await conn.exec_driver_sql('INSERT INTO '+target+' VALUES(5,\'reverted\')');await nested.rollback()
        async with engine.connect() as conn:
            result=await conn.exec_driver_sql('SELECT id FROM '+target+' WHERE id=5');assert result.fetchall()==[]
            await conn.rollback()
        async with engine.connect() as conn:
            result=await conn.exec_driver_sql('SELECT 1');result.fetchall();await conn.invalidate()
        async with engine.connect() as conn:
            assert (await conn.exec_driver_sql('SELECT 2')).scalar_one()==2
    finally:await engine.dispose()
    return finish(observer,output)



class CommitAckLossProxy:
    """Forward real local PG traffic; drop only an actual COMMIT completion."""
    def __init__(self,host,port):
        if host!='localhost' and not ipaddress.ip_address(host).is_loopback:
            raise ValueError('COMMIT-loss fixture requires an owned loopback PostgreSQL endpoint')
        self.host,self.server_port=host,port
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen(1)
        self.port=self.listener.getsockname()[1]
        self.armed,self.observed=threading.Event(),threading.Event()
        self.client=self.server=None;self.threads=[];self.command_sha=None
    def start(self):
        thread=threading.Thread(target=self._accept,daemon=True);thread.start();self.threads.append(thread)
        return self
    @staticmethod
    def exact(sock,size):
        parts=[]
        while size:
            part=sock.recv(size)
            if not part:raise EOFError()
            parts.append(part);size-=len(part)
        return b''.join(parts)
    def _accept(self):
        try:
            self.client,_=self.listener.accept();self.server=socket.create_connection((self.host,self.server_port),timeout=5)
            self.server.settimeout(None)
            sender=threading.Thread(target=self._upstream,daemon=True);sender.start();self.threads.append(sender)
            while True:
                head=self.exact(self.server,5);size=struct.unpack('!I',head[1:])[0]
                if not 4<=size<=16*1024*1024:raise ValueError('Unexpected PostgreSQL frame bound')
                payload=self.exact(self.server,size-4);packet=head+payload
                if self.armed.is_set() and head[:1]==b'C' and payload==b'COMMIT\0':
                    self.command_sha=hashlib.sha256(packet).hexdigest();self.observed.set();break
                self.client.sendall(packet)
        except (EOFError,OSError):pass
        finally:self.close()
    def _upstream(self):
        try:
            while True:
                data=self.client.recv(65536)
                if not data:break
                self.server.sendall(data)
        except OSError:pass
    def close(self):
        for sock in (self.client,self.server,self.listener):
            if sock is not None:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                try:sock.close()
                except OSError:pass


def lost_commit_sync(psycopg,kwargs,setup,schema,output):
    target=setup_table(setup,schema,'lost_commit_sync')
    proxy=CommitAckLossProxy(kwargs.get('host','127.0.0.1'),int(kwargs.get('port',5432))).start()
    observer=tracked(Instrumentation(output))
    proxied=dict(kwargs,host='127.0.0.1',port=proxy.port,sslmode='disable')
    conn=observer.wrap(psycopg.connect(**proxied))
    try:
        conn.execute('INSERT INTO '+target+' VALUES(3,\'committed-with-lost-ack\')')
        proxy.armed.set()
        try:conn.commit()
        except psycopg.Error:pass
        else:raise AssertionError('Lost actual COMMIT ACK must not return success')
        assert proxy.observed.wait(2),'Proxy did not observe a genuine server COMMIT completion'
        assert setup.execute('SELECT value FROM '+target+' WHERE id=3').fetchone()==('committed-with-lost-ack',)
        before=events(observer)
        assert not any(e['kind']=='commit_ok' for e in before)
        assert any(e['kind']=='disconnect' for e in before)
        try:conn.rollback()
        except psycopg.Error:pass
        assert not any(e['kind']=='rollback_ok' for e in events(observer))
    finally:
        conn.close();proxy.close()
    result=finish(observer,output)
    result.update(actualServerCommitObserved=True,commitResponseFrameSha256=proxy.command_sha,
                  actualBusinessWriteCommitted=True,collectorOutcome='unknown')
    return result


async def lost_commit_async(psycopg,kwargs,setup,schema,output):
    target=setup_table(setup,schema,'lost_commit_async')
    proxy=CommitAckLossProxy(kwargs.get('host','127.0.0.1'),int(kwargs.get('port',5432))).start()
    observer=tracked(Instrumentation(output))
    proxied=dict(kwargs,host='127.0.0.1',port=proxy.port,sslmode='disable')
    conn=observer.wrap_async(await psycopg.AsyncConnection.connect(**proxied))
    try:
        await conn.execute('INSERT INTO '+target+' VALUES(3,\'committed-with-lost-ack\')')
        proxy.armed.set()
        try:await conn.commit()
        except psycopg.Error:pass
        else:raise AssertionError('Lost async actual COMMIT ACK must not return success')
        assert proxy.observed.wait(2)
        assert setup.execute('SELECT value FROM '+target+' WHERE id=3').fetchone()==('committed-with-lost-ack',)
        assert not any(e['kind']=='commit_ok' for e in events(observer))
        try:await conn.rollback()
        except psycopg.Error:pass
        assert not any(e['kind']=='rollback_ok' for e in events(observer))
    finally:
        await conn.close();proxy.close()
    result=finish(observer,output)
    result.update(actualServerCommitObserved=True,commitResponseFrameSha256=proxy.command_sha,
                  actualBusinessWriteCommitted=True,collectorOutcome='unknown')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file',default=os.environ.get('MTW_PG_CONNECTION_FILE'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--commit-loss',action='store_true',help='also exercise native ACK loss through an owned loopback proxy')
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    receipt={'schema':1,'status':'not-executed','actualDatabaseExecution':False,'cases':[],
             'formalPerformanceMeasurement':False,'noModelCoverageClaim':True,'noDownloads':True}
    if not args.connection_file:
        receipt['reason']='owned connection file required'
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8');return 3
    try:import psycopg,sqlalchemy
    except ImportError:
        receipt['reason']='optional pinned driver/SQLAlchemy missing'
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8');return 3
    inputs=[Path(__file__).resolve(),*(ROOT/'integrations/python/moontxnwitness_capture'/name for name in ['instrumentation.py','capture_v3.py','journal_v3.py','_durable_policy.py','capture.py','_orm_raw_async.py'])]
    before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    kwargs=json.loads(Path(args.connection_file).read_text(encoding='utf8'))
    kwargs.setdefault('connect_timeout',5)
    kwargs['options']='-c statement_timeout=10000 -c lock_timeout=5000'
    setup=None
    try:
        setup=psycopg.connect(**dict(kwargs,autocommit=True))
        receipt.update(actualDatabaseExecution=True,server=setup.execute('SELECT version()').fetchone()[0],
                       psycopg=psycopg.__version__,sqlalchemy=sqlalchemy.__version__)
        assert 180000<=setup.info.server_version<190000
        assert psycopg.__version__=='3.3.6' and sqlalchemy.__version__=='2.0.55'
        schema='mtw_instrumentation_'+uuid.uuid4().hex[:16]
        setup.execute('CREATE SCHEMA "'+schema+'"');receipt['fixtureSchema']=schema
        cases=[('native-sync',native_sync),('native-async',native_async),('engine-sync',engine_sync),('engine-async',engine_async)]
        if args.commit_loss:cases.extend([('lost-commit-sync',lost_commit_sync),('lost-commit-async',lost_commit_async)])
        for name,function in cases:
            folder=output/name
            try:
                if asyncio.iscoroutinefunction(function):
                    if sys.platform=='win32':
                        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                            detail=runner.run(function(psycopg,kwargs,setup,schema,folder))
                    else:detail=asyncio.run(function(psycopg,kwargs,setup,schema,folder))
                else:detail=function(psycopg,kwargs,setup,schema,folder)
                case={'name':name,'passed':True,'detail':detail}
            except BaseException as error:
                case={'name':name,'passed':False,'errorClass':type(error).__name__,
                      'sqlstate':getattr(error,'sqlstate',None),
                      'assertion':str(error) if isinstance(error,AssertionError) else None,
                      'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]}
                receipt['cases'].append(case)
                raise
            receipt['cases'].append(case)
        receipt.update(status='passed',passed=True)
        code=0
    except BaseException as error:
        receipt.update(status='failed',passed=False,errorClass=type(error).__name__,sqlstate=getattr(error,'sqlstate',None));code=1
    finally:
        for observer in OBSERVERS:
            try:
                observer.close()
                if not (observer.output/'trace.json').exists():observer.export_diagnostic(observer.output/'trace.json')
            except BaseException:pass
        if setup is not None:setup.close()
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        receipt['sourceBindings']=before;receipt['sourceUnchangedAfterExecution']=before==after
        if before!=after:receipt['passed']=False;receipt['status']='failed';code=1
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':receipt['status'],'cases':len(receipt['cases']),'actualDatabaseExecution':receipt['actualDatabaseExecution']}))
    return code


if __name__=='__main__':raise SystemExit(main())
