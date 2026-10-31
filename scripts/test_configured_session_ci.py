"""Owned-CI startup and retained diagnostic boundaries; never connect to SQL."""
import contextlib, hashlib, importlib.util, io, json, os, subprocess, sys, tempfile, types, unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('configured_ci_controller',ROOT/'scripts/configured-session-ci-postgres.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)

class ControllerBoundaries(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/configured-ci-unit';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.out=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def completed(self,code=2,stdout=b'',stderr=b''):
        return subprocess.CompletedProcess([],code,stdout,stderr)
    def test_original_ci_namespace_is_rejected_before_parser_or_connection(self):
        with self.assertRaisesRegex(ValueError,'Explicit private mtw_source_'):
            controller.SourceInstallPolicy('mtw_cs_source_0123456789ab',('mtw_cs_writer_0123456789ab',),4096,8388608)
    def test_actual_ci_policy_uses_validated_private_prefix(self):
        policy=controller.source_policy('0123456789ab','mtw_cs_writer_0123456789ab')
        self.assertEqual(policy.namespace,'mtw_source_cs_0123456789ab');self.assertEqual(policy.writers,('mtw_cs_writer_0123456789ab',))
        self.assertEqual(policy.max_initial_rows,4096);self.assertEqual(policy.max_log_bytes,8388608)
    def test_invalid_fixture_token_cannot_change_namespace_or_execute_sql(self):
        for value in ['','ABCDEF012345','../../x','0123456789ab;DROP ROLE x']:
            with self.subTest(value=value),self.assertRaises(ValueError):controller.source_policy(value,'writer')
    def test_three_original_table_shapes_keep_pk_type_and_explicit_source_column(self):
        config=controller.SQLCaptureConfig.from_json((ROOT/'examples/configured-session/config.json').read_text('utf8'))
        before=config.to_dict();keys=[1,'feature-a',1]
        for table,key in zip(config.tables,keys):
            result=controller.initial_request(table,key)
            fields=','.join(controller.identifier(c.name) for c in table.columns)+','+controller.identifier(controller.VERSION_COLUMN)
            self.assertEqual(result,{'sql':'SELECT '+fields+' FROM '+controller.identifier(table.schema)+'.'+controller.identifier(table.table)+' WHERE '+controller.identifier(table.primary_key)+'=%s','parameters':[key]})
        self.assertEqual(config.to_dict(),before)
    def test_dynamic_schema_request_does_not_rewrite_table_or_parameter(self):
        config=controller.SQLCaptureConfig.from_json((ROOT/'examples/configured-session/config.json').read_text('utf8'))
        table=replace(config.tables[1],schema='mtw_cs_0123456789ab_1')
        result=controller.initial_request(table,'feature-a')
        self.assertIn('FROM "mtw_cs_0123456789ab_1"."Flag.Store" WHERE "Feature Key"=%s',result['sql'])
        self.assertEqual(result['parameters'],['feature-a'])
    def test_failure_retains_exact_stream_bytes_and_independent_hashes(self):
        original=self.completed(stdout=b'raw\x00stdout',stderr=b'raw\xffstderr')
        result=controller.retain_controller_result(self.out,original)
        for field,raw in [('stdout',original.stdout),('stderr',original.stderr)]:
            row=result[field];self.assertEqual((self.out/row['path']).read_bytes(),raw);self.assertEqual(row['bytes'],len(raw));self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(result['sourceFactsProduced']);self.assertFalse(result['isolationAnalysisReady'])
    def test_original_namespace_traceback_has_actionable_safe_reason(self):
        result=controller.retain_controller_result(self.out,self.completed(stderr=b'Traceback (most recent call last):\nValueError: Explicit private mtw_source_* namespace required\n'))
        self.assertEqual(result['controllerErrorClass'],'ValueError');self.assertEqual(result['reasonCode'],'invalid-private-source-namespace')
    def test_exception_text_and_credentials_never_enter_console_diagnostic(self):
        raw=b'OperationalError: password=private-password DSN=postgres://user:secret@host/db\n'
        result=controller.retain_controller_result(self.out,self.completed(stderr=raw));text=json.dumps(result)
        for secret in ['private-password','postgres://','secret@host']:self.assertNotIn(secret,text)
        self.assertEqual(result['controllerErrorClass'],'OperationalError');self.assertEqual((self.out/'controller-stderr.json').read_bytes(),raw)
    def test_structured_driver_stage_is_kept_without_arbitrary_error_message(self):
        raw=json.dumps({'errorClass':'SourceInstallError','failedStage':'installation-and-original-initial-reads','message':'sensitive arbitrary text'}).encode()
        result=controller.retain_controller_result(self.out,self.completed(stderr=raw))
        self.assertEqual(result['controllerErrorClass'],'SourceInstallError');self.assertEqual(result['controllerFailedStage'],'installation-and-original-initial-reads');self.assertNotIn('sensitive',json.dumps(result))
    def test_malformed_or_unknown_structured_error_is_retained_but_not_trusted(self):
        result=controller.retain_controller_result(self.out,self.completed(stderr=b'{"errorClass":[],"failedStage":"password=hidden"}\n'))
        self.assertNotIn('controllerErrorClass',result);self.assertNotIn('controllerFailedStage',result)
    def test_missing_optional_parser_is_distinguishable_from_source_failure(self):
        result=controller.retain_controller_result(self.out,self.completed(stderr=b'moontxnwitness_capture.configured_sql.OptionalParserUnavailable: SQLGlot required\n'))
        self.assertEqual(result['reasonCode'],'optional-sql-parser-unavailable');self.assertEqual(result['controllerErrorClass'],'OptionalParserUnavailable')
    def test_timeout_retains_partial_output_and_does_not_claim_completion(self):
        result=controller.retain_controller_result(self.out,self.completed(code=124,stdout=b'partial output',stderr=b'partial error'),timed_out=True)
        self.assertTrue(result['timedOut']);self.assertEqual(result['exitCode'],124);self.assertEqual(result['reasonCode'],'timeout');self.assertFalse(result['isolationAnalysisReady'])
    def test_success_stream_is_retained_without_extra_authority(self):
        result=controller.retain_controller_result(self.out,self.completed(code=0,stdout=b'{"passed":true}\n'))
        self.assertEqual(result['exitCode'],0);self.assertFalse(result['timedOut']);self.assertFalse(result['sourceFactsProduced'])
    def test_repeated_diagnostic_cannot_replace_original_stream(self):
        controller.retain_controller_result(self.out,self.completed(stderr=b'original'))
        with self.assertRaises(FileExistsError):controller.retain_controller_result(self.out,self.completed(stderr=b'different'))
        self.assertEqual((self.out/'controller-stderr.json').read_bytes(),b'original')
    def test_invalid_policy_stops_actual_wrapper_before_connection_or_ddl(self):
        connection=Mock(side_effect=AssertionError('No SQL permitted'))
        fake_psycopg=types.SimpleNamespace(connect=connection);output=self.out/'attempt';stderr=io.StringIO()
        argv=['controller','--execute','--owned-database','--dsn-env','MTW_UNIT_DSN','--output',str(output)]
        with patch.dict(sys.modules,{'psycopg':fake_psycopg}),patch.dict(os.environ,{'MTW_UNIT_DSN':'password=private-password'}),patch.object(sys,'argv',argv),patch.object(controller,'source_policy',side_effect=ValueError('Original invalid namespace')),contextlib.redirect_stderr(stderr):
            self.assertEqual(controller.main(),2)
        connection.assert_not_called();self.assertNotIn('private-password',stderr.getvalue());self.assertFalse(json.loads((output/'failure.json').read_bytes())['passed'])
    def test_execution_requires_explicit_owned_database_before_output_or_connection(self):
        argv=['controller','--dsn-env','MTW_UNIT_DSN','--output',str(self.out/'not-created')]
        with patch.object(sys,'argv',argv),self.assertRaisesRegex(ValueError,'Explicit owned-database'):controller.main()
        self.assertFalse((self.out/'not-created').exists())
    def test_workflow_keeps_owned_attempt_and_runtime_material_upload_paths(self):
        workflow=(ROOT/'.github/workflows/postgres.yml').read_text('utf8')
        self.assertIn('verification/configured-session-v4/postgres-ci-*/',workflow)
        for path in ['verification/releases/*/postgres/','verification/provenance-presence/ci-*/','verification/postgres-ci-runtime/${{ github.run_id }}-${{ github.run_attempt }}/']:
            self.assertIn(path,workflow)

if __name__=='__main__':unittest.main()
