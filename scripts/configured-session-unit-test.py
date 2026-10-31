"""Pure producer/delegation checks; no database, driver call or MoonBit build."""
from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.configured_sql import SQLCaptureConfig,TableConfig,ColumnConfig
from moontxnwitness_capture.configured_source import SourceInstallPolicy,VERSION_COLUMN
from moontxnwitness_capture import configured_session as m


def config():
 return SQLCaptureConfig((TableConfig('alpha','thing','key',(ColumnConfig('key','int64'),ColumnConfig('value','bool'))),),default_schema='alpha')

class FakeObserver:
 def __init__(self,path,capture,**kwargs):
  self.path=Path(path);self.path.mkdir();self.capture=capture;self.kwargs=kwargs;self.closed=False;self.calls=[]
 def close(self,**kwargs):self.calls.append(('close',kwargs));self.closed=True;(self.path/'lifecycle.jsonl').write_text('{"kind":"synthetic-unit-log"}\n',encoding='utf-8',newline='\n')
 def export_diagnostic(self,path):
  assert self.closed
  text='{"events":[],"gaps":[{"code":"synthetic-unit-only"}]}\n';Path(path).write_text(text,encoding='utf-8',newline='\n')
  return {'sha256':hashlib.sha256(text.encode()).hexdigest(),'sourceFactsProduced':False}
 def psycopg_factory(self,factory,**kwargs):self.calls.append(('factory',factory,kwargs));return factory
 def attach_engine(self,engine):self.calls.append(('engine',engine))
 def wrap(self,raw):self.calls.append(('sync',raw));return raw
 def wrap_async(self,raw):self.calls.append(('async',raw));return raw

