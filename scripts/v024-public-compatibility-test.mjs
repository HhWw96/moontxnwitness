// Actual public24 contracts. Expects immutable fixtures from the original public producer.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync,cpSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {produceV024} from './generate-v024-compatibility.mjs';
const [providerArg,fixturesArg,expectedSource,outArg,...extra]=process.argv.slice(2);
assert.ok(providerArg&&fixturesArg&&/^[0-9a-f]{40}$/.test(expectedSource??'')&&outArg&&!extra.length,
 'Usage: AUTHENTIC_PROVIDER ORIGINAL_FIXTURES EXPECTED_PUBLIC_SOURCE NEW_OUTPUT');
const provider=resolve(providerArg),fixtureRoot=resolve(fixturesArg),out=resolve(outArg);mkdirSync(out,{recursive:false});
const canonical=x=>JSON.stringify(x,null,2)+'\n',sha=x=>createHash('sha256').update(x).digest('hex');
const checks=[],receipt={passed:false,kind:'actual-public-v024-producer-contracts',actualPublishedProducer:true,
 authenticPublic24FixturesGenerated:true,developmentOnly:false,expectedSourceCommit:expectedSource,
 actualDatabaseExecutedHere:false,compilerExecutedHere:false,authorDistRead:false,
 futureSdkIntegrationImplemented:false,independentAcceptance:false,checks};
