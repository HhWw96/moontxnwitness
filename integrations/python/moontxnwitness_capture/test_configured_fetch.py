"""Configured delivery tests use actual wrapper calls and an explicit fake libpq buffer."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import types
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.configured_fetch import ConfiguredInstrumentation,StoredColumnObservation
from moontxnwitness_capture.configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig

ROOT=Path(os.environ['MTW_CONFIGURED_FETCH_TEST_ROOT']);ROOT.mkdir(parents=True,exist_ok=True)
CONFIG=SQLCaptureConfig((TableConfig('biz','orders','id',(ColumnConfig('id','int64'),ColumnConfig('enabled','bool'),ColumnConfig('version','text',comparison='postgres-c-utf8-v1'))),),default_schema='biz')
SQL='SELECT id,enabled,version FROM biz.orders WHERE id=%s'
class Native:
    status=2;nfields=3;ntuples=2
    def fname(self,i):return [b'id',b'enabled',b'version'][i]
    def ftype(self,i):return [20,16,25][i]
    def fformat(self,i):return 0
    def fmod(self,i):return -1
    def ftable(self,i):return 17000
    def ftablecol(self,i):return i+1
    def get_value(self,row,column):return [[b'1',b't','初🙂'.encode()],[b'2',b'f',b'v2']][row][column]
class Raw:
    def __init__(self):
        self.info=types.SimpleNamespace(transaction_status=0,encoding='utf-8')
        self.autocommit=self.closed=False;self._pipeline=self._tpc=None
        self.calls=[];self.cursors=[];self.execute_error=self.fetch_error=self.close_error=None
    def cursor(self,*args,**kwargs):
        c=Cursor(self);self.cursors.append(c);return c
    def rollback(self):self.info.transaction_status=0
    def close(self):self.closed=True
class Cursor:
    def __init__(self,c):
        self.connection=c;self.rowcount=-1;self.rownumber=0;self.arraysize=1
        self.description=None;self.pgresult=None;self.row_factory=None;self.closed=False;self.fetches=0
        self.rows=[(1,True,'初🙂'),(2,False,'v2')]
    def execute(self,sql,params=None,**kwargs):
        self.connection.calls.append((sql,params,kwargs))
        if self.connection.execute_error:raise self.connection.execute_error
        self.connection.info.transaction_status=2;self.rownumber=0;self.rowcount=2
        self.description=[types.SimpleNamespace(name=x,type_code=y) for x,y in [('id',20),('enabled',16),('version',25)]]
        self.pgresult=Native();return self
    def executemany(self,sql,values,**kwargs):
        for value in values:self.connection.calls.append((sql,value,kwargs))
        self.description=None;return None
    def fetchone(self):
        self.fetches+=1
        if self.connection.fetch_error:raise self.connection.fetch_error
        if self.rownumber>=len(self.rows):return None
        r=self.rows[self.rownumber];self.rownumber+=1;return r
    def fetchmany(self,size=None):
        self.fetches+=1
        if self.connection.fetch_error:raise self.connection.fetch_error
        size=self.arraysize if size is None else size
        rows=self.rows[self.rownumber:self.rownumber+size];self.rownumber+=len(rows);return rows
    def fetchall(self):
        self.fetches+=1
        if self.connection.fetch_error:raise self.connection.fetch_error
        rows=self.rows[self.rownumber:];self.rownumber=len(self.rows);return rows
    def close(self):
        if self.connection.close_error:raise self.connection.close_error
        self.closed=True
    def _close(self):return self.close()
class AsyncRaw(Raw):
    def cursor(self,*args,**kwargs):
        c=AsyncCursor(self);self.cursors.append(c);return c
    async def rollback(self):return super().rollback()
    async def close(self):return super().close()
class AsyncCursor(Cursor):
    async def execute(self,*args,**kwargs):return super().execute(*args,**kwargs)
    async def executemany(self,*args,**kwargs):return super().executemany(*args,**kwargs)
    async def fetchone(self):return super().fetchone()
    async def fetchmany(self,*args):return super().fetchmany(*args)
    async def fetchall(self):return super().fetchall()
    async def close(self):return super().close()
    def _close(self):return Cursor.close(self)

class Tests(unittest.TestCase):
    def setUp(self):self.observers=[]
    def tearDown(self):
        for observer in self.observers:observer.close()
    def observer(self,**options):
        o=ConfiguredInstrumentation(ROOT/uuid.uuid4().hex,CONFIG,**options);self.observers.append(o);return o
    def frames(self,o,kind):
        o.lifecycle.file.flush()
        return [json.loads(r['frameText']) for r in map(json.loads,(o.output/'lifecycle.jsonl').read_text(encoding='utf8').splitlines()) if r.get('kind')==kind]
    def test_no_prefetch_and_unchanged_objects(self):
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();params=(1,)
        self.assertIs(c.execute(SQL,params),c);self.assertEqual(c._raw.fetches,0)
        self.assertIs(raw.calls[0][0],SQL);self.assertIs(raw.calls[0][1],params)
        self.assertEqual(len(self.frames(o,'configured-native-result')),1)
        self.assertEqual(self.frames(o,'configured-delivery'),[])
        row=c.fetchone();self.assertIs(row,c._raw.rows[0]);self.assertEqual(c._raw.fetches,1)
    def test_mixed_fetch_preserves_rows_and_positions(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,))
        self.assertEqual(c.fetchone(),(1,True,'初🙂'));self.assertEqual(c.fetchmany(1),[(2,False,'v2')]);self.assertIsNone(c.fetchone())
        f=self.frames(o,'configured-delivery');self.assertEqual([x['start'] for x in f],[0,1,2]);self.assertTrue(f[-1]['complete'])
        self.assertEqual(c.description,c._raw.description)
    def test_iteration_uses_actual_fetch(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));self.assertEqual(list(c),c._raw.rows)
        self.assertEqual(c._raw.fetches,3)
    def test_fetchall_same_list(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));rows=c.fetchall()
        self.assertEqual(rows,c._raw.rows);self.assertTrue(self.frames(o,'configured-delivery')[0]['complete'])
    def test_execute_exception_identity(self):
        o=self.observer();raw=Raw();error=RuntimeError('business');raw.execute_error=error;c=o.wrap(raw).cursor()
        with self.assertRaises(RuntimeError) as r:c.execute(SQL,(1,))
        self.assertIs(r.exception,error);self.assertEqual(self.frames(o,'configured-native-result'),[])
    def test_fetch_exception_identity_and_no_delivery(self):
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();c.execute(SQL,(1,));error=RuntimeError('fetch');raw.fetch_error=error
        with self.assertRaises(RuntimeError) as r:c.fetchone()
        self.assertIs(r.exception,error);self.assertEqual(self.frames(o,'configured-delivery'),[])
    def test_close_exception_identity(self):
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();c.execute(SQL,(1,));error=RuntimeError('close');raw.close_error=error
        with self.assertRaises(RuntimeError) as r:c.close()
        self.assertIs(r.exception,error)
    def test_duplicate_wrap_and_raw_reuse(self):
        o=self.observer();raw=Raw();a=o.wrap(raw);self.assertIs(o.wrap(raw),a);self.assertIs(o.wrap(a),a)
        a.cursor().execute(SQL,(1,));a.rollback();self.assertIs(o.wrap(raw),a)
    def test_foreign_wrap_not_double_observed(self):
        a=self.observer();b=self.observer();c=a.wrap(Raw());self.assertIs(b.wrap(c),c)
    def test_unknown_sql_still_exactly_executes(self):
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();q='SELECT lower(version) FROM biz.orders';c.execute(q,None)
        self.assertEqual(raw.calls[0][:2],(q,None));self.assertEqual(c.fetchall(),c._raw.rows)
        self.assertEqual(self.frames(o,'configured-native-result'),[])
    def test_unknown_params_never_iterated(self):
        class NoIter:
            def __iter__(self):raise AssertionError('consumed params')
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();params=NoIter();c.execute(SQL,params)
        self.assertIs(raw.calls[0][1],params)
    def test_stored_column_not_source_fact(self):
        o=self.observer(stored_columns=(StoredColumnObservation('biz','orders','version'),));c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));c.fetchall()
        frame=self.frames(o,'configured-native-result')[0]
        self.assertEqual(frame['storedColumnDeclarations'],['version']);self.assertFalse(frame['sourceFactsProduced'])
    def test_configuration_rejects_unconfigured_version(self):
        with self.assertRaises(ValueError):self.observer(stored_columns=(StoredColumnObservation('biz','orders','no'),))
    def test_unread_close_records_gap(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));c.close()
        self.assertEqual(len(self.frames(o,'configured-result-incomplete')),1)
    def test_result_replacement_records_gap(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));c.execute(SQL,(2,))
        self.assertEqual(len(self.frames(o,'configured-result-incomplete')),1)
    def test_native_observer_failure_preserves_return(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c._raw.pgresult=None
        old=Native.get_value
        try:
            Native.get_value=lambda *a:(_ for _ in ()).throw(ValueError('observer'))
            self.assertIs(c.execute(SQL,(1,)),c);self.assertEqual(c.fetchall(),c._raw.rows)
        finally:Native.get_value=old
    def test_batch_keeps_generator_consumption_at_driver(self):
        o=self.observer();raw=Raw();c=o.wrap(raw).cursor();seen=[]
        def rows():
            for i in range(3):seen.append(i);yield (i,)
        values=rows();self.assertEqual(seen,[]);self.assertIsNone(c.executemany(SQL,values));self.assertEqual(seen,[0,1,2])
    def test_bounded_sink_failure_keeps_results(self):
        o=self.observer(max_lifecycle_records=128);c=o.wrap(Raw()).cursor()
        for _ in range(130):o.note('fill',value='x')
        self.assertTrue(o.lifecycle.failed);c.execute(SQL,(1,));self.assertEqual(c.fetchall(),c._raw.rows)
    def test_async_all_fetch_paths(self):
        async def run():
            o=self.observer();raw=AsyncRaw();connection=o.wrap_async(raw);self.assertIs(o.wrap_async(raw),connection)
            c=connection.cursor();self.assertIs(await c.execute(SQL,(1,)),c);self.assertEqual(c._raw.fetches,0)
            self.assertEqual(await c.fetchone(),(1,True,'初🙂'));self.assertEqual(await c.fetchmany(),[(2,False,'v2')]);self.assertEqual(await c.fetchall(),[])
            await c.execute(SQL,(1,));self.assertEqual([r async for r in c],c._raw.rows)
            await c.close()
        asyncio.run(run())
    def test_async_exceptions_preserved(self):
        async def run():
            o=self.observer();raw=AsyncRaw();c=o.wrap_async(raw).cursor();error=RuntimeError('async')
            raw.execute_error=error
            with self.assertRaises(RuntimeError) as r:await c.execute(SQL,(1,))
            self.assertIs(r.exception,error);raw.execute_error=None;await c.execute(SQL,(1,));raw.fetch_error=error
            with self.assertRaises(RuntimeError) as r:await c.fetchall()
            self.assertIs(r.exception,error)
        asyncio.run(run())
    def test_adapter_prefetch_not_actual_delivery(self):
        async def run():
            o=self.observer();c=o.wrap_async(AsyncRaw()).cursor();c._adapter_delivery=True
            await c.execute(SQL,(1,));rows=await c.fetchall();self.assertEqual(self.frames(o,'configured-delivery'),[])
            c.delivered(rows,True);self.assertEqual(len(self.frames(o,'configured-delivery')),1)
        asyncio.run(run())
    def test_async_adapter_partial_delivery_method(self):
        async def run():
            o=self.observer();c=o.wrap_async(AsyncRaw()).cursor();c._adapter_delivery=True
            await c.execute(SQL,(1,));rows=await c.fetchall();c.delivered(rows[:1],False);c.delivered(rows[1:],True)
            f=self.frames(o,'configured-delivery');self.assertEqual([x['method'] for x in f],['adapter-delivered','adapter-delivered']);self.assertEqual([x['start'] for x in f],[0,1])
        asyncio.run(run())
    def test_native_replaced_outside_wrapper_not_certified(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));c._raw.pgresult=Native();self.assertEqual(c.fetchall(),c._raw.rows)
        self.assertEqual(self.frames(o,'configured-delivery'),[])
    def test_local_factory_does_not_change_raw_factory(self):
        from moontxnwitness_capture.configured_fetch import instrument_configured_psycopg
        raw=Raw();calls=[]
        def factory(*args,**kwargs):calls.append((args,kwargs));return raw
        o,connect=instrument_configured_psycopg(factory,ROOT/uuid.uuid4().hex,CONFIG);self.observers.append(o)
        c=connect('argument',value=True);self.assertIs(c._raw,raw);self.assertEqual(calls,[(('argument',),{'value':True})]);self.assertIs(factory(),raw)
    def test_engine_duplicate_install_keeps_seven_scoped_callbacks(self):
        from sqlalchemy import create_engine,event
        engine=create_engine('postgresql+psycopg://');o=self.observer()
        try:
            self.assertIs(o.attach_engine(engine),o);listeners=list(o._listeners);self.assertEqual(len(listeners),7)
            with self.assertRaises(ValueError):o.attach_engine(engine)
            self.assertEqual(o._listeners,listeners)
            o.detach()
            self.assertTrue(all(not event.contains(*item) for item in listeners))
        finally:engine.dispose()
    def test_closed_observer_passes_through_new_connections(self):
        o=self.observer();o.close();raw=Raw();self.assertIs(o.wrap(raw),raw)
    def test_no_events_array_retains_full_delivery(self):
        o=self.observer();c=o.wrap(Raw()).cursor();c.execute(SQL,(1,));c.fetchall()
        self.assertIsNone(getattr(o,'_events',None));self.assertNotIn('rows',c._configured_native);self.assertNotIn('parameters',c._configured_native)
    def test_equal_raw_objects_keep_distinct_connection_identity(self):
        class EqualRaw(Raw):
            def __hash__(self):return 1
            def __eq__(self,other):return isinstance(other,EqualRaw)
        o=self.observer();a=EqualRaw();b=EqualRaw();wa=o.wrap(a);wb=o.wrap(b)
        self.assertIsNot(wa,wb);self.assertIs(wa._raw,a);self.assertIs(wb._raw,b);self.assertIs(o.wrap(a),wa)
    def test_weak_registry_drops_dead_wrapper_without_retaining_raw(self):
        import gc,weakref
        o=self.observer();raw=Raw();wrapped=o.wrap(raw);reference=weakref.ref(wrapped)
        del wrapped;gc.collect();self.assertIsNone(reference());self.assertEqual(len(o._configured_registry),0)
        self.assertIs(o.wrap(raw)._raw,raw)
if __name__=='__main__':unittest.main(verbosity=2)
