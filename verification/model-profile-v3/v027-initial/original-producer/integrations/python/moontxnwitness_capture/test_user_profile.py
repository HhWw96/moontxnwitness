"""Fixed profile driver-contract tests. Fake PG results, never database proof."""
import asyncio
import ast
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moontxnwitness_capture.orm import UserScope,FIELDS,VERSION
from moontxnwitness_capture.profiles.fastapi_users import UserProfileCapture
from moontxnwitness_capture.source_sink import GroupedSourceSink
from moontxnwitness_capture.profiles.orm_control import native_result,source_parameters

BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(Path.cwd()/'artifacts/user-profile-unit')))
RUN=BASE/('profile-'+uuid.uuid4().hex);RUN.mkdir(parents=True)
KEY='00000000-0000-4000-8000-000000000001'
OLD='00000000-0000-4000-8000-000000000011'
NEW='00000000-0000-4000-8000-000000000012'
IMAGE={'id':KEY,'email':'person@example.invalid','hashed_password':'fixture-only',
       'is_active':True,'is_superuser':False,'is_verified':False}


class Result:
    def __init__(self,cells,oids,typmods,tag=b'SELECT 1'):
        self.cells,self.oids,self.typmods=cells,oids,typmods
        self.status=2;self.ntuples=len(cells);self.nfields=len(oids)
        self.command_status,self.command_tuples=tag,len(cells)
    def get_value(self,row,column):return self.cells[row][column]
    def ftype(self,column):return self.oids[column]
    def fmod(self,column):return self.typmods[column]
    def fformat(self,column):return 0


class Raw:
    def __init__(self,present=True):
        self.present=present;self.info=types.SimpleNamespace(transaction_status=0,encoding='utf-8')
        self.autocommit=self.closed=False;self._pipeline=self._tpc=None
        self.executions=[];self.fetches=0;self.effect_zero=False;self.execute_error=self.fetch_error=None
    def cursor(self):return Cursor(self)
    def _exec_command(self,command):
        if False:yield None
        return types.SimpleNamespace(command_status=b'COMMIT')
    def commit(self):
        list(self._exec_command(b'COMMIT'));self.info.transaction_status=0
    def rollback(self):self.info.transaction_status=0
    def close(self):self.closed=True


class Cursor:
    row_factory=None;arraysize=1
    def __init__(self,raw):
        self.raw=raw;self.description=self.pgresult=None;self.rowcount=-1;self.rownumber=0
    def execute(self,query,params=None,**kwargs):
        self.raw.executions.append((query,params,kwargs));self.raw.info.transaction_status=2
        if self.raw.execute_error:raise self.raw.execute_error
        if query.startswith('SELECT'):
            values=[uuid.UUID(KEY),IMAGE['email'],IMAGE['hashed_password'],True,False,False]
            if not self.raw.present:values=[None]*6
            if '_mtw_scope' in query:
                self.rows=[tuple(values+[OLD,self.raw.present])]
                wire=[None if v is None else (b't' if v else b'f') if type(v) is bool else str(v).encode() for v in self.rows[0]]
                self.pgresult=Result([wire],[2950,1043,1043,16,16,16,25,16],[-1,324,1028,-1,-1,-1,-1,-1])
                self.description=[types.SimpleNamespace(name=name,type_code=oid) for name,oid in zip((*FIELDS,'token','present'),self.pgresult.oids)]
            else:
                self.rows=[tuple(values)] if self.raw.present else []
                self.pgresult=Result([],[],[])
                self.description=[types.SimpleNamespace(name=name,type_code=oid) for name,oid in zip(FIELDS,[2950,1043,1043,16,16,16])]
        else:
            action='INSERT' if query.startswith('INSERT') else 'UPDATE' if query.startswith('UPDATE') else 'DELETE'
            before,after=(False,True) if action=='INSERT' else (True,False) if action=='DELETE' else (True,True)
            image=json.dumps(IMAGE).encode()
            wire=[KEY.encode(),OLD.encode(),NEW.encode(),b't' if before else b'f',b't' if after else b'f',image if before else None,image if after else None,action.encode()]
            self.rows=[] if self.raw.effect_zero else [tuple(wire)]
            count=len(self.rows);tag=(('INSERT 0 ' if action=='INSERT' else action+' ')+str(count)).encode()
            self.pgresult=Result([] if not count else [wire],[25,25,25,16,16,1043,1043,25],[-1,-1,-1,-1,-1,12292,12292,-1],tag)
            self.description=[types.SimpleNamespace(name='source'+str(i),type_code=oid) for i,oid in enumerate(self.pgresult.oids)]
        self.rowcount=len(self.rows);self.rownumber=0;self.statusmessage=self.pgresult.command_status.decode()
        return self
    def fetchone(self):
        self.raw.fetches+=1
        if self.rownumber>=len(self.rows):return None
        row=self.rows[self.rownumber];self.rownumber+=1;return row
    def fetchall(self):
        if self.raw.fetch_error:raise self.raw.fetch_error
        self.raw.fetches+=1;rows=self.rows[self.rownumber:];self.rownumber=len(self.rows);return rows
    def fetchmany(self,size=None):
        self.raw.fetches+=1;size=self.arraysize if size is None else size
        rows=self.rows[self.rownumber:self.rownumber+size];self.rownumber+=len(rows);return rows
    def close(self):pass
    def _close(self):pass


