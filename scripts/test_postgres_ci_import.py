"""Synthetic transport/closure boundary tests; no SQL, network or compiler execution."""
import copy, hashlib, io, json, os, stat, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import import_postgres_ci_bundle as pg

ROOT=Path(__file__).resolve().parents[1]
REPO='HhWw96/moontxnwitness'
COMMIT='a'*40

def encode(v):return (json.dumps(v,sort_keys=True)+'\n').encode()
def fixture():
    compiler={'compiler':'v0.10.16+b1a0e846e','moon':'moon 0.1.test'}
    current={'version':'0.3.4','sourceSha256':pg.digest(b'moon source'),'toolchain':compiler,'coreSha256':pg.digest(b'windows core'),'captureCoreSha256':pg.digest(b'windows capture')}
    database={**current,'coreSha256':pg.digest(b'linux core'),'captureCoreSha256':pg.digest(b'linux capture')}
    shared={'src/core.mbt':pg.digest(b'moon source'),'integrations/python/capture.py':pg.digest(b'actual SQL adapter'),'fixtures/example.json':pg.digest(b'fixed fixture')}
    tested={**shared,'dist/core.mjs':current['coreSha256'],'dist/capture-core.mjs':current['captureCoreSha256'],'dist/build-manifest.json':pg.digest(encode(current))}
    observed={**shared,'dist/core.mjs':database['coreSha256'],'dist/capture-core.mjs':database['captureCoreSha256'],'dist/build-manifest.json':pg.digest(encode(database))}
    expected={'commit':COMMIT,'version':'0.3.4','buildManifest':current,'testedFileSha256':tested}
    run={'id':123,'run_attempt':2,'head_sha':COMMIT,'path':'.github/workflows/postgres.yml','repository':{'full_name':REPO},'status':'completed','conclusion':'success','event':'push','run_started_at':'2026-10-31T01:00:00Z'}
    prefix='verification/releases/0.3.4/postgres/'
    names=['capture.json','mini-history.json','mini-report.json','mini.capsule.json','reduction.json','rr-history.json','rr-report.json','rr.capsule.json','serial-history.json','serial-report.json','serial.capsule.json','sql-events.json','sql-events.jsonl']
    payload={prefix+n:encode({'syntheticTransportFixture':n}) for n in names}
    payload[prefix+'capture.json']=encode({'passed':True,'actualDatabaseExecution':True})
    payload[prefix+'receipt.json']=encode({'version':'0.3.4','passed':True,'actualDatabaseExecution':True,'status':'passed','files':{n:pg.digest(payload[prefix+n]) for n in names}})
    payload['verification/postgres-ci-source.json']=encode({'sourceCommit':COMMIT,'workflowCommit':COMMIT})
    binding=f"verification/postgres-ci-runtime/{run['id']}-{run['run_attempt']}/"
    for phase in ['before','after']:payload[binding+'postgres-ci-runtime-'+phase+'.json']=encode({'phase':phase,'sourceCommit':COMMIT,'buildManifest':database,'testedFileSha256':observed})
    payload['dist/core.mjs']=b'linux core';payload['dist/capture-core.mjs']=b'linux capture'
    return expected,run,payload

