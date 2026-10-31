"""Additional exact-run reproduction boundaries; original 32 tests stay unchanged."""
import copy, json, os, unittest
from unittest.mock import patch
import import_postgres_ci_bundle as pg
import test_postgres_ci_import as original
from test_postgres_ci_import import fixture, encode, REPO, COMMIT

def full_fixture():
    expected, run, payload = fixture(); release = 'verification/releases/0.3.4/'
    prefix = release+'postgres/'; presence = 'verification/provenance-presence/ci-123-2/'
    binding = 'verification/postgres-ci-runtime/123-2/'
    sources = ['integrations/python/moontxnwitness_capture/capture.py','integrations/python/moontxnwitness_capture/__init__.py',
        'experiments/provenance/initialization_postgres.py','scripts/capture-postgres-test.py','scripts/capture-postgres-e2e.mjs']
    sources += ['integrations/python/'+name for name in sorted(pg.IMPLEMENTATION) if 'integrations/python/'+name not in sources]
    for name in sources: expected['testedFileSha256'][name] = pg.digest(name.encode())
    for phase in ('before','after'):
        value = pg.json_bytes(payload[binding+'postgres-ci-runtime-'+phase+'.json'])
        for name in sources: value['testedFileSha256'][name] = expected['testedFileSha256'][name]
        payload[binding+'postgres-ci-runtime-'+phase+'.json'] = encode(value)
    pg_build = pg.json_bytes(payload[binding+'postgres-ci-runtime-before.json'])['buildManifest']
    observed = pg.json_bytes(payload[binding+'postgres-ci-runtime-before.json'])['testedFileSha256']
    receipt = pg.json_bytes(payload[prefix+'receipt.json']); receipt['tool'] = 'MoonTxnWitness'; payload[prefix+'receipt.json'] = encode(receipt)
    payload[prefix+'attempt-2026-10-31T01-02-03-004Z.json'] = payload[prefix+'receipt.json']
    payload['verification/postgres.json'] = payload[prefix+'receipt.json']
    impl = {name:{'bytes':5,'sha256':expected['testedFileSha256']['integrations/python/'+name]} for name in sorted(pg.IMPLEMENTATION)}
    implementation = {'before':impl,'after':copy.deepcopy(impl),'unchanged':True}
    scenarios = []
    for i in range(3):
        name = 'case-'+str(i); history = {'schema':2,'transactions':[]}; capsule = {'historyText':json.dumps(history)}
        objects = {'trace':{},'coverage':{'status':'ready'},'audit':{},'history':history,'report':{},'capsule':capsule,'tamperChecks':{}}
        bindings = {}
        for kind,value in objects.items():
            leaf = name+'.'+kind+'.json'; raw = encode(value); payload[presence+leaf] = raw
            bindings[kind] = {'path':leaf,'bytes':len(raw),'sha256':pg.digest(raw)}
        scenarios.append({'name':name,'trace':bindings['trace']['path'],'expectedStatus':'ready','artifactBindings':bindings,
            'committedAuditExactlyMatchesCapturedWrites':True,'initialPresenceMatchedLockedAudit':True,'uninstallPreservedBusinessRows':True})
    presence_receipt = {'status':'passed','passed':True,'actualDatabaseExecution':True,'coreVersion':'0.3.4','replayedCapsules':3,
        'scenarios':scenarios,'captureSource':{'files':{'dist/core.mjs':pg_build['coreSha256'],'dist/build-manifest.json':observed['dist/build-manifest.json']},
            'implementationFiles':{'integrations/python/'+n:r['sha256'] for n,r in impl.items()},'buildManifestSourceSha256':pg_build['sourceSha256']},'implementationSources':implementation}
    payload[presence+'presence-receipt.json'] = encode(presence_receipt)
    init = {'schema':1,'passed':True,'actualDatabaseExecution':True,'packageVersion':'0.3.4',
        **{k:False for k in ['analyzerExecuted','releaseAcceptance','coreProofImplemented','sourceClosureVerified','formalPerformanceMeasured']},
        'implementationSources':implementation,'fixtureSources':{'before':expected['testedFileSha256']['experiments/provenance/initialization_postgres.py'],'after':expected['testedFileSha256']['experiments/provenance/initialization_postgres.py'],'unchanged':True},
        'cases':[{'name':'actual-confirmed-commit-and-crud','passed':True,'initializationAck':{'actualCommitConfirmed':True,'commandTag':'COMMIT'},'trace':'confirmed-crud.trace.json'}]+[{'name':'negative-'+str(i),'passed':True,'initialFactsPublished':False} for i in range(3)]}
    payload[presence+'initialization/initialization-receipt.json'] = encode(init)
    payload[presence+'initialization/confirmed-crud.trace.json'] = encode({'retained':'actual initial trace'})
    capture_path = 'releases/0.3.4/capture/2026-10-31T01-02-03-004Z'; capture = 'verification/'+capture_path+'/'
    cap = {'passed':True,'actualDatabaseExecution':True,'version':'0.3.4','replayedCapsules':1,'scenarios':[{'name':'sync','trace':'sync.trace.json','expectedStatus':'ready'}],
        'captureSource':{'adapterSha256':expected['testedFileSha256'][sources[0]],'captureCoreSha256':pg_build['captureCoreSha256'],'analysisCoreSha256':pg_build['coreSha256'],'fixtureSha256':expected['testedFileSha256']['scripts/capture-postgres-test.py'],'e2eSha256':expected['testedFileSha256']['scripts/capture-postgres-e2e.mjs']}}
    payload[capture+'receipt.json'] = encode(cap); payload['verification/capture-postgres.json'] = encode({**cap,'path':capture_path})
    for leaf in ['sync.trace.json','sync.coverage.json','sync.report.json','sync.capsule.json','database.json']: payload[capture+leaf] = encode({'syntheticActualMember':leaf})
    return expected,run,payload