class Tests(unittest.TestCase):
 def setUp(self):
  base=ROOT/'artifacts/configured-session-unit-temp';base.mkdir(parents=True,exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def session(self,**kwargs):
  with patch.object(m,'ConfiguredInstrumentation',FakeObserver):return m.ConfiguredDiagnosticSession(self.root/'attempt',config(),**kwargs)
 def test_default_construction_has_no_database_or_ddl(self):
  with patch.object(m,'install_configured_source',side_effect=AssertionError('DDL called')):
   session=self.session();self.assertIs(session.capture_config,session.config);self.assertEqual(session.observer.kwargs['stored_columns'],())
 def test_local_factory_delegates_without_global_replacement(self):
  session=self.session();factory=lambda:None;self.assertIs(session.psycopg_factory(factory),factory);self.assertEqual(session.observer.calls[-1],('factory',factory,{'asynchronous':False}))
 def test_async_factory_preserves_mode(self):
  session=self.session();factory=lambda:None;session.psycopg_factory(factory,asynchronous=True);self.assertTrue(session.observer.calls[-1][2]['asynchronous'])
 def test_sync_and_async_connection_ownership(self):
  session=self.session();raw=object();self.assertIs(session.wrap_connection(raw),raw);self.assertIs(session.wrap_connection(raw,asynchronous=True),raw);self.assertEqual([x[0]for x in session.observer.calls],['sync','async'])
 def test_engine_installation_delegates_before_borrow(self):
  session=self.session();engine=object();self.assertIs(session.instrument_engine(engine),session);self.assertEqual(session.observer.calls[-1],('engine',engine))
 def test_augmentation_does_not_mutate_three_arbitrary_structures(self):
  configs=json.loads((ROOT/'fixtures/source-components-v4/config.json').read_text(encoding='utf-8'));c=SQLCaptureConfig.from_json(json.dumps(configs));before=m.canonical(c.to_dict());a=m.augmented_source_config(c)
  self.assertEqual([len(t.columns)for t in a.tables],[5,4,7]);self.assertEqual(m.canonical(c.to_dict()),before);self.assertNotEqual(a.sha256,c.sha256)
 def test_reserved_column_collision_fails_before_ddl(self):
  c=SQLCaptureConfig((TableConfig('s','t','k',(ColumnConfig('k','int64'),ColumnConfig(VERSION_COLUMN,'int64'))),))
  with self.assertRaises(ValueError):m.augmented_source_config(c)
 def test_column_capacity_checked_before_ddl(self):
  c=SQLCaptureConfig((TableConfig('s','t','k0',tuple(ColumnConfig('k'+str(i),'int64')for i in range(128))),))
  with self.assertRaises(ValueError):m.augmented_source_config(c)
 def test_seal_preserves_raw_text_and_all_authority_flags_false(self):
  session=self.session();bundle=session.seal();value=json.loads(bundle.read_text(encoding='utf-8'));receipt=json.loads((bundle.parent/'session-receipt.json').read_text())
  self.assertEqual(value['lifecycleText'],'{"kind":"synthetic-unit-log"}\n');self.assertEqual(value['sourceInputsText'],'null');self.assertEqual(session.observer.calls[-1],('close',{}))
  for key in ['sourceFactsProduced','writerWindowVerified','sourceAuthenticated','serverInstanceIdentityAuthenticated','isolationModelChecked','isolationAnalysisReady']:self.assertIs(receipt[key],False)
  self.assertEqual(receipt['bundleSha256'],hashlib.sha256(bundle.read_bytes()).hexdigest())
 def test_repeat_seal_cannot_overwrite_original_bundle(self):
  s=self.session();target=s.seal();before=target.read_bytes()
  with self.assertRaises(ValueError):s.seal()
  self.assertEqual(target.read_bytes(),before)
 def test_original_file_bounds_do_not_truncate(self):
  p=self.root/'raw';p.write_bytes(b'1234')
  with self.assertRaises(ValueError):m.read_text(p,3)
  self.assertEqual(p.read_bytes(),b'1234')
 def test_new_output_cannot_replace_existing_file(self):
  p=self.root/'out';p.write_text('old')
  with self.assertRaises(FileExistsError):m.write_new(p,'new')
  self.assertEqual(p.read_text(),'old')
 def test_source_context_is_original_and_caller_asserted(self):
  a=self.root/'source';a.mkdir();raw='{"seq":1}\n';(a/'source-install.jsonl').write_text(raw,encoding='utf-8',newline='\n');(a/'receipt.json').write_text('{"environment":{"databaseOid":5},"sourceFactsProduced":true}')
  policy=SourceInstallPolicy('mtw_source_unit',('writer',));context=m.InstallationInputs.from_attempt(a,policy)
  self.assertEqual(context.log_text,raw);self.assertEqual(json.loads(context.context_text)['format'],'caller-asserted-installation-epoch/v1');self.assertEqual(json.loads(context.context_text)['installationLogSha256'],hashlib.sha256(raw.encode()).hexdigest())
 def test_source_receipt_missing_database_oid_cannot_be_repaired(self):
  a=self.root/'source';a.mkdir();(a/'source-install.jsonl').write_text('{}\n');(a/'receipt.json').write_text('{}')
  with self.assertRaises(ValueError):m.InstallationInputs.from_attempt(a,SourceInstallPolicy('mtw_source_unit',('writer',)))
 def test_source_install_requires_explicit_opt_in_before_any_connection_read(self):
  connection=Mock();policy=SourceInstallPolicy('mtw_source_unit',('writer',))
  with self.assertRaises(ValueError):m.install_and_capture_initial_reads(connection,self.root/'out',config(),policy,(('SELECT key FROM alpha.thing',None),))
  self.assertEqual(connection.mock_calls,[])
 def test_async_installation_controller_rejected_before_ddl(self):
  class Parser:
   def __init__(self,_config):pass
   def recognize(self,_sql):return self
   operation='select'
   def bind(self,_params):return ()
  async def commit():pass
  connection=Mock();connection.commit=commit
  with patch.object(m,'ConfiguredSQLParser',Parser),patch.object(m,'install_configured_source',side_effect=AssertionError('DDL executed')),self.assertRaisesRegex(ValueError,'synchronous'):
   m.install_and_capture_initial_reads(connection,self.root/'out',config(),SourceInstallPolicy('mtw_source_unit',('writer',)),(('SELECT key FROM alpha.thing',None),),opt_in=True)
 def test_source_input_must_be_original_typed_context(self):
  with patch.object(m,'ConfiguredInstrumentation',FakeObserver),self.assertRaises(ValueError):m.ConfiguredDiagnosticSession(self.root/'attempt',config(),installation={'valid':True})
 def test_whole_session_write_failure_does_not_mark_sealed(self):
  session=self.session()
  with patch.object(m,'write_new',side_effect=OSError('disk-full')),self.assertRaises(OSError):session.seal()
  self.assertFalse(session._sealed);self.assertTrue((session.output/'capture/lifecycle.jsonl').exists())

if __name__=='__main__':unittest.main()
