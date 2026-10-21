import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,openSync,writeSync,closeSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {gunzipSync,gzipSync} from 'node:zlib';
const here=dirname(fileURLToPath(import.meta.url)),sha=b=>createHash('sha256').update(b).digest('hex');
const pin='af606ccd40106ae9a5b46d12d550f0a3002b404c60018ca4512544c66295f1d1';
assert.equal(typeof process.argv[2],'string','Pass the separately published fixed capture-core.mjs path');
const path=resolve(process.argv[2]);
assert.equal(sha(readFileSync(path)),pin);
const engine=await import(pathToFileURL(path).href);
const manifest=JSON.parse(readFileSync(resolve(here,'conversion-freeze.json')));
for(const[name,b]of Object.entries(manifest.files)){const raw=readFileSync(resolve(here,name));assert.equal(raw.length,b.bytes);assert.equal(sha(raw),b.sha256);}
const inputs=gunzipSync(readFileSync(resolve(here,'converted-inputs-v1.jsonl.gz'))).toString().trim().split('\n').map(JSON.parse);
const D=e=>e.kind==='ww'||e.kind==='wr',RW=e=>e.kind==='rw-item';
function reachability(n,arcs){const a=Array.from({length:n},()=>Array(n).fill(false));for(const[u,v]of arcs)a[u][v]=true;for(let k=0;k<n;k++)for(let i=0;i<n;i++)for(let j=0;j<n;j++)a[i][j] ||=a[i][k]&&a[k][j];return a;}
function truth(g){
 const ix=new Map(g.nodes.map((x,i)=>[x,i])),edges=g.edges.map(e=>({...e,u:ix.get(e.from),v:ix.get(e.to)}));
 const d=edges.filter(D),rw=edges.filter(RW),ww=edges.filter(e=>e.kind==='ww');
 const h=[...d.map(e=>[e.u,e.v]),...d.flatMap(e=>rw.filter(f=>e.v===f.u).map(f=>[e.u,f.v]))],markedH=d.flatMap(e=>rw.filter(f=>e.v===f.u).map(f=>[e.u,f.v]));
 const rd=reachability(ix.size,d.map(e=>[e.u,e.v])),rf=reachability(ix.size,edges.map(e=>[e.u,e.v])),rh=reachability(ix.size,h),rww=reachability(ix.size,ww.map(e=>[e.u,e.v]));
 const cyclic=a=>a.some((row,i)=>row[i]);
 const marked=(a,es)=>es.some(([u,v])=>u===v||a[v][u]);
 return {ww:cyclic(rww),'wr-ww':cyclic(rd),'item-rw':marked(rf,rw.map(e=>[e.u,e.v])),'any-rw':marked(rf,rw.map(e=>[e.u,e.v])),'nonadjacent-rw':marked(rh,markedH),'strict-graph':cyclic(rf),gsiRejected:cyclic(rh),serialRejected:cyclic(rf)};
}
let checkedWitnesses=0,checkedAbsences=0;const differences=[],outputs=openSync(resolve(here,'kernel-results-v1.jsonl.gz'),'wx');
function verify(g,r,expected){
 assert.equal(r.valid,true);assert.equal(r.graphOnly,true);assert.equal(r.modelCoverageAccepted,false);
 const originals=new Map(g.edges.map(e=>[e.id,e])),index=new Map(g.nodes.map((n,i)=>[n,i]));
 for(const[name,c]of Object.entries(r.categories)){
  if(c.status==='inconclusive')continue;
  assert.equal(c.status==='cycle',expected[name],name+' independent macro/reachability disagreement');
  if(c.status==='acyclic'){checkedAbsences++;continue;}
  assert.equal(c.status,'cycle');checkedWitnesses++;assert(c.edges.length>0);assert.equal(c.states.length,c.edges.length+1);assert.equal(c.states[0],c.states.at(-1));
  for(let i=0;i<c.edges.length;i++){
   const e=c.edges[i],next=c.edges[(i+1)%c.edges.length];assert.deepEqual(e,originals.get(e.id));assert.equal(e.to,next.from);
   if(c.productGraph){assert.equal(Math.floor(c.states[i]/2),index.get(e.from));assert.equal(Math.floor(c.states[i+1]/2),index.get(e.to));if(RW(e)){assert.equal(c.states[i]%2,0);assert.equal(c.states[i+1]%2,1);}else{assert(D(e));assert.equal(c.states[i+1]%2,0);}}
   else{assert.equal(c.states[i],index.get(e.from));assert.equal(c.states[i+1],index.get(e.to));}
  }
  if(name==='ww')assert(c.edges.every(e=>e.kind==='ww'));
  if(name==='wr-ww')assert(c.edges.every(D));
  if(['item-rw','any-rw','nonadjacent-rw'].includes(name))assert(c.edges.some(RW));
  if(name==='nonadjacent-rw'){
   for(let i=0;i<c.edges.length;i++)assert(!(RW(c.edges[i])&&RW(c.edges[(i+1)%c.edges.length])));
   const expanded=c.macroSteps.flatMap(m=>{assert(m.parts.length===1||m.parts.length===2);assert(D(m.parts[0]));if(m.parts.length===2){assert(RW(m.parts[1]));assert.equal(m.parts[0].to,m.parts[1].from);}return m.parts;});
   assert.equal(expanded.length,c.edges.length);for(let i=0;i<expanded.length;i++){assert.deepEqual(expanded[i],originals.get(expanded[i].id));assert.equal(expanded[i].to,expanded[(i+1)%expanded.length].from);}
   assert(c.edges.some((_,off)=>expanded.every((e,i)=>e.id===c.edges[(off+i)%c.edges.length].id)));
  }
 }
}
const state=r=>Object.fromEntries(Object.entries(r.categories).map(([k,c])=>[k,c.status]));
let common=0,reverseChecks=0,kernelUnknown=0,budgetChecks=0;
for(const input of inputs){
 if(!input.conversion.eligible)continue;
 const g=input.conversion.graph,t=truth(g);assert.equal(t.gsiRejected,input.conversion.truth.gsiRejected);assert.equal(t.serialRejected,input.conversion.truth.serialRejected);
 try{
  const r=JSON.parse(engine.classification_graph_v3_json(JSON.stringify(g)));verify(g,r,t);
  const reverse={...g,nodes:[...g.nodes].reverse(),edges:[...g.edges].reverse()};const rr=JSON.parse(engine.classification_graph_v3_json(JSON.stringify(reverse)));verify(reverse,rr,t);assert.deepEqual(state(r),state(rr));reverseChecks++;
  const combine=(a,b)=>[r.categories[a].status,r.categories[b].status].includes('cycle')?'unsatisfiable':[r.categories[a].status,r.categories[b].status].every(x=>x==='acyclic')?'satisfiable':'inconclusive';
  const mapped={si:combine('wr-ww','nonadjacent-rw'),serial:combine('wr-ww','any-rw')};if(Object.values(mapped).includes('inconclusive'))kernelUnknown++;
  writeSync(outputs,gzipSync(Buffer.from(JSON.stringify({id:input.id,inputSha256:input.inputSha256,report:r,mapped,independent:t,reverseReportSha256:sha(Buffer.from(JSON.stringify(rr)))})+'\n')));common++;
 }catch(error){differences.push({id:input.id,inputSha256:input.inputSha256,error:error.message});}
}
closeSync(outputs);
for(const graph of [{nodes:['n0'],edges:[],complete:true,budgets:{maxEdgeScans:0}},...inputs.filter(x=>x.conversion.eligible&&x.conversion.graph.edges.length).slice(0,2).map(x=>({...x.conversion.graph,budgets:{maxEdgeScans:0}}))]){
 const r=JSON.parse(engine.classification_graph_v3_json(JSON.stringify(graph)));assert.equal(r.valid,true);assert.equal(r.execution.edgeScans,0);assert(Object.values(r.categories).every(c=>c.status===(graph.edges.length?'inconclusive':'acyclic')));budgetChecks++;
}
const receipt={schema:1,passed:differences.length===0,inputRecords:inputs.length,commonGraphCases:common,excludedOrDirectCases:inputs.length-common,kernelUnknown,reverseNodeEdgeOrderChecks:reverseChecks,additionalBudgetChecks:budgetChecks,checkedWitnesses,checkedAbsences,differences,
 captureCoreSha256:pin,sourceSha256:'217388d9be420c2b881f32e57ccf1e71f598d929ed5e4f745924be71d65e58ca',conversionManifestSha256:sha(readFileSync(resolve(here,'conversion-freeze.json'))),implementationSha256:sha(readFileSync(fileURLToPath(import.meta.url))),kernelResultsSha256:sha(readFileSync(resolve(here,'kernel-results-v1.jsonl.gz'))),oracleResultsRead:false,oracleImplementationRead:false,elleExecuted:false,stableClassifier:false,experimental:true};
const raw=JSON.stringify(receipt,null,2)+'\n';writeFileSync(resolve(here,'kernel-check-receipt-v1.json'),raw,{flag:'wx'});console.log(JSON.stringify({...receipt,receiptSha256:sha(Buffer.from(raw))}));if(!receipt.passed)process.exitCode=1;
