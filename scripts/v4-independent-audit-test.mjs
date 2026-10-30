// Independent v4 regressions: semantic budgets and source-closed minimality.
// Uses synthetic observations and the current built SDK; writes no receipts.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {analyzeV4,classifyV4,reduceV4,verifyReductionV4,
  makeCapsuleV4,makeClassificationCapsuleV4,makeReductionCapsuleV4,replayCapsuleV4} from '../dist/sdk.mjs';

const digest=text=>createHash('sha256').update(text,'utf8').digest('hex');
const results=[];
function check(name,fn){
  try{fn();results.push({name,passed:true});}
  catch(error){results.push({name,passed:false,error:error.message});}
}
function capture(model,events,extras={}){
  return {traceSchema:3,dataModel:model,clockDomain:'independent-v4-semantic-boundaries',
    scope:{exclusiveWriters:true},gaps:[],...extras,
    events:events.map((event,index)=>({seq:index+1,time:index,...event}))};
}
function withoutCaptureTransaction(source,tx){
  return {...source,events:source.events.filter(event=>event.tx!==tx)
    .map((event,index)=>({...event,seq:index+1}))};
}
const list=capture('append-list-v1',[
  {kind:'snapshot',consistent:true,initial:{x:[]}},
  {kind:'begin',tx:'P',connection:'P'},
  {kind:'append',tx:'P',key:'x',id:'p',value:'original'},
  {kind:'commit_request',tx:'P'},{kind:'commit_ok',tx:'P'},
  {kind:'begin',tx:'A',connection:'A'},
  {kind:'list_read',tx:'A',key:'x',items:[{id:'p',value:'changed'}]},
  {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},
]);
const relationMismatch=capture('relation-set-v1',[
  {kind:'snapshot',consistent:true,initial:{r:[]}},
  {kind:'begin',tx:'P',connection:'P'},
  {kind:'row_write',tx:'P',relation:'r',key:'1',action:'insert',version:'p',predecessor:null,values:{n:'1'}},
  {kind:'commit_request',tx:'P'},{kind:'commit_ok',tx:'P'},
  {kind:'begin',tx:'A',connection:'A'},
  {kind:'row_read',tx:'A',relation:'r',predicate:[],rows:[{key:'1',version:'p',values:{n:'2'}}],complete:true},
  {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},
],{relationSchema:{r:{primaryKey:'id',columns:{id:'int64',n:'int64'}}},
  scope:{exclusiveWriters:true,completeSnapshotTables:['r']}});
const register={schemaVersion:1,model:'serializable',
  initial:{x:'x0',y:'y0',u:'u0',z:'z0'},
  versionOrders:{x:['x0','x1'],y:['y0','y1'],u:['u0','u1']},
  transactions:[
    {id:'A',status:'committed',ops:[{type:'read',key:'x',version:'x0'},
      {type:'write',key:'y',version:'y1'},{type:'write',key:'z',version:'zA'}]},
    {id:'B',status:'committed',ops:[{type:'read',key:'y',version:'y0'},
      {type:'write',key:'u',version:'u1'},{type:'write',key:'z',version:'zB'}]},
    {id:'C',status:'committed',ops:[{type:'read',key:'u',version:'u0'},
      {type:'write',key:'x',version:'x1'},{type:'write',key:'z',version:'zC'}]},
  ]};
function withoutDeclaredTransaction(source,id){
  const candidate=structuredClone(source);
  candidate.transactions=candidate.transactions.filter(tx=>tx.id!==id);
  for(const [key,chain] of Object.entries(candidate.versionOrders)){
    const retained=new Set(candidate.transactions.flatMap(tx=>tx.ops
      .filter(op=>op.type==='write'&&op.key===key).map(op=>op.version)));
    candidate.versionOrders[key]=chain.filter(version=>version===candidate.initial[key]||retained.has(version));
  }
  return candidate;
}