function check(name,fn){fn();checks.push({name,passed:true});}
async function asyncCheck(name,fn){await fn();checks.push({name,passed:true});}
try{
 const manifestText=readFileSync(resolve(fixtureRoot,'manifest.json'),'utf8'),manifest=JSON.parse(manifestText);
 receipt.fixtureManifestSha256=sha(manifestText);
 const actualProvider=JSON.parse(readFileSync(resolve(provider,'provider.json'),'utf8'));
 await asyncCheck('authentic mode refuses a different explicit public source before emission',async()=>{
  await assert.rejects(()=>produceV024(provider,resolve(out,'must-not-match-wrong-source'),{expectedSource:'0'.repeat(40)}));
  assert.equal(existsSync(resolve(out,'must-not-match-wrong-source')),false);
 });
 const sdk=await import(pathToFileURL(resolve(fixtureRoot,'producer-runtime/sdk.mjs')).href);
 const evidence=await import(pathToFileURL(resolve(fixtureRoot,'producer-runtime/evidence.mjs')).href);
 check('actual workflow has15 naturally generated original public24 capsules',()=>{
  assert.equal(manifest.cases.length,15);assert.equal(manifest.actualPublishedProducer,true);assert.equal(sdk.version(),'0.2.4');
  for(const row of manifest.cases){
   for(const field of ['input','report','capsule','producerReplay']){
    const record=row[field],raw=readFileSync(resolve(fixtureRoot,record.file));
    assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);
   }
   if(row.type!=='orm-profile'){
    const capsule=readFileSync(resolve(fixtureRoot,row.capsule.file),'utf8');
    const replay=row.type==='execution'?sdk.replayExecutionCapsuleV3(capsule):row.type==='v3'?sdk.replayCapsuleV3(capsule):evidence.replayCapsule(capsule);
    assert.deepEqual(replay,JSON.parse(readFileSync(resolve(fixtureRoot,row.producerReplay.file),'utf8')));assert.equal(replay.valid,true);
   }
  }
 });
 check('actual manifest binds completed public receipt and exact original runtime without rewritten headers',()=>{
  assert.equal(manifest.format,'moontxnwitness-actual-public-producer-fixtures/v1');
  assert.equal(manifest.actualPublishedProducer,true);assert.equal(manifest.authorDistRead,false);
  assert.equal(manifest.sourceCommit,expectedSource);assert.equal(manifest.expectedSourceCommit,expectedSource);
  assert.equal(manifest.developmentProbe,false);assert.equal(manifest.headerRewriting,false);
  assert.equal(actualProvider.actualPublishedProducer,true);assert.equal(actualProvider.authorDistRead,false);
  assert.equal(manifest.providerSha256,sha(readFileSync(resolve(provider,'provider.json'))));
  assert.equal(manifest.publicationReceiptSha256,actualProvider.publicationReceiptSha256);
  assert.deepEqual(manifest.minimalOrmReplayFiles,['core.mjs','orm-profile.mjs']);
  assert.deepEqual(manifest.fullSdkEsmFiles,['capture-core.mjs','core.mjs','evidence.mjs','orm-profile.mjs','sdk.mjs']);
  for(const [name,record]of Object.entries(manifest.producerFiles)){
   const raw=readFileSync(resolve(fixtureRoot,record.file));assert.equal(raw.length,record.bytes);assert.equal(sha(raw),record.sha256);
   assert.deepEqual({bytes:record.bytes,sha256:record.sha256},actualProvider.runtime[name]);
  }
 });
 const minimal=resolve(out,'only-two-original-modules');mkdirSync(minimal);
 for(const name of ['core.mjs','orm-profile.mjs'])copyFileSync(resolve(fixtureRoot,'producer-runtime',name),resolve(minimal,name));
 const old=await import(pathToFileURL(resolve(minimal,'orm-profile.mjs')).href);
 // This route-only control is not a stable future SDK implementation or acceptance.
 const routeOld=text=>{const value=JSON.parse(text);
  if(value?.format==='moontxnwitness-orm-profile/v1'&&value.engineVersion==='0.2.4')return old.replayOrmProfileCapsuleV3(text);
  return {valid:false,reason:'unimplemented-future-route'};
 };
 for(const row of manifest.cases.filter(c=>c.type==='orm-profile')){
  const capsule=readFileSync(resolve(fixtureRoot,row.capsule.file),'utf8'),cap=JSON.parse(capsule);
  const input=readFileSync(resolve(fixtureRoot,row.input.file),'utf8'),report=JSON.parse(readFileSync(resolve(fixtureRoot,row.report.file),'utf8'));
  const expected=JSON.parse(readFileSync(resolve(fixtureRoot,row.producerReplay.file),'utf8'));
  check(row.name+' exact two-module original replay and route-only control',()=>{
   assert.deepEqual(old.replayOrmProfileCapsuleV3(capsule),expected);assert.deepEqual(routeOld(capsule),expected);assert.equal(expected.valid,true);
   assert.equal(old.verifyOrmProfileV3(input,report,row.requestOptions).valid,true);
   assert.equal(cap.engineVersion,'0.2.4');assert.equal(expected.envelopeText,input);
  });
  for(const [name,mutate]of [
   ['engine',c=>c.engineVersion='9.9.9'],['algorithm',c=>c.algorithm='future-host'],
   ['source-algorithm',c=>c.sourceAlgorithm='future-source'],['extra-field',c=>c.extra=true],
   ['missing-budget',c=>delete c.budgets],['source-binding',c=>c.sourceBindings.traceSha256='0'.repeat(64)],
   ['rehashed-options',c=>{c.requestOptionsText='{"maxAttempts":0}';c.requestOptionsSha256=sha(c.requestOptionsText);}],
   ['rehashed-result',c=>{const value=JSON.parse(c.reportText);value.status='forged';c.reportText=JSON.stringify(value);c.reportSha256=sha(c.reportText);}],
  ])check(row.name+' refuses '+name,()=>{const changed=structuredClone(cap);mutate(changed);assert.equal(old.replayOrmProfileCapsuleV3(canonical(changed)).valid,false);});
  check(row.name+' refuses noncanonical suffix and duplicate header',()=>{
   assert.equal(old.replayOrmProfileCapsuleV3(capsule+' ').valid,false);
   assert.equal(old.replayOrmProfileCapsuleV3(capsule.replace(/\n}\n$/,'\n,"engineVersion":"0.2.4"}\n')).valid,false);
  });
 }
 check('zero candidate budget keeps complete original facts and no minimality',()=>{
  const row=manifest.cases.find(c=>c.name==='orm-synthetic-zero-budget'),report=JSON.parse(readFileSync(resolve(fixtureRoot,row.report.file),'utf8'));
  assert.equal(report.result.reduction.oneMinimal,false);assert.equal(report.result.reduction.semanticCandidateChecks,0);
 });
 check('business version/Unicode and explicitly mismatched unknown sources stay unchanged',()=>{
  const row=manifest.cases.find(c=>c.name==='orm-unsupported-business-metadata');
  const input=readFileSync(resolve(fixtureRoot,row.input.file),'utf8');assert.equal(JSON.parse(input).businessValue.version,'0.2.0');
  assert.equal(JSON.parse(input).businessValue.text,'吴芳芳\\n/😀');
  const unknown=manifest.cases.find(c=>c.name==='orm-unmatched-unknown-commit');
  const replay=JSON.parse(readFileSync(resolve(fixtureRoot,unknown.producerReplay.file),'utf8'));
  assert.equal(replay.status,'inconclusive');assert.equal(replay.analysisCoverageAccepted,false);assert.equal(unknown.inputOrigin.originalInputUnchanged,false);
 });
 await asyncCheck('runtime corruption rejected before any fixture emission',async()=>{
  const damaged=resolve(out,'damaged-provider');cpSync(provider,damaged,{recursive:true});
  const path=resolve(damaged,'runtime/core.mjs');writeFileSync(path,Buffer.concat([readFileSync(path),Buffer.from(' ')]));
  await assert.rejects(()=>produceV024(damaged,resolve(out,'must-not-exist'),{expectedSource}));
  assert.equal(existsSync(resolve(out,'must-not-exist')),false);
 });
 await asyncCheck('existing frozen outputs never overwritten',async()=>{
  const before=readFileSync(resolve(fixtureRoot,'manifest.json'));
  await assert.rejects(()=>produceV024(provider,fixtureRoot,{expectedSource}));
  assert.deepEqual(readFileSync(resolve(fixtureRoot,'manifest.json')),before);
 });
 assert.equal(checks.length,77);receipt.passed=true;receipt.checkCount=checks.length;receipt.publicCapsules=15;receipt.minimalRuntimeFiles=2;
}catch(error){receipt.failure={name:error.name,message:error.message};process.exitCode=1;}
writeFileSync(resolve(out,'receipt.json'),canonical(receipt),{flag:'wx'});
console.log(JSON.stringify({passed:receipt.passed,checks:checks.length,actualPublishedProducer:true,authenticPublic24FixturesGenerated:true,
 expectedSourceCommit:expectedSource,failure:receipt.failure??null}));
