import {readFileSync,mkdirSync,mkdtempSync,cpSync,copyFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..');
const public030=await import('../dist/legacy-v030.mjs');public030.verifyPublic030Runtime();
const original=await import(pathToFileURL(resolve(root,'dist/legacy/v030/sdk.mjs')).href);
const current=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')).href);
const oldEvidence=await import(pathToFileURL(resolve(root,'dist/legacy/v030/evidence.mjs')).href);
const newEvidence=await import(pathToFileURL(resolve(root,'dist/evidence.mjs')).href);
assert.equal(original.version(),'0.3.0');assert.equal(current.version(),JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version);
const read=p=>readFileSync(resolve(root,p),'utf8');
let checks=0;
for(const fixture of ['examples/write-skew.json','examples/consistent.json']){
 const history=read(fixture),report=original.analyzeWithOptions(history);
 assert.equal(current.replayReport(history,report).valid,true);checks++;
 const capsule=oldEvidence.makeCapsule(history,report);
 assert.equal(newEvidence.replayCapsule(capsule).valid,true);checks++;
 const changed=structuredClone(report);changed.status=report.status==='violation'?'consistent':'violation';
 assert.equal(current.replayReport(history,changed).valid,false);checks++;
}
for(const fixture of ['examples/list-cycle.json','examples/relation-source-closure.json','fixtures/classification-v3/source-closed-noisy-g2.json']){
 const trace=read(fixture),report=original.analyzeV3(trace);
 assert.equal(current.verifyV3(trace,report).valid,true);checks++;
 assert.equal(current.replayCapsuleV3(original.makeCapsuleV3(trace,report)).valid,true);checks++;
}
for(const fixture of ['fixtures/classification-models-v3/list-skew.json','fixtures/classification-models-v3/empty-register.json']){
 const source=read(fixture),report=original.classifyModelsV3(source);
 assert.equal(current.verifyModelsClassificationV3(source,report).valid,true);checks++;
 assert.equal(current.replayModelsClassificationCapsuleV3(original.makeModelsClassificationCapsuleV3(source)).valid,true);checks++;
 const changed=structuredClone(report);changed.status='forged-conclusion';
 assert.equal(current.verifyModelsClassificationV3(source,changed).valid,false);checks++;
}
const trace=read('fixtures/classification-v3/source-closed-noisy-g2.json'),report=original.classifyV3(trace);
assert.equal(current.verifyClassificationV3(trace,report).valid,true);checks++;
assert.equal(current.replayClassificationCapsuleV3(original.makeClassificationCapsuleV3(trace)).valid,true);checks++;
const diagnosis=original.diagnoseV3(trace);
assert.equal(current.verifyDiagnosisV3(trace,diagnosis).valid,true);checks++;
const {routeLegacyV030}=await import('../dist/legacy-v030.mjs');
assert.equal(routeLegacyV030('verify-v3',[trace,{version:'unrecognized',schemaVersion:3,business:{version:'0.3.0'}}],current.version()).matched,false);checks++;
assert.equal(routeLegacyV030('not-a-method',[],current.version()).matched,false);checks++;
const legacyTrace=read('fixtures/compat-v020-list-wrapper/list-forwarded-lifecycle.trace.json');
const legacyReport=JSON.parse(read('fixtures/compat-v020-list-wrapper/list-forwarded-lifecycle.report.json'));
assert.equal(current.verifyV3(legacyTrace,legacyReport).valid,true);checks++;
assert.equal(current.replayCapsuleV3(read('fixtures/compat-v020-list-wrapper/list-forwarded-lifecycle.capsule.json')).valid,true);checks++;
const changedLegacy=structuredClone(legacyReport);changedLegacy.coverage.gaps[0].message+=' forged';
assert.equal(current.verifyV3(legacyTrace,changedLegacy).valid,false);checks++;
const work=resolve(root,'artifacts/public030-corruption');mkdirSync(work,{recursive:true});
const copy=mkdtempSync(resolve(work,'run-'));
for(const name of ['legacy-v030.mjs','legacy-v028-policy.mjs','legacy-v028-binding.mjs'])copyFileSync(resolve(root,'dist',name),resolve(copy,name));
cpSync(resolve(root,'dist/legacy/v030'),resolve(copy,'legacy/v030'),{recursive:true});
const isolated=await import(pathToFileURL(resolve(copy,'legacy-v030.mjs')).href);isolated.verifyPublic030Runtime();checks++;
const originalHash=createHash('sha256').update(readFileSync(resolve(root,'dist/legacy/v030/core.mjs'))).digest('hex');
writeFileSync(resolve(copy,'legacy/v030/core.mjs'),'corrupt');
assert.throws(()=>isolated.verifyPublic030Runtime());checks++;
assert.equal(createHash('sha256').update(readFileSync(resolve(root,'dist/legacy/v030/core.mjs'))).digest('hex'),originalHash);checks++;
console.log(JSON.stringify({passed:true,checks,publicVersion:'0.3.0',currentVersion:current.version()}));
