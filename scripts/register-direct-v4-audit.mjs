// Independent SDK gate for formal direct register dependencies.
// Expected semantics are identical for every product version and transport.
// This is a small independent reference, not execution of the full Elle checker.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'..'),options={};
for(let i=2;i<process.argv.length;i+=2){
 const key=process.argv[i];assert(['--runtime','--output-root'].includes(key),'Unknown audit option');
 assert(process.argv[i+1],'Missing audit option value');assert(!options[key],'Duplicate audit option');options[key]=resolve(process.argv[i+1]);
}
const runtime=options['--runtime']||resolve(root,'dist'),output=options['--output-root']||resolve(root,'artifacts');mkdirSync(output,{recursive:true});
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const w=(key,version)=>({type:'write',key,version}),r=(key,version)=>({type:'read',key,version});
function history(ops,{b=[w('x','x2'),w('y','y1')],order=['x0','x1','x2']}={}){
 return {schemaVersion:1,model:'serializable',initial:{x:'x0',y:'y0'},versionOrders:{x:order,y:['y0','y1']},transactions:[{id:'A',status:'committed',ops},{id:'B',status:'committed',ops:b}]};
}
// Frozen hashes bind the three original histories and their direct edge sets.
// The first audit ran each against two runtimes (six original observations).
const inputs=[
 {name:'own-read-after-write',input:history([w('x','x1'),r('x','x1'),r('y','y1')]),
  inputSha256:'4e5df2f49bc6537a7d07fe974195c92da17061acb75dabfba74e07ac0dabad1f',edgeSha256:'0dee590ade7396d2eaa5b94c8e9c26513ebe590ec363360bc53ae726fcde8b6b'},
 {name:'initial-read-with-own-immediate-successor',input:history([r('x','x0'),w('x','x1'),r('y','y1')]),
  inputSha256:'713963723ae35f04ee86bf8a205720fa375b87a2e7882266d11ab2355412a5ef',edgeSha256:'0dee590ade7396d2eaa5b94c8e9c26513ebe590ec363360bc53ae726fcde8b6b'},
 {name:'genuine-immediate-external-successor-control',input:history([r('x','x0'),r('y','y1')],{b:[w('x','x1'),w('y','y1')],order:['x0','x1']}),
  inputSha256:'29c950d1407946c493a0ec61f5ad96159a2c8784a64dac7a7af369634379c694',edgeSha256:'841c58dab15382cab76c80f6a5db628582817e57213f38a086240755794a1afe'},
];
function directGraph(input){
 const readers=new Map(),writers=new Map();
 for(const tx of input.transactions){
  const touched=new Set(),reads=new Map(),writes=new Map();
  for(const op of tx.ops){if(!touched.has(op.key)&&op.type==='read')reads.set(op.key,op.version);touched.add(op.key);if(op.type==='write')writes.set(op.key,op.version);}
  readers.set(tx.id,reads);writers.set(tx.id,writes);
 }
 const edges=[];const add=(from,to,kind,key,fromVersion,toVersion)=>{if(from!==to)edges.push({from,to,kind,key,fromVersion,toVersion});};
 for(const [key,order]of Object.entries(input.versionOrders))for(let i=0;i+1<order.length;i++){
  const current=order[i],next=order[i+1],before=[...writers].filter(([,m])=>m.get(key)===current),after=[...writers].filter(([,m])=>m.get(key)===next);
  for(const [a]of before)for(const [b]of after)add(a,b,'ww',key,current,next);
  // An immediate successor owned by the reader produces only a self edge.
  // Dropping that self edge must not jump to a later external writer.
  for(const [a,reads]of readers)if(reads.get(key)===current)for(const [b]of after)add(a,b,'rw',key,current,next);
 }
 for(const [a,writes]of writers)for(const [b,reads]of readers)for(const [key,value]of writes)if(reads.get(key)===value)add(a,b,'wr',key,value,value);
 const cycles=[];
 for(const start of input.transactions.map(t=>t.id)){
  function walk(at,path,seen){for(const edge of edges.filter(e=>e.from===at)){if(edge.to===start&&path.length)cycles.push([...path,edge]);else if(!seen.has(edge.to))walk(edge.to,[...path,edge],new Set([...seen,edge.to]));}}
  walk(start,[],new Set([start]));
 }
 return {externalReads:Object.fromEntries([...readers].map(([id,map])=>[id,Object.fromEntries(map)])),finalWrites:Object.fromEntries([...writers].map(([id,map])=>[id,Object.fromEntries(map)])),edges,
  refuted:{G0:cycles.some(c=>c.every(e=>e.kind==='ww')),G1c:cycles.some(c=>c.every(e=>e.kind!=='rw')),'G2-item':cycles.some(c=>c.some(e=>e.kind==='rw')),'G-single':cycles.some(c=>c.filter(e=>e.kind==='rw').length===1)}};
}
function edgesOf(edges){return edges.map(raw=>{const e=raw.edge??raw;return {from:e.from,to:e.to,kind:e.kind,key:e.key,fromVersion:e.fromVersion,toVersion:e.toVersion};}).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));}
function bindings(){
 const result=Object.fromEntries(['sdk.mjs','v4.mjs','core.mjs','capture-core.mjs'].map(name=>[name,hash(readFileSync(resolve(runtime,name)))]));
 result['build-manifest.json']=existsSync(resolve(runtime,'build-manifest.json'))?hash(readFileSync(resolve(runtime,'build-manifest.json'))):null;return result;
}
const results=[];let before,after,version,categories,gSingleSupport,setupError;
try{
 before=bindings();const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);version=sdk.version();
 const parts=/^(\d+)\.(\d+)\.(\d+)$/.exec(version);assert(parts,'Unrecognized product version metadata');
 const [major,minor,patch]=parts.slice(1).map(Number),declaresSingle=major>0||minor>3||(minor===3&&patch>=3);
 categories=['G0','G1c','G2-item'];
 if(declaresSingle){
  // Product metadata only selects an additional required API capability check;
  // the named rule must actually be implemented. Expected graph semantics never vary.
  const capability=sdk.classifyV4(inputs[2].input,{categories:['G-single']});
  assert(capability.judgment.rules['G-single'],'Declared G-single API capability is absent');
  assert.equal(capability.judgment.rules['G-single'].status,'refuted','G-single positive capability control');
  assert.equal(capability.judgment.rules['G-single'].evidence?.specificCategory,'G-single-item');
  categories.push('G-single');gSingleSupport='declared >=0.3.3 and explicitly verified named G-single positive control';
 }else gSingleSupport='not requested: original <=0.3.2 SDK contract supports G0/G1c/G2-item only';
 for(const transport of ['object','json-text'])for(const frozen of inputs){
  const entry={name:frozen.name+' / '+transport,originalCase:frozen.name,transport,inputSha256:frozen.inputSha256,expectedEdgeSha256:frozen.edgeSha256};
  try{
   assert.equal(hash(JSON.stringify(frozen.input)),frozen.inputSha256,'Original frozen input changed');
   const reference=directGraph(frozen.input);assert.equal(hash(JSON.stringify(reference.edges)),frozen.edgeSha256,'Original frozen direct graph changed');entry.reference=reference;
   const input=transport==='object'?structuredClone(frozen.input):JSON.stringify(frozen.input),report=sdk.classifyV4(input,{categories});entry.actualReport=report;
   const verified=sdk.verifyClassificationV4(input,report,{categories});entry.reportSelfVerification=verified;
   assert.equal(verified.valid,true,'Report self-verification is required but is not sufficient to establish category correctness');
   assert.equal(report.judgment.dependencyGraphComplete,true,'These complete histories must not be hidden behind an unknown graph');
   assert.deepEqual(report.judgment.sourceOrOrderGaps,[]);
   assert.deepEqual(edgesOf(report.judgment.dependencies),edgesOf(reference.edges),'Item graph must use external reads/final writes and immediate version successors');
   for(const category of categories){
    const rule=report.judgment.rules[category];assert(rule,'Missing requested category '+category);
    assert.equal(rule.status,reference.refuted[category]?'refuted':'checked-compatible','Independent '+category+' classification');
    if(reference.refuted[category])for(const edge of edgesOf(rule.evidence.edges))assert(edgesOf(reference.edges).some(expected=>JSON.stringify(expected)===JSON.stringify(edge)),'Witness uses an edge absent from the independent direct graph');
   }
   entry.passed=true;
  }catch(error){entry.passed=false;entry.error=error.message;}
  results.push(entry);
 }
 after=bindings();assert.deepEqual(after,before,'Runtime changed during independent audit');
}catch(error){setupError=error;results.push({name:'audit setup or runtime identity',passed:false,error:error.message});}
const failed=results.filter(row=>!row.passed),receipt={suite:'register-direct-v4-independent-sdk-audit-1',passed:!setupError&&failed.length===0,checks:results.length,failed:failed.length,
 version:version??null,runtime,checkedCategories:categories??[],gSingleSupport:gSingleSupport??null,actualDatabaseExecution:false,formalPerformanceMeasurement:false,actualClojureExecution:false,
 formalReferenceIsCompleteElleChecker:false,scope:'Formal item direct-dependency categories on the frozen declared-register histories; report replay consistency alone does not prove a sound category.',
 originalFailure:{artifact:'independent-register-rw-validation.json',sha256:'0bdf0d1f2d8fa54b1d79a5aa45050260a282eb80c83652658fd2da65b0032efd',suite:'independent-register-external-next-version-audit-1',originalObservations:6,uniqueHistories:3,disagreeingOriginalRuntimeCases:2,
  mapping:'The original three histories were checked against two runtimes. This portable gate checks the same three unchanged histories through object and JSON-text SDK transports, with identical expected direct graphs.'},
 primaryReferences:[{url:'https://jepsen.io/consistency/dependencies',rule:'Item WW and RW target the next version; predicate edges follow a distinct rule.'},
  {url:'https://github.com/jepsen-io/elle/blob/4e359e597c52938b0afebb8bc42273914d68a424/src/elle/rw_register.clj#L704',sha256:'9ad17da5b86e6e25fe66b77e0deab9000265901a1bedd5045dbba98c7dddd1ce',rule:'External-read/final-write indexes, explicit version-graph edges, remove self edges. Default nil-version inference is not the complete-order reference used by this audit.'},
  {url:'https://repo.clojars.org/jepsen/txn/jepsen.txn/0.1.3/jepsen.txn-0.1.3.jar',sha256:'cef71a591cbb7d7d3df29cc332bb03930cc18802104f7441d551aeb36f510b1b',member:'jepsen/txn.clj',memberSha256:'7bff6ba23bd59bca8e8c7fe870ec94c3677b4e6e484a387121e87e46e963cb21',lineRange:[49,78]}],
 testedFileSha256Before:before??null,testedFileSha256After:after??null,runtimeUnchanged:before!==undefined&&after!==undefined&&JSON.stringify(before)===JSON.stringify(after),testFileSha256:hash(readFileSync(new URL(import.meta.url))),results};
writeFileSync(resolve(output,'register-direct-v4-audit.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
