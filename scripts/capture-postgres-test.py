"""Actual DB integration checks; these controlled fixtures are not business adoption."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'integrations/python'))
from moontxnwitness_capture import CaptureSession, Table, PointRead, PointWrite, load_jsonl


def main():
    import psycopg
    destination=Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    if os.environ.get('MTW_PG_CONNECTION_FILE'):
        connection=json.loads(Path(os.environ['MTW_PG_CONNECTION_FILE']).read_text(encoding='utf8'))
        connect=lambda **extra: psycopg.connect(**connection, **extra)
        async_connect=lambda **extra: psycopg.AsyncConnection.connect(**connection, **extra)
    elif os.environ.get('MTW_PG_DSN'):
        connect=lambda **extra: psycopg.connect(os.environ['MTW_PG_DSN'], **extra)
        async_connect=lambda **extra: psycopg.AsyncConnection.connect(os.environ['MTW_PG_DSN'], **extra)
    else:
        print('Capture PostgreSQL tests not executed: no test database configured.')
        return 3
    schema='mtw_capture_' + uuid.uuid4().hex
    scenarios=[]
    with connect(autocommit=True) as setup:
        server=setup.execute('SELECT version()').fetchone()[0]
        setup.execute('CREATE SCHEMA "' + schema + '"')
        setup.execute('CREATE TABLE "' + schema + '".registers (key text PRIMARY KEY,value integer NOT NULL,version text NOT NULL)')
        table=Table(schema,'registers','key','version')
        select='SELECT value,version FROM "' + schema + '".registers WHERE key=%s'
        update='UPDATE "' + schema + '".registers SET value=%s,version=%s WHERE key=%s'
        def session(name):
            setup.execute('TRUNCATE TABLE "' + schema + '".registers')
            setup.execute('INSERT INTO "' + schema + '".registers VALUES (%s,%s,%s),(%s,%s,%s)',('x',1,'x0','y',1,'y0'))
            recorder=CaptureSession([PointRead(select,table),PointWrite(update,table)],
                jsonl_path=destination/(name+'.jsonl'),exclusive_writers=True)
            recorder.initialize(setup)
            return recorder
        def save(name,recorder,expected,verdict=None):
            recorder.close()
            trace=recorder.document()
            recovered=load_jsonl(destination/(name+'.jsonl'))
            assert recovered==trace, name + ': persisted trace differs'
            (destination/(name+'.trace.json')).write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            scenarios.append({'name':name,'expectedStatus':expected,'expectedVerdict':verdict,'trace':name+'.trace.json'})
        recorder=session('sync-write-skew')
        with recorder.wrap(connect()) as first, recorder.wrap(connect()) as second:
            first.execute('BEGIN ISOLATION LEVEL REPEATABLE READ')
            second.execute('BEGIN ISOLATION LEVEL REPEATABLE READ')
            assert first.execute(select,('x',)).fetchone()==(1,'x0')
            assert second.execute(select,('y',)).fetchone()==(1,'y0')
            first.execute(update,(0,'y1','y'))
            second.execute(update,(0,'x1','x'))
            first.commit()
            second.commit()
        save('sync-write-skew',recorder,'ready','violation')

        recorder=session('rollback')
        with recorder.wrap(connect()) as transaction:
            transaction.execute(select,('x',)).fetchall()
            transaction.execute(update,(5,'x-aborted','x'))
            transaction.rollback()
        save('rollback',recorder,'ready','consistent')

        recorder=session('unsupported')
        with recorder.wrap(connect()) as transaction:
            assert transaction.execute('SELECT count(*) FROM "' + schema + '".registers').fetchone()[0]==2
        save('unsupported',recorder,'inconclusive')

        recorder=session('unconsumed')
        with recorder.wrap(connect()) as transaction:
            transaction.execute(select,('x',))
        save('unconsumed',recorder,'inconclusive')

        recorder=session('failed-transaction-commit')
        with recorder.wrap(connect()) as transaction:
            assert transaction.execute(select,('x',)).fetchone()==(1,'x0')
            try:
                transaction.execute(update,('not-an-integer','x-never-written','x'))
            except psycopg.Error:
                pass
            else:
                raise AssertionError('Expected actual server input error')
            # PostgreSQL acknowledges this as rollback, not a committed write.
            transaction.commit()
        save('failed-transaction-commit',recorder,'ready','consistent')

        recorder=session('async')
        async def async_case():
            async with recorder.awrap(await async_connect()) as transaction:
                cursor=await transaction.execute(select,('x',))
                assert await cursor.fetchone()==(1,'x0')
                await transaction.execute(update,(2,'x-async','x'))
            async with recorder.awrap(await async_connect()) as transaction:
                cursor=await transaction.execute(select,('x',))
                assert await cursor.fetchall()==[(2,'x-async')]
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(async_case())
        save('async',recorder,'ready','consistent')

        raw=(destination/'async.jsonl').read_bytes()
        (destination/'truncated.jsonl').write_bytes(raw[:raw.rfind(b'\n',0,len(raw)-1)+1])
        truncated=load_jsonl(destination/'truncated.jsonl')
        assert truncated['gaps']
        (destination/'truncated.trace.json').write_text(json.dumps(truncated,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        scenarios.append({'name':'truncated','expectedStatus':'inconclusive','expectedVerdict':None,'trace':'truncated.trace.json'})

        # The entire uniquely named schema is owned by this fixture run.
        setup.execute('DROP SCHEMA "' + schema + '" CASCADE')
    receipt={'actualDatabaseExecution':True,'server':server,'driver':psycopg.__version__,
             'scope':'controlled capture integration fixtures; not independent business adoption',
             'scenarios':scenarios}
    (destination/'database.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print('Actual capture fixtures completed: '+str(len(scenarios)))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
