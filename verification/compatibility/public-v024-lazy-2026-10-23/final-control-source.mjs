// Current runtime versus immutable actual-public24 expectations. No expected regeneration.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
const [runtimeArg,fixturesArg,outputArg,...extra]=process.argv.slice(2);
assert.ok(runtimeArg&&fixturesArg&&outputArg&&!extra.length,'Usage: CURRENT_RUNTIME AUTHENTIC24_FIXTURES NEW_OUTPUT');
const runtime=resolve(runtimeArg),fixtures=resolve(fixturesArg),output=resolve(outputArg);mkdirSync(output,{recursive:false});
const require=createRequire(import.meta.url),sha=raw=>createHash('sha256').update(raw).digest('hex'),canonical=value=>JSON.stringify(value,null,2)+'\n';
const checks=[],receipt={passed:false,kind:'current-sdk-genuine-public024-compatibility',node:process.version,
 originalFixtureManifestSha256:'f5bb94653aaa16ff98510a86f6585ebe1da2aabbdbd27f8576c80c6b7a8762dd',
 sourceCommit:'d583cb4f3cb1c4da4cc63e2ce255cc8834b08e2a',expectedRegenerated:false,
 actualDatabaseExecution:false,compilerExecuted:false,formalPerformanceMeasurement:false,independentAcceptance:false,checks};
