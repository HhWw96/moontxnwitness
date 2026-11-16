"""V2 installer/catalog regression with fake native control results only; no DB."""
from __future__ import annotations

import base64
import copy
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch
import uuid

from . import configured_source_v2 as m
from . import test_configured_source as old_fixtures
from .configured_sql import ColumnConfig, TEXT_COMPARISON
from .configured_sql_v2 import SQLCaptureConfigV2, TableConfigV2, PrimaryKeyConfigV2

POLICY=m.SourceInstallPolicy('mtw_source_unit_v2',('writer',))


def config(kind='uuid',schema='App.X',name='Records Space'):
    return SQLCaptureConfigV2(TableConfigV2(schema,name,PrimaryKeyConfigV2('Key ID',kind,TEXT_COMPARISON if kind=='text' else None),
        (ColumnConfig('flag','bool'),ColumnConfig('text','text',TEXT_COMPARISON))))


def catalog(cfg,installed=False,order=None):
    table=cfg.table; selected={c.name:c for c in table.columns}
    # Deliberately put the PK last in the physical table, unlike config row order.
    order=order or ['flag','text','Key ID']
    columns=[]
    for number,name in enumerate(order,1):
        column=selected[name]; text=column.type=='text'
        columns.append(dict(name=name,number=number,oid={'int64':20,'bool':16,'text':25,'uuid':2950}[column.type],
            generated='',identity='',notNull=True,typeKind='b',typeSchema='pg_catalog',elementType=0,
            collation='C' if text else None,collationSchema='pg_catalog' if text else None,
            collationProvider='c' if text else None,collationDeterministic=True if text else None,default=None))
    value=dict(schema=table.schema,table=table.table,oid=17000,kind='r',persistence='p',owner='owner',rls=False,forceRls=False,
        inherits=False,rules=False,columns=columns,primaryKeys=[dict(columns=[table.primary_key],keys=1,valid=True,ready=True,immediate=True)],triggers=[],uniqueIndexes=[])
    if installed:
        columns.append(dict(name=m.VERSION_COLUMN,number=4,oid=20,notNull=True,typeKind='b',typeSchema='pg_catalog',elementType=0,
            generated='',identity='',default=None,collation=None,collationSchema=None,collationProvider=None,collationDeterministic=None))
        value['uniqueIndexes']=[dict(columns=[m.VERSION_COLUMN],keys=1,valid=True,ready=True,immediate=True,noPredicate=True,noExpression=True)]
        bodies=m.function_bodies_v2(POLICY)
        for trigger,kind,function,body in [(m.BEFORE_TRIGGER,23,'before_write',bodies[0]),(m.AFTER_TRIGGER,29,'after_write',bodies[1])]:
            value['triggers'].append(dict(name=trigger,type=kind,enabled='A',argsHex=(table.primary_key.encode('utf-8')+b'\0').hex(),
                noCondition=True,noColumns=True,functionSchema=POLICY.namespace,function=function,body=body,owner='owner',securityDefiner=True,
                returnType=2279,volatile='v',parallel='u',argCount=0,settings=['search_path=pg_catalog, pg_temp','standard_conforming_strings=on']))
    return value


def sidecar():
    value=old_fixtures.sidecar();value['namespace']=POLICY.namespace
    return value


class Native:
    def __init__(self,rows,tag,count=None):
        self.data=rows;self.nfields=1 if rows is not None else 0;self.ntuples=len(rows or [])
        self.status=2 if self.nfields else 1;self.command_status=tag.encode('ascii')
        self.command_tuples=len(rows) if rows is not None else count;self.oid=25;self.format=0
    def get_value(self,row,column):return self.data[row][column].encode('utf-8')
    def ftype(self,column):return self.oid
    def fformat(self,column):return self.format


class Cursor:
    def __init__(self,values=None,tag=None,count=None):
        self.rows=None if values is None else [(json.dumps(v,ensure_ascii=False),) for v in values]
        self.pgresult=Native(self.rows,tag or ('SELECT '+str(len(self.rows)) if self.rows is not None else 'COMMAND'),count)
        self.tamper=False
    def fetchall(self):return [('{}',)] if self.tamper else self.rows


