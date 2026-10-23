// Offline configured-profile consumer. No database, compiler, download or fixture rewrite.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve,dirname,basename} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),args=process.argv.slice(2),options={};
for(let i=0;i<args.length;i+=2){assert.ok(['--runtime','--out-root'].includes(args[i]));assert.ok(args[i+1]);assert.equal(options[args[i]],undefined);options[args[i]]=resolve(args[i+1]);}
const runtime=options['--runtime']||resolve(root,'dist'),outRoot=options['--out-root']||resolve(root,'artifacts/orm-profile-demo');
mkdirSync(outRoot,{recursive:true});const out=mkdtempSync(resolve(outRoot,'orm-profile-'));
const hash=text=>createHash('sha256').update(text).digest('hex');
const bound=[];
const save=(name,text)=>{const path=resolve(out,name);writeFileSync(path,text,{flag:'wx'});bound.push({file:name,bytes:Buffer.byteLength(text),sha256:hash(text)});};
const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
const sourceRoot=resolve(root,'verification/configured-user-profile/v024-initial');
const fixtureReceipt=JSON.parse(readFileSync(resolve(sourceRoot,'manifest.json'),'utf8'));
let checks=0;
for(const producer of ['producer-first','producer-second']){
  const name=producer+'/profile-source.json',source=readFileSync(resolve(sourceRoot,name),'utf8');
  assert.equal(hash(source),fixtureReceipt.files[name].sha256);
  const report=sdk.analyzeOrmProfileV3(source);
  assert.equal(report.analysisCoverageAccepted,true);assert.equal(report.status,'consistent');
  assert.equal(report.result.originalDiagnosticCoverage.complete,false);assert.equal(report.result.originalSourceProof.history,null);
  const capsule=sdk.makeOrmProfileCapsuleV3(source),replay=sdk.replayOrmProfileCapsuleV3(capsule);
  assert.equal(replay.valid,true);assert.equal(replay.envelopeText,source);checks+=2;
  save(producer+'.capsule.json',capsule);
}
const syntheticRoot=resolve(root,'fixtures/orm-profile-v3/synthetic-nonrepeatable-first');
const synthetic=readFileSync(resolve(syntheticRoot,'profile-source.json'),'utf8');
const syntheticManifest=JSON.parse(readFileSync(resolve(syntheticRoot,'manifest.json'),'utf8'));
assert.equal(syntheticManifest.actualPostgresAnomaly,false);assert.equal(hash(synthetic),syntheticManifest.envelopeSha256);
const reduced=sdk.reduceOrmProfileV3(synthetic),result=reduced.result.reduction;
assert.equal(reduced.status,'reduced');assert.equal(reduced.result.originalEnvelopeText,synthetic);
assert.equal(result.sourceClosure.complete,true);assert.equal(result.report.complete,true);assert.equal(result.report.status,'violation');
assert.equal(result.reducedHistory.transactions.length,3);assert.equal(result.oneMinimal,true);assert.equal(result.checks,7);
assert.equal(reduced.result.finalReplay.valid,true);assert.equal(sdk.verifyOrmProfileV3(synthetic,reduced).valid,true);checks+=2;
save('synthetic-closed-mini.json',JSON.stringify(result.reducedHistory,null,2)+'\n');
save('synthetic-closed-report.json',JSON.stringify(reduced,null,2)+'\n');
const capsule=sdk.makeOrmProfileReductionCapsuleV3(synthetic),replay=sdk.replayOrmProfileCapsuleV3(capsule);
assert.equal(replay.valid,true);assert.deepEqual(replay.report,reduced);checks++;
save('synthetic-closed.capsule.json',capsule);
const receipt={schema:1,passed:true,checks,version:sdk.version(),actualDatabaseExecution:false,
  formalPerformanceMeasurement:false,originalPacketsFromRetainedActualDatabaseRuns:2,
  syntheticAnomalyIsActualDatabaseExecution:false,syntheticOriginalTransactions:4,syntheticReducedTransactions:3,
  sourceClosureComplete:true,oneMinimal:true,semanticCandidateChecks:result.semanticCandidateChecks,
  cachedCandidateLookups:result.cachedCandidateLookups,candidateAttempts:result.candidateAttempts,
  maxSemanticCandidateChecks:result.maxChecks,verificationPasses:result.verificationPasses,
  originalDiagnosticsRemainPartial:true,scope:'Offline recomputation of two retained actual producer packets plus an explicitly synthetic closed anomaly; no complete ORM/application acceptance.',
  runtimeSha256:Object.fromEntries(['core.mjs','capture-core.mjs','sdk.mjs','orm-profile.mjs'].map(name=>[name,hash(readFileSync(resolve(runtime,name)))])),
  files:bound,outputDirectory:basename(out)};
writeFileSync(resolve(out,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(receipt,null,2));
