// Independent synthetic counterexamples for v0.3.3 core/wire semantics.
// This suite neither builds dist nor exercises the compact-runtime implementation.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import * as sdk from '../dist/sdk.mjs';
const root=resolve(import.meta.dirname,'..'),results=[];
const hash=value=>createHash('sha256').update(value).digest('hex');
function check(name,fn){try{fn();results.push({name,passed:true});}catch(error){results.push({name,passed:false,error:error.stack});}}
const read=(key,version)=>({type:'read',key,version}),write=(key,version)=>({type:'write',key,version});
const tx=(id,ops,status='committed',extra={})=>({id,status,ops,...extra});
const history=(initial,transactions,extra={})=>({schemaVersion:1,model:'serializable',initial,transactions,...extra});
function capture(model,initial,body){return {traceSchema:3,dataModel:model,clockDomain:'independent-033-audit',scope:{exclusiveWriters:true},gaps:[],events:[{kind:'snapshot',initial,consistent:true},...body].map((event,index)=>({seq:index+1,time:index,...event}))};}
function has(report,kind){assert.ok(Array.isArray(report.findings),report.error||'Missing finding list');return report.findings.some(item=>item.kind===kind);}
const effective={listGraph:'effective-v1',categories:['G0','G1c','G2-item','G-single']};
const sourceNames=['scripts/v033-independent-anomalies-test.mjs','src/anomalies_v4.mbt','src/lost_updates_v4.mbt','src/g_single_v4.mbt','src/list_graph_v4.mbt','src/classification_v4.mbt','src/api_v4.mbt','cmd/v4.mjs','dist/v4.mjs','dist/core.mjs'];
const before=Object.fromEntries(sourceNames.map(name=>[name,hash(readFileSync(resolve(root,name)))]));

check('key-scoped external identities cannot masquerade as an own future write',()=>{
 const source=history({x:'same0',y:'same0'},[tx('A',[read('x','same1'),write('y','same1')]),tx('B',[write('x','same1')])]);
 const report=sdk.inspectAnomaliesV4(source);
 assert.equal(has(report,'future-read'),false);assert.equal(has(report,'identity-conflict'),false);assert.equal(has(report,'missing-source'),false);
});
check('an aborted own-future observation does not assert a committed anomaly',()=>{
 const source=history({x:'x0'},[tx('A',[read('x','later'),write('x','later')],'aborted')]);
 assert.equal(has(sdk.inspectAnomaliesV4(source),'future-read'),false);
});
check('a committed own-future observation has a real operation-order witness',()=>{
 const source=history({x:'x0'},[tx('A',[read('x','later'),write('x','later')])]);
 const report=sdk.inspectAnomaliesV4(source),proof=report.findings.find(item=>item.kind==='future-read');
 assert.ok(proof);assert.equal(proof.evidence.read.operationIndex,0);assert.equal(proof.evidence.source.operationIndex,1);
 assert.equal(report.scope.acceptsIsolationModels,false);assert.equal(sdk.verifyAnomaliesV4(source,report).valid,true);
});
check('a later cross-client write observation stays uncertain rather than future-read',()=>{
 const source=capture('point-register-v1',{x:'x0'},[
  {kind:'begin',tx:'R',connection:'r'},{kind:'read',tx:'R',key:'x',version:'v1'},
  {kind:'begin',tx:'W',connection:'w'},{kind:'write',tx:'W',key:'x',version:'v1',predecessor:'x0'},
  {kind:'commit_request',tx:'R'},{kind:'commit_ok',tx:'R'},{kind:'commit_request',tx:'W'},{kind:'commit_ok',tx:'W'},
 ]);
 const report=sdk.inspectAnomaliesV4(source);assert.equal(has(report,'future-read'),false);
 assert.ok(report.coverage.diagnosticGaps.some(item=>item.kind==='source-observation-order'));
});
check('equal list business values never substitute for a future item identity',()=>{
 const source=capture('append-list-v1',{x:[{id:'initial',value:'same'}]},[
  {kind:'begin',tx:'A',connection:'a'},{kind:'list_read',tx:'A',key:'x',items:[{id:'initial',value:'same'}]},
  {kind:'append',tx:'A',key:'x',id:'later',value:'same'},{kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},
 ]);
 const report=sdk.inspectAnomaliesV4(source);assert.equal(has(report,'future-read'),false);assert.equal(has(report,'identity-conflict'),false);
});
check('conflicting order in an aborted read is not a proved source-order cycle',()=>{
 const source=capture('append-list-v1',{x:[{id:'a',value:'A'},{id:'b',value:'B'}]},[
  {kind:'begin',tx:'R',connection:'r'},{kind:'list_read',tx:'R',key:'x',items:[{id:'b',value:'B'},{id:'a',value:'A'}]},{kind:'rollback_ok',tx:'R'},
 ]);
 assert.equal(has(sdk.inspectAnomaliesV4(source),'version-order-conflict'),false);
});
check('list identity-value conflict is source-bound rather than a future-read guess',()=>{
 const source=capture('append-list-v1',{x:[{id:'i',value:'original'}]},[
  {kind:'begin',tx:'R',connection:'r'},{kind:'list_read',tx:'R',key:'x',items:[{id:'i',value:'different'}]},
  {kind:'commit_request',tx:'R'},{kind:'commit_ok',tx:'R'},
 ]);
 const report=sdk.inspectAnomaliesV4(source);assert.equal(has(report,'identity-conflict'),true);assert.equal(has(report,'future-read'),false);
 assert.equal(report.scope.authenticityVerified,false);
});

