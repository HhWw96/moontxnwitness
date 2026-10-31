"""CRUD v2 protocol regression checks: real runner code, fake DBAPI, no database."""
from __future__ import annotations
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value
m=module('cost_crud_v2',HERE/'full_capture_cost_v2.py')
legacy=module('cost_legacy_v1',HERE/'full_capture_cost.py')
prep=module('cost_fixture_preparer',HERE/'prepare_full_capture_cost_inputs.py')
BASE=Path(os.environ.get('MTW_JOURNAL_TEST_ROOT',str(ROOT/'artifacts/cost-v2-unit')))
RUN=BASE/('crud-v2-'+uuid.uuid4().hex)
RUN.mkdir(parents=True,exist_ok=False)
TABLE='"owned"."items"'

class DuplicateKey(Exception):
    sqlstate='23505'

class Cursor:
    def __init__(self,count,row=None):self.rowcount=count;self.row=row
    def fetchone(self):return self.row

class Store:
    def __init__(self):self.rows={'key-'+str(i):0 for i in range(4096)};self.lock=threading.Lock()

class Connection:
    def __init__(self,store=None):self.store=store or Store();self.calls=[]
    def execute(self,sql,params):
        self.calls.append((sql,tuple(params)))
        key=params[0]
        with self.store.lock:
            rows=self.store.rows
            if sql.startswith('INSERT INTO '):
                if key in rows:
                    if 'ON CONFLICT (id) DO NOTHING' not in sql:raise DuplicateKey(key)
                    return Cursor(0)
                rows[key]=0;return Cursor(1)
            if sql.startswith('DELETE FROM '):
                present=key in rows;rows.pop(key,None);return Cursor(int(present))
            if sql.startswith('UPDATE '):
                if key not in rows:return Cursor(0)
                rows[key]=rows[key]+1 if 'value=value+1' in sql else 1
                return Cursor(1,(rows[key],) if 'RETURNING value' in sql else None)
            raise AssertionError('Unregistered SQL reached fake connection: '+sql)

