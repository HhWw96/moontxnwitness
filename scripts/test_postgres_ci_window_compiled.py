"""Two independently source-bound window outputs; original four slots stay intact."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import import_postgres_ci_bundle as pg
import test_postgres_ci_configured as previous
from test_postgres_ci_import import encode, REPO, COMMIT


class WindowCompiledBoundaries(unittest.TestCase):
    setUp = previous.ConfiguredRuntimeBoundaries.setUp
    tearDown = previous.ConfiguredRuntimeBoundaries.tearDown
    archive = previous.ConfiguredRuntimeBoundaries.archive
    validate = previous.ConfiguredRuntimeBoundaries.validate
    rejection = previous.ConfiguredRuntimeBoundaries.rejection
    mutate_pg = previous.ConfiguredRuntimeBoundaries.mutate_pg
    identity = previous.ConfiguredRuntimeBoundaries.identity

    def configured(self):
        expected, run, payload, source = previous.ConfiguredRuntimeBoundaries.configured(self)
        tested = expected['testedFileSha256']
        path = source/'scripts/build.mjs'
        build = path.read_text('utf8') + 'const configuredWindowCompiledCores={' + ','.join(
            encode(name).decode()+':'+encode(bridge).decode() for name, bridge in pg.WINDOW_COMPILED_SLOTS.items()) + '};\n'
        build += "for(const [name,folder]of Object.entries(configuredWindowCompiledCores))copyFileSync(resolve(root,'_build/js/release/build',folder,folder+'.js'),resolve(output,name));\n"
        path.write_text(build, 'utf8', newline='\n')
        tested['scripts/build.mjs'] = pg.digest(build.encode())
        for bridge in pg.WINDOW_COMPILED_SLOTS.values():
            for leaf in ('moon.pkg', 'bridge.mbt'):
                name = 'src/'+bridge+'/'+leaf
                path = source/name; path.parent.mkdir(parents=True, exist_ok=True)
                raw = ('independent synthetic window source '+name+'\n').encode()
                path.write_bytes(raw); tested[name] = pg.digest(raw)
        expected['configuredRuntimeSource'] = pg.configured_source_binding(source, tested)
        expected['windowCompiledRuntimeSource'] = pg.window_compiled_source_binding(source, tested)
        expected['windowCompiledRuntimeFiles'] = {}
        current = expected['buildManifest']
        prefix = 'verification/postgres-ci-runtime/123-2/'
        database = pg.json_bytes(payload[prefix+'postgres-ci-runtime-before.json'])['buildManifest']
        for field, names in pg.WINDOW_COMPILED_INVENTORIES.items():
            current[field] = {}; database[field] = {}
            for name in names:
                raw = ('shared wrapper '+name).encode()
                linux = raw
                if name in pg.WINDOW_COMPILED_SLOTS:
                    raw = ('synthetic Windows compiled '+name).encode()
                    linux = ('synthetic Linux compiled '+name).encode()
                    expected['windowCompiledRuntimeFiles'][name] = {'bytes':len(raw), 'sha256':pg.digest(raw)}
                    payload['dist/'+name] = linux
                (source/'dist'/name).write_bytes(raw)
                current[field][name] = pg.digest(raw)
                database[field][name] = pg.digest(linux)
                tested['dist/'+name] = pg.digest(raw)
        (source/'dist/build-manifest.json').write_bytes(encode(current))
        tested['dist/build-manifest.json'] = pg.digest(encode(current))
        pg_tested = {**tested, 'dist/core.mjs':database['coreSha256'],
            'dist/capture-core.mjs':database['captureCoreSha256'],
            'dist/build-manifest.json':pg.digest(encode(database)),
            **{'dist/'+name:value for name,value in database['configuredCoreSha256'].items()}}
        for field in pg.WINDOW_COMPILED_INVENTORIES:
            pg_tested.update({'dist/'+name:value for name,value in database[field].items()})
        payload['dist/build-manifest.json'] = encode(database)
        for phase in ('before', 'after'):
            name = prefix+'postgres-ci-runtime-'+phase+'.json'
            observed = pg.json_bytes(payload[name]); observed['buildManifest'] = database
            observed['testedFileSha256'] = pg_tested; payload[name] = encode(observed)
        name = 'verification/provenance-presence/ci-123-2/presence-receipt.json'
        presence = pg.json_bytes(payload[name]); presence['captureSource']['files']['dist/build-manifest.json'] = pg_tested['dist/build-manifest.json']
        payload[name] = encode(presence)
        return expected, run, payload, source

    def test_exact_two_raw_outputs_are_retained_with_independent_binding(self):
        e,r,p,_ = self.configured(); files,comparison,_ = self.validate(e,r,p)
        binding = comparison['windowCompiledRuntimeBinding']
        self.assertEqual(binding['slots'], pg.WINDOW_COMPILED_SLOTS)
        self.assertEqual(comparison['configuredRuntimeBinding']['slots'], pg.CONFIGURED_SLOTS)
        self.assertTrue(binding['actualPostgresBytesVerified'])
        self.assertTrue(all(value is False for value in binding['compiledBytesEqual'].values()))
        self.assertEqual(set(comparison['platformRuntimeExceptions']),
            {'dist/core.mjs','dist/capture-core.mjs','dist/build-manifest.json'} |
            {'dist/'+name for name in (*pg.CONFIGURED_SLOTS,*pg.WINDOW_COMPILED_SLOTS)})
        for name in pg.WINDOW_COMPILED_SLOTS:
            self.assertEqual(files['verification/releases/0.3.7/postgres-ci-import/bound-runtimes/'+name], p['dist/'+name])

    def test_each_missing_changed_or_swapped_actual_pg_output_is_rejected(self):
        for name in pg.WINDOW_COMPILED_SLOTS:
            for change in ('missing','corrupt','consumer-output'):
                e,r,p,s = self.configured()
                if change == 'missing': del p['dist/'+name]
                else: p['dist/'+name] = b'corrupt' if change == 'corrupt' else (s/'dist'/name).read_bytes()
                self.rejection(e,r,p)
        e,r,p,_ = self.configured(); names = list(pg.WINDOW_COMPILED_SLOTS)
        p['dist/'+names[0]],p['dist/'+names[1]] = p['dist/'+names[1]],p['dist/'+names[0]]
        self.rejection(e,r,p)

    def test_manifest_slots_are_exact_and_tested_hashes_cannot_be_forged(self):
        for field,names in pg.WINDOW_COMPILED_INVENTORIES.items():
            for change in ('missing','extra','hash','tested'):
                e,r,p,_ = self.configured()
                def mutate(value):
                    slots = value['buildManifest'][field]
                    if change == 'missing': slots.pop(names[0])
                    elif change == 'extra': slots['other-core.mjs'] = '0'*64
                    elif change == 'hash': slots[names[0]] = '0'*64
                    else: value['testedFileSha256']['dist/'+names[0]] = '0'*64
                self.mutate_pg(p, mutate); self.rejection(e,r,p)

    def test_current_manifest_files_and_raw_manifest_are_bound(self):
        for field,names in pg.WINDOW_COMPILED_INVENTORIES.items():
            for change in ('missing','extra','hash'):
                e,r,p,_ = self.configured()
                if change == 'missing': e['buildManifest'][field].pop(names[0])
                elif change == 'extra': e['buildManifest'][field]['other-core.mjs'] = '0'*64
                else: e['buildManifest'][field][names[0]] = '0'*64
                self.rejection(e,r,p)
        e,r,p,_ = self.configured(); p['dist/build-manifest.json'] = b'{}'; self.rejection(e,r,p)

    def test_source_bridge_build_and_wrapper_differences_are_not_platform_exceptions(self):
        names = ['scripts/build.mjs','src/sql_projection_v2_bridge/bridge.mbt',
            'src/structured_window_verification_bridge/moon.pkg', 'dist/configured-window-v2-host.mjs',
            'dist/configured-window-v2-structured.mjs','dist/configured-window-v2-capsule.mjs',
            'integrations/python/capture.py','fixtures/example.json']
        for name in names:
            e,r,p,_ = self.configured()
            self.mutate_pg(p, lambda value:value['testedFileSha256'].update({name:'0'*64}))
            self.rejection(e,r,p)

    def test_rehashed_wrapper_and_unlisted_dist_output_still_must_match(self):
        e,r,p,_ = self.configured(); name = 'configured-window-v2-host.mjs'
        def change(value):
            value['buildManifest']['configuredWindowRuntimeSha256'][name] = '0'*64
            value['testedFileSha256']['dist/'+name] = '0'*64
        self.mutate_pg(p, change)
        before = pg.json_bytes(p['verification/postgres-ci-runtime/123-2/postgres-ci-runtime-before.json'])
        p['dist/build-manifest.json'] = encode(before['buildManifest'])
        self.mutate_pg(p, lambda value:value['testedFileSha256'].update({'dist/build-manifest.json':pg.digest(p['dist/build-manifest.json'])}))
        self.rejection(e,r,p)
        e,r,p,_ = self.configured(); e['testedFileSha256']['dist/unrelated-core.mjs'] = '1'*64
        self.mutate_pg(p, lambda value:value['testedFileSha256'].update({'dist/unrelated-core.mjs':'2'*64}))
        self.rejection(e,r,p)

    def test_missing_or_forged_source_contract_and_current_file_inventory_are_rejected(self):
        for change in ('missing-contract','slots','format','algorithm','inventory','missing-source','source-sha',
                       'missing-current','extra-current','current-sha','current-length'):
            e,r,p,_ = self.configured(); source = e['windowCompiledRuntimeSource']
            name = next(iter(pg.WINDOW_COMPILED_SLOTS))
            if change == 'missing-contract': e.pop('windowCompiledRuntimeSource')
            elif change in ('slots','format','algorithm'): source[change] = 'unknown'
            elif change == 'inventory': source['manifestInventories'] = {}
            elif change == 'missing-source': source['sourceFiles'].pop('scripts/build.mjs')
            elif change == 'source-sha': source['sourceFiles']['scripts/build.mjs']['sha256'] = '0'*64
            elif change == 'missing-current': e['windowCompiledRuntimeFiles'].pop(name)
            elif change == 'extra-current': e['windowCompiledRuntimeFiles']['other.mjs'] = {'bytes':1,'sha256':'0'*64}
            elif change == 'current-sha': e['windowCompiledRuntimeFiles'][name]['sha256'] = '0'*64
            else: e['windowCompiledRuntimeFiles'][name]['bytes'] = True
            self.rejection(e,r,p)

    def test_actual_checkout_reads_and_rechecks_both_current_outputs(self):
        e,_,_,s = self.configured(); current = self.identity(e,s)
        self.assertEqual(current['windowCompiledRuntimeSource'],e['windowCompiledRuntimeSource'])
        self.assertEqual(current['windowCompiledRuntimeFiles'],e['windowCompiledRuntimeFiles'])
        for name in pg.WINDOW_COMPILED_SLOTS:
            e,_,_,s = self.configured(); (s/'dist'/name).write_bytes(b'changed actual current bytes')
            with self.assertRaises(pg.ImportFailure): self.identity(e,s)

    def test_build_mapping_and_its_actual_copy_loop_are_both_required(self):
        for change in ('bridge','duplicate','unused-map'):
            e,_,_,s = self.configured(); path = s/'scripts/build.mjs'; raw = path.read_bytes()
            if change == 'bridge': raw = raw.replace(b'structured_window_verification_bridge',b'arbitrary_bridge')
            elif change == 'duplicate': raw += b'const configuredWindowCompiledCores={};\n'
            else: raw = raw.replace(b'Object.entries(configuredWindowCompiledCores)',b'Object.entries(anotherMap)')
            path.write_bytes(raw); e['testedFileSha256']['scripts/build.mjs'] = pg.digest(raw)
            with self.assertRaises(pg.ImportFailure): pg.window_compiled_source_binding(s,e['testedFileSha256'])

    def test_actual_checkout_rejects_changed_bridge_and_manifest_bytes(self):
        for name in ('src/sql_projection_v2_bridge/bridge.mbt',
                     'src/structured_window_verification_bridge/moon.pkg','dist/build-manifest.json'):
            e,_,_,s = self.configured(); (s/name).write_bytes(b'changed actual source')
            with self.assertRaises((pg.ImportFailure,KeyError)): self.identity(e,s)

    def test_installation_and_revalidation_keep_each_original_raw_output(self):
        e,r,p,_ = self.configured(); files,comparison,artifact = self.validate(e,r,p)
        target = self.root/'installed'; target.mkdir()
        record = {'version':'0.3.7','sourceCommit':COMMIT,'repository':REPO,'run':r,'artifact':artifact,
            'prHead':None,'comparison':comparison}
        installed = pg.install_reproduction(target,files,record)
        self.assertEqual(installed['runtimeBindingAlgorithm'],pg.CONFIGURED_ALGORITHM)
        self.assertEqual(installed['windowCompiledRuntimeBindingAlgorithm'],pg.WINDOW_COMPILED_ALGORITHM)
        with patch.object(pg,'checkout_identity',return_value=e),patch.object(pg,'event_pr_head',return_value=None):
            self.assertEqual(len(pg.validated_ci_reproduction_files(target,'0.3.7')),len(files)+1)
            name = next(iter(pg.WINDOW_COMPILED_SLOTS))
            (target/'verification/releases/0.3.7/postgres-ci-import/bound-runtimes'/name).write_bytes(b'changed retained output')
            with self.assertRaises(pg.ImportFailure): pg.validated_ci_reproduction_files(target,'0.3.7')

    def test_install_cannot_drop_the_new_binding_or_its_raw_files(self):
        for change in ('binding','raw'):
            e,r,p,_ = self.configured(); files,comparison,artifact = self.validate(e,r,p)
            if change == 'binding': comparison.pop('windowCompiledRuntimeBinding')
            else: files.pop('verification/releases/0.3.7/postgres-ci-import/bound-runtimes/'+next(iter(pg.WINDOW_COMPILED_SLOTS)))
            with self.assertRaises(pg.ImportFailure): pg.install_reproduction(self.root/'installed',files,
                {'version':'0.3.7','sourceCommit':COMMIT,'run':r,'comparison':comparison})

    def test_original_ff61_projection_preserves_both_raw_platform_outputs_and_failure(self):
        path = Path(__file__).resolve().parents[1]/'fixtures/postgres-ci-import/window-ff61-platform-runtime-projection.json'
        raw = path.read_bytes()
        self.assertEqual(pg.digest(raw),'1a67282e1b5204f038cb91484d3f5459325ce85ce2156f5dec97707600b80360')
        value = pg.json_bytes(raw)
        self.assertEqual(value['sourceCommit'],'ff61f96a8defa106ea551f1d003761fa669d073b')
        self.assertEqual(value['slotMapping'],pg.WINDOW_COMPILED_SLOTS)
        self.assertEqual(value['originalImporterExceptionCount'],7)
        self.assertEqual(set(value['remainingDifferencePaths']),{'dist/'+name for name in pg.WINDOW_COMPILED_SLOTS})
        self.assertTrue(value['otherSharedInputsEqual'])
        self.assertEqual(value['windows']['runId'],'44133079241')
        self.assertEqual(value['windows']['importOutcome'],'failed')
        self.assertEqual(value['windows']['artifact']['id'],14352787107)
        self.assertEqual(value['postgres']['artifact']['id'],14350143885)
        self.assertEqual(value['windows']['coreTestCountsByTarget'],{'js':2078,'wasm-gc':2056,'wasm':2056})
        self.assertEqual(value['windows']['oracleHistories'],10320)
        self.assertEqual(value['windows']['verifiedCycleCertificates'],6373)
        self.assertFalse(value['normalizationPerformed'])
        self.assertFalse(value['failedWindowsCIPromoted'])
        self.assertFalse(value['releaseReady'])
        names = {'scripts/build.mjs'} | {'src/'+bridge+'/'+leaf for bridge in pg.WINDOW_COMPILED_SLOTS.values() for leaf in ('moon.pkg','bridge.mbt')}
        self.assertEqual(set(value['sourceFiles']),names)
        for name in pg.WINDOW_COMPILED_SLOTS:
            windows = value['windows']['files'][name]; postgres = value['postgres']['files'][name]
            self.assertEqual(windows['bytes']-postgres['bytes'],22)
            self.assertNotEqual(windows['sha256'],postgres['sha256'])
            self.assertTrue(pg.SHA.fullmatch(windows['sha256']))
            self.assertTrue(pg.SHA.fullmatch(postgres['sha256']))


if __name__ == '__main__': unittest.main()