check('list source-closed unknown deletion prevents oneMinimal',()=>{
  const options={maxStates:0};
  const original=analyzeV4(list,options);
  assert.equal(original.judgment.status,'violation');
  assert.equal(original.judgment.evidence.findings[0].code,'item_value_mismatch');
  const closed=analyzeV4(withoutCaptureTransaction(list,'A'),options);
  assert.equal(closed.judgment.status,'inconclusive');
  assert.equal(closed.judgment.coverage.complete,true);
  const requested={preserve:'serializable',analysisOptions:options};
  const reduced=reduceV4(list,requested);
  assert.equal(reduced.analysis.judgment.status,'violation');
  assert.equal(reduced.oneMinimal,false,'A source-complete deletion exhausted its semantic search budget');
  assert.equal(verifyReductionV4(list,reduced,requested).valid,true);
});
check('relation source-closed unknown deletion prevents oneMinimal',()=>{
  const options={maxStates:0};
  const original=analyzeV4(relationMismatch,options);
  assert.equal(original.judgment.status,'violation');
  const closed=analyzeV4(withoutCaptureTransaction(relationMismatch,'A'),options);
  assert.equal(closed.judgment.status,'inconclusive');
  assert.equal(closed.judgment.coverage.complete,true);
  const requested={preserve:'serializable',analysisOptions:options};
  const reduced=reduceV4(relationMismatch,requested);
  assert.equal(reduced.analysis.judgment.status,'violation');
  assert.equal(reduced.oneMinimal,false,'A source-complete relation deletion exhausted its semantic search budget');
  assert.equal(verifyReductionV4(relationMismatch,reduced,requested).valid,true);
});
check('declared register unknown singleton deletions prevent oneMinimal',()=>{
  const options={maxAttempts:0};
  assert.equal(analyzeV4(register,options).judgment.status,'violation');
  for(const {id} of register.transactions){
    const candidate=withoutDeclaredTransaction(register,id);
    const report=analyzeV4(candidate,options);
    assert.equal(report.judgment.status,'inconclusive',id);
    assert.equal(report.judgment.evidence.search.status,'budget',id);
  }
  const requested={preserve:'serializable',analysisOptions:options};
  const reduced=reduceV4(register,requested);
  assert.equal(reduced.analysis.judgment.status,'violation');
  assert.equal(reduced.oneMinimal,false,'Unknown legacy reducer candidates cannot justify v4 minimality');
  assert.equal(verifyReductionV4(register,reduced,requested).valid,true);
});
check('adequate budgets still prove source-closed transaction minimality',()=>{
  for(const source of [list,relationMismatch,register]){
    const reduced=reduceV4(source,{preserve:'serializable'});
    assert.equal(reduced.oneMinimal,true);
    assert.equal(reduced.analysis.judgment.status,'violation');
  }
});
check('missing list writer remains unknown and cannot be accepted as complete',()=>{
  const missing=withoutCaptureTransaction(list,'P');
  const report=analyzeV4(missing);
  assert.equal(report.judgment.status,'inconclusive');
  assert.equal(report.judgment.coverage.complete,false);
  assert.ok(report.judgment.coverage.gaps.some(gap=>gap.code==='missing_item_source'));
  const classification=classifyV4(missing);
  assert.notEqual(classification.judgment.status,'checked-compatible');
});
check('reduction retains the required list source writer',()=>{
  const reduced=reduceV4(list,{preserve:'serializable'});
  const ids=reduced.reducedSource.events.filter(event=>event.kind==='begin').map(event=>event.tx);
  assert.deepEqual(ids,['P','A']);
  assert.deepEqual(reduced.source,list);
  assert.equal(reduced.analysis.observations.authenticityVerified,false);
});
check('reduction capsules require independent model and budget',()=>{
  const options={preserve:'serializable',maxChecks:0,analysisOptions:{maxStates:0}};
  const capsule=makeReductionCapsuleV4(list,options);
  assert.equal(replayCapsuleV4(capsule).valid,false);
  assert.equal(replayCapsuleV4(capsule,{...options,preserve:'strict-serializable'}).valid,false);
  assert.equal(replayCapsuleV4(capsule,options).valid,true);
});
check('capsule cannot authorize an over-limit budget with a recomputed digest',()=>{
  const capsule=JSON.parse(makeCapsuleV4(list));
  capsule.optionsText=JSON.stringify({maxStates:100001});
  capsule.optionsSha256=digest(capsule.optionsText);
  assert.equal(replayCapsuleV4(JSON.stringify(capsule),{maxStates:100001}).valid,false);
});
check('forged semantic identifiers remain invalid with matching envelope and report hashes',()=>{
  const capsule=JSON.parse(makeCapsuleV4(list));
  const report=JSON.parse(capsule.reportText);
  report.semanticContract='moontxnwitness-history-analysis-v4-forged';
  capsule.semanticContract=report.semanticContract;
  capsule.reportText=JSON.stringify(report);
  capsule.reportSha256=digest(capsule.reportText);
  assert.equal(replayCapsuleV4(JSON.stringify(capsule)).valid,false);
});
check('relation unsupported classification cannot be forged into a complete check',()=>{
  const relation=capture('relation-set-v1',[
    {kind:'snapshot',consistent:true,initial:{r:[]}},
    {kind:'begin',tx:'A',connection:'A'},
    {kind:'row_read',tx:'A',relation:'r',predicate:[],rows:[],complete:true},
    {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},
  ],{relationSchema:{r:{primaryKey:'id',columns:{id:'int64',n:'int64'}}},
    scope:{exclusiveWriters:true,completeSnapshotTables:['r']}});
  const capsule=JSON.parse(makeClassificationCapsuleV4(relation));
  const report=JSON.parse(capsule.reportText);
  assert.equal(report.judgment.status,'unsupported');
  assert.equal(replayCapsuleV4(JSON.stringify(capsule)).valid,true);
  report.judgment.status='checked-compatible';report.judgment.dependencyGraphComplete=true;
  for(const rule of Object.values(report.judgment.rules))rule.status='checked-compatible';
  capsule.reportText=JSON.stringify(report);capsule.reportSha256=digest(capsule.reportText);
  assert.equal(replayCapsuleV4(JSON.stringify(capsule)).valid,false);
});
const failed=results.filter(result=>!result.passed);
console.log(JSON.stringify({suite:'v4-independent-semantic-boundaries-1',passed:!failed.length,
  checks:results.length,failed:failed.length,results},null,2));
if(failed.length)process.exitCode=1;