class ReproductionBoundaries(unittest.TestCase):
    setUp = original.Boundaries.setUp
    tearDown = original.Boundaries.tearDown
    archive = original.Boundaries.archive
    installed = original.Boundaries.installed
    def full(self, payload=None):
        self.expected,self.run,base = full_fixture(); payload = base if payload is None else payload
        path,artifact = self.archive(payload)
        return pg.validate_archive(path,self.run,artifact,self.expected,REPO,reproduction=True),artifact
    def altered(self, name, fn):
        expected,run,payload = full_fixture(); value = pg.json_bytes(payload[name]); fn(value); payload[name] = encode(value)
        return expected,run,payload
    def reject(self, payload):
        with self.assertRaises(pg.ImportFailure): self.full(payload)
    def test_full_packet_keeps_attempt_and_initialization_without_acceptance(self):
        (files,c),_ = self.full()
        self.assertIn('verification/provenance-presence/ci-123-2/initialization/confirmed-crud.trace.json',files)
        self.assertFalse(any(n.endswith('/acceptance.json') for n in files))
        repro = pg.json_bytes(files['verification/releases/0.3.4/reproduction.json'])
        self.assertFalse(repro['releaseReady']); self.assertEqual(repro['databaseEvidence'],'database-ci.json')
        self.assertEqual(c['reproduction']['presenceReadyCapsules'],3)
        db = pg.json_bytes(files['verification/releases/0.3.4/database-ci.json']); self.assertTrue(db['passed']); self.assertFalse(db['releaseReady'])
        for row in db['receipts'].values(): self.assertEqual(pg.digest(files['verification/'+row['path']+'/'+row['receiptFile']]),row['sha256'])
    def test_failed_and_unexecuted_attempts_are_retained_not_success(self):
        _,_,p = full_fixture()
        for i,status in enumerate(['failed','not-executed']): p[self.prefix+f'attempt-2026-10-30T01-02-0{i}-004Z.json'] = encode({'tool':'MoonTxnWitness','version':'0.3.4','passed':False,'actualDatabaseExecution':False,'status':status})
        (files,c),_ = self.full(p); rows = c['attempts']; self.assertEqual(len(rows),3)
        self.assertEqual(sum(x['role']=='current-success' for x in rows),1)
        self.assertEqual(sum(x['passed'] is False for x in rows),2)
        for row in rows: self.assertEqual(pg.digest(files[row['path']]),row['sha256'])
    def test_failed_actual_database_attempt_remains_original_failure(self):
        _,_,p=full_fixture();name=self.prefix+'attempt-2026-10-30T01-02-03-004Z.json'
        p[name]=encode({'tool':'MoonTxnWitness','version':'0.3.4','passed':False,'actualDatabaseExecution':True,'status':'failed'})
        (files,c),_=self.full(p);row=next(x for x in c['attempts'] if x['path']==name)
        self.assertFalse(row['passed']);self.assertEqual(row['role'],'historical-attempt');self.assertEqual(files[name],p[name])
    def test_historical_passed_attempt_does_not_validate_old_payload_against_current(self):
        _,_,p = full_fixture(); old = pg.json_bytes(p[self.prefix+'receipt.json']); old['files']['rr-report.json'] = '0'*64
        p[self.prefix+'attempt-2026-10-30T01-02-03-004Z.json'] = encode(old)
        (_,c),_ = self.full(p); row = next(x for x in c['attempts'] if x['role']=='historical-attempt')
        self.assertFalse(row['historicalReferencedPayloadVerified']); self.assertTrue(row['passed'])
    def test_attempt_current_bytes_are_required(self):
        _,_,p = full_fixture(); p[self.prefix+'attempt-2026-10-31T01-02-03-004Z.json'] = encode({'tool':'MoonTxnWitness','version':'0.3.4','passed':False,'actualDatabaseExecution':False,'status':'failed'}); self.reject(p)
    def test_full_reproduction_cannot_use_narrow_packet_without_attempt(self):
        _,_,p = full_fixture(); del p[self.prefix+'attempt-2026-10-31T01-02-03-004Z.json']; self.reject(p)
    def test_attempt_unknown_extra_nested_and_bad_calendar_are_rejected(self):
        for leaf in ['other.json','nested/attempt-2026-10-31T01-02-03-004Z.json','attempt-2026-02-31T01-02-03-004Z.json']:
            _,_,p = full_fixture(); p[self.prefix+leaf] = p[self.prefix+'receipt.json']; self.reject(p)
    def test_attempt_fake_success_flags_tool_version_and_status_are_rejected(self):
        for key,value in [('tool','other'),('version','0.3.5'),('passed','true'),('actualDatabaseExecution',1),('passed',False),('status','unknown')]:
            _,_,p = full_fixture(); leaf = self.prefix+'attempt-2026-10-31T01-02-03-004Z.json'; value_obj = pg.json_bytes(p[leaf]); value_obj[key] = value; p[leaf] = encode(value_obj); self.reject(p)
    def test_exact_run_presence_is_mandatory(self):
        _,_,p = full_fixture(); name='verification/provenance-presence/ci-123-2/presence-receipt.json'; p[name.replace('123-2','123-1')] = p.pop(name); self.reject(p)
    def test_initialization_receipt_and_actual_confirmed_trace_are_mandatory(self):
        for leaf in ['initialization-receipt.json','confirmed-crud.trace.json']:
            _,_,p = full_fixture(); del p['verification/provenance-presence/ci-123-2/initialization/'+leaf]; self.reject(p)
    def test_presence_raw_binding_hashes_and_lengths_are_checked(self):
        _,_,p = full_fixture(); p['verification/provenance-presence/ci-123-2/case-1.audit.json'] = b'changed'; self.reject(p)
    def test_presence_bound_path_traversal_is_rejected(self):
        _,_,p = self.altered('verification/provenance-presence/ci-123-2/presence-receipt.json',lambda x:x['scenarios'][0]['artifactBindings']['audit'].update(path='../escape')); self.reject(p)
    def test_presence_three_ready_assertion_is_preserved(self):
        _,_,p = self.altered('verification/provenance-presence/ci-123-2/presence-receipt.json',lambda x:x['scenarios'].pop()); self.reject(p)
    def test_presence_capsule_history_must_equal_original_history(self):
        _,_,p = full_fixture(); name='verification/provenance-presence/ci-123-2/case-0.capsule.json'; p[name]=encode({'historyText':'{"different":true}'})
        receipt=pg.json_bytes(p['verification/provenance-presence/ci-123-2/presence-receipt.json']); receipt['scenarios'][0]['artifactBindings']['capsule'].update(bytes=len(p[name]),sha256=pg.digest(p[name])); p['verification/provenance-presence/ci-123-2/presence-receipt.json']=encode(receipt); self.reject(p)
    def test_presence_sources_cannot_self_assert_other_adapter(self):
        _,_,p = self.altered('verification/provenance-presence/ci-123-2/presence-receipt.json',lambda x:x['captureSource']['files'].update({'dist/core.mjs':'0'*64})); self.reject(p)
    def test_presence_and_initialization_cannot_drop_actual_implementation_members(self):
        for name in ['verification/provenance-presence/ci-123-2/presence-receipt.json','verification/provenance-presence/ci-123-2/initialization/initialization-receipt.json']:
            def change(value):
                for phase in ('before','after'):value['implementationSources'][phase].pop('moontxnwitness_capture/presence.py')
            _,_,p=self.altered(name,change);self.reject(p)
    def test_initialization_scope_cannot_be_upgraded_to_source_or_release_acceptance(self):
        for key in ['analyzerExecuted','releaseAcceptance','coreProofImplemented','sourceClosureVerified','formalPerformanceMeasured']:
            _,_,p=self.altered('verification/provenance-presence/ci-123-2/initialization/initialization-receipt.json',lambda x:x.update({key:True})); self.reject(p)
    def test_initialization_failed_controls_and_unconfirmed_commit_are_rejected(self):
        for fn in [lambda x:x['cases'][1].update(passed=False),lambda x:x['cases'][0]['initializationAck'].update(actualCommitConfirmed=False)]:
            _,_,p=self.altered('verification/provenance-presence/ci-123-2/initialization/initialization-receipt.json',fn); self.reject(p)
    def test_capture_pointer_cannot_select_other_version_or_missing_run(self):
        for path in ['releases/0.3.5/capture/current','releases/0.3.4/capture/missing','releases/0.3.4/capture/a/b']:
            _,_,p=self.altered('verification/capture-postgres.json',lambda x:x.update(path=path)); self.reject(p)
    def test_top_capture_and_top_postgres_cannot_differ_from_originals(self):
        for name in ['verification/capture-postgres.json','verification/postgres.json']:
            _,_,p=self.altered(name,lambda x:x.update(passed=False)); self.reject(p)
    def test_capture_source_runtime_is_executed_pg_not_consumer_platform(self):
        _,_,p=full_fixture(); top=pg.json_bytes(p['verification/capture-postgres.json']); path='verification/'+top['path']+'/receipt.json'
        top['captureSource']['analysisCoreSha256']=self.expected['buildManifest']['coreSha256']; p['verification/capture-postgres.json']=encode(top); p[path]=encode({k:v for k,v in top.items() if k!='path'}); self.reject(p)
    def test_all_capture_tree_members_are_preserved(self):
        _,_,p=full_fixture(); top=pg.json_bytes(p['verification/capture-postgres.json']); name='verification/'+top['path']+'/nested/original.log'; p[name]=b'preserve original failure log'
        (files,_),_=self.full(p); self.assertEqual(files[name],p[name])
    def test_install_and_inventory_recompute_all_reproduction_bytes(self):
        (files,c),artifact=self.full(); record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':c,'sqlExecutedByImporter':False}
        pg.install_reproduction(self.root,files,record)
        with patch.object(pg,'checkout_identity',return_value=self.expected),patch.object(pg,'event_pr_head',return_value=None):
            inventory=pg.validated_ci_reproduction_files(self.root,'0.3.4'); self.assertEqual(len(inventory),len(files)+1)
            raw=self.root/'verification/provenance-presence/ci-123-2/initialization/confirmed-crud.trace.json'; raw.write_bytes(b'changed')
            with self.assertRaises(pg.ImportFailure):pg.validated_ci_reproduction_files(self.root,'0.3.4')
    def test_narrow_record_is_not_a_production_reproduction_allowlist(self):
        self.installed()
        with self.assertRaises(pg.ImportFailure):pg.validated_ci_reproduction_files(self.root,'0.3.4')
    def test_rehashed_generated_reproduction_cannot_claim_release_ready(self):
        (files,c),artifact=self.full(); name='verification/releases/0.3.4/reproduction.json'; value=pg.json_bytes(files[name]); value['releaseReady']=True; files[name]=encode(value)
        record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':c,'sqlExecutedByImporter':False}; pg.install_reproduction(self.root,files,record)
        with patch.object(pg,'checkout_identity',return_value=self.expected),patch.object(pg,'event_pr_head',return_value=None):
            with self.assertRaises(pg.ImportFailure):pg.validated_ci_reproduction_files(self.root,'0.3.4')
    def test_install_rejects_unknown_destination_and_preexisting_conflicts(self):
        (files,c),artifact=self.full(); record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':c}
        with self.assertRaises(pg.ImportFailure):pg.install_reproduction(self.root,{**files,'verification/secret.json':b'x'},record)
        path=self.root/'verification/postgres.json';path.parent.mkdir(parents=True);path.write_bytes(b'old original')
        with self.assertRaises(pg.ImportFailure):pg.install_reproduction(self.root,files,record)
        self.assertEqual(path.read_bytes(),b'old original')
    def test_original_tracked_rolling_pointers_are_retained_before_atomic_update(self):
        (files,c),artifact=self.full(); record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':c}
        old={'verification/postgres.json':b'original tracked PostgreSQL pointer','verification/capture-postgres.json':b'original tracked capture pointer'}
        for name,raw in old.items(): target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        with patch.object(pg,'_original_pointer',side_effect=lambda root,name:old[name]),patch.object(pg,'checkout_identity',return_value=self.expected),patch.object(pg,'event_pr_head',return_value=None):
            first=pg.install_reproduction(self.root,files,record);second=pg.install_reproduction(self.root,files,record);self.assertEqual(first,second)
            inventory=pg.validated_ci_reproduction_files(self.root,'0.3.4')
            for name,raw in old.items():
                retained='verification/releases/0.3.4/postgres-ci-import/previous-pointers/'+name.split('/')[-1]
                self.assertEqual((self.root/retained).read_bytes(),raw);self.assertIn(retained,inventory);self.assertEqual((self.root/name).read_bytes(),files[name])
    def test_rolling_pointer_cannot_overwrite_untracked_changed_original(self):
        (files,c),artifact=self.full(); record={'repository':REPO,'version':'0.3.4','sourceCommit':COMMIT,'run':self.run,'artifact':artifact,'prHead':None,'comparison':c}
        target=self.root/'verification/postgres.json';target.parent.mkdir(parents=True);target.write_bytes(b'local unrelated changes')
        with patch.object(pg,'_original_pointer',return_value=b'original tracked pointer'),self.assertRaises(pg.ImportFailure):pg.install_reproduction(self.root,files,record)
        self.assertEqual(target.read_bytes(),b'local unrelated changes')

if __name__=='__main__':unittest.main()