class AsyncRaw(Raw):
    def cursor(self):return AsyncCursor(self)
    async def commit(self):return super().commit()
    async def rollback(self):return super().rollback()
    async def close(self):return super().close()


class AsyncCursor(Cursor):
    async def execute(self,*args,**kwargs):return super().execute(*args,**kwargs)
    async def fetchone(self):return super().fetchone()
    async def fetchall(self):return super().fetchall()
    async def fetchmany(self,*args):return super().fetchmany(*args)
    async def close(self):pass


class Helpers:
    def make(self,**options):
        output=RUN/(self.id().split('.')[-1]+'-'+uuid.uuid4().hex);output.mkdir()
        scope=UserScope('mtw_orm_v3_unit','observed_user',(KEY,))
        initial={KEY:{'version':OLD,'present':True,'image':IMAGE}}
        installation=types.SimpleNamespace(scope=scope,initial=initial,nonce=NEW,
            metadata={'initialState':initial,'initialSnapshotQuerySeq':2,'initializationWindow':[{'querySeq':3,'commandTag':'COMMIT'}]})
        capture=UserProfileCapture(output/'capture',installation,GroupedSourceSink(output/'sources.jsonl'),**options)
        self.observers.append(capture);return capture
    def sources(self,capture):
        capture.sink.flush()
        return [json.loads(line) for line in capture.sink.path.read_text().splitlines()]
    def events(self,capture):
        capture.flush()
        return [json.loads(line) for path in sorted(capture.journal.path.glob('segment-*.jsonl')) for line in path.read_text().splitlines()]
    def tear(self):
        for capture in self.observers:capture.close()