const twoRW=history({x:'x0',y:'y0'},[
 tx('A',[read('x','x0'),write('y','y1')]),tx('B',[read('y','y0'),write('x','x1')]),
]);
check('a two-anti-dependency cycle does not refute G-single',()=>{
 const report=sdk.classifyV4(twoRW,{categories:['G-single']});assert.equal(report.judgment.rules['G-single'].status,'checked-compatible');
 assert.equal(sdk.classifyV4(twoRW,{categories:['G2-item']}).judgment.status,'refuted');
});
check('a realtime edge cannot close a G-single data witness',()=>{
 const source=history({x:'x0'},[tx('W',[write('x','x1')],'committed',{start:0,end:1}),tx('R',[read('x','x0')],'committed',{start:2,end:3})],{model:'strict-serializable'});
 assert.equal(sdk.analyzeV4(source).judgment.status,'violation');
 assert.equal(sdk.classifyV4(source,{categories:['G-single']}).judgment.status,'checked-compatible');
});
const staleBlind=history({x:'x0'},[tx('A',[write('x','a')]),tx('B',[read('x','x0'),write('x','b')])],{versionOrders:{x:['x0','a','b']}});
check('a valid one-RW cycle remains distinct from the two-reader lost-update pattern',()=>{
 const report=sdk.classifyV4(staleBlind,{categories:['G-single']});assert.equal(report.judgment.status,'refuted');
 assert.equal(report.judgment.rules['G-single'].evidence.rwEdgeCount,1);
 assert.equal(has(sdk.inspectLostUpdatesV4(staleBlind),'lost-update'),false);
});

