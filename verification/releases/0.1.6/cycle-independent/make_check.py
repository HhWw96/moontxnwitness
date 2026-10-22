from pathlib import Path
OUT=Path(__file__).resolve().parent
original=(OUT/'prior-independent-check.mjs').read_text(encoding='utf-8')
helper=original[original.index('function subtype(types)'):original.index("await check('frozen-candidate")]
def group(start,end):
    return original[original.index("await check('"+start):original.index("await check('"+end)]
header=r'''// Independent actual-v0.1.6 review. No build, database, network, JVM or new Elle run.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=dirname(fileURLToPath(import.meta.url)),flags=new Map();
for(let i=2;i<process.argv.length;i+=2){assert.ok(['--main-root','--output-root'].includes(process.argv[i]));assert.ok(process.argv[i+1]);flags.set(process.argv[i],process.argv[i+1]);}
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const bind=file=>{const raw=readFileSync(file);return{bytes:raw.length,sha256:hash(raw)};};
const load=file=>JSON.parse(readFileSync(file,'utf8'));
const clone=value=>structuredClone(value);
const prep=load(resolve(here,'preparation.json'));
const sourceExpected='3eabe931cc6816527c0cf43334722b805ab8dc51bd66be102232c79eb43e41b1';
const coreExpected='752ebcf6166b310b5b3981d38e7aba1ebae5164e2475eb70aa858b03e813e4e8';
const captureExpected='60da31aafe9d8fb034289d6deb132c36eb61cb021bf3bc0668401e27987bf5ee';
assert.equal(prep.actualManifest.version,'0.1.6');assert.equal(prep.actualManifest.sourceSha256,sourceExpected);
assert.equal(prep.actualManifest.coreSha256,coreExpected);assert.equal(prep.actualManifest.captureCoreSha256,captureExpected);
for(const [name,expected]of Object.entries(prep.dependencies))assert.deepEqual(bind(resolve(here,name)),expected,name);
assert.equal(bind(resolve(here,'runtime/core.mjs')).sha256,coreExpected);
assert.equal(bind(resolve(here,'runtime/capture-core.mjs')).sha256,captureExpected);
const dependenciesBefore=Object.fromEntries(Object.keys(prep.dependencies).map(name=>[name,bind(resolve(here,name))]));
const mainRoot=flags.has('--main-root')?resolve(flags.get('--main-root')):null;
const mainBefore={};
if(mainRoot){
 for(const [name,expected]of Object.entries(prep.mainSourceFiles)){const actual=bind(resolve(mainRoot,name));assert.deepEqual(actual,expected);mainBefore[name]=actual;}
 const fingerprint=createHash('sha256');for(const name of Object.keys(prep.mainSourceFiles).sort()){fingerprint.update(name+'\0');fingerprint.update(readFileSync(resolve(mainRoot,name)));fingerprint.update('\0');}
 assert.equal(fingerprint.digest('hex'),sourceExpected);
 for(const name of ['core.mjs','capture-core.mjs','sdk.mjs','evidence.mjs','build-manifest.json']){assert.deepEqual(bind(resolve(mainRoot,'dist',name)),bind(resolve(here,'runtime',name)));mainBefore['dist/'+name]=bind(resolve(mainRoot,'dist',name));}
}
const outputRoot=resolve(flags.get('--output-root')||resolve(here,'runs'));mkdirSync(outputRoot,{recursive:true});
const out=mkdtempSync(resolve(outputRoot,'review-'));
const save=(name,value)=>writeFileSync(resolve(out,name),JSON.stringify(value,null,2)+'\n',{flag:'wx'});
const redact=text=>[here,here.replaceAll('\\','/'),JSON.stringify(here).slice(1,-1),...(mainRoot?[mainRoot,mainRoot.replaceAll('\\','/'),JSON.stringify(mainRoot).slice(1,-1)]:[])].reduce((s,prefix)=>s.replaceAll(prefix,'<review-input>'),text);
const receipt={schema:1,kind:'independent-ai-actual-v016-register-cycle-review',passed:false,
 actualBuild:prep.actualManifest,independentOfImplementation:true,newCoreBuild:false,
 databaseExecuted:false,newElleExecution:false,downloaded:false,performanceMeasurement:false,
 humanAcceptance:false,contestApproval:false,overallMainRegressionReexecuted:false,checks:[]};
const check=async(name,fn)=>{try{receipt.checks.push({name,passed:true,...await fn()});}catch(error){receipt.checks.push({name,passed:false,error:{name:error.name,message:redact(error.message),stack:redact(error.stack||'')}});}};
const inputRoot=resolve(here,'inputs/source-inputs');
const referenceRoot=resolve(inputRoot,'verification/experimental-candidates/elle-smoke-r2-2026-10-21');
const custom=load(resolve(here,'inputs/independent-inputs.json'));
const customManifest=load(resolve(here,'inputs/independent-input-manifest.json'));
assert.deepEqual(bind(resolve(here,'inputs/independent-inputs.json')),{bytes:customManifest.bytes,sha256:customManifest.sha256});
const manual=load(resolve(here,'inputs/handwritten-inputs.json')),byId=new Map(manual.map(row=>[row.id,row]));
// All required source/runtime/input bindings were checked before the first product import.
const sdk=await import(pathToFileURL(resolve(here,'runtime/sdk.mjs')).href);
const base=await import(pathToFileURL(resolve(here,'runtime/generic-sdk.mjs')).href);
const old=await import(pathToFileURL(resolve(here,'prior-v015/sdk.mjs')).href);
const evidence=await import(pathToFileURL(resolve(here,'runtime/evidence.mjs')).href);
const priorEvidence=await import(pathToFileURL(resolve(here,'prior-v015/evidence.mjs')).href);
'''
first=r'''
await check('frozen-expectations-primary-rule-and-actual-v016-runtime-before-import-bindings',()=>{
 assert.equal(sdk.version(),'0.1.6');assert.equal(base.version(),'0.1.6');assert.equal(old.version(),'0.1.5');
 assert.equal(custom.length,119);assert.equal(manual.length,13);
 const pins=load(resolve(referenceRoot,'source-pins.json')),rulePath=resolve(referenceRoot,'primary-references/src/elle/txn.clj');
 assert.equal(pins.fixedCommit,'4e359e597c52938b0afebb8bc42273914d68a424');assert.deepEqual(bind(rulePath),pins.files['src/elle/txn.clj']);
 const rule=readFileSync(rulePath,'utf8');assert.ok(rule.includes('(cons (last (:steps ex)))'));assert.ok(rule.includes('"G-nonadjacent-item"'));
 assert.ok(readFileSync(resolve(here,'runtime/sdk.mjs'),'utf8').startsWith(readFileSync(resolve(here,'runtime/generic-sdk.mjs'),'utf8')));
 assert.deepEqual(Object.keys(sdk).filter(name=>!(name in old)).sort(),['explainRegisterCycleV3','verifyRegisterCycleExplanationV3']);
 for(const name of Object.keys(old))assert.ok(name in sdk,name);
 return {actualRuntime:'0.1.6',priorRuntime:'0.1.5',frozenHistories:132,priorExportsPreserved:Object.keys(old).length,addedExports:2,sourceRuntimeBoundBeforeImport:true};
});
const reviewed=new Map();
await check('132-frozen-real-history-explanations-complete-source-map-and-prior-model-behavior',()=>{
 const results=[];
 for(const row of [...manual,...custom]){
  const result=verifyExplanation(sdk,row),prior=old.analyzeV3(row.traceText);
  assert.equal(result.report.version,'0.1.6');assert.equal(prior.version,'0.1.5');
  const currentBody=clone(result.report),priorBody=clone(prior);delete currentBody.version;delete priorBody.version;
  if(currentBody.evidence?.tool==='MoonTxnWitness'&&currentBody.evidence?.schemaVersion===2){assert.equal(currentBody.evidence.version,'0.1.6');assert.equal(priorBody.evidence.version,'0.1.5');delete currentBody.evidence.version;delete priorBody.evidence.version;}
  assert.deepEqual(currentBody,priorBody,'All report fields except the two explicitly advanced engine headers must match: '+row.id);
  reviewed.set(row.id,result);results.push({id:row.id,inputSha256:row.inputSha256,sourceStatus:result.report.status,
    status:result.exp.status,subtype:result.exp.subtype,reportSha256:hash(JSON.stringify(result.report)),
    priorReportSha256:hash(JSON.stringify(prior)),explanationSha256:hash(JSON.stringify(result.exp))});
 }
 assert.equal(results.length,132);save('132-actual-v016-results.json',results);
 return {histories:132,generatedRingPatterns:117,additionalSavepointHistories:2,originalManualHistories:13,allPriorReportFieldsExceptTwoExplicitEngineHeadersPreserved:true};
});
'''
wrap=group('wraparound-adjacency','same-name-savepoint')
savepoint=group('same-name-savepoint','isolated-current')
diagnostics=group('coverage-unknown','derived-and-source')
tamper=group('derived-and-source','existing-v3-capsule')
capsules=group('existing-v3-capsule','actual-old-deadlock')
oldelle=group('actual-old-deadlock','author43-regressions')
legacy=r'''
await check('287-stored-old-v2-list-relation-capsules-replay-on-actual-v016',()=>{
 const manifest=load(resolve(here,'inputs/legacy-capsules-manifest.json')),results=[];
 assert.deepEqual(manifest.families,{'register-v2':3,'capture-v2':4,'append-list-v3':120,'relation-v3':160});
 for(const row of manifest.capsules){
  const file=resolve(here,row.file);assert.deepEqual(bind(file),{bytes:row.bytes,sha256:row.sha256});
  const raw=readFileSync(file,'utf8'),capsule=JSON.parse(raw);
  const actual=row.schemaVersion===3?sdk.replayCapsuleV3(raw):evidence.replayCapsule(raw);
  const prior=row.schemaVersion===3?old.replayCapsuleV3(raw):priorEvidence.replayCapsule(raw);
  assert.equal(actual.valid,true,row.file);assert.equal(prior.valid,true,row.file);
  const actualBody=clone(actual),priorBody=clone(prior);
  if(row.schemaVersion===2){assert.equal(actual.currentEngine,'0.1.6');assert.equal(prior.currentEngine,'0.1.5');assert.equal(actual.recordedEngine,row.engineVersion);assert.equal(prior.recordedEngine,row.engineVersion);delete actualBody.currentEngine;delete priorBody.currentEngine;}
  assert.deepEqual(actualBody,priorBody,'Complete replay result except the explicitly advanced currentEngine header must match v0.1.5: '+row.file);
  if(row.schemaVersion===3){assert.equal(actual.status,row.expectedStatus);
   const fixed=row.family==='append-list-v3'?sdk.replayListCapsuleV3(raw):sdk.replayRelationCapsuleV3(raw);assert.equal(fixed.valid,true,row.file);
   const exp=sdk.explainRegisterCycleV3(capsule.traceText,capsule.reportText);assert.equal(exp.subtype,null);assert.notEqual(exp.status,'explained');assert.equal(exp.scope.acceptsIsolationModels,false);
  }
  results.push({family:row.family,inputSha256:row.sha256,engineVersion:row.engineVersion,storedStatus:row.expectedStatus,valid:true,resultSha256:hash(JSON.stringify(actual))});
 }
 assert.equal(results.length,287);save('old-capsule-replay-results.json',results);
 return {storedCapsules:287,v2RegisterAndCapture:7,listV3:120,relationV3:160,sourceDatabaseReexecuted:false,relationCapsulesDerivedFromPreservedRealSql:true};
});
'''
example=r'''
await check('unchanged-shipped-example-original-capsule-and-separate-explanation-on-actual-v016',()=>{
 const script=resolve(here,'example-repository/examples/register-cycle-roundtrip.mjs');
 const child=spawnSync(process.execPath,[script,'--out-root',out],{cwd:here,encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:2*1024*1024});
 save('example-process.json',{exitCode:child.status,stdout:child.stdout||'',stderr:child.stderr||'',error:child.error?.name||null});
 assert.equal(child.error,undefined);assert.equal(child.status,0,child.stderr||child.stdout);
 const example=JSON.parse(child.stdout);assert.equal(example.version,'0.1.6');assert.equal(example.passed,true);assert.equal(example.selectedCycleSubtype,'G2-item');
 const directory=resolve(out,example.outputDirectory),capsuleText=readFileSync(resolve(directory,'original-v3.capsule.json'),'utf8');
 const capsule=JSON.parse(capsuleText),exp=load(resolve(directory,'cycle-explanation.json'));
 assert.equal(sdk.replayCapsuleV3(capsuleText).valid,true);assert.equal(sdk.verifyRegisterCycleExplanationV3(capsule.traceText,capsule.reportText,exp).valid,true);
 for(const row of example.files)assert.deepEqual(bind(resolve(directory,row.file)),{bytes:row.bytes,sha256:row.sha256});
 return {actualExampleRuntime:'0.1.6',originalExampleUnchanged:true,syntheticInput:true,newDatabaseExecution:false,originalCapsuleReplayed:true,separateExplanationVerified:true};
});
'''
footer=r'''
const dependenciesAfter=Object.fromEntries(Object.keys(prep.dependencies).map(name=>[name,bind(resolve(here,name))]));
receipt.frozenDependenciesUnchanged=JSON.stringify(dependenciesBefore)===JSON.stringify(dependenciesAfter);
receipt.mainSourceAndRuntimeUnchanged=mainRoot?Object.entries(mainBefore).every(([name,expected])=>JSON.stringify(bind(resolve(mainRoot,name)))===JSON.stringify(expected)):null;
receipt.mainSourceChecked=Boolean(mainRoot);receipt.mainSourceBindings=mainBefore;
receipt.frozenIndependentInputs=bind(resolve(here,'inputs/independent-inputs.json'));
receipt.checker=bind(fileURLToPath(import.meta.url));receipt.preparation=bind(resolve(here,'preparation.json'));
receipt.publicReviewDependencyCount=Object.keys(prep.dependencies).length;
receipt.passed=receipt.checks.every(row=>row.passed)&&receipt.frozenDependenciesUnchanged&&receipt.mainSourceAndRuntimeUnchanged!==false;
save('receipt.json',receipt);
console.log(JSON.stringify({passed:receipt.passed,groups:receipt.checks.length,failed:receipt.checks.filter(row=>!row.passed),receipt:relative(here,resolve(out,'receipt.json')).replaceAll('\\','/')}));
if(!receipt.passed)process.exitCode=1;
'''
text=header+helper+first+wrap+savepoint+legacy+diagnostics+tamper+capsules+oldelle+example+footer
with (OUT/'check.mjs').open('x',encoding='utf-8',newline='\n') as f:f.write(text)
print('Prepared 10-group actual-v0.1.6 checker from frozen independent rules/assertions, without executing product code.')
