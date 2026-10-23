import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const hash=x=>createHash('sha256').update(x).digest('hex');
const frozen=resolve(root,'fixtures/compat-v023');
const manifestBytes=readFileSync(resolve(frozen,'manifest.json'));
assert.equal(hash(manifestBytes),'f4fdfdd0bf4b1ea77a887ac59e31d8467d58b4c710a7698cf48f557464b72693');
const manifest=JSON.parse(manifestBytes);
assert.equal(manifest.actualPublishedProducer,true);
assert.equal(manifest.producerEngineVersion,'0.2.3');
assert.equal(manifest.sourceCommit,'2403aad35bed961e3ad1b2c6f4f0f7024f29f257');
assert.equal(manifest.publicPackage.sha256,'d1bbf6e23f513612f44491b3c50d2ec94023332bc7e5a5fa414557373f9bc9e0');
assert.equal(manifest.registryPackage.sha256,'0d91f6d6435ff261793b7ff36ac9ad80923d2174e49bc3e8dedb1e7721d94394');
const sdk=await import(pathToFileURL(resolve(root,'dist/sdk.mjs')));
const evidence=await import(pathToFileURL(resolve(root,'dist/evidence.mjs')));
assert.notEqual(sdk.version(),'0.2.3','A newer engine must reproduce authentic published23 bytes');
let checks=0; const cases=[];
const check=(condition,label)=>{assert.equal(condition,true,label);checks++;};
function original(row,label){const b=readFileSync(resolve(frozen,row.file));check(b.length===row.bytes&&hash(b)===row.sha256,label+' exact original bytes');return b.toString('utf8');}
for(const [name,row] of Object.entries(manifest.producerFiles))original(row,'published23 '+name);
for(const c of manifest.cases){
 const input=original(c.input,c.name+' input'), reportText=original(c.report,c.name+' report'), capsuleText=original(c.capsule,c.name+' capsule');
 const producer=JSON.parse(original(c.producerReplay,c.name+' original producer replay'));
 check(producer.valid===true,c.name+' authentic producer replay was valid');
 const replay=text=>c.type==='execution'?sdk.replayExecutionCapsuleV3(text):c.type==='v3'?sdk.replayCapsuleV3(text):evidence.replayCapsule(text);
 const reproduced=replay(capsuleText); check(reproduced.valid===true,c.name+' unchanged published23 capsule replay');
 const cap=JSON.parse(capsuleText), report=JSON.parse(reportText);
 check(cap.engineVersion==='0.2.3',c.name+' authentic capsule engine header');
 if(c.type==='execution'){
   assert.deepEqual(sdk.inspectExecutionFailuresV3(input),report); checks++;
   check(cap.traceText===input,c.name+' exact unknown outcome observations retained');
   check(report.transactionOutcomes.some(t=>t.status==='unknown')&&report.captureCoverage.complete===false,c.name+' unconfirmed commit stays unknown');
   check(reproduced.scope.modelViolationClaim===false,c.name+' diagnostic cannot certify an isolation model');
   const changed=structuredClone(cap);const diagnostic=JSON.parse(changed.diagnosticText);diagnostic.transactionOutcomes[0].status='committed';
   changed.diagnosticText=JSON.stringify(diagnostic);changed.diagnosticSha256=hash(changed.diagnosticText);
   check(replay(JSON.stringify(changed,null,2)+'\n').valid===false,c.name+' fabricated commit outcome rejected');
 }else{
   check(report.version==='0.2.3'&&report.status===c.expectedStatus,c.name+' authentic report status/header');
   const verify=r=>c.type==='v3'?sdk.verifyV3(input,r):sdk.replayReport(input,r);
   check(verify(report).valid===true,c.name+' original complete report reproduced');
   const changed=structuredClone(report);changed.status=report.status==='violation'?'consistent':'violation';
   check(verify(changed).valid===false,c.name+' altered conclusion rejected');
   const future=structuredClone(report);future.version='9.9.9';
   check(verify(future).valid===false,c.name+' unrecognized engine rejected');
   const tamper=structuredClone(cap);const altered=JSON.parse(tamper.reportText);altered.status=changed.status;
   tamper.reportText=JSON.stringify(altered);tamper.reportSha256=hash(tamper.reportText);
   check(replay(JSON.stringify(tamper,null,2)+'\n').valid===false,c.name+' altered capsule conclusion with updated digest rejected');
   if(c.type==='v3'){
     const budget=structuredClone(report);const options=budget.execution.analysisOptions;
     check(options!==undefined,c.name+' original explicit budget is present');
     assert.notEqual(options.maxStates,0);options.maxStates=0;
     check(verify(budget).valid===false,c.name+' altered recorded budget rejected');
     // Re-hashing an arbitrary changed invalid input can legitimately preserve its
     // invalid diagnostic. Only violation inputs have this additional semantic check.
     if(c.expectedStatus==='violation'){
       const obs=structuredClone(cap), trace=JSON.parse(obs.traceText);assert.equal(trace.events[0].consistent,true);trace.events[0].consistent=false;
       obs.traceText=JSON.stringify(trace);obs.traceSha256=hash(obs.traceText);
       check(replay(JSON.stringify(obs,null,2)+'\n').valid===false,c.name+' changed source observation with updated digest rejected');
     }
     if(c.name==='list'||c.name==='relation')check(input.includes('0.2.0')&&reportText.includes('0.2.0'),c.name+' version-shaped business strings retained');
   }
 }
 const futureCap=structuredClone(cap);futureCap.engineVersion='9.9.9';
 check(replay(JSON.stringify(futureCap,null,2)+'\n').valid===false,c.name+' unrecognized capsule engine rejected');
 const digest=structuredClone(cap);const field=c.type==='v3'||c.type==='execution'?'traceSha256':'historySha256';
 assert.equal(typeof digest[field],'string');digest[field]='0'.repeat(64);
 check(replay(JSON.stringify(digest,null,2)+'\n').valid===false,c.name+' tampered original input digest rejected');
 cases.push({name:c.name,type:c.type,expectedStatus:c.expectedStatus,passed:true});
}
assert.equal(cases.length,8);
console.log(JSON.stringify({passed:true,runtimeVersion:sdk.version(),producerEngineVersion:'0.2.3',producerSourceCommit:manifest.sourceCommit,actualPublishedProducer:true,capsules:cases.length,checks,cases,manifestSha256:hash(manifestBytes),actualDatabaseExecutedHere:false}));
