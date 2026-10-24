// Host checks reuse exact first real source packages. No PG/Moon/performance run.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=resolve(process.env.MTW_MODEL_HOST_OUTPUT||resolve(root,'artifacts/model-profile-sdk-'+randomUUID()));mkdirSync(output,{recursive:true});
const sha=raw=>createHash('sha256').update(raw).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const fixture=resolve(root,'verification/model-profile-v3/v027-initial/database');
const sources=Object.fromEntries(['list-values','list-rollback','list-write-skew','list-unknown-sql','relation-crud','relation-predicate','relation-rollback','relation-write-skew','relation-zero-write','relation-partial-fetch']
  .map(name=>[name,readFileSync(resolve(fixture,name,'profile-source.json'),'utf8')]));
const cases=[];function test(name,action){try{action();cases.push({name,passed:true});}catch(error){cases.push({name,passed:false,error:String(error.message)});}}
const main=sources['list-write-skew'],baseline=sdk.analyzeModelProfileV3(main),capsule=sdk.makeModelProfileCapsuleV3(main);
const parsed=JSON.parse(capsule);writeFileSync(resolve(output,'original.capsule.json'),capsule,{flag:'wx'});
function resign(value){
  value.requestOptionsSha256=sha(value.requestOptionsText);value.reportSha256=sha(value.reportText);
  value.sourceBindings.envelopeSha256=sha(value.envelopeText);
  const source=JSON.parse(value.envelopeText);
  for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])value.sourceBindings[name+'Sha256']=sha(source[name+'Text']);
  return canonical(value);
}
function mutation(name,change){test(name,()=>{const copy=structuredClone(parsed);change(copy);assert.equal(sdk.replayModelProfileCapsuleV3(canonical(copy)).valid,false);});}
for(const[name,text]of Object.entries(sources))test('original '+name+' report and full capsule',()=>{
  const report=sdk.analyzeModelProfileV3(text),unknown=['list-unknown-sql','relation-zero-write','relation-partial-fetch'].includes(name);
  assert.equal(report.status,unknown?'inconclusive':name.endsWith('write-skew')?'violation':'consistent');
  assert.equal(report.analysisCoverageAccepted,!unknown);assert.equal(sdk.verifyModelProfileV3(text,report).valid,true);
  const replay=sdk.replayModelProfileCapsuleV3(sdk.makeModelProfileCapsuleV3(text));assert.equal(replay.valid,true);assert.equal(replay.envelopeText,text);
});
test('current exact core and host bytes identified',()=>{
  assert.equal(baseline.engine.coreSha256,sha(readFileSync(resolve(root,'dist/core.mjs'))));
  assert.equal(baseline.engine.hostSha256,sha(readFileSync(resolve(root,'dist/model-profile.mjs'))));
});
test('original generic coverage remains incomplete',()=>assert.equal(baseline.result.originalDiagnosticCoverage.complete,false));
test('source envelope and four original hashes agree',()=>{
  const source=JSON.parse(main);assert.equal(baseline.sourceBindings.envelopeSha256,sha(main));
  for(const name of ['trace','sourceJournal','lifecycle','journalIndex'])assert.equal(baseline.sourceBindings[name+'Sha256'],sha(source[name+'Text']));
});
test('extra report field rejected',()=>assert.equal(sdk.verifyModelProfileV3(main,{...baseline,extra:true}).valid,false));
test('missing report field rejected',()=>{const x=structuredClone(baseline);delete x.scope;assert.equal(sdk.verifyModelProfileV3(main,x).valid,false);});
test('changed result rejected',()=>{const x=structuredClone(baseline);x.result.status='consistent';assert.equal(sdk.verifyModelProfileV3(main,x).valid,false);});
test('changed raw-source hash rejected',()=>{const x=structuredClone(baseline);x.sourceBindings.traceSha256='0'.repeat(64);assert.equal(sdk.verifyModelProfileV3(main,x).valid,false);});
test('changed explicit search options rejected',()=>assert.equal(sdk.verifyModelProfileV3(main,baseline,{maxStates:0}).valid,false));
test('zero search budget is visible',()=>{const r=sdk.analyzeModelProfileV3(main,{maxStates:0});assert.equal(r.status,'inconclusive');assert.equal(r.analysisCoverageAccepted,true);assert.equal(r.result.analysis.execution.metrics.complete,false);});
for(const[value,label]of [[{maxStates:-1},'negative'],[{maxStates:100001},'excessive'],[{maxStates:.5},'fractional'],[{maxAttempts:1},'old register option'],[JSON.parse('{"__proto__":1}'),'prototype-like'],[null,'null']])
  test('unsupported options '+label,()=>assert.throws(()=>sdk.analyzeModelProfileV3(main,value)));
