import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {classifyV4,verifyClassificationV4,makeClassificationCapsuleV4,replayCapsuleV4} from '../dist/sdk.mjs';
const root=resolve(import.meta.dirname,'..'),rows=[];function check(name,fn){fn();rows.push({name,passed:true});}
function trace(body){return {traceSchema:3,dataModel:'append-list-v1',clockDomain:'effective-sdk',scope:{exclusiveWriters:true},events:[{kind:'snapshot',initial:{x:[]},consistent:true},...body].map((event,index)=>({seq:index+1,time:index,...event})),gaps:[]};}
const simple=trace([{kind:'begin',tx:'A',connection:'a'},{kind:'append',tx:'A',key:'x',id:'a',value:'same'},
 {kind:'append',tx:'A',key:'x',id:'b',value:'same'},{kind:'list_read',tx:'A',key:'x',items:[{id:'a',value:'same'},{id:'b',value:'same'}]},
 {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'}]);
const requested={listGraph:'effective-v1'},report=classifyV4(simple,requested),capsule=makeClassificationCapsuleV4(simple,requested);
check('effective profile handles multiple appends with independent IDs',()=>{
 assert.equal(report.judgment.status,'checked-compatible');assert.equal(report.execution.listGraph,'effective-v1');
 assert.equal(report.algorithm,'v4-source-bound-category-list-effective-1');assert.equal(report.execution.counterContract,'v4-list-effective-category-counters-1');
 assert.equal(report.judgment.acceptsIsolationModels,false);
});
check('legacy default remains explicit unknown for unsupported multi-append scope',()=>{
 const old=classifyV4(simple);assert.equal(old.algorithm,'v4-source-bound-category-bfs-1');assert.equal(old.execution.listGraph,undefined);
 assert.equal(old.judgment.status,'inconclusive');assert.equal(verifyClassificationV4(simple,old).valid,true);
});
check('profile report verification requires caller selection',()=>{
 assert.equal(verifyClassificationV4(simple,report,requested).valid,true);assert.equal(verifyClassificationV4(simple,report).valid,false);
});
check('profile capsule cannot self-select an effective graph',()=>{
 assert.equal(replayCapsuleV4(capsule).valid,false);assert.equal(replayCapsuleV4(capsule,requested).valid,true);
});
check('effective profile takes precedence over G-single IDs',()=>{
 const options={...requested,categories:['G-single']},result=classifyV4(simple,options);
 assert.equal(result.algorithm,'v4-source-bound-category-list-effective-1');assert.equal(verifyClassificationV4(simple,result,options).valid,true);
 assert.equal(replayCapsuleV4(makeClassificationCapsuleV4(simple,options),options).valid,true);
});
check('construction budget zero stays inconclusive',()=>{
 const options={...requested,maxListGraphChecks:0},result=classifyV4(simple,options);
 assert.equal(result.judgment.status,'inconclusive');assert.equal(result.execution.limits.listGraphChecks,0);
 const packed=makeClassificationCapsuleV4(simple,options);assert.equal(replayCapsuleV4(packed,requested).valid,false);assert.equal(replayCapsuleV4(packed,options).valid,true);
});
for(const options of [{listGraph:'unknown'},{listGraph:null},{maxListGraphChecks:0},{listGraph:'legacy',maxListGraphChecks:999999},{listGraph:'effective-v1',maxListGraphChecks:1000001}])
 check('invalid construction options '+JSON.stringify(options),()=>assert.throws(()=>classifyV4(simple,options)));
for(const [name,change] of [
 ['profile',r=>{r.execution.listGraph='legacy';}],['budget',r=>{r.execution.limits.listGraphChecks=0;}],
 ['counter',r=>{r.execution.counterContract='v4-category-seed-bfs-counters-1';}],
 ['inferences',r=>{r.inferences.listGraph={forged:true};}],
])check('tampered '+name+' rejected',()=>{const altered=structuredClone(report);change(altered);assert.equal(verifyClassificationV4(simple,altered,requested).valid,false);});
check('non-list effective profile remains unsupported',()=>{
 const source={schemaVersion:1,model:'serializable',initial:{x:'x0'},transactions:[]};
 const result=classifyV4(source,requested);assert.equal(result.judgment.status,'unsupported');
});
mkdirSync(resolve(root,'artifacts'),{recursive:true});const receipt={suite:'v033-effective-list-sdk-1',passed:true,checks:rows.length,actualDatabaseExecution:false,results:rows};
writeFileSync(resolve(root,'artifacts/list-effective-sdk-validation.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
