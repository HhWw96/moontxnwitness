// Synthetic host workflows over the actual compiled category core; no database run.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=resolve(process.env.MTW_CLASSIFICATION_HOST_OUTPUT||resolve(root,'artifacts/classification-host-'+randomUUID()));
mkdirSync(output,{recursive:true});
const sha=raw=>createHash('sha256').update(raw).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n';
const load=name=>readFileSync(resolve(root,'fixtures/classification-v3',name+'.json'),'utf8');
const main=load('source-closed-noisy-g2'),baseline=sdk.classifyV3(main),capsule=sdk.makeClassificationCapsuleV3(main);
const parsed=JSON.parse(capsule),cases=[];
function test(name,action){try{action();cases.push({name,passed:true});}catch(error){cases.push({name,passed:false,error:String(error.message)});}}
function mutation(name,change){test(name,()=>{const copy=structuredClone(parsed);change(copy);assert.equal(sdk.replayClassificationCapsuleV3(canonical(copy)).valid,false);});}
function resign(value){
  value.sourceBindings={sourceSha256:sha(value.sourceText),traceSha256:sha(value.sourceText)};
  value.requestOptionsSha256=sha(value.requestOptionsText);value.reportSha256=sha(value.reportText);
  return canonical(value);
}
writeFileSync(resolve(output,'original.capsule.json'),capsule,{flag:'wx'});
for(const[fixture,category]of [['g0','G0'],['g1c','G1c'],['source-closed-noisy-g2','G2-item']])test('actual core '+category+' proof and full capsule',()=>{
  const source=load(fixture),report=sdk.classifyV3(source,{categories:[category]});
  assert.equal(report.status,'refuted');assert.equal(report.result.rules[category].status,'refuted');
  assert.equal(report.scope.isolationModelsAccepted,false);assert.equal(report.result.acceptsIsolationModels,false);
  assert.equal(sdk.verifyClassificationV3(source,report).valid,true);
  const replay=sdk.replayClassificationCapsuleV3(sdk.makeClassificationCapsuleV3(source,{categories:[category]}));
  assert.equal(replay.valid,true);assert.equal(replay.report.originalSourceText,source);
});
test('G1c-only request includes pure G0 logical closure',()=>{
  const report=sdk.classifyV3(load('g0'),{categories:['G1c']});
  assert.equal(report.status,'refuted');assert.equal(report.result.rules.G1c.evidence.specificCategory,'G0');
});
test('compatibility concerns requested category only',()=>{
  const report=sdk.classifyV3(main,{categories:['G0']});
  assert.equal(report.status,'checked-compatible');assert.equal(report.scope.isolationModelsAccepted,false);
});
test('raw business version string is never migrated',()=>{
  assert.equal(baseline.result.normalized.history.initial.x,'0.2.0');
  assert.equal(JSON.parse(main).events[0].initial.x,'0.2.0');
});
test('current exact core/host bytes bound',()=>{
  assert.equal(baseline.engine.coreSha256,sha(readFileSync(resolve(root,'dist/core.mjs'))));
  assert.equal(baseline.engine.hostSha256,sha(readFileSync(resolve(root,'dist/classification.mjs'))));
});
test('complete original source bytes retained',()=>{
  assert.equal(baseline.originalSourceText,main);assert.equal(baseline.sourceBindings.sourceSha256,sha(main));
});
for(const name of ['missing-source','unknown-sql'])test('partial '+name+' stays inconclusive and replays',()=>{
  const source=load(name),report=sdk.classifyV3(source);
  assert.equal(report.status,'inconclusive');assert.equal(report.result.dependencyGraphComplete,false);
  const replay=sdk.replayClassificationCapsuleV3(sdk.makeClassificationCapsuleV3(source));
  assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');assert.equal(replay.report.originalSourceText,source);
});
test('zero per-category search budget is visible',()=>{
  const report=sdk.classifyV3(main,{maxStates:0,maxEdgeChecks:0});
  assert.equal(report.status,'inconclusive');assert.equal(report.result.rules['G2-item'].status,'unknown');
  assert.equal(report.result.rules['G2-item'].states,0);assert.equal(report.result.rules['G2-item'].edgeChecks,0);
});
test('reduction keeps exact requested category and source writer',()=>{
  const report=sdk.reduceClassificationV3(main,{category:'G2-item'});
  assert.equal(report.status,'reduced');assert.deepEqual(new Set(report.result.removed),new Set(['N']));
  assert.equal(report.result.report.rules['G2-item'].status,'refuted');assert.equal(report.result.oneMinimal,true);
  assert.equal(report.sourceClosure.complete,true);assert.equal(report.sourceClosure.originalEventsPreserved,true);
  assert.equal(report.finalReplay.valid,true);assert.ok(report.result.checks<=256);
  assert.equal(report.verificationPasses.finalClassification,1);assert.equal(report.verificationPasses.finalReportVerification,1);
  const ids=new Set(report.result.reducedCapture.events.filter(e=>e.tx).map(e=>e.tx));
  assert.deepEqual(ids,new Set(['S','A','B']));
  assert.equal(sdk.verifyClassificationV3(main,report).valid,true);
  writeFileSync(resolve(output,'closed-reduction.report.json'),canonical(report),{flag:'wx'});
});
test('reduction cannot replace G2 witness with competing G0 witness',()=>{
  const report=sdk.reduceClassificationV3(load('competing-categories'),{category:'G2-item',classificationOptions:{categories:['G0','G2-item']}});
  assert.equal(report.result.report.rules['G2-item'].status,'refuted');assert.equal(report.sourceClosure.complete,true);
  assert.equal(report.result.reducedCapture.events.some(e=>e.tx==='C'||e.tx==='D'),false);
});
test('zero candidate budget preserves facts without minimality',()=>{
  const report=sdk.reduceClassificationV3(main,{category:'G2-item',maxChecks:0});
  assert.equal(report.status,'budget');assert.equal(report.result.checks,0);assert.equal(report.result.oneMinimal,false);
  assert.equal(report.result.removed.length,0);assert.equal(report.result.reducedTraceText,main);
  assert.equal(report.sourceClosure.complete,true);assert.equal(report.finalReplay.valid,true);
});
test('nonrefuted requested category is not an arbitrary-anomaly shrink',()=>{
  const report=sdk.reduceClassificationV3(main,{category:'G0'});
  assert.equal(report.status,'not-refuted');assert.equal(report.result.removed.length,0);assert.equal(report.result.oneMinimal,false);
});
test('closed reduction capsule replays exact original source and mapping',()=>{
  const text=sdk.makeClassificationReductionCapsuleV3(main,{category:'G2-item'});
  const replay=sdk.replayClassificationCapsuleV3(text);
  assert.equal(replay.valid,true);assert.equal(replay.report.sourceClosure.complete,true);
  assert.equal(replay.report.originalSourceText,main);
  writeFileSync(resolve(output,'closed-reduction.capsule.json'),text,{flag:'wx'});
});
test('malformed raw source remains a reproducible invalid report',()=>{
  const report=sdk.classifyV3('{"events":');
  assert.equal(report.status,'invalid');assert.equal(report.originalSourceText,'{"events":');
  assert.equal(sdk.verifyClassificationV3('{"events":',report).valid,true);
});
test('report extra field refused',()=>assert.equal(sdk.verifyClassificationV3(main,{...baseline,extra:true}).valid,false));
test('report missing field refused',()=>{const x=structuredClone(baseline);delete x.budgets;assert.equal(sdk.verifyClassificationV3(main,x).valid,false);});
test('report changed raw version refused',()=>{const x=structuredClone(baseline);x.result.normalized.history.initial.x='changed';assert.equal(sdk.verifyClassificationV3(main,x).valid,false);});
test('report changed options refused',()=>assert.equal(sdk.verifyClassificationV3(main,baseline,{maxStates:0}).valid,false));
for(const value of [{categories:[]},{categories:['G0','G0']},{categories:['G2']},{models:['adya-pl-3-v1']},{maxStates:-1},{maxStates:100001},{maxEdgeChecks:1.5},JSON.parse('{"__proto__":1}'),null])
  test('unsupported category options '+JSON.stringify(value),()=>assert.throws(()=>sdk.classifyV3(main,value)));
