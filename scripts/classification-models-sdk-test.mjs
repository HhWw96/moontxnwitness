// Model host workflows use synthetic/frozen inputs and retained collector bytes; no new DB run.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),fixtures=resolve(root,'fixtures/classification-models-v3');
const output=resolve(process.env.MTW_MODELS_HOST_OUTPUT||resolve(root,'artifacts/model-classification-host-'+randomUUID()));mkdirSync(output,{recursive:true});
const sha=raw=>createHash('sha256').update(raw).digest('hex'),canonical=x=>JSON.stringify(x,null,2)+'\n',load=name=>readFileSync(resolve(fixtures,name+'.json'),'utf8');
const MODELS=['adya-pl-1-v1','adya-pl-2-v1','adya-pl-2.99-v1','elle-generalized-si-v1','adya-pl-3-v1','strict-pl-ss-v1'];
const main=load('strict-bound-synthetic'),baseline=sdk.classifyModelsV3(main),capsule=sdk.makeModelsClassificationCapsuleV3(main),parsed=JSON.parse(capsule),cases=[];
function test(name,action){try{action();cases.push({name,passed:true});}catch(error){cases.push({name,passed:false,error:String(error.message)});}}
function resign(value){
  const source=JSON.parse(value.sourceText);
  value.sourceBindings={sourceSha256:sha(value.sourceText),traceSha256:sha(source.traceText??value.sourceText),
    intervalEvidenceSha256:source.intervalEvidenceText?sha(source.intervalEvidenceText):null,
    lifecycleSha256:source.lifecycleText?sha(source.lifecycleText):null,journalIndexSha256:source.journalIndexText?sha(source.journalIndexText):null};
  value.reportSha256=sha(value.reportText);value.requestOptionsSha256=sha(value.requestOptionsText);return canonical(value);
}
function mutation(name,change){test(name,()=>{const v=structuredClone(parsed);change(v);assert.equal(sdk.replayModelsClassificationCapsuleV3(canonical(v)).valid,false);});}
function reseal(source,change){
  const records=source.lifecycleText.trimEnd().split('\n').map(JSON.parse);records.pop();change(records);
  for(let i=0;i<records.length;i++)records[i].seq=i+1;
  const prefix=records.map(r=>JSON.stringify(r)+'\n').join(''),seal={seq:records.length+1,kind:'seal',records:records.length,prefixSha256:sha(prefix)};
  source.lifecycleText=prefix+JSON.stringify(seal)+'\n';
  const interval=JSON.parse(source.intervalEvidenceText);interval.sourceTraceSha256=sha(source.traceText);
  interval.sourceLifecycleSha256=sha(source.lifecycleText);interval.sourceJournalIndexSha256=sha(source.journalIndexText);interval.records=[...records,seal];
  source.intervalEvidenceText=JSON.stringify(interval);return JSON.stringify(source);
}
writeFileSync(resolve(output,'original.capsule.json'),capsule,{flag:'wx'});
test('default five graph models and absent strict evidence remain distinct',()=>{
  const r=sdk.classifyModelsV3(load('empty-register'));
  for(const name of MODELS)assert.equal(r.result.models[name].status,name==='strict-pl-ss-v1'?'inconclusive':'checked-compatible');
  assert.equal(r.status,'inconclusive');assert.equal(r.scope.databaseWideCertification,false);
});
test('explicit subset has exactly requested definition',()=>{
  const r=sdk.classifyModelsV3(load('empty-register'),{models:['adya-pl-1-v1']});
  assert.deepEqual(Object.keys(r.result.models),['adya-pl-1-v1']);assert.equal(r.status,'checked-compatible');
});
test('register write skew distinguishes SI and serial checks',()=>{
  const source=readFileSync(resolve(root,'fixtures/classification-v3/source-closed-noisy-g2.json'),'utf8'),r=sdk.classifyModelsV3(source);
  assert.equal(r.result.models['elle-generalized-si-v1'].status,'checked-compatible');
  assert.equal(r.result.models['adya-pl-3-v1'].status,'refuted');assert.equal(r.result.models['adya-pl-2.99-v1'].status,'refuted');
  assert.equal(r.result.normalized.history.initial.x,'0.2.0');
});
test('list write skew distinguishes model checks with equal business values',()=>{
  const r=sdk.classifyModelsV3(load('list-skew'));
  assert.equal(r.result.models['elle-generalized-si-v1'].status,'checked-compatible');
  assert.equal(r.result.models['adya-pl-3-v1'].status,'refuted');assert.equal(r.result.dataModel,'append-list-v1');
});
test('INT is an applicability precondition for operational serial claim',()=>{
  const r=sdk.classifyModelsV3(load('own-internal'));
  assert.equal(r.result.rules.INT.status,'refuted');assert.equal(r.result.models['elle-generalized-si-v1'].status,'refuted');
  assert.equal(r.result.models['adya-pl-3-v1'].status,'inconclusive');
  assert.equal(r.result.models['adya-pl-3-v1'].internalValidity.status,'not-satisfied');
});
test('relation classification and model reduction explicitly unsupported',()=>{
  const r=sdk.classifyModelsV3(load('relation-unsupported'));
  assert.equal(r.status,'unsupported');assert.equal(r.scope.relationModelClassificationSupported,false);
  assert.equal(r.scope.modelPreservingReductionSupported,false);
  for(const name of MODELS)assert.equal(r.result.models[name].status,'unsupported');
});
test('bound synthetic call intervals can finish strict checks',()=>{
  assert.equal(baseline.result.models['strict-pl-ss-v1'].status,'checked-compatible');
  assert.equal(baseline.result.realTimeDependencies.length,1);assert.equal(baseline.coreReportReplay.valid,true);
  assert.equal(baseline.scope.actualDatabaseExecution,false);assert.equal(baseline.scope.clientEvidenceAuthenticatesCollector,false);
});
test('equal monotonic boundaries prove no realtime edge',()=>{
  const r=sdk.classifyModelsV3(load('strict-equal-synthetic'));
  assert.equal(r.result.realTimeDependencies.length,0);assert.equal(r.result.models['strict-pl-ss-v1'].status,'checked-compatible');
});
test('COMMIT without original native confirmation stays unknown',()=>{
  const source=JSON.parse(main),text=reseal(source,records=>{
    for(const r of records)if(r.kind==='call-end'&&r.method==='commit')delete r.nativeCommandTag;
  });
  const r=sdk.classifyModelsV3(text);assert.equal(r.result.models['strict-pl-ss-v1'].status,'inconclusive');
});
test('missing entire first SQL call pair cannot finish strict check',()=>{
  const source=JSON.parse(main),text=reseal(source,records=>{
    const retained=records.filter(r=>r.callId!=='sql-A');records.splice(0,records.length,...retained);
  });
  const r=sdk.classifyModelsV3(text);assert.equal(r.result.models['strict-pl-ss-v1'].status,'inconclusive');
});
test('zero cycle budgets remain visible',()=>{
  const r=sdk.classifyModelsV3(load('list-skew'),{maxStates:0,maxEdgeChecks:0});
  assert.equal(r.result.rules['G2-item'].status,'unknown');assert.equal(r.result.models['adya-pl-3-v1'].status,'inconclusive');
});
for(const name of ['native-sync','native-async','lost-commit-sync','lost-commit-async'])test('actual retained '+name+' diagnostics never become complete model acceptance',()=>{
  const text=load('retained-'+name),r=sdk.classifyModelsV3(text),source=JSON.parse(text);
  assert.notEqual(r.result.models?.['strict-pl-ss-v1']?.status,'checked-compatible');
  assert.notEqual(r.status,'checked-compatible');
  for(const[name,field]of [['trace','traceText'],['intervalEvidence','intervalEvidenceText'],['lifecycle','lifecycleText'],['journalIndex','journalIndexText']])
    assert.equal(r.sourceBindings[name+'Sha256'],sha(source[field]));
  assert.equal(sdk.verifyModelsClassificationV3(text,r).valid,true);
});
const g1bPlan=JSON.parse(load('frozen-g1b-expectations'));
for(const c of g1bPlan.cases)test('frozen repaired list source '+c.id,()=>{
  const text=load('g1b/'+c.id),r=sdk.classifyModelsV3(text),rule=r.result.rules.G1b.status;
  if(c.expected.g1b==='not-refuted')assert.notEqual(rule,'refuted');else assert.equal(rule,c.expected.g1b);
  assert.equal(r.result.rules.G1a.status==='refuted',c.expected.g1aRefuted);
  assert.equal(r.result.validityGaps.length>0,c.expected.validityGap);
  assert.equal(sdk.verifyModelsClassificationV3(text,r).valid,true);
});
test('entire source and four exact original texts are independently hash-bound',()=>{
  const source=JSON.parse(main);assert.equal(baseline.originalSourceText,main);
  assert.equal(baseline.sourceBindings.sourceSha256,sha(main));
  for(const name of ['trace','intervalEvidence','lifecycle','journalIndex'])assert.equal(baseline.sourceBindings[name+'Sha256'],sha(source[name+'Text']));
  assert.equal(baseline.engine.coreSha256,sha(readFileSync(resolve(root,'dist/core.mjs'))));
  assert.equal(baseline.engine.hostSha256,sha(readFileSync(resolve(root,'dist/classification-models.mjs'))));
});
test('model capsule full original source replay',()=>{
  const replay=sdk.replayModelsClassificationCapsuleV3(capsule);
  assert.equal(replay.valid,true);assert.equal(replay.report.originalSourceText,main);assert.deepEqual(replay.report,baseline);
});
test('unknown result full capsule replay stays unknown',()=>{
  const text=load('empty-register'),replay=sdk.replayModelsClassificationCapsuleV3(sdk.makeModelsClassificationCapsuleV3(text));
  assert.equal(replay.valid,true);assert.equal(replay.status,'inconclusive');
});
for(const value of [{models:[]},{models:['adya-pl-1-v1','adya-pl-1-v1']},{models:['serializable']},{categories:['G0']},{maxStates:-1},{maxStates:100001},{normalizationOptions:{sqlProof:true}},JSON.parse('{"__proto__":1}'),null])
  test('invalid explicit model options '+JSON.stringify(value),()=>assert.throws(()=>sdk.classifyModelsV3(main,value)));
