"""Installer contract boundaries; no database or optional SQLGlot import."""
import copy,json,os,re,types,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from .configured_sql import ColumnConfig,TableConfig,SQLCaptureConfig
from .configured_source import (SourceInstallPolicy,SourceInstallError,VERSION_COLUMN,BEFORE_TRIGGER,AFTER_TRIGGER,
 verify_environment,verify_table_catalog,verify_source_catalog,function_bodies,installation_ddl,identifier,literal,install_configured_source)

POLICY=SourceInstallPolicy('mtw_source_unit',('writer',))
TABLE=TableConfig('App.X','Records Space','Key ID',(ColumnConfig('Key ID','int64'),ColumnConfig('flag','bool'),ColumnConfig('text','text',comparison='postgres-c-utf8-v1')))
CONFIG=SQLCaptureConfig((TABLE,))
def environment():
 return {'database':'unit','databaseOid':5,'backendPid':1234,'eventTriggers':[],'serverVersionNum':'180006','serverEncoding':'UTF8','clientEncoding':'UTF8','standardConformingStrings':'on','replicationRole':'origin','owner':'owner','ownerRole':dict(name='owner',superuser=False,login=False,createRole=False,replication=False,bypassRls=False),'writers':[dict(name='writer',superuser=False,login=True,createRole=False,createDb=False,replication=False,bypassRls=False,ownerMembership=False,privilegedMembership=False,canSetReplicationRole=False)]}
def catalog(installed=False):
 cols=[dict(name=c.name,number=i+1,oid={'int64':20,'bool':16,'text':25}[c.type],generated='',identity='',notNull=i==0,typeKind='b',typeSchema='pg_catalog',elementType=0,collation='C'if c.type=='text'else None,collationSchema='pg_catalog'if c.type=='text'else None,collationDeterministic=True if c.type=='text'else None,default=None)for i,c in enumerate(TABLE.columns)]
 result={'schema':TABLE.schema,'table':TABLE.table,'oid':17000,'kind':'r','persistence':'p','owner':'owner','rls':False,'forceRls':False,'inherits':False,'rules':False,'columns':cols,'primaryKeys':[dict(valid=True,ready=True,immediate=True,keys=1,columns=[TABLE.primary_key])],'triggers':[],'uniqueIndexes':[]}
 if installed:
  result['columns'].append(dict(name=VERSION_COLUMN,oid=20,notNull=True,generated='',identity='',default=None))
  result['uniqueIndexes']=[dict(valid=True,ready=True,immediate=True,keys=1,noPredicate=True,noExpression=True,columns=[VERSION_COLUMN])]
  for name,kind,function,body in [(BEFORE_TRIGGER,23,'before_write',function_bodies(POLICY)[0]),(AFTER_TRIGGER,29,'after_write',function_bodies(POLICY)[1])]:
   result['triggers'].append(dict(name=name,type=kind,enabled='A',argsHex=(TABLE.primary_key.encode()+bytes([0])).hex(),noCondition=True,noColumns=True,functionSchema=POLICY.namespace,function=function,body=body,owner='owner',securityDefiner=True,returnType=2279,volatile='v',parallel='u',argCount=0,settings=['search_path=pg_catalog, pg_temp','standard_conforming_strings=on']))
 return result

def sidecar():
 return {'namespace':POLICY.namespace,'owner':'owner','objects':[dict(name=n,kind=k,owner='owner')for n,k in {'scope':'r','effects':'r','scope_pkey':'i','effects_pkey':'i','versions':'S'}.items()],'nonOwnerGrants':[],'ownerMembers':[],'sequence':dict(type=20,start=1,increment=1,minimum=1,maximum=9223372036854775807,cache=1,cycle=False),'functionCount':2}

