"""Exact four compiled slots; all original76 import/reproduction checks remain."""
import copy,json,os,unittest
from pathlib import Path
from unittest.mock import patch
import import_postgres_ci_bundle as pg
import test_postgres_ci_reproduction as previous
from test_postgres_ci_import import encode,REPO,COMMIT

class ConfiguredRuntimeBoundaries(unittest.TestCase):
    setUp=previous.ReproductionBoundaries.setUp
    tearDown=previous.ReproductionBoundaries.tearDown
    archive=previous.ReproductionBoundaries.archive
    def configured(self):
        expected,run,original=previous.full_fixture()
        expected=json.loads(json.dumps(expected).replace('0.3.4','0.3.7'))
        payload={name.replace('0.3.4','0.3.7'):raw.replace(b'0.3.4',b'0.3.7') for name,raw in original.items()}
        source=self.root/'current';(source/'scripts').mkdir(parents=True,exist_ok=True);(source/'dist').mkdir(exist_ok=True)
        build='const configuredCores={'+','.join(json.dumps(k)+':'+json.dumps(v) for k,v in pg.CONFIGURED_SLOTS.items())+'};\n'
        (source/'scripts/build.mjs').write_text(build,'utf8',newline='\n');tested=expected['testedFileSha256'];tested['scripts/build.mjs']=pg.digest(build.encode())
        for bridge in pg.CONFIGURED_SLOTS.values():
            for leaf in ('moon.pkg','bridge.mbt'):
                name='src/'+bridge+'/'+leaf;path=source/name;path.parent.mkdir(parents=True,exist_ok=True);raw=('synthetic '+name+'\n').encode();path.write_bytes(raw);tested[name]=pg.digest(raw)
        expected['configuredRuntimeSource']=pg.configured_source_binding(source,tested);current=expected['buildManifest']
        binding='verification/postgres-ci-runtime/123-2/';database=pg.json_bytes(payload[binding+'postgres-ci-runtime-before.json'])['buildManifest'];current['configuredCoreSha256']={};database['configuredCoreSha256']={};current_files={}
        for name in pg.CONFIGURED_SLOTS:
            win=('synthetic WINDOWS '+name).encode();linux=('synthetic LINUX '+name).encode();(source/'dist'/name).write_bytes(win);payload['dist/'+name]=linux
            current['configuredCoreSha256'][name]=pg.digest(win);database['configuredCoreSha256'][name]=pg.digest(linux);tested['dist/'+name]=pg.digest(win);current_files[name]={'bytes':len(win),'sha256':pg.digest(win)}
        expected['configuredRuntimeFiles']=current_files
        for name,raw in [('core.mjs',b'windows core'),('capture-core.mjs',b'windows capture')]: (source/'dist'/name).write_bytes(raw)
        (source/'package.json').write_bytes(encode({'version':'0.3.7'}));(source/'dist/build-manifest.json').write_bytes(encode(current));tested['dist/build-manifest.json']=pg.digest(encode(current))
        pg_tested={**tested,'dist/core.mjs':database['coreSha256'],'dist/capture-core.mjs':database['captureCoreSha256'],'dist/build-manifest.json':pg.digest(encode(database)),**{'dist/'+n:h for n,h in database['configuredCoreSha256'].items()}}
        payload['dist/build-manifest.json']=encode(database)
        for phase in ('before','after'):
            name=binding+'postgres-ci-runtime-'+phase+'.json';value=pg.json_bytes(payload[name]);value['buildManifest']=database;value['testedFileSha256']=pg_tested;payload[name]=encode(value)
        name='verification/provenance-presence/ci-123-2/presence-receipt.json';presence=pg.json_bytes(payload[name]);presence['captureSource']['files']['dist/build-manifest.json']=pg_tested['dist/build-manifest.json'];payload[name]=encode(presence)
        return expected,run,payload,source
    def validate(self,expected,run,payload):
        self.run=run;path,artifact=self.archive(payload)
        return (*pg.validate_archive(path,run,artifact,expected,REPO,reproduction=True),artifact)
    def rejection(self,expected,run,payload):
        with self.assertRaises((pg.ImportFailure,KeyError)):self.validate(expected,run,payload)
    def mutate_pg(self,payload,fn):
        for phase in ('before','after'):
            name='verification/postgres-ci-runtime/123-2/postgres-ci-runtime-'+phase+'.json';value=pg.json_bytes(payload[name]);fn(value);payload[name]=encode(value)
    def identity(self,expected,source):
        def output(args,**kwargs):return COMMIT if args[0]=='git' else encode(expected['testedFileSha256'])
        with patch.object(pg.subprocess,'check_output',side_effect=output),patch.object(pg,'source_fingerprint',return_value=expected['buildManifest']['sourceSha256']):return pg.checkout_identity(source)
    def test_exact_four_declared_platform_outputs_are_raw_checked_and_retained(self):
        e,r,p,_=self.configured();files,c,_=self.validate(e,r,p);binding=c['configuredRuntimeBinding'];self.assertEqual(binding['slots'],pg.CONFIGURED_SLOTS);self.assertTrue(binding['actualPostgresBytesVerified']);self.assertTrue(all(v is False for v in binding['compiledBytesEqual'].values()))
        self.assertEqual(set(c['platformRuntimeExceptions']),{'dist/core.mjs','dist/capture-core.mjs','dist/build-manifest.json'}|{'dist/'+n for n in pg.CONFIGURED_SLOTS})
        for n in [*pg.CONFIGURED_SLOTS,'build-manifest.json']:self.assertEqual(files['verification/releases/0.3.7/postgres-ci-import/bound-runtimes/'+n],p['dist/'+n])
    def test_every_missing_actual_pg_slot_is_rejected(self):
        for n in pg.CONFIGURED_SLOTS:
            e,r,p,_=self.configured();del p['dist/'+n];self.rejection(e,r,p)
    def test_each_windows_raw_file_cannot_substitute_for_pg_raw_file(self):
        for n in pg.CONFIGURED_SLOTS:
            e,r,p,s=self.configured();p['dist/'+n]=(s/'dist'/n).read_bytes();self.rejection(e,r,p)
    def test_swapped_actual_pg_slot_is_rejected(self):
        e,r,p,_=self.configured();names=list(pg.CONFIGURED_SLOTS);p['dist/'+names[0]]=p['dist/'+names[1]];self.rejection(e,r,p)
    def test_actual_pg_manifest_bytes_and_tested_digest_are_required(self):
        for raw in [None,b'{}']:
            e,r,p,_=self.configured()
            if raw is None:del p['dist/build-manifest.json']
            else:p['dist/build-manifest.json']=raw
            self.rejection(e,r,p)
    def test_missing_and_extra_pg_manifest_slots_are_rejected(self):
        for extra in (False,True):
            e,r,p,_=self.configured()
            def change(v):
                if extra:v['buildManifest']['configuredCoreSha256']['unlisted.mjs']='0'*64
                else:v['buildManifest']['configuredCoreSha256'].pop(next(iter(pg.CONFIGURED_SLOTS)))
            self.mutate_pg(p,change);self.rejection(e,r,p)
    def test_missing_and_extra_current_manifest_slots_are_rejected(self):
        for extra in (False,True):
            e,r,p,_=self.configured()
            if extra:e['buildManifest']['configuredCoreSha256']['unlisted.mjs']='0'*64
            else:e['buildManifest']['configuredCoreSha256'].pop(next(iter(pg.CONFIGURED_SLOTS)))
            self.rejection(e,r,p)
    def test_fake_pg_sha_and_wrong_tested_runtime_are_rejected(self):
        for which in ('manifest','tested'):
            e,r,p,_=self.configured();name=next(iter(pg.CONFIGURED_SLOTS))
            self.mutate_pg(p,lambda v:v['buildManifest']['configuredCoreSha256'].update({name:'0'*64}) if which=='manifest' else v['testedFileSha256'].update({'dist/'+name:'0'*64}));self.rejection(e,r,p)
    def test_fake_current_file_sha_length_inventory_are_rejected(self):
        for change in ('sha','length','missing','extra'):
            e,r,p,_=self.configured();name=next(iter(pg.CONFIGURED_SLOTS))
            if change=='sha':e['configuredRuntimeFiles'][name]['sha256']='0'*64
            elif change=='length':e['configuredRuntimeFiles'][name]['bytes']=True
            elif change=='missing':del e['configuredRuntimeFiles'][name]
            else:e['configuredRuntimeFiles']['unknown.mjs']={'bytes':1,'sha256':'0'*64}
            self.rejection(e,r,p)
    def test_source_bridge_changed_on_pg_side_is_not_a_platform_exception(self):
        e,r,p,_=self.configured();name='src/configured_session_bridge/bridge.mbt';self.mutate_pg(p,lambda v:v['testedFileSha256'].update({name:'0'*64}));self.rejection(e,r,p)
    def test_build_script_changed_on_pg_side_is_rejected(self):
        e,r,p,_=self.configured();self.mutate_pg(p,lambda v:v['testedFileSha256'].update({'scripts/build.mjs':'0'*64}));self.rejection(e,r,p)
    def test_other_sql_or_fixture_source_difference_is_rejected(self):
        e,r,p,_=self.configured();self.mutate_pg(p,lambda v:v['testedFileSha256'].update({'fixtures/example.json':'0'*64}));self.rejection(e,r,p)
    def test_wrong_declared_mapping_and_profile_are_rejected(self):
        for field,value in [('slots',{'configured-session-core.mjs':'arbitrary_bridge'}),('algorithm','unknown'),('format','unknown')]:
            e,r,p,_=self.configured();e['configuredRuntimeSource'][field]=value;self.rejection(e,r,p)
    def test_missing_extra_or_forged_source_input_is_rejected(self):
        for change in ('missing','extra','sha'):
            e,r,p,_=self.configured();rows=e['configuredRuntimeSource']['sourceFiles'];name=next(iter(rows))
            if change=='missing':del rows[name]
            elif change=='extra':rows['src/arbitrary/bridge.mbt']={'bytes':1,'sha256':'0'*64}
            else:rows[name]['sha256']='0'*64
            self.rejection(e,r,p)
    def test_actual_current_identity_reads_all_four_files_and_sources(self):
        e,_,_,s=self.configured();identity=self.identity(e,s);self.assertEqual(identity['configuredRuntimeFiles'],e['configuredRuntimeFiles']);self.assertEqual(identity['configuredRuntimeSource'],e['configuredRuntimeSource'])
    def test_actual_current_identity_rejects_changed_runtime_bytes(self):
        for n in pg.CONFIGURED_SLOTS:
            e,_,_,s=self.configured();(s/'dist'/n).write_bytes(b'changed original current runtime')
            with self.assertRaises(pg.ImportFailure):self.identity(e,s)
    def test_actual_current_identity_rejects_changed_bridge_file(self):
        e,_,_,s=self.configured();(s/'src/configured_session_bridge/bridge.mbt').write_bytes(b'changed source bridge')
        with self.assertRaises(pg.ImportFailure):self.identity(e,s)
    def test_build_mapping_cannot_execute_or_select_another_bridge(self):
        e,_,_,s=self.configured();path=s/'scripts/build.mjs';raw=path.read_bytes().replace(b'configured_session_bridge',b'arbitrary_module_bridge');path.write_bytes(raw);e['testedFileSha256']['scripts/build.mjs']=pg.digest(raw)
        with self.assertRaises(pg.ImportFailure):pg.configured_source_binding(s,e['testedFileSha256'])
    def test_actual_current_identity_rejects_manifest_digest_mismatch(self):
        e,_,_,s=self.configured();(s/'dist/build-manifest.json').write_bytes(encode({**e['buildManifest'],'extra':'changed'}))
        with self.assertRaises(pg.ImportFailure):self.identity(e,s)
    def test_new_v3_installs_and_revalidates_all_original_raw_slots(self):
        e,r,p,_=self.configured();files,c,a=self.validate(e,r,p);target=self.root/'installed';target.mkdir();record={'version':'0.3.7','sourceCommit':COMMIT,'repository':REPO,'run':r,'artifact':a,'prHead':None,'comparison':c}
        installed=pg.install_reproduction(target,files,record);self.assertEqual(installed['format'],pg.CONFIGURED_FORMAT);self.assertEqual(installed['runtimeBindingAlgorithm'],pg.CONFIGURED_ALGORITHM)
        with patch.object(pg,'checkout_identity',return_value=e),patch.object(pg,'event_pr_head',return_value=None):
            inventory=pg.validated_ci_reproduction_files(target,'0.3.7');self.assertEqual(len(inventory),len(files)+1)
            (target/'verification/releases/0.3.7/postgres-ci-import/bound-runtimes/sql-fetch-core.mjs').write_bytes(b'changed retained source')
            with self.assertRaises(pg.ImportFailure):pg.validated_ci_reproduction_files(target,'0.3.7')
    def test_old_import_format_cannot_authorize_new_profile(self):
        e,r,p,_=self.configured();files,c,a=self.validate(e,r,p);target=self.root/'installed';target.mkdir();record={'version':'0.3.7','sourceCommit':COMMIT,'repository':REPO,'run':r,'artifact':a,'prHead':None,'comparison':c};pg.install_reproduction(target,files,record)
        index=target/'verification/releases/0.3.7/postgres-ci-import/receipt.json';v=pg.json_bytes(index.read_bytes());v['format']=pg.FULL_FORMAT;index.write_bytes(encode(v))
        with self.assertRaises(pg.ImportFailure):pg.validated_ci_reproduction_files(target,'0.3.7')
    def test_missing_installation_raw_slot_cannot_claim_v3(self):
        e,r,p,_=self.configured();files,c,a=self.validate(e,r,p);del files['verification/releases/0.3.7/postgres-ci-import/bound-runtimes/sql-fetch-core.mjs']
        with self.assertRaises(pg.ImportFailure):pg.install_reproduction(self.root/'installed',files,{'version':'0.3.7','sourceCommit':COMMIT,'run':r,'comparison':c})
    def test_actual_4c_projection_retains_each_distinct_original_and_failed_ci(self):
        path=Path(__file__).resolve().parents[1]/'fixtures/postgres-ci-import/configured-4c225-platform-runtime-projection.json';raw=path.read_bytes()
        self.assertEqual(pg.digest(raw),'4d331fd9e8568f6469d7f5635c8972513aa988c87e4348c1610b1a6b848d9a30');v=pg.json_bytes(raw)
        self.assertEqual(v['sourceCommit'],'4c2252ab13c30d46c336ef7b1363f7d207923b3b');self.assertEqual(v['slotMapping'],pg.CONFIGURED_SLOTS)
        self.assertEqual(v['windows']['runId'],41200247209);self.assertEqual(v['windows']['conclusion'],'failure');self.assertEqual(v['postgres']['runId'],41200247284);self.assertEqual(v['postgres']['conclusion'],'success')
        self.assertFalse(v['normalizationPerformed']);self.assertFalse(v['failedWindowsCIPromoted']);self.assertFalse(v['releaseReady'])
        self.assertEqual(v['postgres']['artifact'],{'id':13042283040,'size_in_bytes':51865651,'digest':'sha256:e984302701b2e4696afe421ee4a576078e5cd401d3eedad75f282ecc269e8e0b'})
        self.assertEqual(set(v['windows']['files']),set(pg.CONFIGURED_SLOTS));self.assertEqual(set(v['postgres']['files']),set(pg.CONFIGURED_SLOTS))
        expected={'scripts/build.mjs'}|{'src/'+bridge+'/'+leaf for bridge in pg.CONFIGURED_SLOTS.values() for leaf in ('moon.pkg','bridge.mbt')}
        self.assertEqual(set(v['sourceFiles']),expected)
        for name in pg.CONFIGURED_SLOTS:
            w=v['windows']['files'][name];p=v['postgres']['files'][name];self.assertEqual(w['bytes']-p['bytes'],22);self.assertNotEqual(w['sha256'],p['sha256'])
            for row in (w,p):self.assertRegex(row['sha256'],r'\A[0-9a-f]{64}\Z');self.assertGreater(row['bytes'],0)

if __name__=='__main__':unittest.main()