class SyncTests(Helpers,unittest.TestCase):
    def setUp(self):self.observers=[]
    def tearDown(self):self.tear()
    def test_initial_source_is_first_snapshot_without_editing_old_events(self):
        capture=self.make();snapshot=self.events(capture)[0]
        self.assertEqual(snapshot['initial'],{KEY:OLD});self.assertTrue(snapshot['consistent']);self.assertTrue(capture.exclusive_writers)
    def test_frozen_installation_and_catalog_logic_changes_only_imports(self):
        root=Path(__file__).resolve().parents[3]
        frozen=root/'verification/experimental-candidates/orm-source2-r3-2026-10-21/producer-templates'
        current=Path(__file__).resolve().parent/'profiles'
        for original,target in [('install.py','orm_install.py'),('relation_contract.py','orm_relation.py')]:
            def logic(path):
                tree=ast.parse(path.read_text(encoding='utf8'))
                tree.body=[item for item in tree.body if not isinstance(item,(ast.Import,ast.ImportFrom))]
                return ast.dump(tree,include_attributes=False)
            self.assertEqual(logic(frozen/original),logic(current/target))
    def test_get_metadata_not_delivered_or_source_proved_before_fetch(self):
        capture=self.make();raw=Raw();conn=capture.wrap(raw);plan=capture.cache.prepare(capture.scope,'get')
        cursor=conn.execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        self.assertEqual(raw.fetches,0);self.assertEqual(len(cursor.description),6)
        self.assertFalse(any(row['kind']=='source-batch' for row in self.sources(capture)))
        row=cursor.fetchone();self.assertEqual(row,(uuid.UUID(KEY),*tuple(IMAGE[name] for name in FIELDS[1:])))
        batch=next(row for row in self.sources(capture) if row['kind']=='source-batch')
        self.assertEqual(batch['observation']['source'],{'key':KEY,'version':OLD,'present':True})
        self.assertFalse(any(row['kind'] in ('read','write','condition') for row in self.events(capture)))
    def test_absent_get_requires_actual_eof_and_hides_metadata_row(self):
        capture=self.make();raw=Raw(False);plan=capture.cache.prepare(capture.scope,'get')
        cursor=capture.wrap(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        self.assertEqual(cursor.rowcount,0);self.assertEqual(cursor.statusmessage,'SELECT 0')
        self.assertFalse(any(row['kind']=='source-batch' for row in self.sources(capture)))
        self.assertIsNone(cursor.fetchone())
        batch=next(row for row in self.sources(capture) if row['kind']=='source-batch')
        self.assertEqual(batch['observation']['source']['present'],False)
    def test_update_same_statement_source_restores_command_surface(self):
        capture=self.make();raw=Raw();plan=capture.cache.prepare(capture.scope,'update',('is_active',),capture.scope.schema+'_'+capture.scope.table+'_id')
        cursor=capture.wrap(raw).execute(plan.original_sql,{plan.key.pk_bind:uuid.UUID(KEY),'is_active':False})
        self.assertEqual(raw.executions[0][0],plan.observed_sql);self.assertEqual(raw.fetches,0)
        self.assertIsNone(cursor.description);self.assertEqual(cursor.rowcount,1);self.assertIsNone(cursor.rownumber)
        self.assertEqual(cursor.pgresult.status,1)
        batch=next(row for row in self.sources(capture) if row['kind']=='source-batch')
        self.assertEqual(batch['observation']['effectRows'][0][1:3],[OLD,NEW])
    def test_zero_row_command_is_gap_and_never_absence_read(self):
        capture=self.make();raw=Raw();raw.effect_zero=True
        plan=capture.cache.prepare(capture.scope,'delete',pk_bind='id')
        cursor=capture.wrap(raw).execute(plan.original_sql,{'id':uuid.UUID(KEY)})
        self.assertIsNone(cursor.description);self.assertEqual(cursor.rowcount,0)
        self.assertTrue(any(row['kind']=='source-gap' for row in self.sources(capture)))
        self.assertFalse(any(row['kind']=='source-batch' for row in self.sources(capture)))
    def test_unknown_sql_and_out_of_domain_parameters_are_unchanged(self):
        capture=self.make();raw=Raw();conn=capture.wrap(raw)
        cursor=conn.execute('SELECT arbitrary',{'outside':'same'});cursor.fetchall()
        self.assertEqual(raw.executions[0][0],'SELECT arbitrary')
        plan=capture.cache.prepare(capture.scope,'get')
        conn.execute(plan.original_sql,{'id_1':uuid.uuid4()}).fetchall()
        self.assertEqual(raw.executions[1][0],plan.original_sql)
        self.assertTrue(any(g['code']=='profile_statement_unproven' for g in capture.gaps))
    def test_original_driver_error_identity_is_preserved(self):
        capture=self.make();raw=Raw();original=raw.execute_error=RuntimeError('original-driver')
        plan=capture.cache.prepare(capture.scope,'get')
        with self.assertRaises(RuntimeError) as caught:capture.wrap(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        self.assertIs(caught.exception,original)
    def test_observer_value_budget_does_not_replace_business_row(self):
        capture=self.make(max_value_bytes=128);raw=Raw();plan=capture.cache.prepare(capture.scope,'get')
        with mock.patch.dict(IMAGE,{'hashed_password':'x'*500}):
            cursor=capture.wrap(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
            self.assertEqual(cursor.fetchall()[0][2],'x'*500)
        self.assertTrue(any(g['code']=='profile_read_delivery_unproven' for g in capture.gaps))
    def test_original_fetch_error_identity_and_gap_are_preserved(self):
        capture=self.make();raw=Raw();plan=capture.cache.prepare(capture.scope,'get')
        cursor=capture.wrap(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        error=raw.fetch_error=RuntimeError('original-fetch')
        with self.assertRaises(RuntimeError) as caught:cursor.fetchall()
        self.assertIs(caught.exception,error)
        self.assertTrue(any(g['code']=='profile_fetch_failed' for g in capture.gaps))
    def test_raw_source_closed_stays_false_after_incomplete_cleanup(self):
        capture=self.make();capture.close()
        index=json.loads((capture.journal.path/'journal-index.json').read_text())
        self.assertTrue(index['closed']);self.assertFalse(index['sourceClosed'])
        self.assertTrue(any(g['code']=='profile_window_unclosed' for g in capture.gaps))
    def test_pending_business_result_keeps_prefix_after_diagnostic_cleanup(self):
        capture=self.make();raw=Raw();plan=capture.cache.prepare(capture.scope,'get')
        cursor=capture.wrap(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        capture.close()
        self.assertEqual(len(cursor.fetchall()[0]),6)
        self.assertTrue(any(g['code']=='profile_window_unclosed' for g in capture.gaps))
    def test_cached_cursor_executes_original_sql_after_window_close(self):
        capture=self.make();raw=Raw();conn=capture.wrap(raw);cursor=conn.cursor()
        capture.close();cursor.execute('SELECT raw-after-window').fetchall()
        self.assertEqual(raw.executions[-1][0],'SELECT raw-after-window')
    def test_unproven_update_bind_variant_is_not_rewritten(self):
        capture=self.make();raw=Raw()
        plan=capture.cache.prepare(capture.scope,'update',('is_active',),capture.scope.table+'_id')
        capture.wrap(raw).execute(plan.original_sql,{plan.key.pk_bind:uuid.UUID(KEY),'is_active':False})
        self.assertEqual(raw.executions[-1][0],plan.original_sql)
        self.assertTrue(any(g['code']=='profile_statement_unproven' for g in capture.gaps))
    def test_finalization_with_active_transaction_cannot_declare_quiescence(self):
        from moontxnwitness_capture.profiles.orm_control import ControlConnection
        capture=self.make();raw=Raw();plan=capture.cache.prepare(capture.scope,'get')
        connection=capture.wrap(raw);connection.execute(plan.original_sql,{'id_1':uuid.UUID(KEY)}).fetchall()
        control=object.__new__(ControlConnection);control.sink=capture.sink
        with self.assertRaises(ValueError):capture.finalize(control)
        self.assertTrue(any(g['code']=='profile_window_active' for g in capture.gaps))
        self.assertFalse(any(row['kind']=='final-effect-ledger' for row in self.sources(capture)))
    def test_bounded_native_result_and_explicit_jsonb_serializer(self):
        from psycopg.types.json import Jsonb
        self.assertEqual(source_parameters(Jsonb({'field':True},dumps=json.dumps))['objectDumps'],'stdlib-json-dumps')
        with self.assertRaises(ValueError):source_parameters(Jsonb({'field':True}))
        with self.assertRaises(ValueError):native_result(Result([[b'x'*20]],[25],[-1]),max_bytes=10)


class AsyncTests(Helpers,unittest.IsolatedAsyncioTestCase):
    def setUp(self):self.observers=[]
    def tearDown(self):self.tear()
    async def test_native_async_get_keeps_six_columns_and_real_delivery(self):
        capture=self.make();raw=AsyncRaw();plan=capture.cache.prepare(capture.scope,'get')
        cursor=await capture.wrap_async(raw).execute(plan.original_sql,{'id_1':uuid.UUID(KEY)})
        self.assertEqual(raw.fetches,0);self.assertEqual(len((await cursor.fetchall())[0]),6)
        self.assertEqual(sum(row['kind']=='source-batch' for row in self.sources(capture)),1)
    async def test_actual_async_adapter_prefetch_does_not_publish_source(self):
        import psycopg
        from sqlalchemy.dialects.postgresql.psycopg import AsyncAdapt_psycopg_connection,AsyncAdapt_psycopg_cursor
        from sqlalchemy.util.concurrency import greenlet_spawn
        from moontxnwitness_capture.instrumentation import _AdapterConnection
        capture=self.make();raw=AsyncRaw();conn=capture.wrap_async(raw)
        cursor=_AdapterConnection(AsyncAdapt_psycopg_connection(conn),conn).cursor()
        plan=capture.cache.prepare(capture.scope,'get')
        with mock.patch.object(AsyncAdapt_psycopg_cursor,'_psycopg_ExecStatus',psycopg.pq.ExecStatus):
            await greenlet_spawn(cursor.execute,plan.original_sql,{'id_1':uuid.UUID(KEY)})
        self.assertEqual(raw.fetches,1)
        self.assertFalse(any(row['kind']=='source-batch' for row in self.sources(capture)))
        self.assertEqual(len(cursor.fetchone()),6)
        self.assertEqual(sum(row['kind']=='source-batch' for row in self.sources(capture)),1)
        self.assertEqual(raw.fetches,1)


if __name__=='__main__':unittest.main(verbosity=2)