for(const[field,value]of [['format','unknown'],['algorithm','unknown'],['sourceAlgorithm','unknown'],['profile','unknown'],['schemaVersion',2],['tool','unknown']])mutation('capsule unknown '+field,x=>x[field]=value);
mutation('capsule unknown core engine',x=>x.engine.coreSha256='0'.repeat(64));
mutation('capsule unknown host engine',x=>x.engine.hostSha256='0'.repeat(64));
mutation('capsule extra field',x=>x.extra=true);mutation('capsule missing field',x=>delete x.budgets);
// Missing one actual required field, separately from the extra/unknown test.
test('capsule omitted report rejected',()=>{const x=structuredClone(parsed);delete x.reportText;assert.equal(sdk.replayModelProfileCapsuleV3(canonical(x)).valid,false);});
mutation('capsule modified budget',x=>x.budgets.exactSearchTransactions=12);
mutation('capsule invalid report SHA',x=>x.reportSha256='f'.repeat(64));
test('resigned changed conclusion refused',()=>{const x=structuredClone(parsed);const report=JSON.parse(x.reportText);report.status=report.result.status='consistent';x.reportText=JSON.stringify(report);assert.equal(sdk.replayModelProfileCapsuleV3(resign(x)).valid,false);});
test('resigned changed options refused',()=>{const x=structuredClone(parsed);x.requestOptionsText='{"maxStates":0}';assert.equal(sdk.replayModelProfileCapsuleV3(resign(x)).valid,false);});
test('resigned original sequence modification refused',()=>{const x=structuredClone(parsed),source=JSON.parse(x.envelopeText),trace=JSON.parse(source.traceText);trace.events[1].seq=99;source.traceText=JSON.stringify(trace);x.envelopeText=JSON.stringify(source);assert.equal(sdk.replayModelProfileCapsuleV3(resign(x)).valid,false);});
test('resigned original capture field change refused',()=>{const x=structuredClone(parsed),source=JSON.parse(x.envelopeText),trace=JSON.parse(source.traceText);trace.scope.exclusiveWriters=true;source.traceText=JSON.stringify(trace);x.envelopeText=JSON.stringify(source);assert.equal(sdk.replayModelProfileCapsuleV3(resign(x)).valid,false);});
test('duplicate capsule fields refused',()=>assert.equal(sdk.replayModelProfileCapsuleV3(capsule.replace('{\n','{\n  "schemaVersion": 1,\n')).valid,false));
test('noncanonical equivalent capsule bytes refused',()=>assert.equal(sdk.replayModelProfileCapsuleV3(capsule.replace('"schemaVersion": 1,','"schemaVersion": 1.0,')).valid,false));
test('unknown business-looking version retained exactly',()=>{const input=JSON.parse(main);input.unknownBusiness={version:'0.2.0',value:'😀'};const raw=JSON.stringify(input),r=sdk.replayModelProfileCapsuleV3(sdk.makeModelProfileCapsuleV3(raw));assert.equal(r.valid,true);assert.equal(r.status,'inconclusive');assert.equal(r.envelopeText,raw);});
test('source-closed reduction explicitly unavailable',()=>assert.equal(baseline.scope.sourceClosedReductionAvailable,false));
const cli=(args)=>spawnSync(process.execPath,[resolve(root,'dist/moontxnwitness.mjs'),...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:16*1024*1024,timeout:30000});
test('CLI original-source analysis and capsule',()=>{
  const r=cli(['model-profile-v3',resolve(fixture,'list-write-skew/profile-source.json'),'--output',resolve(output,'cli.report.json'),'--capsule',resolve(output,'cli.capsule.json')]);
  assert.equal(r.status,1,r.stderr);assert.equal(JSON.parse(readFileSync(resolve(output,'cli.report.json'),'utf8')).status,'violation');
});
test('CLI full capsule replay',()=>{const r=cli(['replay-model-profile-v3',resolve(output,'cli.capsule.json')]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).valid,true);});
test('CLI report verification',()=>{const r=cli(['verify-model-profile-v3',resolve(fixture,'list-write-skew/profile-source.json'),resolve(output,'cli.report.json')]);assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).valid,true);});
test('CLI refuses to overwrite original source',()=>{const path=resolve(fixture,'list-write-skew/profile-source.json'),before=sha(readFileSync(path));const r=cli(['model-profile-v3',path,'--output',path]);assert.notEqual(r.status,0);assert.equal(sha(readFileSync(path)),before);});
const receipt={output,passed:cases.every(x=>x.passed),cases:cases.length,checks:cases,actualDatabaseExecution:false,formalPerformanceMeasurement:false,
  sourceClosedReductionClaimed:false,compiledCoreSha256:sha(readFileSync(resolve(root,'dist/core.mjs'))),hostSourceSha256:sha(readFileSync(resolve(root,'dist/model-profile.mjs')))};
writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify({...receipt,checks:undefined,failures:cases.filter(x=>!x.passed)}));
if(!receipt.passed)process.exitCode=1;