class Boundaries(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'artifacts/pg-import-unit';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
        self.expected,self.run,self.payload=fixture();self.prefix='verification/releases/0.3.4/postgres/'
    def tearDown(self):self.temp.cleanup()
    def archive(self,payload=None,entries=()):
        payload=self.payload if payload is None else payload;data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,raw in list(payload.items())+list(entries):
                info=zipfile.ZipInfo(name);info.filename=name;info.orig_filename=name;info.external_attr=(stat.S_IFREG|0o644)<<16;z.writestr(info,raw)
        raw=data.getvalue();path=self.root/'bundle.zip';path.write_bytes(raw)
        artifact={'id':7,'name':pg.ARTIFACT,'expired':False,'workflow_run':{'id':self.run['id'],'head_sha':self.run['head_sha']},'created_at':'2026-10-31T01:10:00Z','size_in_bytes':len(raw),'digest':'sha256:'+pg.digest(raw)}
        return path,artifact
    def validate(self,payload=None,entries=(),run=None,artifact_change=None,expected=None,pr_head=None):
        path,a=self.archive(payload,entries)
        if artifact_change:a.update(artifact_change)
        return pg.validate_archive(path,run or self.run,a,expected or self.expected,REPO,pr_head)
    def mutate_binding(self,payload,phase,fn):
        name=f"verification/postgres-ci-runtime/123-2/postgres-ci-runtime-{phase}.json";v=pg.json_bytes(payload[name]);fn(v);payload[name]=encode(v)
    def installed(self):
        path,artifact=self.archive();files,comparison=pg.validate_archive(path,self.run,artifact,self.expected,REPO)
        record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':comparison,'sqlExecutedByImporter':False}
        pg.install(self.root,files,record);return record,files

    def test_original_fourteen_packet_files_and_three_bindings_are_preserved(self):
        files,comparison=self.validate();self.assertEqual(len(files),17)
        for name,raw in self.payload.items():
            if name.startswith(self.prefix):self.assertEqual(files[name],raw)
        self.assertFalse(comparison['runtimeBinaryIdentityClaimed']);self.assertFalse(comparison['coreBytesEqual'])
        self.assertEqual(comparison['sharedExecutableInputCount'],3)
    def test_cross_platform_difference_is_not_normalized_to_same_binary(self):
        _,c=self.validate();self.assertNotEqual(c['postgresBuildManifest']['coreSha256'],c['consumerBuildManifest']['coreSha256'])
        self.assertTrue(c['sourceVersionCompilerMatch'])
    def test_api_zip_digest_and_exact_length_are_required(self):
        for change in [{'digest':'sha256:'+'0'*64},{'size_in_bytes':1},{'digest':None}]:
            with self.subTest(change=change),self.assertRaises(pg.ImportFailure):self.validate(artifact_change=change)
    def test_expired_wrong_name_or_wrong_run_artifact_is_rejected(self):
        for change in [{'expired':True},{'name':'other'},{'workflow_run':{'id':999,'head_sha':COMMIT}}]:
            with self.subTest(change=change),self.assertRaises(pg.ImportFailure):self.validate(artifact_change=change)
    def test_previous_attempt_artifact_is_not_reused(self):
        with self.assertRaises(pg.ImportFailure):self.validate(artifact_change={'created_at':'2026-10-30T01:00:00Z'})
    def test_failed_pending_wrong_workflow_and_foreign_repo_are_rejected(self):
        for key,value in [('status','in_progress'),('conclusion','failure'),('path','.github/workflows/ci.yml'),('repository',{'full_name':'other/repo'})]:
            r=copy.deepcopy(self.run);r[key]=value
            with self.subTest(key=key),self.assertRaises(pg.ImportFailure):self.validate(run=r)
    def test_future_or_unrelated_head_is_rejected(self):
        r={**self.run,'head_sha':'b'*40}
        with self.assertRaises(pg.ImportFailure):self.validate(run=r)
    def test_pr_api_head_needs_the_exact_event_head_and_original_merge_source(self):
        pr='b'*40;r={**self.run,'head_sha':pr,'event':'pull_request'};path,a=self.archive();a['workflow_run']['head_sha']=pr
        files,_=pg.validate_archive(path,r,a,self.expected,REPO,pr);self.assertEqual(len(files),17)
        with self.assertRaises(pg.ImportFailure):pg.validate_archive(path,r,a,self.expected,REPO,'c'*40)
        payload=copy.deepcopy(self.payload);payload['verification/postgres-ci-source.json']=encode({'sourceCommit':pr})
        path,a=self.archive(payload);a['workflow_run']['head_sha']=pr
        with self.assertRaises(pg.ImportFailure):pg.validate_archive(path,r,a,self.expected,REPO,pr)
    def test_artifact_actual_source_must_match_checkout(self):
        p=copy.deepcopy(self.payload);p['verification/postgres-ci-source.json']=encode({'sourceCommit':'b'*40})
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_before_after_runtime_changes_are_rejected(self):
        p=copy.deepcopy(self.payload);self.mutate_binding(p,'after',lambda x:x['buildManifest'].update(coreSha256='0'*64))
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_before_after_source_map_changes_are_rejected(self):
        p=copy.deepcopy(self.payload);self.mutate_binding(p,'after',lambda x:x['testedFileSha256'].update({'integrations/python/capture.py':'0'*64}))
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_stable_but_wrong_sql_adapter_fingerprint_is_rejected(self):
        p=copy.deepcopy(self.payload)
        for phase in ['before','after']:self.mutate_binding(p,phase,lambda x:x['testedFileSha256'].update({'integrations/python/capture.py':'0'*64}))
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_extra_or_missing_current_fixture_is_rejected(self):
        e=copy.deepcopy(self.expected);e['testedFileSha256']['fixtures/new.json']='0'*64
        with self.assertRaises(pg.ImportFailure):self.validate(expected=e)
    def test_source_fingerprint_and_compiler_must_match(self):
        for key in ['sourceSha256','toolchain']:
            e=copy.deepcopy(self.expected);e['buildManifest'][key]='0'*64 if key=='sourceSha256' else {'compiler':'wrong'}
            with self.subTest(key=key),self.assertRaises(pg.ImportFailure):self.validate(expected=e)
    def test_actual_artifact_core_bytes_must_match_pg_bindings(self):
        p=copy.deepcopy(self.payload);p['dist/core.mjs']=b'false runtime'
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_missing_each_mandatory_original_file_is_rejected(self):
        for name in pg.MANDATORY:
            p=copy.deepcopy(self.payload);del p[self.prefix+name]
            with self.subTest(name=name),self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_every_original_thirteen_file_digest_is_checked(self):
        for name in ['sql-events.jsonl','reduction.json','serial-history.json','mini-report.json']:
            p=copy.deepcopy(self.payload);p[self.prefix+name]=b'tampered'
            with self.subTest(name=name),self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_unreferenced_packet_file_is_not_published(self):
        with self.assertRaises(pg.ImportFailure):self.validate(entries=[(self.prefix+'unreferenced.json',b'{}')])
    def test_failed_or_non_actual_receipt_is_not_promoted(self):
        for key,value in [('passed',False),('actualDatabaseExecution',False),('version','0.3.5')]:
            p=copy.deepcopy(self.payload);r=pg.json_bytes(p[self.prefix+'receipt.json']);r[key]=value;p[self.prefix+'receipt.json']=encode(r)
            with self.subTest(key=key),self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_rehashed_capture_failure_still_fails_actual_capture_rule(self):
        p=copy.deepcopy(self.payload);p[self.prefix+'capture.json']=encode({'passed':False,'actualDatabaseExecution':True});r=pg.json_bytes(p[self.prefix+'receipt.json']);r['files']['capture.json']=pg.digest(p[self.prefix+'capture.json']);p[self.prefix+'receipt.json']=encode(r)
        with self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_unsafe_packet_references_are_rejected(self):
        for name in ['../secret','a/b','C:/secret','x\\y']:
            p=copy.deepcopy(self.payload);r=pg.json_bytes(p[self.prefix+'receipt.json']);r['files'][name]='0'*64;p[self.prefix+'receipt.json']=encode(r)
            with self.subTest(name=name),self.assertRaises(pg.ImportFailure):self.validate(p)
    def test_zip_paths_and_case_collisions_are_rejected(self):
        for name in ['../escape','/absolute','x\\y','x//y','nul.txt','dist/CORE.MJS']:
            with self.subTest(name=name),self.assertRaises(pg.ImportFailure):self.validate(entries=[(name,b'bad')])
    def test_symlink_archive_member_is_rejected(self):
        path,a=self.archive()
        with zipfile.ZipFile(path,'a') as z:
            i=zipfile.ZipInfo('linked');i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,b'target')
        raw=path.read_bytes();a.update(size_in_bytes=len(raw),digest='sha256:'+pg.digest(raw))
        with self.assertRaises(pg.ImportFailure):pg.validate_archive(path,self.run,a,self.expected,REPO)
    def test_duplicate_json_members_include_unicode_escape_aliases(self):
        with self.assertRaises(pg.ImportFailure):pg.json_bytes(b'{"passed":true,"pa\\u0073sed":false}')
    def test_crc_corruption_is_not_hidden_by_a_new_api_digest(self):
        path,a=self.archive();raw=bytearray(path.read_bytes())
        with zipfile.ZipFile(path) as z:i=z.getinfo('dist/core.mjs');offset=i.header_offset+30+len(i.filename.encode())+len(i.extra)
        raw[offset]^=1;path.write_bytes(raw);a['digest']='sha256:'+pg.digest(raw)
        with self.assertRaises((pg.ImportFailure,zipfile.BadZipFile)):pg.validate_archive(path,self.run,a,self.expected,REPO)
    def test_declared_zip_budgets_reject_before_payload_processing(self):
        with patch.object(pg,'MAX_TOTAL',10),self.assertRaises(pg.ImportFailure):self.validate()
        with patch.object(pg,'MAX_ZIP',10),self.assertRaises(pg.ImportFailure):self.validate()
    def test_installed_inventory_is_narrow_and_rechecks_original_files(self):
        _,files=self.installed()
        with patch.object(pg,'checkout_identity',return_value=self.expected),patch.dict(os.environ,{},clear=True):
            result=pg.validated_postgres_import_files(self.root,'0.3.4');self.assertEqual(len(result),18)
            unrelated=self.root/'verification/unrelated-private.json';unrelated.write_text('PRIVATE');self.assertNotIn('verification/unrelated-private.json',result)
            (self.root/(self.prefix+'sql-events.jsonl')).write_bytes(b'changed')
            with self.assertRaises(pg.ImportFailure):pg.validated_postgres_import_files(self.root,'0.3.4')
    def test_no_import_record_does_not_authorize_ignored_files(self):
        self.assertEqual(pg.validated_postgres_import_files(self.root,'0.3.4'),{})
    def test_install_never_overwrites_existing_or_mixes_runs(self):
        path=self.root/(self.prefix+'capture.json');path.parent.mkdir(parents=True);path.write_bytes(b'ORIGINAL')
        _,a=self.archive();files,c=self.validate()
        with self.assertRaises(pg.ImportFailure):pg.install(self.root,files,{'version':'0.3.4'})
        self.assertEqual(path.read_bytes(),b'ORIGINAL')
    def test_foreign_import_destinations_are_rejected(self):
        with self.assertRaises(pg.ImportFailure):pg.install(self.root,{'verification/releases/0.3.5/postgres/receipt.json':b'{}'},{'version':'0.3.4'})
    def test_nul_delimiters_match_the_original_source_fingerprint(self):
        (self.root/'src').mkdir();(self.root/'moon.mod').write_bytes(b'module');(self.root/'src/a.mbt').write_bytes(b'code')
        h=hashlib.sha256();h.update(b'moon.mod\0module\0src/a.mbt\0code\0');self.assertEqual(pg.source_fingerprint(self.root),h.hexdigest())
    def test_cross_host_redirect_removes_authorization(self):
        import urllib.request
        request=urllib.request.Request('https://api.github.com/repos/o/r/actions/artifacts/1/zip',headers={'Authorization':'Bearer SECRET'})
        redirected=pg.SafeRedirect().redirect_request(request,None,302,'Found',{},'https://example.blob.core.windows.net/file?signature=x')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(pg.ImportFailure):pg.SafeRedirect().redirect_request(request,None,302,'Found',{},'http://example.com/file')

if __name__=='__main__':unittest.main(verbosity=2)
