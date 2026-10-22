from pathlib import Path
import datetime, hashlib, json, shutil
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
PUBLIC=ROOT/'artifacts/v016-cycle-independent/public'
REPRO=PUBLIC/'reproduction/repository'
CANDIDATE=REPRO/'artifacts/v016-classification-planning'
EXPECTED_SOURCE='3eabe931cc6816527c0cf43334722b805ab8dc51bd66be102232c79eb43e41b1'
EXPECTED_CORE='752ebcf6166b310b5b3981d38e7aba1ebae5164e2475eb70aa858b03e813e4e8'
EXPECTED_CAPTURE='60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee'
sha=lambda b:hashlib.sha256(b).hexdigest()
def binding(p):
    b=p.read_bytes()
    return {'bytes':len(b),'sha256':sha(b)}
def write_json(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(x,f,ensure_ascii=False,indent=2)
        f.write('\n')
def copy(src,relative):
    dst=OUT/relative
    dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists()
    shutil.copyfile(src,dst)
    source_bindings[src.relative_to(ROOT).as_posix()]=binding(src)
    return relative
def source_fingerprint():
    files=sorted([ROOT/'moon.mod']+[p for p in (ROOT/'src').rglob('*') if p.is_file() and (p.suffix=='.mbt' or p.name=='moon.pkg')],key=lambda p:p.relative_to(ROOT).as_posix())
    h=hashlib.sha256()
    for p in files:h.update(p.relative_to(ROOT).as_posix().encode()+b'\0'+p.read_bytes()+b'\0')
    return h.hexdigest(),{p.relative_to(ROOT).as_posix():binding(p) for p in files}
assert not (OUT/'preparation.json').exists()
assert binding(PUBLIC/'review-summary.json')['sha256']=='04a7ace426a9080e5095a2a785ec9da8f5439f1dd04249cbda3b8d3efd746249'
integration=ROOT/'artifacts/v016-release-integration/candidate-manifest.json'
assert binding(integration)['sha256']=='e29cb1a2791af3e5c3eb193136c2c6e815f0a7549ee532c881feb823252ac5bf'
closure=json.loads((PUBLIC/'closure-manifest.json').read_text(encoding='utf-8'))
for rel,expected in closure['files'].items():assert binding(PUBLIC/rel)==expected,rel
actual=json.loads((ROOT/'dist/build-manifest.json').read_text())
assert actual['version']=='0.1.6' and actual['sourceSha256']==EXPECTED_SOURCE
assert actual['coreSha256']==EXPECTED_CORE and actual['captureCoreSha256']==EXPECTED_CAPTURE
assert binding(ROOT/'dist/core.mjs')['sha256']==EXPECTED_CORE
assert binding(ROOT/'dist/capture-core.mjs')['sha256']==EXPECTED_CAPTURE
source_sha,source_files=source_fingerprint()
assert source_sha==EXPECTED_SOURCE
payload=json.loads(integration.read_text(encoding='utf-8'))['payloadFiles']
assert binding(ROOT/'dist/sdk.mjs')==payload['cmd/sdk.mjs']
source_bindings={}
for name in ['core.mjs','capture-core.mjs','sdk.mjs','evidence.mjs','build-manifest.json']:
    copy(ROOT/'dist'/name,'runtime/'+name)
    copy(REPRO/'dist'/name,'prior-v015/'+name)
copy(REPRO/'dist/sdk.mjs','runtime/generic-sdk.mjs')
assert (OUT/'runtime/sdk.mjs').read_bytes().startswith((OUT/'runtime/generic-sdk.mjs').read_bytes())
copy(PUBLIC/'independent-inputs.json','inputs/independent-inputs.json')
copy(PUBLIC/'independent-input-manifest.json','inputs/independent-input-manifest.json')
copy(CANDIDATE/'handwritten-inputs.json','inputs/handwritten-inputs.json')
copy(PUBLIC/'check.mjs','prior-independent-check.mjs')
for name in ['review-summary.json','closure-manifest.json','static-rule-review.json']:
    copy(PUBLIC/name,'prior-review/'+name)
ref='verification/experimental-candidates/elle-smoke-r2-2026-10-21'
for rel in ['source-pins.json','primary-references/src/elle/txn.clj','primary-references/LICENSE','primary-references/project.clj','smoke-inputs-v1.json','actual-ci-39599513353/actual/elle-result.json']:
    copy(CANDIDATE/'source-inputs'/ref/rel,'inputs/source-inputs/'+ref+'/'+rel)
for rel in ['fixtures/list-v3/manual.json','fixtures/relation-v3/boundary.json','verification/faults/mlflow/run-c7227fba032f4c92b127b7357252107c/before/capture.json']:
    copy(CANDIDATE/'source-inputs'/rel,'inputs/source-inputs/'+rel)
for name in ['register-cycle.json','register-cycle-roundtrip.mjs']:
    assert binding(ROOT/'examples'/name)==payload['examples/'+name]
    copy(ROOT/'examples'/name,'example-repository/examples/'+name)
for name in ['core.mjs','capture-core.mjs','sdk.mjs','evidence.mjs','build-manifest.json']:
    copy(ROOT/'dist'/name,'example-repository/dist/'+name)
copy(ROOT/'LICENSE','LICENSE')
copy(ROOT/'THIRD_PARTY.md','THIRD_PARTY.md')
caps=[]
families=[
 ('register-v2','verification/releases/0.1.5/postgres',3),
 ('capture-v2','verification/releases/0.1.5/capture',4),
 ('append-list-v3','verification/list-v3/postgres-d3b6329cc706446ebc16d4edbca54a2c',120),
 ('relation-v3','verification/relation-v3/postgres-727f5c9401c94f8089ed1614a567c26a-model',160),
]
for family,folder,count in families:
    source=ROOT/folder
    paths=sorted(set(source.rglob('*.capsule.json'))|set(source.rglob('capsule.json')))
    assert len(paths)==count
    for p in paths:
        rel='inputs/legacy-capsules/'+family+'/'+p.relative_to(source).as_posix()
        copy(p,rel)
        capsule=json.loads(p.read_text(encoding='utf-8'))
        caps.append({'family':family,'file':rel,'origin':p.relative_to(ROOT).as_posix(),
                     **binding(p),'schemaVersion':capsule['schemaVersion'],'engineVersion':capsule['engineVersion'],
                     'expectedStatus':json.loads(capsule['reportText'])['status']})
origins=[
 'verification/releases/0.1.5/postgres/receipt.json',
 'verification/releases/0.1.5/capture/2026-10-22T13-27-25-155Z/receipt.json',
 'verification/list-v3/postgres-d3b6329cc706446ebc16d4edbca54a2c/database-receipt.json',
 'verification/relation-v3/postgres-727f5c9401c94f8089ed1614a567c26a-model/model-receipt.json',
 'verification/relation-v3/postgres-727f5c9401c94f8089ed1614a567c26a/database-receipt.json',
]
for i,rel in enumerate(origins):copy(ROOT/rel,'inputs/legacy-receipts/'+str(i)+'-'+Path(rel).name)
main_regression=ROOT/'artifacts/scoped-v016/test-20261022T143529Z-1b95ad2e/receipt.json'
main_result=json.loads(main_regression.read_text(encoding='utf-8'))
assert main_result['passed'] is True and main_result['exitCode']==0
copy(main_regression,'main-regression-reference.json')
model=json.loads((ROOT/origins[3]).read_text(encoding='utf-8'))
assert model['sourceDatabaseExecutionReceipt']==binding(ROOT/origins[4])
assert json.loads((ROOT/origins[4]).read_text(encoding='utf-8'))['actualDatabaseExecution'] is True
write_json(OUT/'inputs/legacy-capsules-manifest.json',{'schema':1,'capsules':caps,
 'families':{family:count for family,_,count in families},'newDatabaseExecution':False,
 'relationCapsules':'v0.1.5 model replay capsules derived from preserved real SQL observations; original model receipt is explicitly not a new database execution'})
write_json(OUT/'authorization.json',{
 'trustedParentAuthorizedActualSemanticReview':True,
 'authorization':'Parent supplied actual v0.1.6 source/core/capture bindings and then confirmed its overall main regression completed with passed true and exit 0. This review signs only its own independent execution scope.',
 'externalManifest':actual,'parentMainRegressionReceipt':binding(main_regression),
 'overallMainRegressionIndependentlyReexecuted':False,
 'newCoreBuildAuthorized':False,'databaseAuthorized':False,'newElleAuthorized':False,'performanceAuthorized':False})
write_json(OUT/'preparation.json',{
 'schema':1,'preparedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'actualManifest':actual,'sourceFingerprintVerifiedBeforeImport':True,'mainSourceFiles':source_files,
 'frozenIndependentSummarySha256':'04a7ace426a9080e5095a2a785ec9da8f5439f1dd04249cbda3b8d3efd746249',
 'releaseIntegrationManifest':binding(integration),'priorClosureVerifiedFiles':len(closure['files']),
 'frozenExpectationRows':132,'frozenExpectationsChanged':False,
 'legacyCapsules':len(caps),'allImportsDeferredUntilBindingsFrozen':True,
 'implementationAuthor':False,'originalReferences':source_bindings,
 'dependencies':{p.relative_to(OUT).as_posix():binding(p) for p in sorted(OUT.rglob('*')) if p.is_file()},
 'newCoreBuild':False,'newDatabaseExecution':False,'newElleExecution':False,'performanceMeasurement':False})
print(json.dumps({'prepared':True,'actualVersion':actual['version'],'inputs':132,'legacyCapsules':len(caps),'sourceSha256':source_sha,'priorClosureFiles':len(closure['files'])}))