class Connection:
    autocommit=True
    def __init__(self,cfg=None,rows=1):
        self.config=cfg or config();self.info=types.SimpleNamespace(transaction_status=0)
        self.calls=[];self.installed=False;self.committed=False;self.rollback_called=False
        self.commit_tag='COMMIT';self.fail_sql=None;self.error=RuntimeError('original control error')
        self.scope=[];self.effects=[];self.ledger_change=None;self.snapshot_marker=False;self.decoder_tamper=False
        self.values=[]
        for index in range(rows):
            key=(str(uuid.UUID(int=index+1)) if self.config.table.key.type=='uuid' else index+7 if self.config.table.key.type=='int64' else '键-'+str(index))
            self.values.append({'Key ID':key,'flag':True,'text':'原始🙂文本',m.VERSION_COLUMN:index+1})
    def execute(self,sql,params=None):
        self.calls.append((sql,params))
        if self.fail_sql and self.fail_sql in sql:raise self.error
        if sql=='BEGIN':self.info.transaction_status=2;return Cursor(tag='BEGIN')
        if sql=='COMMIT':
            self.info.transaction_status=0;self.committed=self.commit_tag=='COMMIT';return Cursor(tag=self.commit_tag)
        if sql.startswith('SET LOCAL'):return Cursor(tag='SET')
        if sql.startswith('LOCK TABLE'):return Cursor(tag='LOCK TABLE')
        if sql==m.ENVIRONMENT_SQL:
            cursor=Cursor([old_fixtures.environment()]);cursor.tamper=self.decoder_tamper;return cursor
        if sql==m.TABLE_CATALOG_SQL:return Cursor([catalog(self.config,self.installed)])
        if sql==m.PERMISSIONS_SQL:return Cursor([dict(role=params[0],table=params[1],trigger=False,truncate=False,ownerMembership=False)])
        if sql==m.LOCKS_SQL:return Cursor([{'pid':1234,'locks':[dict(relation=17000,mode='AccessExclusiveLock',granted=True)]}])
        if sql==m.SOURCE_CATALOG_SQL:return Cursor([sidecar()])
        if "'kind','initial-row'" in sql:
            values=[row for row in self.values if row[m.VERSION_COLUMN]>params[0]][:1]
            return Cursor([{'kind':'initial-row-budget'}] if values and self.snapshot_marker else [{'kind':'initial-row','row':row} for row in values])
        if "'kind','initial-ledger'" in sql:return Cursor([row for row in self.effects if row['version']>params[0]][:1])
        if sql.startswith("SELECT pg_catalog.jsonb_build_object('relation_oid'"):return Cursor(self.scope)
        if 'count(*) FILTER' in sql:return Cursor([{'rows':len(self.effects),'nonInitial':sum(row['operation']!='INITIAL' for row in self.effects)}])
        if sql.startswith('INSERT INTO') and '.scope VALUES' in sql:
            self.scope=[dict(relation_oid=params[0],relation_schema=params[1],relation_table=params[2],primary_key=params[3],config_sha256=params[4])]
            return Cursor(tag='INSERT 0 1',count=1)
        if sql.startswith('INSERT INTO') and '.effects(' in sql:
            self.effects=[dict(kind='initial-ledger',version=row[m.VERSION_COLUMN],baseVersion=None,relationOid=17000,operation='INITIAL',
                writerXid='123',writerLogin='installer',writerPid=1234,rowKey=row['Key ID'],oldKey=None,
                rowValues={k:v for k,v in row.items() if k!=m.VERSION_COLUMN}) for row in self.values]
            if self.ledger_change:self.ledger_change(self.effects)
            return Cursor(tag='INSERT 0 '+str(len(self.values)),count=len(self.values))
        if sql.startswith('UPDATE '):return Cursor(tag='UPDATE '+str(len(self.values)),count=len(self.values))
        if sql.startswith('ALTER TABLE') and 'ADD COLUMN' in sql:self.installed=True
        for prefix,tag in [('CREATE SCHEMA ','CREATE SCHEMA'),('CREATE SEQUENCE ','CREATE SEQUENCE'),('CREATE TABLE ','CREATE TABLE'),
                           ('CREATE FUNCTION ','CREATE FUNCTION'),('CREATE UNIQUE INDEX ','CREATE INDEX'),('CREATE TRIGGER ','CREATE TRIGGER'),
                           ('ALTER TABLE ','ALTER TABLE'),('REVOKE ','REVOKE')]:
            if sql.startswith(prefix):return Cursor(tag=tag)
        raise AssertionError('Unexpected installer SQL: '+sql)
    def rollback(self):self.rollback_called=True;self.info.transaction_status=0