test('old category API keeps its exact option boundary',()=>assert.throws(()=>sdk.classifyV3(main,{models:['adya-pl-1-v1']})));
test('old category reduction cannot silently become model shrink',()=>assert.throws(()=>sdk.reduceClassificationV3(main,{category:'G2-item',classificationOptions:{models:MODELS}})));
for(const[field,value]of [['format','unknown'],['algorithm','unknown'],['coreAlgorithm','unknown'],['schemaVersion',2],['tool','unknown']])mutation('capsule unknown '+field,v=>v[field]=value);
mutation('capsule unknown current engine',v=>v.engine.coreSha256='0'.repeat(64));mutation('capsule unknown host',v=>v.engine.hostSha256='0'.repeat(64));
mutation('capsule extra field',v=>v.extra=true);mutation('capsule missing field',v=>delete v.budgets);
mutation('capsule altered source SHA',v=>v.sourceBindings.lifecycleSha256='0'.repeat(64));
test('resigned altered model conclusion refused',()=>{
  const v=structuredClone(parsed),r=JSON.parse(v.reportText);r.result.models['strict-pl-ss-v1'].status='refuted';v.reportText=JSON.stringify(r);
  assert.equal(sdk.replayModelsClassificationCapsuleV3(resign(v)).valid,false);
});
test('resigned altered required checks refused',()=>{
  const v=structuredClone(parsed),r=JSON.parse(v.reportText);r.result.models['strict-pl-ss-v1'].requiredRules=[];v.reportText=JSON.stringify(r);
  assert.equal(sdk.replayModelsClassificationCapsuleV3(resign(v)).valid,false);
});
test('resigned altered requested models refused',()=>{
  const v=structuredClone(parsed);v.requestOptionsText='{"models":["adya-pl-1-v1"]}';assert.equal(sdk.replayModelsClassificationCapsuleV3(resign(v)).valid,false);
});
test('resigned altered source budget/closure refused',()=>{
  const v=structuredClone(parsed),source=JSON.parse(v.sourceText),index=JSON.parse(source.journalIndexText);index.sourceClosed=false;
  source.journalIndexText=JSON.stringify(index);v.sourceText=JSON.stringify(source);
  assert.equal(sdk.replayModelsClassificationCapsuleV3(resign(v)).valid,false);
});
test('resigned all sidecar digests cannot keep an unconfirmed strict conclusion',()=>{
  const v=structuredClone(parsed);v.sourceText=reseal(JSON.parse(v.sourceText),records=>{
    for(const r of records)if(r.kind==='call-end'&&r.method==='commit')delete r.nativeCommandTag;
  });
  assert.equal(sdk.replayModelsClassificationCapsuleV3(resign(v)).valid,false);
});
test('duplicate capsule key refused',()=>assert.equal(sdk.replayModelsClassificationCapsuleV3(capsule.replace('{\n','{\n  "schemaVersion": 1,\n')).valid,false));
test('extra report field refused',()=>assert.equal(sdk.verifyModelsClassificationV3(main,{...baseline,extra:true}).valid,false));
test('missing report field refused',()=>{const r=structuredClone(baseline);delete r.scope;assert.equal(sdk.verifyModelsClassificationV3(main,r).valid,false);});
function cli(args){return spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:32*1024*1024});}
const input=resolve(output,'source.json'),report=resolve(output,'cli.report.json'),cap=resolve(output,'cli.capsule.json');writeFileSync(input,main,{flag:'wx'});
test('CLI explicit models report and capsule',()=>{
  const child=cli(['classify-models-v3',input,'--output',report,'--capsule',cap]);
  assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(readFileSync(report)).status,'checked-compatible');
});
test('CLI model verification',()=>{const child=cli(['verify-models-classification-v3',input,report]);assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(child.stdout).valid,true);});
test('CLI full model capsule replay',()=>{const child=cli(['replay-models-classification-v3',cap]);assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(child.stdout).valid,true);});
test('CLI unknown strict input exit stays inconclusive',()=>{
  const p=resolve(output,'empty.json');writeFileSync(p,load('empty-register'),{flag:'wx'});assert.equal(cli(['classify-models-v3',p]).status,3);
});
test('CLI refuses overwriting original',()=>assert.equal(cli(['classify-models-v3',input,'--output',input]).status,2));
test('CLI refuses duplicate output',()=>{const path=resolve(output,'duplicate.json');assert.equal(cli(['classify-models-v3',input,'--output',path,'--capsule',path]).status,2);});
const receipt={passed:cases.every(c=>c.passed),checks:cases.length,version:sdk.version(),newDatabaseExecution:false,formalPerformanceMeasured:false,
  retainedActualCollectorPackets:4,syntheticStrictEvidence:true,originalG1bRegressions:9,
  coreSha256:sha(readFileSync(resolve(root,'dist/core.mjs'))),hostSha256:sha(readFileSync(resolve(root,'dist/classification-models.mjs'))),
  sourceManifestSha256:sha(readFileSync(resolve(fixtures,'manifest.json'))),outputDirectory:output,cases};
writeFileSync(resolve(output,'receipt.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