const legacyCount=()=>Object.keys(require.cache).filter(name=>name.replaceAll('\\','/').includes('/legacy/v024/')&&name.endsWith('.cjs')).length;
function check(name,fn){fn();checks.push({name,passed:true});}
function originalResult(actual,expected,type,currentVersion){
 if(type==='v1'||type==='v2'){
  assert.equal(expected.currentEngine,'0.2.4');assert.equal(expected.recordedEngine,'0.2.4');
  assert.equal(actual.currentEngine,currentVersion);assert.equal(actual.recordedEngine,'0.2.4');
  assert.deepEqual(actual,{...expected,currentEngine:currentVersion});
 }else assert.deepEqual(actual,expected);
}
receipt.verificationResponseOnlyCurrentEngineDeltaAllowedFor=['v1','v2'];
receipt.originalReportsAndCapsulesRemainByteIdentical=true;
try{
 const rawManifest=readFileSync(resolve(fixtures,'manifest.json'));assert.equal(sha(rawManifest),receipt.originalFixtureManifestSha256);
 const manifest=JSON.parse(rawManifest);assert.equal(manifest.cases.length,15);assert.equal(manifest.actualPublishedProducer,true);
 const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href),evidence=await import(pathToFileURL(resolve(runtime,'evidence.mjs')).href);
 receipt.currentRuntimeVersion=sdk.version();receipt.currentCoreSha256=sha(readFileSync(resolve(runtime,'core.mjs')));
 check('normal current SDK import does not load frozen public24 CommonJS core',()=>assert.equal(legacyCount(),0));
 const point=manifest.cases.find(c=>c.name==='register-v1'),pointText=readFileSync(resolve(fixtures,point.input.file),'utf8');
 sdk.analyze(pointText);
 const actual=manifest.cases.find(c=>c.name==='orm-actual-1'),actualText=readFileSync(resolve(fixtures,actual.input.file),'utf8');
 const fresh=sdk.analyzeOrmProfileV3(actualText);assert.equal(fresh.engineVersion,sdk.version());
 assert.equal(sdk.verifyOrmProfileV3(actualText,fresh).valid,true);
 check('new generic and configured ORM analysis/verification do not load legacy core',()=>assert.equal(legacyCount(),0));
 const original=await import(pathToFileURL(resolve(fixtures,'producer-runtime/sdk.mjs')).href);
 const originalEvidence=await import(pathToFileURL(resolve(fixtures,'producer-runtime/evidence.mjs')).href);
 const originalOrm=await import(pathToFileURL(resolve(fixtures,'producer-runtime/orm-profile.mjs')).href);
 const replay=(s,e,row,text)=>row.type==='orm-profile'?s.replayOrmProfileCapsuleV3(text):row.type==='execution'?s.replayExecutionCapsuleV3(text):row.type==='v3'?s.replayCapsuleV3(text):e.replayCapsule(text);
 for(const row of manifest.cases){
  for(const key of ['input','report','capsule','producerReplay']){
   const record=row[key],raw=readFileSync(resolve(fixtures,record.file));assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);
  }
  const text=readFileSync(resolve(fixtures,row.capsule.file),'utf8'),cap=JSON.parse(text);
  const input=readFileSync(resolve(fixtures,row.input.file),'utf8'),report=JSON.parse(readFileSync(resolve(fixtures,row.report.file),'utf8'));
  const expected=JSON.parse(readFileSync(resolve(fixtures,row.producerReplay.file),'utf8'));
  check(row.name+' unchanged actual24 capsule reproduces original semantics and explicit current engine',()=>{
   assert.equal(cap.engineVersion,'0.2.4');originalResult(replay(sdk,evidence,row,text),expected,row.type,sdk.version());assert.equal(expected.valid,true);
  });
  check(row.name+' unknown engine remains rejected',()=>{
   const changed=structuredClone(cap);changed.engineVersion='9.9.9';assert.equal(replay(sdk,evidence,row,canonical(changed)).valid,false);
  });
  if(row.type==='orm-profile'){
   check(row.name+' old report verification uses exact original algorithm and budgets',()=>assert.deepEqual(sdk.verifyOrmProfileV3(input,report,row.requestOptions),originalOrm.verifyOrmProfileV3(input,report,row.requestOptions)));
   for(const [name,mutate]of [
    ['algorithm',c=>c.algorithm='unknown-host'],['source-algorithm',c=>c.sourceAlgorithm='unknown-source'],
    ['extra-field',c=>c.extra=true],['missing-budget',c=>delete c.budgets],
    ['source-binding',c=>c.sourceBindings.traceSha256='0'.repeat(64)],
    ['rehashed-options',c=>{c.requestOptionsText='{"maxAttempts":0}';c.requestOptionsSha256=sha(c.requestOptionsText);}],
    ['rehashed-result',c=>{const r=JSON.parse(c.reportText);r.status='forged';c.reportText=JSON.stringify(r);c.reportSha256=sha(c.reportText);}],
   ])check(row.name+' rejects '+name+' exactly as original public host',()=>{
    const changed=structuredClone(cap);mutate(changed);const encoded=canonical(changed),expected=originalOrm.replayOrmProfileCapsuleV3(encoded);
    assert.equal(expected.valid,false);assert.deepEqual(sdk.replayOrmProfileCapsuleV3(encoded),expected);
   });
   check(row.name+' refuses noncanonical suffix and duplicate header',()=>{
    for(const changed of [text+' ',text.replace(/\n}\n$/,'\n,"engineVersion":"0.2.4"}\n')])assert.equal(sdk.replayOrmProfileCapsuleV3(changed).valid,false);
   });
  }else if(row.type==='v3')check(row.name+' old report verifies with original v3 rules',()=>assert.deepEqual(sdk.verifyV3(input,report),original.verifyV3(input,report)));
  else if(row.type!=='execution')check(row.name+' old report verifies with original v1/v2 rules',()=>originalResult(sdk.replayReport(input,report),original.replayReport(input,report),row.type,sdk.version()));
 }
 for(const row of manifest.cases.filter(c=>['orm-actual-1','orm-actual-2','orm-synthetic-reduce'].includes(c.name))){
  check(row.name+' actual current CLI returns the exact original public24 replay',()=>{
   const child=spawnSync(process.execPath,[resolve(runtime,'moontxnwitness.mjs'),'replay-orm-profile-v3',resolve(fixtures,row.capsule.file)],{encoding:'utf8',timeout:120000,maxBuffer:128*1024*1024});
   writeFileSync(resolve(output,row.name+'.cli.stdout.json'),child.stdout??'',{flag:'wx'});writeFileSync(resolve(output,row.name+'.cli.stderr.log'),child.stderr??'',{flag:'wx'});
   assert.equal(child.error,undefined);assert.equal(child.status,0);assert.deepEqual(JSON.parse(child.stdout),JSON.parse(readFileSync(resolve(fixtures,row.producerReplay.file),'utf8')));
  });
 }
 check('only old ORM calls loaded the fixed two CommonJS modules',()=>assert.equal(legacyCount(),2));
 check('zero budget and unsupported business metadata retain original values',()=>{
  const zero=manifest.cases.find(c=>c.name==='orm-synthetic-zero-budget'),report=JSON.parse(readFileSync(resolve(fixtures,zero.report.file),'utf8'));
  assert.equal(report.result.reduction.semanticCandidateChecks,0);assert.equal(report.result.reduction.oneMinimal,false);
  const meta=manifest.cases.find(c=>c.name==='orm-unsupported-business-metadata'),input=JSON.parse(readFileSync(resolve(fixtures,meta.input.file),'utf8'));
  assert.equal(input.businessValue.version,'0.2.0');assert.equal(input.businessValue.text,'吴芳芳\\n/😀');
 });
 receipt.passed=true;receipt.checkCount=checks.length;receipt.originalProducerFamilies=15;receipt.normalAnalysisLegacyModulesLoaded=0;receipt.oldOrmLegacyModulesLoaded=legacyCount();
}catch(error){receipt.failure={name:error.name,message:error.message};process.exitCode=1;}
writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify({passed:receipt.passed,node:process.version,currentRuntimeVersion:receipt.currentRuntimeVersion,checks:checks.length,failure:receipt.failure??null}));