class ContractTests(unittest.TestCase):
 def test_valid_components(self):
  self.assertEqual(verify_environment(POLICY,environment()),'owner');self.assertEqual(verify_table_catalog(TABLE,POLICY,'owner',catalog()),17000);self.assertEqual(verify_table_catalog(TABLE,POLICY,'owner',catalog(True),installed=True),17000);verify_source_catalog(POLICY,'owner',sidecar())
 def test_explicit_opt_in_precedes_connection_or_filesystem_access(self):
  class Bomb:
   def __getattr__(self,name):raise AssertionError('Connection touched')
  with self.assertRaises(ValueError):install_configured_source(Bomb(),'not-created',CONFIG,POLICY)
 def test_policy_validates_identifier_and_budgets(self):
  for namespace in ('public','mtw_source_\x00','mtw_source_'+('x'*64)):
   with self.subTest(namespace=namespace),self.assertRaises(ValueError):SourceInstallPolicy(namespace,('writer',))
  for writers in ([],(),('writer','writer')):
   with self.subTest(writers=writers),self.assertRaises(ValueError):SourceInstallPolicy('mtw_source_x',writers)
  for n in (0,16385,-1,True):
   with self.subTest(n=n),self.assertRaises(ValueError):SourceInstallPolicy('mtw_source_x',('writer',),max_initial_rows=n)
 def test_role_bypass_capabilities_are_individually_rejected(self):
  for field in ('superuser','createRole','createDb','replication','bypassRls','ownerMembership','privilegedMembership','canSetReplicationRole'):
   with self.subTest(field=field),self.assertRaises(SourceInstallError):
    e=environment();e['writers'][0][field]=True;verify_environment(POLICY,e)
 def test_owner_login_and_superuser_are_rejected(self):
  for field in ('superuser','login','createRole','replication','bypassRls'):
   with self.subTest(field=field),self.assertRaises(SourceInstallError):
    e=environment();e['ownerRole'][field]=True;verify_environment(POLICY,e)
 def test_missing_writer_and_encoding_mismatch_are_rejected(self):
  for name,value in [('writers',[]),('serverEncoding','LATIN1'),('clientEncoding','LATIN1'),('serverVersionNum','190000'),('standardConformingStrings','off')]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):e=environment();e[name]=value;verify_environment(POLICY,e)
 def test_existing_event_trigger_cannot_silently_rewrite_installation_ddl(self):
  e=environment();e['eventTriggers']=['unreviewed_ddl_hook']
  with self.assertRaises(SourceInstallError):verify_environment(POLICY,e)
 def test_nonheap_or_nonowner_table_rejected(self):
  for name,value in [('owner','other'),('kind','v'),('persistence','u'),('rls',True),('forceRls',True),('inherits',True),('rules',True)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog();c[name]=value;verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_oid_json_strings_cannot_masquerade_as_numeric_catalog_ids(self):
  c=catalog();c['oid']='17000'
  with self.assertRaises(SourceInstallError):verify_table_catalog(TABLE,POLICY,'owner',c)
  c=catalog();c['columns'][0]['oid']='20'
  with self.assertRaises(SourceInstallError):verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_missing_extra_reordered_business_columns_rejected(self):
  for change in ('missing','extra','order'):
   with self.subTest(change=change),self.assertRaises(SourceInstallError):
    c=catalog()
    if change=='missing':c['columns'].pop()
    elif change=='extra':c['columns'].append(copy.deepcopy(c['columns'][0]))
    else:c['columns'].reverse()
    verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_column_domain_array_generated_or_identity_rejected(self):
  for name,value in [('oid',2950),('typeKind','d'),('typeSchema','evil'),('elementType',20),('generated','s'),('identity','a')]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog();c['columns'][0][name]=value;verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_text_non_c_or_nondeterministic_collation_rejected(self):
  for name,value in [('collation','default'),('collationSchema','evil'),('collationDeterministic',False)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog();c['columns'][2][name]=value;verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_composite_deferred_missing_primary_key_rejected(self):
  for change in ('missing','composite','deferred','invalid'):
   with self.subTest(change=change),self.assertRaises(SourceInstallError):
    c=catalog()
    if change=='missing':c['primaryKeys']=[]
    elif change=='composite':c['primaryKeys'][0]['keys']=2
    elif change=='deferred':c['primaryKeys'][0]['immediate']=False
    else:c['primaryKeys'][0]['valid']=False
    verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_preexisting_user_trigger_rejected(self):
  c=catalog();c['triggers']=[{}]
  with self.assertRaises(SourceInstallError):verify_table_catalog(TABLE,POLICY,'owner',c)
 def test_metadata_column_type_nullability_default_rejected(self):
  for name,value in [('oid',25),('notNull',False),('generated','s'),('identity','a'),('default','1')]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog(True);c['columns'][-1][name]=value;verify_table_catalog(TABLE,POLICY,'owner',c,installed=True)
 def test_version_unique_index_must_not_be_partial_or_expression(self):
  for name,value in [('valid',False),('ready',False),('immediate',False),('noPredicate',False),('noExpression',False),('keys',2)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog(True);c['uniqueIndexes'][0][name]=value;verify_table_catalog(TABLE,POLICY,'owner',c,installed=True)
 def test_each_trigger_identity_and_scope_is_bound(self):
  for name,value in [('type',31),('enabled','D'),('argsHex','00'),('noCondition',False),('noColumns',False),('functionSchema','public'),('function','other'),('owner','other'),('body','BEGIN RETURN NULL; END'),('securityDefiner',False),('returnType',25),('volatile','s'),('parallel','s'),('argCount',1)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=catalog(True);c['triggers'][0][name]=value;verify_table_catalog(TABLE,POLICY,'owner',c,installed=True)
 def test_search_path_and_function_string_rules_are_bound(self):
  for settings in ([],['search_path=public'],['search_path=pg_catalog,pg_temp'],['search_path=pg_catalog,evil','standard_conforming_strings=on'],['search_path=pg_catalog,pg_temp','standard_conforming_strings=off']):
   with self.subTest(settings=settings),self.assertRaises(SourceInstallError):c=catalog(True);c['triggers'][0]['settings']=settings;verify_table_catalog(TABLE,POLICY,'owner',c,installed=True)
 def test_sidecar_grants_or_owner_membership_rejected(self):
  for field in ('nonOwnerGrants','ownerMembers'):
   with self.subTest(field=field),self.assertRaises(SourceInstallError):c=sidecar();c[field]=['writer'];verify_source_catalog(POLICY,'owner',c)
 def test_sidecar_owner_object_count_and_functions_rejected(self):
  for name,value in [('namespace','other'),('owner','other'),('objects',[]),('functionCount',3)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=sidecar();c[name]=value;verify_source_catalog(POLICY,'owner',c)
 def test_sequence_cycle_or_resettable_shape_rejected(self):
  for name,value in [('type',23),('cycle',True),('increment',2),('minimum',0),('cache',32)]:
   with self.subTest(name=name),self.assertRaises(SourceInstallError):c=sidecar();c['sequence'][name]=value;verify_source_catalog(POLICY,'owner',c)
 def test_all_business_names_are_quoted_without_fixed_table_templates(self):
  ddl=installation_ddl(CONFIG,POLICY)
  self.assertTrue(any('"App.X"."Records Space"'in sql for sql in ddl));self.assertTrue(any("'Key ID'"in sql for sql in ddl));self.assertFalse(any(re.match(r'^CREATE\s+(?:SCHEMA|TABLE|SEQUENCE|(?:UNIQUE\s+)?INDEX|FUNCTION)\s+IF\s+NOT\s+EXISTS\b',sql)for sql in ddl))
 def test_sequence_regclass_literal_quotes_are_escaped(self):
  policy=SourceInstallPolicy("mtw_source_quote'\\x",("writer'role",));before,after=function_bodies(policy)
  expected=literal(identifier(policy.namespace)+'.versions')
  self.assertIn('pg_catalog.nextval('+expected+'::pg_catalog.regclass)',before);self.assertIn(expected,after)
  self.assertIn("writer''role",before)
 def test_only_after_trigger_records_installed_effects(self):
  before,after=function_bodies(POLICY);self.assertNotIn('INSERT INTO',before);self.assertIn('INSERT INTO',after)
  self.assertNotIn('pg_current_xact_id',before);self.assertIn('pg_current_xact_id',after)
 def test_dml_trigger_uses_original_login_and_explicit_relation_scope(self):
  for body in function_bodies(POLICY):self.assertIn('SESSION_USER',body);self.assertIn('relation_oid=TG_RELID',body);self.assertIn('primary_key=TG_ARGV[0]',body)
 def test_writer_login_comparison_does_not_use_database_default_collation(self):
  for body in function_bodies(POLICY):self.assertIn('SESSION_USER::text COLLATE pg_catalog."C"',body)
 def test_no_business_reads_or_row_sql_templates_in_installation_plan(self):
  ddl=installation_ddl(CONFIG,POLICY);self.assertFalse(any(sql.startswith('SELECT ')for sql in ddl));self.assertFalse(any('RETURNING'in sql for sql in ddl))

class _Native:
 def __init__(self,rows,tag):self.rows=rows;self.nfields=1 if rows is not None else 0;self.ntuples=len(rows or[]);self.status=2 if self.nfields else 1;self.command_status=tag.encode('ascii')
 def get_value(self,row,col):return self.rows[row][0].encode('utf8')
 def ftype(self,col):return 25
 def fformat(self,col):return 0
class _Cursor:
 def __init__(self,rows=None,tag='OK',decoder_tamper=False):self.pgresult=_Native(rows,tag);self.rows=rows or[];self.decoder_tamper=decoder_tamper
 def fetchall(self):return [("{}",)]if self.decoder_tamper else self.rows
class _ControlConnection:
 autocommit=True
 def __init__(self,rows=1,commit_tag='COMMIT',fail_sql=None):
  self.info=types.SimpleNamespace(transaction_status=0);self.rows=rows;self.commit_tag=commit_tag;self.fail_sql=fail_sql;self.calls=[];self.rollback_called=False;self.installed=False;self.scope=[];self.committed=False
 def execute(self,sql,params=None):
  from . import configured_source as module
  self.calls.append((sql,params))
  if self.fail_sql and self.fail_sql in sql:raise self.failure
  if sql=='BEGIN':self.info.transaction_status=2;return _Cursor(tag='BEGIN')
  if sql.startswith('LOCK TABLE'):return _Cursor(tag='LOCK TABLE')
  if sql=='COMMIT':self.info.transaction_status=0;self.committed=self.commit_tag=='COMMIT';return _Cursor(tag=self.commit_tag)
  values=None
  if sql==module.ENVIRONMENT_SQL:values=[environment()]
  elif sql==module.TABLE_CATALOG_SQL:values=[catalog(self.installed)]
  elif sql==module.LOCKS_SQL:values=[{'pid':1234,'locks':[{'relation':17000,'mode':'AccessExclusiveLock','granted':True}]}]
  elif sql==module.PERMISSIONS_SQL:values=[dict(role='writer',table=params[1],trigger=False,truncate=False,ownerMembership=False)]
  elif sql==module.SOURCE_CATALOG_SQL:values=[sidecar()]
  elif sql.startswith("SELECT CASE WHEN"):
   values=[{'kind':'initial-row','row':{'Key ID':i,'flag':True,'text':'same',VERSION_COLUMN:i+1}}for i in range(self.rows)if i+1>params[0]][:1]
  elif sql.startswith("SELECT pg_catalog.jsonb_build_object('relation_oid',s.relation_oid::bigint"):values=self.scope
  elif 'count(*) FILTER' in sql:values=[{'rows':self.rows,'nonInitial':0}]
  if sql.startswith('INSERT INTO')and '.scope VALUES'in sql:self.scope=[dict(relation_oid=params[0],relation_schema=params[1],relation_table=params[2],primary_key=params[3],config_sha256=params[4])]
  if sql.startswith('ALTER TABLE')and'ADD COLUMN'in sql:self.installed=True
  return _Cursor([(json.dumps(x,ensure_ascii=False),)for x in values]if values is not None else None,tag='SELECT'if values is not None else'COMMAND')
 def rollback(self):self.rollback_called=True;self.info.transaction_status=0

class InstallationFlowTests(unittest.TestCase):
 def setUp(self):
  self.base=Path(os.environ.get('MTW_SOURCE_TEST_ROOT',str(Path.cwd()/'artifacts/configured-source-unit')));self.base.mkdir(parents=True,exist_ok=True)
 def output(self):return self.base/uuid.uuid4().hex
 def receipt(self,path):return json.loads((path/'receipt.json').read_text(encoding='utf8'))
 def test_native_control_flow_commits_but_never_promotes_source_facts(self):
  c=_ControlConnection();p=self.output();r=install_configured_source(c,p,CONFIG,POLICY,opt_in=True).to_dict()
  self.assertTrue(c.committed);self.assertTrue(r['catalogVerified']);self.assertTrue(r['initialSnapshotVerified']);self.assertTrue(r['actualCommitConfirmed'])
  for key in ('sourceFactsProduced','sourceAuthenticated','moonbitCatalogVerified','writerWindowVerified','driverFetchVerified'):self.assertFalse(r[key])
  self.assertTrue(r['log']['sealed']);self.assertEqual(r['initialRows'],1)
 def test_initial_snapshot_pages_beyond_256_and_has_no_eight_key_limit(self):
  c=_ControlConnection(rows=300);r=install_configured_source(c,self.output(),CONFIG,POLICY,opt_in=True).to_dict()
  self.assertEqual(r['initialRows'],300);self.assertEqual(sum(sql.startswith('SELECT CASE WHEN')for sql,_ in c.calls),301)
 def test_initial_snapshot_budget_failure_rolls_back_not_truncates(self):
  c=_ControlConnection(rows=3);p=self.output();policy=SourceInstallPolicy(POLICY.namespace,POLICY.writers,max_initial_rows=2)
  with self.assertRaises(SourceInstallError):install_configured_source(c,p,CONFIG,policy,opt_in=True)
  r=self.receipt(p);self.assertTrue(c.rollback_called);self.assertFalse(c.committed);self.assertFalse(r['catalogVerified']);self.assertFalse(r['sourceFactsProduced'])
 def test_commit_request_with_rollback_response_is_not_confirmation(self):
  c=_ControlConnection(commit_tag='ROLLBACK');p=self.output()
  with self.assertRaises(SourceInstallError):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  r=self.receipt(p);self.assertFalse(r['actualCommitConfirmed']);self.assertFalse(r['catalogVerified']);self.assertFalse(r['sourceFactsProduced'])
 def test_control_exception_retains_original_object_and_records_request(self):
  c=_ControlConnection(fail_sql='CREATE SEQUENCE');error=RuntimeError('original control exception');c.failure=error;p=self.output()
  with self.assertRaises(RuntimeError)as caught:install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertIs(caught.exception,error);self.assertTrue(c.rollback_called)
  log=[json.loads(line)for line in (p/'source-install.jsonl').read_text(encoding='utf8').splitlines()]
  self.assertTrue(any(x['kind']=='source-control-request'and'CREATE SEQUENCE'in x['sql']for x in log));self.assertTrue(any(x['kind']=='source-control-error'for x in log))
 def test_control_snapshot_decoder_cannot_replace_native_catalog_values(self):
  from . import configured_source as module
  class DecoderTampered(_ControlConnection):
   def execute(self,sql,params=None):
    cursor=super().execute(sql,params)
    if sql==module.ENVIRONMENT_SQL:cursor.decoder_tamper=True
    return cursor
  c=DecoderTampered();p=self.output()
  with self.assertRaisesRegex(SourceInstallError,'Decoded catalog'):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertTrue(c.rollback_called);self.assertFalse(self.receipt(p)['sourceFactsProduced'])
 def test_incomplete_log_after_commit_returns_no_confirmed_installation_object(self):
  from . import configured_source as module
  original=module._LifecycleLog.append
  def append(log,item):
   if item.get('kind')=='source-control'and item.get('queryId')=='installation-commit':raise OSError('disk full after commit')
   return original(log,item)
  c=_ControlConnection();p=self.output()
  with patch.object(module._LifecycleLog,'append',append),self.assertRaises(OSError):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertTrue(c.committed);r=self.receipt(p);self.assertFalse(r['actualCommitConfirmed']);self.assertFalse(r['sourceFactsProduced']);self.assertIn('inspect-owned-schema-before-any-retry',r['gaps'])
 def test_busy_or_non_autocommit_control_rejected_before_output(self):
  for mode in ('busy','auto'):
   c=_ControlConnection();p=self.output()
   if mode=='busy':c.info.transaction_status=2
   else:c.autocommit=False
   with self.subTest(mode=mode),self.assertRaises(ValueError):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
   self.assertEqual(c.calls,[]);self.assertFalse(p.exists())
 def test_oversized_row_marker_aborts_instead_of_accepting_a_partial_snapshot(self):
  class Oversized(_ControlConnection):
   def execute(self,sql,params=None):
    cursor=super().execute(sql,params)
    if sql.startswith('SELECT CASE WHEN'):return _Cursor([(json.dumps({'kind':'initial-row-budget'}),)],tag='SELECT')
    return cursor
  c=Oversized();p=self.output()
  with self.assertRaisesRegex(SourceInstallError,'snapshot bound'):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertTrue(c.rollback_called);self.assertFalse(c.committed);self.assertFalse(self.receipt(p)['initialSnapshotVerified'])
 def test_source_transaction_needs_actual_begin_acknowledgment(self):
  class WrongBegin(_ControlConnection):
   def execute(self,sql,params=None):
    c=super().execute(sql,params)
    if sql=='BEGIN':c.pgresult.command_status=b'COMMAND'
    return c
  c=WrongBegin();p=self.output()
  with self.assertRaisesRegex(SourceInstallError,'not acknowledged'):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertFalse(c.committed);self.assertFalse(self.receipt(p)['sourceFactsProduced'])
 def test_missing_actual_lock_catalog_cannot_confirm_initialization(self):
  from . import configured_source as module
  class MissingLock(_ControlConnection):
   def execute(self,sql,params=None):
    c=super().execute(sql,params)
    if sql==module.LOCKS_SQL:return _Cursor([(json.dumps({'pid':1234,'locks':[]}),)],tag='SELECT')
    return c
  c=MissingLock();p=self.output()
  with self.assertRaisesRegex(SourceInstallError,'lock inventory'):install_configured_source(c,p,CONFIG,POLICY,opt_in=True)
  self.assertFalse(c.committed);self.assertFalse(self.receipt(p)['initialSnapshotVerified'])
 def test_installation_result_getter_is_detached(self):
  r=install_configured_source(_ControlConnection(),self.output(),CONFIG,POLICY,opt_in=True);one=r.to_dict();one['sourceFactsProduced']=True
  self.assertFalse(r.to_dict()['sourceFactsProduced'])

if __name__=='__main__':unittest.main(verbosity=2)
