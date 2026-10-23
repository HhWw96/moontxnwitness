import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const hash=x=>createHash('sha256').update(x).digest('hex');
const frozen=resolve(root,'fixtures/compat-v020');
const manifestBytes=readFileSync(resolve(frozen,'manifest.json'));
assert.equal(hash(manifestBytes),'c6d4fe126fc8de744d5e4dd6293e52863ba9fdc93c6f223df3f262e3b96dd91c');
const manifest=JSON.parse(manifestBytes);
const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')));
const evidence=await import(pathToFileURL(resolve(root,'dist/evidence.mjs')));
assert.notEqual(sdk.version(),'0.2.0','A new engine must reproduce actual20 bytes');
let checks=0;const cases=[];
const check=(condition,label)=>{assert.equal(condition,true,label);checks++;};
for(const c of manifest.cases) {
 const content={};
 for(const key of ['input','report','capsule'])if(c[key]) {
   const bytes=readFileSync(resolve(frozen,c[key].file));
   check(bytes.length===c[key].bytes&&hash(bytes)===c[key].sha256,c.name+' original '+key+' unchanged');
   content[key]=bytes.toString('utf8');
 }
 const replay=text=>c.type==='execution'?sdk.replayExecutionCapsuleV3(text):c.type==='v3'?sdk.replayCapsuleV3(text):evidence.replayCapsule(text);
 check(replay(content.capsule).valid===true,c.name+' published20 capsule replay');
 if(content.report) {
  const report=JSON.parse(content.report);
  check(report.version==='0.2.0',c.name+' actual producer header');
  const verify=r=>c.type==='v3'?sdk.verifyV3(content.input,r):sdk.replayReport(content.input,r);
  check(verify(report).valid===true,c.name+' full original report');
  const changed=structuredClone(report);changed.status=report.status==='violation'?'consistent':'violation';
  check(verify(changed).valid===false,c.name+' changed verdict rejected');
  const future=structuredClone(report);future.version='9.9.9';
  check(verify(future).valid===false,c.name+' future engine rejected');
  if(c.type==='v3') {
   const budget=structuredClone(report),options=budget.execution.analysisOptions;
   if('maxStates' in options)options.maxStates=0;else options.maxAttempts=0;
   check(verify(budget).valid===false,c.name+' changed recorded budget rejected');
  }
 }
 const capsule=JSON.parse(content.capsule);
 capsule.engineVersion='9.9.9';
 check(replay(JSON.stringify(capsule,null,2)+'\n').valid===false,c.name+' future capsule engine rejected');
 if(c.type==='v3') {
  const tamper=JSON.parse(content.capsule);const input=JSON.parse(tamper.traceText);input.events[0].consistent=false;
  tamper.traceText=JSON.stringify(input);tamper.traceSha256=hash(tamper.traceText);
  check(replay(JSON.stringify(tamper,null,2)+'\n').valid===false,c.name+' changed observation with updated digest rejected');
  if(c.name==='list'||c.name==='relation')check(content.input.includes('0.2.0')&&content.report.includes('0.2.0'),c.name+' version-shaped business values retained');
 }
 if(c.type==='execution') {
  const original=JSON.parse(content.capsule);
  check(original.traceText===content.input,c.name+' exact unknown outcome trace retained');
  const input=JSON.parse(original.traceText);check(input.events.some(e=>e.kind==='disconnect'),c.name+' unknown commit remains observed');
 }
 cases.push({name:c.name,type:c.type,passed:true});
}
console.log(JSON.stringify({passed:true,runtimeVersion:sdk.version(),producerEngineVersion:'0.2.0',producerSourceCommit:manifest.producerSourceCommit,actualPublishedProducer:true,capsules:cases.length,checks,cases,manifestSha256:hash(manifestBytes),actualDatabaseExecutedHere:false}));