class Tests(unittest.TestCase):
    def args(self,**overrides):
        args=argparse.Namespace(quick=False,profile='column',workload='all',seed=123,archive_cells=False,max_cells=None)
        for key,value in overrides.items():setattr(args,key,value)
        return args
    def op(self,action,key='key-0'):return {'action':action,'key':key,'missing':'missing-0'}
    def test_original_v1_source_is_retained_byte_for_byte(self):
        self.assertEqual(hashlib.sha256(Path(legacy.__file__).read_bytes()).hexdigest(),m.LEGACY_SOURCE_SHA256)
        self.assertEqual(legacy.GENERATOR,'python-random-point-capture-cost/v1')
        self.assertNotEqual(legacy.GENERATOR,m.GENERATOR)
    def test_original_plain_insert_reproduces_duplicate_key_regression(self):
        connection=Connection()
        with self.assertRaises(DuplicateKey) as caught:
            connection.execute('INSERT INTO '+TABLE+'(id,value) VALUES(%s,0)',('key-0',))
        self.assertEqual(caught.exception.sqlstate,'23505')
    def test_existing_key_insert_is_observed_zero_not_retry_or_select(self):
        connection=Connection()
        count=m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],self.op(2))
        self.assertEqual(count,0)
        self.assertEqual(connection.calls,[(m.BUSINESS_SQL['insert-if-absent'].format(table=TABLE),('key-0',))])
        self.assertFalse(any('SELECT' in sql for sql,_ in connection.calls))
    def test_absent_insert_then_duplicate_delivers_one_then_zero(self):
        connection=Connection();del connection.store.rows['key-0']
        self.assertEqual(m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],self.op(2)),1)
        self.assertEqual(m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],self.op(2)),0)
        self.assertEqual(len(connection.calls),2)
    def test_update_delete_and_no_write_keep_distinct_actual_results(self):
        connection=Connection();spec=m.WORKLOADS['crud']
        self.assertEqual(m.execute_business_write(connection,TABLE,spec,self.op(0)),1)
        self.assertEqual(m.execute_business_write(connection,TABLE,spec,self.op(1)),1)
        self.assertEqual(m.execute_business_write(connection,TABLE,spec,self.op(1)),0)
        self.assertEqual(m.execute_business_write(connection,TABLE,spec,self.op(0)),0)
        before=len(connection.calls)
        self.assertIsNone(m.execute_business_write(connection,TABLE,spec,self.op(3)))
        self.assertEqual(len(connection.calls),before)
    def test_fixed_workload_increment_preserves_original_returning_check(self):
        connection=Connection()
        self.assertEqual(m.execute_business_write(connection,TABLE,m.WORKLOADS['parallel'],self.op(0)),1)
        self.assertEqual(connection.store.rows['key-0'],1)
        del connection.store.rows['key-0']
        with self.assertRaisesRegex(AssertionError,'Fixed key disappeared'):
            m.execute_business_write(connection,TABLE,m.WORKLOADS['parallel'],self.op(0))
    def test_missing_or_invalid_rowcount_is_never_reported_as_zero(self):
        class Bad:
            def __init__(self,count):self.count=count
            def execute(self,*args):return Cursor(self.count)
        for count in [None,-1,2,True,'0']:
            with self.subTest(count=count),self.assertRaises(ValueError):
                m.execute_business_write(Bad(count),TABLE,m.WORKLOADS['crud'],self.op(2))
    def test_sql_error_is_not_swallowed_or_retried(self):
        class Bad:
            calls=0
            def execute(self,*args):self.calls+=1;raise DuplicateKey('forced other constraint')
        connection=Bad()
        with self.assertRaises(DuplicateKey):m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],self.op(2))
        self.assertEqual(connection.calls,1)
    def test_no_mode_specific_business_sql_or_parameter_changes(self):
        observations=[]
        for mode in ['A','B','C']:
            connection=Connection();rng=random.Random(789);results=[]
            for _ in range(1000):
                op=m.operation(rng,m.WORKLOADS['crud'])
                results.append((op,m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],op)))
            observations.append((results,connection.calls,connection.store.rows))
        self.assertEqual(observations[0],observations[1]);self.assertEqual(observations[1],observations[2])
    def test_four_concurrent_connections_keep_zero_result_visible(self):
        store=Store()
        def work(worker):
            connection=Connection(store)
            results=[m.execute_business_write(connection,TABLE,m.WORKLOADS['crud'],self.op(2,'key-'+str(i%4))) for i in range(100)]
            return results,len(connection.calls)
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(work,range(4)))
        self.assertEqual(sum(count for _,count in results),400)
        self.assertTrue(all(value==0 for values,_ in results for value in values))
    def test_random_generator_and_rng_state_are_identical_to_v1(self):
        for name,spec in m.WORKLOADS.items():
            a,b=random.Random(123),random.Random(123)
            self.assertEqual([m.operation(a,spec) for _ in range(1000)],[legacy.operation(b,spec) for _ in range(1000)])
            self.assertEqual(a.getstate(),b.getstate())
        def function(path,name):
            return next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name==name)
        self.assertEqual(ast.dump(function(Path(m.__file__),'operation')),ast.dump(function(Path(legacy.__file__),'operation')))
    def test_plan_keeps_domains_rotations_timing_and_targets(self):
        p=m.plan(self.args());old=legacy.plan(self.args())
        self.assertEqual(p['workloads'],old['workloads']);self.assertEqual(p['orders'],old['orders'])
        self.assertEqual(p['performanceTargets'],old['performanceTargets'])
        self.assertEqual(len(p['cells']),36)
        for new,previous in zip(p['cells'],old['cells']):
            for key,value in previous.items():self.assertEqual(new[key],value)
            self.assertEqual((new['warmupSeconds'],new['durationSeconds'],new['drainSeconds']),(15,60,30))
            self.assertEqual(new['protocolVersion'],m.PROTOCOL)
            self.assertEqual(new['businessSqlSha256'],m.BUSINESS_SQL_SHA256)
        self.assertEqual(p['workloads']['crud'],{'keys':4096,'connections':4,'crud':True,'hot':False})
    def test_negative_reads_and_actions_remain_registered_for_every_mode(self):
        for mode in ['A','B','C']:
            rng=random.Random(123);ops=[m.operation(rng,m.WORKLOADS['crud']) for _ in range(1000)]
            self.assertEqual({x['action'] for x in ops},{0,1,2,3})
            self.assertTrue(all(x['missing'].startswith('missing-') and 0<=int(x['missing'][8:])<32 for x in ops))
    def test_protocol_and_capacity_ids_are_distinct(self):
        p=m.plan(self.args(experimental_budget=m.PROFILE))
        self.assertEqual(p['protocolVersion'],'full-capture-cost/crud-conflict-noop-v2')
        self.assertEqual(p['storageBudgetContract'],'full-capture-cost/v2-capacity')
        self.assertEqual(p['actualStorageLimits'],m.LIMITS)
    def test_buffered_source_option_only_applies_to_c(self):
        p=m.plan(self.args(source_write_buffer_bytes=65536))
        for c in p['cells']:self.assertEqual(c.get('sourceWriteBufferBytes',0),65536 if c['mode']=='C' else 0)
    def test_worker_rejects_v1_or_tampered_contract_before_database_access(self):
        for config in [legacy.plan(self.args())['cells'][0],{**m.plan(self.args())['cells'][0],'businessSqlSha256':'0'*64}]:
            with self.assertRaisesRegex(ValueError,'explicitly selected CRUD v2'):
                m.run_cell(config,RUN,lambda **kwargs:self.fail('must not connect'))
    def test_source_binding_tracks_actual_new_runner_and_loaded_package(self):
        names={x.name for x in m.runtime_sources()}
        self.assertIn('full_capture_cost_v2.py',names);self.assertIn('cell_archive.py',names)
        self.assertIn('capacity_budget.py',names)
        self.assertTrue(all(x.is_file() for x in m.runtime_sources()))
    def test_write_result_counters_preserve_zero_one_unknown_and_rollback(self):
        counts={};spec=m.WORKLOADS['crud'];op=self.op(2)
        for count,committed in [(0,True),(1,True),(None,False),(0,False),(1,False)]:m.record_write_result(counts,spec,op,count,committed)
        self.assertEqual(counts['insert-if-absent'],{'observedZeroRows':2,'observedOneRow':2,'unobserved':1,'committedZeroRows':1,'committedOneRow':1})
        m.record_write_result(counts,spec,self.op(3),None,True)
        self.assertNotIn('read-only',counts)
    def test_sqlstate_and_storage_failures_still_disqualify_targets(self):
        base={'status':'passed','formalProtocolCompleted':True,'captureBudgetExhausted':False,'failures':0,'warmupFailures':0,'protocolFailures':[],
              'endToEndCommittedTps':100,'allAttemptP95Ns':1,'protocolVersion':m.PROTOCOL,'generator':m.GENERATOR,
              'businessSqlSha256':m.BUSINESS_SQL_SHA256}
        self.assertFalse(m.target_eligibility_reasons(base))
        for patch in [{'failures':1,'sqlstateCounts':{'23505':1}},{'warmupFailures':1},{'captureBudgetExhausted':True},{'protocolFailures':[{'errorClass':'Unknown'}]}]:
            self.assertTrue(m.target_eligibility_reasons({**base,**patch}))
        for patch in [{'protocolVersion':'legacy-v1'},{'generator':legacy.GENERATOR},{'businessSqlSha256':'0'*64}]:
            self.assertIn('mismatched_cost_protocol_or_sql',m.target_eligibility_reasons({**base,**patch}))
    def test_new_attempt_fields_fit_unchanged_fixed_byte_reservation(self):
        record={'ordinal':1000000,'committed':False,'sqlstate':'40001','latencyNs':2**63-1,
                'key':'key-4095','action':2,'rowcount':None,'businessAction':'insert-if-absent',
                'writeResultObserved':False,'missing':'missing-31'}
        self.assertLessEqual(len((json.dumps(record,separators=(',',':'))+'\n').encode()),512)
    def test_quick_and_partial_are_not_formal_target_success(self):
        p=m.plan(self.args(quick=True,max_cells=3))
        self.assertEqual(len(p['cells']),36);self.assertEqual(p['maximumCellsThisInvocation'],3)
        self.assertFalse(p['formalPerformanceMeasurement'])
    def test_real_plan_only_entry_point_never_imports_or_connects_database(self):
        out=RUN/'plan';env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        env.pop('MTW_PG_DSN',None);env.pop('MTW_PG_CONNECTION_FILE',None)
        result=subprocess.run([sys.executable,'-B',m.__file__,'--output',str(out),'--plan-only','--archive-cells'],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        p=json.loads((out/'plan.json').read_text());receipt=json.loads((out/'receipt.json').read_text())
        self.assertEqual(p['protocolVersion'],m.PROTOCOL);self.assertEqual(len(p['cells']),36)
        self.assertEqual(receipt['status'],'not-executed');self.assertFalse(receipt['actualDatabaseExecution'])
    def test_existing_workflow_preserves_legacy_default_and_routes_v2_explicitly(self):
        text=(ROOT/'.github/workflows/full-capture-cost.yml').read_text()
        self.assertIn('default: legacy-v1',text)
        self.assertIn('MTW_COST_RUNNER=experiments/provenance/full_capture_cost_v2.py',text)
        self.assertIn('MTW_COST_RUNNER=experiments/provenance/full_capture_cost.py',text)
        self.assertEqual(text.count('python -B experiments/provenance/full_capture_cost.py --profile'),2)
        self.assertEqual(text.count('python -B experiments/provenance/full_capture_cost_v2.py --profile'),2)
    def fixture_case(self,name):
        root=RUN/name;root.mkdir()
        manifest,entries=prep.cache.load_index(ROOT)
        return root,manifest,entries
    def test_frozen_cost_fixture_offline_cached_restore_checks_exact_bytes(self):
        root,manifest,entries=self.fixture_case('restore-small')
        data=(ROOT/prep.NAME).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),prep.EXPECTED['sha256'])
        cached=root/'cache';blob=cached/'blobs'/prep.EXPECTED['sha256'][:2]/prep.EXPECTED['sha256']
        blob.parent.mkdir(parents=True);blob.write_bytes(data)
        with patch.object(prep.cache,'load_index',return_value=(manifest,entries)),patch.object(prep.cache,'archive_file',side_effect=AssertionError('no archive or network allowed')):
            result=prep.prepare(root,cached,offline=True)
        self.assertTrue(result['passed']);self.assertEqual((root/prep.NAME).read_bytes(),data)
        self.assertEqual(result['logicalBytes'],2490)
    def test_frozen_cost_fixture_existing_poison_is_not_replaced(self):
        root,manifest,entries=self.fixture_case('existing-poison')
        target=root/prep.NAME;target.parent.mkdir(parents=True);target.write_bytes(b'poison')
        with patch.object(prep.cache,'load_index',return_value=(manifest,entries)),self.assertRaises(ValueError):
            prep.prepare(root,root/'cache',offline=True)
        self.assertEqual(target.read_bytes(),b'poison')
    def test_frozen_cost_fixture_poisoned_blob_is_not_replaced_or_published(self):
        root,manifest,entries=self.fixture_case('blob-poison')
        blob=root/'cache/blobs'/prep.EXPECTED['sha256'][:2]/prep.EXPECTED['sha256']
        blob.parent.mkdir(parents=True);blob.write_bytes(b'poison')
        with patch.object(prep.cache,'load_index',return_value=(manifest,entries)),self.assertRaises(ValueError):
            prep.prepare(root,root/'cache',offline=True)
        self.assertEqual(blob.read_bytes(),b'poison');self.assertFalse((root/prep.NAME).exists())
    def test_frozen_cost_fixture_identity_drift_is_rejected_before_publication(self):
        root,manifest,entries=self.fixture_case('index-drift')
        entries={**entries,prep.NAME:{**entries[prep.NAME],'sha256':'0'*64}}
        with patch.object(prep.cache,'load_index',return_value=(manifest,entries)),self.assertRaises(ValueError):
            prep.prepare(root,root/'cache',offline=True)
        self.assertFalse((root/prep.NAME).exists())

if __name__=='__main__':unittest.main(verbosity=2)
