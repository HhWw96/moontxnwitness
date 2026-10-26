// Frozen original histories plus separate synthetic lifecycle negatives; no database is opened.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=resolve(process.env.MTW_DIAG_OUTPUT||resolve(root,'artifacts/diagnosis-host-'+randomUUID()));
mkdirSync(dirname(output),{recursive:true});mkdirSync(output,{recursive:false});
const hash=value=>createHash('sha256').update(value).digest('hex');
const canonical=value=>JSON.stringify(value,null,2)+'\n';
const cases=[],inputs=new Map(),reports=new Map();
function test(name,action){try{action();cases.push({name,passed:true});}catch(error){cases.push({name,passed:false,error:String(error.stack??error)});}}
const frozen=[['register-0','22de9edb1c67949d1988b56e2a1cb17153587c18a2afecf3bc96e8b9190f1bdf'],
  ['register-4','647375a8a5d8dcb3a2868ae80428d229f353d473692bd11ca5be4475b1e16dc0'],
  ['register-80','67bda8c45363ee6c8e542555f819e04602e9e5c76b477b80fa1f378240fa358a']];
for(const [id,expected]of frozen){const text=readFileSync(resolve(root,'fixtures/diagnosis-v3',id+'.json'),'utf8');assert.equal(hash(text),expected);inputs.set(id,text);}
const load=name=>readFileSync(resolve(root,'fixtures/classification-models-v3',name+'.json'),'utf8');
const own=load('own-internal');
function trace(events){return JSON.stringify({traceSchema:3,clockDomain:'diagnosis-synthetic-control',scope:{exclusiveWriters:true},events:events.map((event,i)=>({...event,seq:i+1,time:i})),gaps:[]});}
const rollback=trace([{kind:'snapshot',initial:{x:'x0'},consistent:true},{kind:'begin',tx:'A',connection:'a'},
  {kind:'read',tx:'A',key:'x',version:'x0'},{kind:'savepoint',tx:'A',name:'s',instance:'s1'},
  {kind:'write',tx:'A',key:'x',version:'x1',predecessor:'x0'},{kind:'read',tx:'A',key:'x',version:'x1'},
  {kind:'rollback_to',tx:'A',instance:'s1'},{kind:'read',tx:'A',key:'x',version:'x0'},
  {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'}]);
const unknown=JSON.parse(own);unknown.events=unknown.events.filter(e=>e.kind!=='commit_ok');
const aborted=JSON.parse(own);aborted.events=aborted.events.filter(e=>!['commit_request','commit_ok'].includes(e.kind));aborted.events.push({kind:'rollback_ok',tx:'A',seq:5,time:4});
const missing=JSON.parse(own);missing.scope.exclusiveWriters=false;
for(const [id,value]of [['own',own],['rollback',rollback],['unknown',JSON.stringify(unknown)],['aborted',JSON.stringify(aborted)],['missing',JSON.stringify(missing)],['list',load('list-skew')],['relation',load('relation-unsupported')]])inputs.set(id,value);
function oldBytes(source,api=sdk){const analysis=api.analyzeV3(source);return {analysis:JSON.stringify(analysis),models:JSON.stringify(api.classifyModelsV3(source)),serialCapsule:api.makeCapsuleV3(source,analysis),modelCapsule:api.makeModelsClassificationCapsuleV3(source)};}
const before=new Map();for(const [id,text]of inputs)before.set(id,oldBytes(text));
for(const [id,text]of inputs)test('exact child reports and independent diagnosis verification '+id,()=>{
  const report=sdk.diagnoseV3(text);reports.set(id,report);
  assert.equal(JSON.stringify(report.analysis),before.get(id).analysis);assert.equal(JSON.stringify(report.models),before.get(id).models);
  assert.equal(report.sourceBindings.traceSha256,hash(text));assert.equal(report.scope.diagnosticOnly,true);
  assert.equal(sdk.verifyDiagnosisV3(text,report).valid,true);assert.equal(sdk.verifyDiagnosisV3(text,canonical(report)).valid,true);
  writeFileSync(resolve(output,id+'.report.json'),canonical(report),{flag:'wx'});
});
for(const id of ['register-0','register-4'])test('frozen committed own-read finding preserves original boundary '+id,()=>{
  const r=reports.get(id),finding=r.findings.find(f=>f.rule==='INT');assert.equal(r.status,'findings');assert.equal(r.analysis.status,'inconclusive');
  assert(finding);assert.deepEqual(finding.evidence,r.models.result.rules.INT.evidence);assert.deepEqual(finding.evidencePath,['models','result','rules','INT','evidence']);
  assert.equal(finding.reason,'read-does-not-observe-current-own-write');assert.equal(r.models.result.models['elle-generalized-si-v1'].status,'refuted');
  for(const model of ['adya-pl-3-v1','strict-pl-ss-v1']){assert.equal(r.models.result.models[model].status,'inconclusive');assert.equal(r.models.result.models[model].internalValidity.status,'not-satisfied');}
  assert(!r.findings.some(f=>f.rule==='G2-item'));
});
test('normal frozen control retains strict gap',()=>{const r=reports.get('register-80');assert.equal(r.findings.length,0);assert.equal(r.status,'inconclusive');assert.equal(r.models.result.models['strict-pl-ss-v1'].status,'inconclusive');});
for(const id of ['rollback','unknown','aborted','missing'])test('no invented INT finding for lifecycle/source negative '+id,()=>assert(!reports.get(id).findings.some(f=>f.rule==='INT')));
test('unconfirmed COMMIT stays incomplete',()=>assert.equal(reports.get('unknown').summary.allChecksComplete,false));
test('unproven writer scope retains gaps',()=>{const r=reports.get('missing');assert.equal(r.analysis.coverage.complete,false);assert.equal(r.status,'inconclusive');});
test('direct finding survives zero graph budgets',()=>{const r=sdk.diagnoseV3(own,{modelOptions:{maxStates:0,maxEdgeChecks:0}});assert(r.findings.some(f=>f.rule==='INT'));assert.equal(r.models.result.rules.G0.status,'unknown');assert.equal(r.status,'findings');assert.equal(sdk.verifyDiagnosisV3(own,r).valid,true);});
test('reliable model verdict does not complete other required rules',()=>{
  const r=sdk.diagnoseV3(own,{modelOptions:{models:['elle-generalized-si-v1'],maxStates:0,maxEdgeChecks:0}});
  assert.equal(r.models.result.models['elle-generalized-si-v1'].status,'refuted');assert.equal(r.summary.requestedModelVerdictsDeterminate,true);
  assert(r.models.result.models['elle-generalized-si-v1'].incompleteRules.length>0);assert.equal(r.summary.requestedModelsComplete,false);assert.equal(r.summary.allChecksComplete,false);
});
test('custom array prototype rejected before inherited toJSON',()=>{let calls=0;const a=[];const proto=Object.create(Array.prototype);proto.toJSON=()=>{calls++;return [];};Object.setPrototypeOf(a,proto);assert.throws(()=>sdk.diagnoseV3(own,{modelOptions:{models:a}}));assert.equal(calls,0);});
test('relation formal classification remains unsupported',()=>{const r=reports.get('relation');assert.equal(r.models.status,'unsupported');assert.equal(r.findings.length,0);assert.equal(r.summary.requestedModelsComplete,false);});
const subset={modelOptions:{models:['adya-pl-3-v1']}};
test('completed selected subset has no-findings without global certification',()=>{const r=sdk.diagnoseV3(inputs.get('register-80'),subset);assert.equal(r.status,'no-findings');assert.equal(r.summary.allChecksComplete,true);assert.equal(r.scope.databaseWideCertification,false);assert.equal(sdk.verifyDiagnosisV3(inputs.get('register-80'),r,subset).valid,true);assert.equal(sdk.verifyDiagnosisV3(inputs.get('register-80'),r,{}).valid,false);});
for(const value of [null,[],new Date(),{extra:true},{analysisOptions:null},{modelOptions:[]},{modelOptions:{maxStates:Infinity}},{analysisOptions:{extra:undefined}}])test('reject unsafe diagnosis options '+String(value),()=>assert.throws(()=>sdk.diagnoseV3(own,value)));
test('option accessor rejected without consumption',()=>{let calls=0;const o={};Object.defineProperty(o,'modelOptions',{enumerable:true,get(){calls++;return {};}});assert.throws(()=>sdk.diagnoseV3(own,o));assert.equal(calls,0);});
test('nested symbol and circular options rejected',()=>{const a={};a.self=a;assert.throws(()=>sdk.diagnoseV3(own,{analysisOptions:a}));assert.throws(()=>sdk.diagnoseV3(own,{modelOptions:{[Symbol()]:1}}));});
test('raw limit and malformed Unicode rejected',()=>{assert.throws(()=>sdk.diagnoseV3(' '.repeat(8*1024*1024+1)),RangeError);assert.throws(()=>sdk.diagnoseV3('\ud800'));});
test('source envelopes rejected',()=>assert.throws(()=>sdk.diagnoseV3({format:'moontxnwitness-classification-source/v1',traceText:own})));
test('bounded child options rejected',()=>assert.throws(()=>sdk.diagnoseV3(own,{analysisOptions:{padding:'x'.repeat(4096)}}),RangeError));
const base=reports.get('register-0'),source=inputs.get('register-0');
function mutate(name,change){test('refuse altered '+name,()=>{const r=structuredClone(base);change(r);assert.equal(sdk.verifyDiagnosisV3(source,r).valid,false);});}
mutate('aggregate status',r=>r.status='no-findings');mutate('removed findings',r=>r.findings=[]);mutate('INT evidence',r=>r.findings[0].evidence={});
mutate('child serial result',r=>r.analysis.status='consistent');mutate('formal model status',r=>r.models.result.models['adya-pl-3-v1'].status='refuted');
mutate('source digest',r=>r.sourceBindings.traceSha256='0'.repeat(64));mutate('engine',r=>r.engine.hostSha256='0'.repeat(64));
mutate('budget',r=>r.budgets.rawTraceUtf8Bytes++);mutate('missing gaps',r=>r.analysis.coverage.gaps=[]);mutate('added field',r=>r.extra=true);mutate('missing field',r=>delete r.scope);
mutate('options and recomputed option fields',r=>{r.requestOptionsText='{"modelOptions":{"maxStates":0}}';r.modelOptionsText='{"maxStates":0}';});
test('changed original trace rejected',()=>assert.equal(sdk.verifyDiagnosisV3(source+' ',base).valid,false));
test('duplicated report field original text rejected',()=>assert.equal(sdk.verifyDiagnosisV3(source,canonical(base).replace('{\n','{\n  "schemaVersion": 1,\n')).valid,false));
function cli(args){return spawnSync(process.execPath,['dist/moontxnwitness.mjs',...args],{cwd:root,encoding:'utf8',windowsHide:true,maxBuffer:32*1024*1024});}
const input=resolve(output,'original.json'),report=resolve(output,'cli.report.json'),options=resolve(output,'subset.options.json');
writeFileSync(input,source,{flag:'wx'});writeFileSync(options,JSON.stringify(subset),{flag:'wx'});
test('CLI findings and verification',()=>{let p=cli(['diagnose-v3',input,'--output',report]);assert.equal(p.status,1,p.stderr);assert.equal(JSON.parse(readFileSync(report)).status,'findings');p=cli(['verify-diagnosis-v3',input,report]);assert.equal(p.status,0,p.stderr);assert.equal(JSON.parse(p.stdout).valid,true);});
test('CLI explicit null options are rejected',()=>{const p=resolve(output,'null.options.json');writeFileSync(p,'null',{flag:'wx'});assert.equal(cli(['diagnose-v3',input,'--options',p]).status,2);});
test('CLI refuses original overwrite',()=>{const old=hash(readFileSync(input));const p=cli(['diagnose-v3',input,'--output',input]);assert.equal(p.status,2);assert.equal(hash(readFileSync(input)),old);});
test('CLI refuses existing report',()=>{const old=hash(readFileSync(report));assert.equal(cli(['diagnose-v3',input,'--output',report]).status,2);assert.equal(hash(readFileSync(report)),old);});
test('CLI default unknown exit and selected subset success',()=>{const normal=resolve(root,'fixtures/diagnosis-v3/register-80.json');assert.equal(cli(['diagnose-v3',normal]).status,3);const p=cli(['diagnose-v3',normal,'--options',options]);assert.equal(p.status,0,p.stderr);assert.equal(JSON.parse(p.stdout).status,'no-findings');});
for(const [id,text]of inputs)test('old reports and capsules byte unchanged after diagnosis '+id,()=>assert.deepEqual(oldBytes(text),before.get(id)));
if(process.env.MTW_DIAG_BASELINE_SDK){const baseline=await import(pathToFileURL(resolve(process.env.MTW_DIAG_BASELINE_SDK)));for(const [id,text]of inputs)test('public027 original old API byte equality '+id,()=>assert.deepEqual(oldBytes(text,baseline),before.get(id)));}
const receipt={passed:cases.every(c=>c.passed),checks:cases.length,version:sdk.version(),newDatabaseExecution:false,newMoonCompilation:false,formalPerformanceMeasured:false,
  frozenOriginalCases:frozen.map(([id,sha256])=>({id,sha256})),syntheticCases:7,outputDirectory:output,
  originalSerialAndModelReportsAndCapsulesPreserved:true,public027BaselineCompared:Boolean(process.env.MTW_DIAG_BASELINE_SDK),
  coreSha256:hash(readFileSync(resolve(root,'dist/core.mjs'))),captureCoreSha256:hash(readFileSync(resolve(root,'dist/capture-core.mjs'))),
  diagnosisHostSha256:hash(readFileSync(resolve(root,'dist/diagnosis.mjs'))),cases};
writeFileSync(resolve(output,'RESULT.json'),canonical(receipt),{flag:'wx'});console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