class CatalogV2Tests(unittest.TestCase):
    def test_three_native_key_types_accept_name_matching_without_pk_first(self):
        for kind in ['uuid','int64','text']:
            with self.subTest(kind=kind):
                cfg=config(kind);before=catalog(cfg);after=catalog(cfg,True)
                self.assertEqual(m.verify_table_catalog_v2(cfg.table,POLICY,'owner',before),17000)
                self.assertEqual(m.verify_table_catalog_v2(cfg.table,POLICY,'owner',after,installed=True),17000)
                comparison=m.compare_installation_catalogs_v2(cfg.table,POLICY,'owner',before,after)
                self.assertFalse(comparison['declaredBusinessViewMatchesBeforeOrder'])
                self.assertFalse(comparison['catalogInstallationSourceAuthorized'])
                self.assertEqual(before['columns'][-1]['name'],'Key ID')
    def test_actual_physical_before_after_star_comparison_is_separate(self):
        cfg=config();order=[c.name for c in cfg.table.columns]
        comparison=m.compare_installation_catalogs_v2(cfg.table,POLICY,'owner',catalog(cfg,order=order),catalog(cfg,True,order))
        self.assertTrue(comparison['declaredBusinessViewMatchesBeforeOrder']);self.assertTrue(comparison['onlyVersionColumnAdded'])
        self.assertFalse(comparison['moonbitProjectionVerified'])
    def test_nonnull_is_required_for_every_key_and_business_column(self):
        cfg=config()
        for index in range(3):
            for value in [False,None,1]:
                raw=catalog(cfg);raw['columns'][index]['notNull']=value
                with self.subTest(index=index,value=value),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_uuid_pg_catalog_oid_domain_array_generation_and_identity(self):
        cfg=config()
        for field,value in [('oid',25),('oid','2950'),('typeSchema','custom'),('typeKind','d'),('elementType',2950),('generated','s'),('identity','a')]:
            raw=catalog(cfg);raw['columns'][-1][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_complete_inventory_and_actual_attribute_numbers_are_required(self):
        cfg=config()
        for change in ['missing','duplicate','order','number','extra']:
            raw=catalog(cfg)
            if change=='missing':raw['columns'].pop()
            elif change=='duplicate':raw['columns'].append(copy.deepcopy(raw['columns'][0]))
            elif change=='order':raw['columns'].reverse()
            elif change=='number':raw['columns'][1]['number']=raw['columns'][0]['number']
            else:raw['columns'].append({**raw['columns'][0],'name':'extra','number':4})
            with self.subTest(change=change),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_physical_business_attributes_may_not_change_after_install(self):
        cfg=config();before=catalog(cfg);after=catalog(cfg,True);after['columns'][0]['number']=2;after['columns'][1]['number']=3;after['columns'][2]['number']=4;after['columns'][3]['number']=5
        with self.assertRaises(m.SourceInstallError):m.compare_installation_catalogs_v2(cfg.table,POLICY,'owner',before,after)
    def test_old_owner_rls_rule_and_trigger_restrictions_remain(self):
        cfg=config()
        for field,value in [('owner','other'),('kind','v'),('persistence','u'),('rls',True),('forceRls',True),('rules',True),('inherits',True),('triggers',[{}])]:
            raw=catalog(cfg);raw[field]=value
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_primary_key_cannot_be_deferred_composite_or_boolean_count(self):
        cfg=config()
        for field,value in [('keys',True),('keys',2),('columns',['flag']),('valid',False),('ready',False),('immediate',False)]:
            raw=catalog(cfg);raw['primaryKeys'][0][field]=value
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_c_text_collation_must_be_actual_and_deterministic(self):
        cfg=config('text')
        for field,value in [('collation','default'),('collationSchema','other'),('collationDeterministic',False)]:
            raw=catalog(cfg);raw['columns'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw)
    def test_installed_metadata_and_unique_index_are_checked(self):
        cfg=config()
        for field,value in [('oid',23),('notNull',False),('typeKind','d'),('default','1')]:
            raw=catalog(cfg,True);raw['columns'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw,installed=True)
        raw=catalog(cfg,True);raw['uniqueIndexes'][0]['noPredicate']=False
        with self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw,installed=True)
    def test_exact_trigger_body_and_guard_cannot_be_replaced_by_v1(self):
        cfg=config()
        for field,value in [('body',m._v1.function_bodies(POLICY)[0]),('enabled','D'),('type',31),('argsHex','00'),('functionSchema','public'),('owner','writer'),('securityDefiner',False),('returnType',25),('settings',['search_path=public'])]:
            raw=catalog(cfg,True);raw['triggers'][0][field]=value
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_table_catalog_v2(cfg.table,POLICY,'owner',raw,installed=True)
    def test_role_and_sidecar_bypass_guards_remain_individually_strict(self):
        for field in ['superuser','createRole','createDb','replication','bypassRls','ownerMembership','privilegedMembership','canSetReplicationRole']:
            raw=old_fixtures.environment();raw['writers'][0][field]=True
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_environment_v2(POLICY,raw)
        for field in ['nonOwnerGrants','ownerMembers']:
            raw=sidecar();raw[field]=['writer']
            with self.subTest(field=field),self.assertRaises(m.SourceInstallError):m.verify_source_catalog_v2(POLICY,'owner',raw)
    def test_ddl_is_pure_explicit_quoted_and_preserves_strict_login_scope(self):
        ddl=m.installation_ddl_v2(config(),POLICY);before,after=m.function_bodies_v2(POLICY)
        self.assertTrue(any('"App.X"."Records Space"' in sql for sql in ddl))
        self.assertIn('V2 primary key is immutable',before)
        self.assertIn('SESSION_USER::text COLLATE pg_catalog."C"',before)
        self.assertIn('relation_oid=TG_RELID',before)
        self.assertIn('ledger',m.function_bodies_v2.__doc__.lower())
        self.assertFalse(any(re.match(r'^CREATE\s+(?:SCHEMA|TABLE|SEQUENCE|(?:UNIQUE\s+)?INDEX|FUNCTION)\s+IF\s+NOT\s+EXISTS\b',sql) for sql in ddl))
        self.assertIn('b:=OLD."__mtw_source_version"',after)
    def test_parameterized_control_identifiers_escape_percent_only_in_sql(self):
        cfg=config(schema='s%',name='t%s')
        sql=m.initial_snapshot_sql_v2(cfg)
        self.assertIn('"s%%"."t%%s"',sql)
        self.assertTrue(any('"s%"."t%s"' in s for s in m.installation_ddl_v2(cfg,POLICY)))
    def test_cold_import_needs_no_parser_driver_or_orm(self):
        script='import sys;sys.path.insert(0,sys.argv[1]);import moontxnwitness_capture.configured_source_v2;assert not any(k.split(".")[0] in ("sqlglot","psycopg","sqlalchemy") for k in sys.modules)'
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',script,str(Path(__file__).resolve().parents[1])],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