const manyBody=[],manyItems=[];
for(let index=0;index<9;index++){
 const id='W'+index;manyBody.push({kind:'begin',tx:id,connection:id});
 for(let op=0;op<2;op++){const item=id+'-'+op;manyBody.push({kind:'append',tx:id,key:'x',id:item,value:'same'});manyItems.push({id:item,value:'same'});}
 manyBody.push({kind:'commit_request',tx:id},{kind:'commit_ok',tx:id});
}
manyBody.push({kind:'begin',tx:'R',connection:'r'},{kind:'list_read',tx:'R',key:'x',items:manyItems},{kind:'commit_request',tx:'R'},{kind:'commit_ok',tx:'R'});
const many=capture('append-list-v1',{x:[]},manyBody);
check('ten transactions with multiple appends have an acyclic effective graph without expanding the legacy scope',()=>{
 const report=sdk.classifyV4(many,effective);assert.equal(report.judgment.status,'checked-compatible');assert.equal(report.judgment.dependencyGraphComplete,true);
 assert.equal(report.judgment.acceptsIsolationModels,false);assert.equal(sdk.classifyV4(many).judgment.status,'inconclusive');
 assert.equal(sdk.analyzeV4(many).judgment.status,'inconclusive');
});
check('delivered own reads before rollback are not global append order evidence',()=>{
 const source=capture('append-list-v1',{x:[]},[
  {kind:'begin',tx:'A',connection:'a'},{kind:'savepoint',tx:'A',name:'s',instance:'s1'},
  {kind:'append',tx:'A',key:'x',id:'temporary',value:'T'},{kind:'list_read',tx:'A',key:'x',items:[{id:'temporary',value:'T'}]},
  {kind:'rollback_to',tx:'A',instance:'s1'},{kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},
 ]);
 const report=sdk.classifyV4(source,effective);assert.equal(report.judgment.status,'checked-compatible');assert.equal(report.judgment.dependencyGraphComplete,true);
 assert.equal(has(sdk.inspectAnomaliesV4(source),'future-read'),false);
});
function externalReadCase(orderings){
 const body=[{kind:'begin',tx:'P',connection:'p'},{kind:'append',tx:'P',key:'x',id:'a',value:'same'},{kind:'commit_request',tx:'P'},{kind:'commit_ok',tx:'P'},
  {kind:'begin',tx:'Q',connection:'q'},{kind:'append',tx:'Q',key:'x',id:'b',value:'same'},{kind:'commit_request',tx:'Q'},{kind:'commit_ok',tx:'Q'}];
 for(let i=0;i<orderings.length;i++){const tx='R'+i;body.push({kind:'begin',tx,connection:tx},{kind:'list_read',tx,key:'x',items:orderings[i].map(id=>({id,value:'same'}))},{kind:'commit_request',tx},{kind:'commit_ok',tx});}
 return capture('append-list-v1',{x:[]},body);
}
check('mutually exclusive item orders are quarantined rather than invented as G0',()=>{
 const source=externalReadCase([['a','b'],['b','a']]),report=sdk.classifyV4(source,{...effective,categories:['G0']});
 assert.equal(report.judgment.rules.G0.status,'unknown');assert.equal(report.judgment.dependencyGraphComplete,false);
 assert.ok(report.inferences.listGraph.quarantinedDependencies.length>0);
});
check('consistent item order with an interleaved transaction block can still prove a real WW cycle',()=>{
 const source=capture('append-list-v1',{x:[]},[
  {kind:'begin',tx:'P',connection:'p'},{kind:'append',tx:'P',key:'x',id:'a1',value:'same'},{kind:'append',tx:'P',key:'x',id:'a2',value:'same'},{kind:'commit_request',tx:'P'},{kind:'commit_ok',tx:'P'},
  {kind:'begin',tx:'Q',connection:'q'},{kind:'append',tx:'Q',key:'x',id:'b',value:'same'},{kind:'commit_request',tx:'Q'},{kind:'commit_ok',tx:'Q'},
  {kind:'begin',tx:'R',connection:'r'},{kind:'list_read',tx:'R',key:'x',items:['a1','b','a2'].map(id=>({id,value:'same'}))},{kind:'commit_request',tx:'R'},{kind:'commit_ok',tx:'R'},
 ]);
 const report=sdk.classifyV4(source,{...effective,categories:['G0']});assert.equal(report.judgment.status,'refuted');assert.equal(report.judgment.dependencyGraphComplete,false);
 const witness=report.judgment.rules.G0.evidence;
 assert.equal(witness.kind,'source-checked-effective-list-dependency-cycle');assert.ok(witness.edges.length>=2);
 for(let i=0;i<witness.edges.length;i++){
  const current=witness.edges[i],next=witness.edges[(i+1)%witness.edges.length];
  assert.equal(current.edge.kind,'ww');assert.equal(current.edge.to,next.edge.from);assert.ok(current.sources.length>0);
  for(const proof of current.sources){
   const observed=source.events.find(event=>event.seq===proof.readSeq);assert.equal(observed.kind,'list_read');
   const from=observed.items.findIndex(item=>item.id===current.edge.fromVersion),to=observed.items.findIndex(item=>item.id===current.edge.toVersion);
   assert.ok(from>=0&&to>from);
  }
 }
 assert.equal(sdk.verifyClassificationV4(source,report,{...effective,categories:['G0']}).valid,true);
});
check('effective graph construction cannot self-authorize a larger budget through a capsule',()=>{
 const limited={...effective,maxListGraphChecks:0},report=sdk.classifyV4(many,limited);assert.equal(report.judgment.status,'inconclusive');
 const capsule=sdk.makeClassificationCapsuleV4(many,limited);assert.equal(sdk.replayCapsuleV4(capsule,effective).valid,false);assert.equal(sdk.replayCapsuleV4(capsule,limited).valid,true);
});