for(const value of [{},{category:'G2'},{category:'G2-item',maxChecks:257},{category:'G2-item',maxChecks:-1},{category:'G2-item',classificationOptions:{categories:['G0']}}])
  test('unsupported reduction options '+JSON.stringify(value),()=>assert.throws(()=>sdk.reduceClassificationV3(main,value)));
for(const[field,value]of [['format','unknown'],['algorithm','unknown'],['coreAlgorithm','unknown'],['schemaVersion',2],['tool','unknown'],['operation','unknown']])mutation('capsule unknown '+field,x=>x[field]=value);
mutation('capsule unknown core engine',x=>x.engine.coreSha256='0'.repeat(64));
mutation('capsule unknown host engine',x=>x.engine.hostSha256='0'.repeat(64));
mutation('capsule extra field',x=>x.extra=true);mutation('capsule missing field',x=>delete x.budgets);
mutation('capsule altered budget',x=>x.budgets.maxCandidateChecks=257);
mutation('capsule altered report hash',x=>x.reportSha256='0'.repeat(64));
test('resigned changed conclusion refused',()=>{
  const x=structuredClone(parsed),report=JSON.parse(x.reportText);report.status=report.result.status='checked-compatible';
  x.reportText=JSON.stringify(report);assert.equal(sdk.replayClassificationCapsuleV3(resign(x)).valid,false);
});
test('resigned changed options refused',()=>{
  const x=structuredClone(parsed);x.requestOptionsText='{"maxStates":0}';assert.equal(sdk.replayClassificationCapsuleV3(resign(x)).valid,false);
});
test('resigned changed original sequence refused',()=>{
  const x=structuredClone(parsed),source=JSON.parse(x.sourceText);source.events[1].seq=900;
  x.sourceText=JSON.stringify(source);assert.equal(sdk.replayClassificationCapsuleV3(resign(x)).valid,false);
});
test('resigned changed original capture field refused',()=>{
  const x=structuredClone(parsed),source=JSON.parse(x.sourceText);source.scope.exclusiveWriters=false;
  x.sourceText=JSON.stringify(source);assert.equal(sdk.replayClassificationCapsuleV3(resign(x)).valid,false);
});
test('resigned changed search count refused',()=>{
  const x=structuredClone(parsed),report=JSON.parse(x.reportText);report.result.rules['G2-item'].states++;
  x.reportText=JSON.stringify(report);assert.equal(sdk.replayClassificationCapsuleV3(resign(x)).valid,false);
});
test('duplicate capsule key refused',()=>{
  const duplicate=capsule.replace('{\n','{\n  "schemaVersion": 1,\n');
  assert.equal(sdk.replayClassificationCapsuleV3(duplicate).valid,false);
});
test('old v3 result and old capsule path remain callable',()=>{
  const raw=load('g0'),report=sdk.analyzeV3(raw);
  assert.equal(sdk.verifyV3(raw,report).valid,true);
});
function cli(args){return spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:32*1024*1024});}
const input=resolve(output,'input.json'),opt=resolve(output,'options.json');writeFileSync(input,main,{flag:'wx'});writeFileSync(opt,'{"categories":["G2-item"]}',{flag:'wx'});
test('CLI classification and capsule safe files',()=>{
  const report=resolve(output,'cli.report.json'),cap=resolve(output,'cli.capsule.json');
  const child=cli(['classify-v3',input,'--options',opt,'--output',report,'--capsule',cap]);
  assert.equal(child.status,1,child.stderr);assert.equal(JSON.parse(readFileSync(report)).status,'refuted');
  assert.equal(sdk.replayClassificationCapsuleV3(readFileSync(cap,'utf8')).valid,true);
});
test('CLI report verification',()=>{
  const child=cli(['verify-classification-v3',input,resolve(output,'cli.report.json')]);
  assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(child.stdout).valid,true);
});
test('CLI fixed category closed reduction and replay',()=>{
  const cap=resolve(output,'cli-reduced.capsule.json'),mini=resolve(output,'cli-mini.json');
  const child=cli(['shrink-classification-v3',input,'--category','G2-item','--max-checks','256','--capture',mini,'--capsule',cap]);
  assert.equal(child.status,1,child.stderr);assert.equal(JSON.parse(child.stdout).sourceClosure.complete,true);
  const replay=cli(['replay-classification-v3',cap]);assert.equal(replay.status,0,replay.stderr);assert.equal(JSON.parse(replay.stdout).valid,true);
});
test('CLI refuses overwrite',()=>{const child=cli(['classify-v3',input,'--output',input]);assert.equal(child.status,2);assert.equal(readFileSync(input,'utf8'),main);});
test('CLI refuses duplicate outputs',()=>{const p=resolve(output,'same.json');assert.equal(cli(['classify-v3',input,'--output',p,'--capsule',p]).status,2);});
test('CLI refuses duplicate category options',()=>{const p=resolve(output,'reduce-options.json');writeFileSync(p,'{"category":"G2-item"}',{flag:'wx'});assert.equal(cli(['shrink-classification-v3',input,'--options',p,'--category','G2-item']).status,2);});
const receipt={passed:cases.every(x=>x.passed),checks:cases.length,actualDatabaseExecution:false,formalPerformanceMeasured:false,syntheticInputs:true,
  version:sdk.version(),coreSha256:sha(readFileSync(resolve(root,'dist/core.mjs'))),hostSha256:sha(readFileSync(resolve(root,'dist/classification.mjs'))),
  sourceCasesSha256:sha(readFileSync(resolve(root,'fixtures/classification-v3/manifest.json'))),outputDirectory:output,cases};
writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});
console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