class InstallationV2Tests(unittest.TestCase):
    def setUp(self):
        self.base=Path(os.environ.get('MTW_SOURCE_V2_TEST_ROOT',str(Path.cwd()/'artifacts/source-v2-unit')))
        self.base.mkdir(parents=True,exist_ok=True)
    def output(self):return self.base/uuid.uuid4().hex
    def receipt(self,path):return json.loads((path/'receipt-v2.json').read_text(encoding='utf-8'))
    def no_facts(self,r):
        for flag in ['sourceFactsProduced','captureFactsProduced','sourceAuthenticated','moonbitCatalogVerified','moonbitProjectionVerified','writerWindowVerified','completeWindow','modelCoverageAccepted','driverFetchVerified','commitVerified']:
            self.assertIs(r[flag],False,flag)
    def test_three_key_types_complete_only_component_records_with_native_commit_ack(self):
        for kind in ['uuid','int64','text']:
            cfg=config(kind);c=Connection(cfg);p=self.output()
            with patch.object(m._v1,'install_configured_source',side_effect=AssertionError('V1 wire invoked')):
                r=m.install_configured_source_v2(c,p,cfg,POLICY,opt_in=True).to_dict()
            self.assertEqual(r['format'],m.FORMAT);self.assertTrue(r['actualCommitConfirmed'])
            self.assertTrue(r['initialLedgerComponentsChecked']);self.assertTrue(r['log']['sealed'])
            self.assertFalse(r['starCatalogComparison']['declaredBusinessViewMatchesBeforeOrder']);self.no_facts(r)
            records=[json.loads(line) for line in (p/'source-install-v2.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(records[0]['format'],m.LOG_FORMAT)
            ack=next(row for row in records if row['kind']=='control-native' and row['queryId']=='installation-commit')
            self.assertEqual(base64.b64decode(ack['native']['commandStatusBase64']),b'COMMIT')
    def test_opt_in_and_v2_type_checks_precede_connection_or_filesystem_access(self):
        class Bomb:
            def __getattr__(self,name):raise AssertionError('Connection accessed')
        p=self.output()
        with self.assertRaises(ValueError):m.install_configured_source_v2(Bomb(),p,config(),POLICY)
        with self.assertRaises(ValueError):m.install_configured_source_v2(Bomb(),p,old_fixtures.CONFIG,POLICY,opt_in=True)
        self.assertFalse(p.exists())
    def test_busy_or_non_autocommit_connection_is_rejected_before_output(self):
        for mode in ['busy','auto']:
            c=Connection();p=self.output()
            if mode=='busy':c.info.transaction_status=2
            else:c.autocommit=False
            with self.assertRaises(ValueError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
            self.assertEqual(c.calls,[]);self.assertFalse(p.exists())
    def test_initial_snapshot_and_ledger_page_beyond_256_without_known_ids(self):
        c=Connection(rows=300);p=self.output();r=m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True).to_dict()
        self.assertEqual(r['initialRows'],300);self.assertEqual(r['initialLedger']['rows'],300)
        self.assertEqual(sum("'kind','initial-ledger'" in sql for sql,_ in c.calls),301)
        self.no_facts(r)
    def test_initial_row_budget_aborts_without_partial_component_acceptance(self):
        c=Connection(rows=3);p=self.output();policy=m.SourceInstallPolicy(POLICY.namespace,POLICY.writers,max_initial_rows=2)
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,policy,opt_in=True)
        self.assertTrue(c.rollback_called);self.assertFalse(c.committed);self.no_facts(self.receipt(p))
    def test_each_initial_ledger_row_must_equal_snapshot_not_only_count(self):
        for mode in ['missing','value','key','operation','base','writer']:
            c=Connection(rows=2);p=self.output()
            def change(rows):
                if mode=='missing':rows.pop()
                elif mode=='value':rows[0]['rowValues']['flag']=False
                elif mode=='key':rows[0]['rowKey']='different'
                elif mode=='operation':rows[0]['operation']='INSERT'
                elif mode=='base':rows[0]['baseVersion']=1
                else:rows[1]['writerXid']='124'
            c.ledger_change=change
            with self.subTest(mode=mode),self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
            self.assertFalse(c.committed);self.no_facts(self.receipt(p))
    def test_bool_cannot_impersonate_int64_initial_ledger_value(self):
        cfg=config('int64');c=Connection(cfg);c.values[0]['Key ID']=1;p=self.output()
        c.ledger_change=lambda rows:rows[0]['rowValues'].update({'Key ID':True})
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,cfg,POLICY,opt_in=True)
        self.no_facts(self.receipt(p))
    def test_duplicate_initial_key_identity_is_rejected(self):
        c=Connection(rows=2);c.values[1]['Key ID']=c.values[0]['Key ID'];p=self.output()
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        self.assertFalse(c.committed)
    def test_native_snapshot_budget_marker_never_becomes_a_partial_initialization(self):
        c=Connection();c.snapshot_marker=True;p=self.output()
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        self.assertFalse(self.receipt(p)['initialSnapshotComponentsChecked'])
    def test_rollback_tag_in_response_to_commit_is_not_commit_ack(self):
        c=Connection();c.commit_tag='ROLLBACK';p=self.output()
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        r=self.receipt(p);self.assertFalse(r['actualCommitConfirmed']);self.assertIn('inspect-owned-schema-before-any-retry',r['gaps']);self.no_facts(r)
    def test_original_control_exception_identity_and_raw_request_are_retained(self):
        c=Connection();c.fail_sql='CREATE SEQUENCE';p=self.output()
        with self.assertRaises(RuntimeError) as caught:m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        self.assertIs(caught.exception,c.error);self.assertTrue(c.rollback_called)
        rows=[json.loads(line) for line in (p/'source-install-v2.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(any(r['kind']=='control-request' and 'CREATE SEQUENCE' in r['sql'] for r in rows))
        self.assertTrue(any(r['kind']=='control-error' and r['phase']=='execute' for r in rows))
    def test_decoder_tamper_keeps_original_native_and_actual_mismatched_delivery_before_failure(self):
        c=Connection();c.decoder_tamper=True;p=self.output()
        with self.assertRaises(m.SourceInstallError):m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        rows=[json.loads(line) for line in (p/'source-install-v2.jsonl').read_text(encoding='utf-8').splitlines()]
        native=next(r for r in rows if r['kind']=='control-native' and r['queryId']=='environment')
        self.assertIn(b'ownerRole',base64.b64decode(native['native']['rows'][0][0]))
        delivery=next(r for r in rows if r['kind']=='control-delivery' and r['queryId']=='environment')
        self.assertEqual(delivery['observation']['rows'][0]['cells'][0]['value'],'{}')
        self.no_facts(self.receipt(p))
    def test_log_failure_after_server_commit_does_not_return_confirmed_installation(self):
        c=Connection();p=self.output();error=OSError('original disk failure');append=m._LogV2.append
        def broken(log,record):
            if record.get('kind')=='control-native' and record.get('queryId')=='installation-commit':raise error
            return append(log,record)
        with patch.object(m._LogV2,'append',broken),self.assertRaises(OSError) as caught:m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        self.assertIs(caught.exception,error);self.assertTrue(c.committed)
        r=self.receipt(p);self.assertFalse(r['actualCommitConfirmed']);self.no_facts(r)
    def test_original_seal_error_is_preserved_and_commit_is_not_promoted(self):
        c=Connection();p=self.output();error=OSError('original seal failure');close=m._LogV2.close
        def broken(log):
            close(log);raise error
        with patch.object(m._LogV2,'close',broken),self.assertRaises(OSError) as caught:m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        self.assertIs(caught.exception,error);r=self.receipt(p);self.assertFalse(r['actualCommitConfirmed']);self.no_facts(r)
    def test_returned_receipt_is_detached(self):
        c=Connection();p=self.output();result=m.install_configured_source_v2(c,p,c.config,POLICY,opt_in=True)
        result.to_dict()['sourceFactsProduced']=True
        self.assertFalse(result.to_dict()['sourceFactsProduced'])


if __name__=='__main__':unittest.main(verbosity=2)