check('blind writes and a first own read cannot be promoted into two external reads',()=>{
 const source=history({x:'x0'},[tx('A',[write('x','a'),read('x','a')]),tx('B',[read('x','x0'),write('x','b')])]);
 assert.equal(has(sdk.inspectLostUpdatesV4(source),'lost-update'),false);
});
check('unknown or aborted participants do not prove a committed lost-update pair',()=>{
 for(const status of ['unknown','aborted']){
  const source=history({x:'x0'},[tx('A',[read('x','x0'),write('x','a')],status),tx('B',[read('x','x0'),write('x','b')])]);
  assert.equal(has(sdk.inspectLostUpdatesV4(source),'lost-update'),false,status);
 }
});
check('same returned version on different keys is not one lost-update group',()=>{
 const source=history({x:'zero',y:'zero'},[tx('A',[read('x','zero'),write('x','one')]),tx('B',[read('y','zero'),write('y','one')])]);
 assert.equal(has(sdk.inspectLostUpdatesV4(source),'lost-update'),false);
});
check('rollback restores the actual external-read overlay and preserves a real lost-update witness',()=>{
 const source=capture('point-register-v1',{x:'x0'},[
  {kind:'begin',tx:'A',connection:'a'},{kind:'begin',tx:'B',connection:'b'},{kind:'read',tx:'B',key:'x',version:'x0'},
  {kind:'savepoint',tx:'A',name:'s',instance:'s1'},{kind:'write',tx:'A',key:'x',version:'temporary',predecessor:'x0'},
  {kind:'rollback_to',tx:'A',instance:'s1'},{kind:'read',tx:'A',key:'x',version:'x0'},{kind:'write',tx:'A',key:'x',version:'a',predecessor:'x0'},
  {kind:'commit_request',tx:'A'},{kind:'commit_ok',tx:'A'},{kind:'write',tx:'B',key:'x',version:'b',predecessor:'a'},{kind:'commit_request',tx:'B'},{kind:'commit_ok',tx:'B'},
 ]);
 const report=sdk.inspectLostUpdatesV4(source);assert.equal(has(report,'lost-update'),true);assert.equal(report.scope.dirtyUpdateSupported,false);
 assert.equal(sdk.verifyLostUpdatesV4(source,report).valid,true);
});
check('self-consistent hashes cannot turn source diagnostics into isolation-model acceptance',()=>{
 const source=history({x:'x0'},[tx('A',[read('x','x0'),write('x','a')]),tx('B',[read('x','x0'),write('x','b')])]);
 const capsule=JSON.parse(sdk.makeLostUpdatesCapsuleV4(source)),report=JSON.parse(capsule.reportText);
 report.scope.acceptsIsolationModels=true;report.scope.dirtyUpdateSupported=true;capsule.reportText=JSON.stringify(report);capsule.reportSha256=hash(capsule.reportText);
 assert.equal(sdk.replayCapsuleV4(JSON.stringify(capsule)).valid,false);
});
const after=Object.fromEntries(sourceNames.map(name=>[name,hash(readFileSync(resolve(root,name)))]));
assert.deepEqual(after,before,'Reviewed source or runtime changed during the independent checks');
const failed=results.filter(result=>!result.passed);
const receipt={suite:'v033-independent-anomaly-counterexamples-1',passed:failed.length===0,checks:results.length,failed:failed.length,
 actualDatabaseExecution:false,formalPerformanceMeasured:false,loaderAcceptanceIncluded:false,reviewedImplementationAuthoredByThisReviewer:false,
 executedFrom:'current frozen dist; no build was run by this test',results,testedFileSha256Before:before,testedFileSha256After:after};
mkdirSync(resolve(root,'artifacts'),{recursive:true});writeFileSync(resolve(root,'artifacts/v033-independent-anomalies.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt,null,2));if(failed.length)process.exitCode=1;
