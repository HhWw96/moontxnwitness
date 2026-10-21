import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const corpus=resolve(process.argv[2]);
const engine=await import(pathToFileURL(resolve('dist/capture-core.mjs')).href);
const hash=b=>createHash('sha256').update(b).digest('hex');
const manifestBytes=readFileSync(resolve(corpus,'manifest.json'));
assert.equal(hash(manifestBytes),'5ead8d42f62b0141dcb2216914452b0e93267b009f2b1960576f0ecc789b389c');
const manifest=JSON.parse(manifestBytes);
for(const name of ['manual-preregistered.json','generated-inputs.json','independent-expectations.json']){
  const b=readFileSync(resolve(corpus,name));assert.equal(hash(b),manifest.files[name].sha256);
}
const inputs=[...JSON.parse(readFileSync(resolve(corpus,'manual-preregistered.json'))),...JSON.parse(readFileSync(resolve(corpus,'generated-inputs.json')))];
const expected=new Map(JSON.parse(readFileSync(resolve(corpus,'independent-expectations.json'))).map(x=>[x.id,x.reference]));
const call=g=>JSON.parse(engine.classification_graph_v3_json(JSON.stringify(g)));
const D=e=>e.kind==='ww'||e.kind==='wr',A=e=>e.kind==='rw-item'||e.kind==='rw-predicate';
let witnesses=0,absenceCertificates=0;
function validate(g,r){
  assert.equal(r.valid,true);assert.equal(r.graphOnly,true);assert.equal(r.modelCoverageAccepted,false);
  const index=new Map(g.nodes.map((n,i)=>[n,i])),original=new Map(g.edges.map(e=>[e.id,e]));
  for(const[name,c]of Object.entries(r.categories)){
    if(c.status==='cycle'){
      witnesses++;assert(c.edges.length>0);assert.equal(c.states.length,c.edges.length+1);
      assert.equal(c.states[0],c.states.at(-1));
      for(let i=0;i<c.edges.length;i++){
        const e=c.edges[i],next=c.edges[(i+1)%c.edges.length];assert.deepEqual(e,original.get(e.id));assert.equal(e.to,next.from);
        if(c.productGraph){
          assert.equal(Math.floor(c.states[i]/2),index.get(e.from));assert.equal(Math.floor(c.states[i+1]/2),index.get(e.to));
          if(A(e)){assert.equal(c.states[i]%2,0);assert.equal(c.states[i+1]%2,1);}else{assert(D(e));assert.equal(c.states[i+1]%2,0);}
        }else{assert.equal(c.states[i],index.get(e.from));assert.equal(c.states[i+1],index.get(e.to));}
      }
      if(name==='ww')assert(c.edges.every(e=>e.kind==='ww'));
      if(name==='wr-ww')assert(c.edges.every(D));
      if(name==='item-rw')assert(c.edges.some(e=>e.kind==='rw-item'));
      if(name==='any-rw'||name==='nonadjacent-rw')assert(c.edges.some(A));
      if(name!=='strict-graph')assert(c.edges.every(e=>e.kind!=='rt'));
      if(name==='nonadjacent-rw'){
        for(let i=0;i<c.edges.length;i++)assert(!(A(c.edges[i])&&A(c.edges[(i+1)%c.edges.length])));
        const expanded=[];
        for(const macro of c.macroSteps){assert(macro.parts.length===1||macro.parts.length===2);assert(D(macro.parts[0]));if(macro.parts.length===2){assert(A(macro.parts[1]));assert.equal(macro.parts[0].to,macro.parts[1].from);}expanded.push(...macro.parts);}
        assert.equal(expanded.length,c.edges.length);
        const ids=c.edges.map(e=>e.id),rotated=expanded.map(e=>e.id);assert(ids.some((_,offset)=>rotated.every((id,i)=>id===ids[(offset+i)%ids.length])));
        for(let i=0;i<expanded.length;i++)assert.equal(expanded[i].to,expanded[(i+1)%expanded.length].from);
      }
    }else if(c.status==='acyclic'){
      absenceCertificates++;assert.equal(g.complete,true);
      const groups=c.componentByState;assert.equal(groups.length,g.nodes.length*(c.productGraph?2:1));
      assert(groups.every(x=>Number.isInteger(x)&&x>=0&&x<groups.length));
      const arcs=[];
      for(const e of g.edges){
        const u=index.get(e.from),v=index.get(e.to);
        if(name==='ww'&&e.kind!=='ww')continue;
        if(name==='wr-ww'&&!D(e))continue;
        if(name!=='strict-graph'&&e.kind==='rt')continue;
        if(c.productGraph){if(D(e)){arcs.push([2*u,2*v,e],[2*u+1,2*v,e]);}else{arcs.push([2*u,2*v+1,e]);}}
        else arcs.push([u,v,e]);
      }
      for(const[u,v,e]of arcs){
        assert(groups[u]<=groups[v]);
        const marked=['ww','wr-ww','strict-graph'].includes(name)||(name==='item-rw'?e.kind==='rw-item':A(e));
        if(marked)assert(groups[u]<groups[v]);
      }
    }else assert.equal(c.status,'inconclusive');
  }
}
const checks=[],differences=[];let cases=0;
for(const item of inputs){
  try{
    const g={...item.graph,complete:true},r=call(g);validate(g,r);
    const actual=Object.entries(r.graphConstraints).filter(([,s])=>s==='cycle').map(([m])=>m).sort();
    assert.deepEqual(actual,[...expected.get(item.id).refuted].sort());
    assert(Object.values(r.graphConstraints).every(s=>s!=='inconclusive'));
  }catch(e){differences.push({id:item.id,error:e.message});}
  cases++;
}
function check(name,fn){try{fn();checks.push({name,passed:true});}catch(e){checks.push({name,passed:false,error:e.message});}}
const one={nodes:['A','B'],edges:[{id:'e',from:'A',to:'B',kind:'ww'}],complete:true};
check('hand-counted-exact-25-scans',()=>{const r=call({...one,budgets:{maxEdgeScans:25}});assert.equal(r.execution.edgeScans,25);assert.equal(r.execution.budgetExhausted,false);validate({...one,complete:true},r);assert(Object.values(r.graphConstraints).every(s=>s==='acyclic'));});
check('one-less-budget-no-false-absence',()=>{const r=call({...one,budgets:{maxEdgeScans:24}});assert.equal(r.execution.edgeScans,24);assert.equal(r.execution.budgetExhausted,true);assert.equal(r.graphConstraints['strict-pl-ss-v1'],'inconclusive');});
check('zero-budget-nonempty-inconclusive',()=>{const r=call({...one,budgets:{maxEdgeScans:0}});assert.equal(r.execution.edgeScans,0);assert(Object.values(r.graphConstraints).every(s=>s==='inconclusive'));});
check('empty-graph-zero-budget-valid-absence',()=>{const g={nodes:['A'],edges:[],complete:true,budgets:{maxEdgeScans:0}},r=call(g);validate(g,r);assert(Object.values(r.graphConstraints).every(s=>s==='acyclic'));});
check('incomplete-never-absence',()=>{const r=call({...one,complete:false});assert(Object.values(r.graphConstraints).every(s=>s==='inconclusive'));});
check('rt-cycle-invalid',()=>assert.equal(call({...one,edges:[{id:'a',from:'A',to:'B',kind:'rt'},{id:'b',from:'B',to:'A',kind:'rt'}]}).valid,false));
check('self-dependency-invalid',()=>assert.equal(call({...one,edges:[{id:'a',from:'A',to:'A',kind:'ww'}]}).valid,false));
check('unknown-vertex-invalid',()=>assert.equal(call({...one,edges:[{id:'a',from:'A',to:'Z',kind:'ww'}]}).valid,false));
check('duplicate-edge-identity-invalid',()=>assert.equal(call({...one,edges:[one.edges[0],one.edges[0]]}).valid,false));
check('duplicate-node-invalid',()=>assert.equal(call({...one,nodes:['A','A','B']}).valid,false));
check('unknown-edge-type-invalid',()=>assert.equal(call({...one,edges:[{...one.edges[0],kind:'unknown'}]}).valid,false));
check('negative-budget-invalid',()=>assert.equal(call({...one,budgets:{maxEdgeScans:-1}}).valid,false));
check('over-budget-invalid',()=>assert.equal(call({...one,budgets:{maxEdgeScans:1000001}}).valid,false));
check('512-node-chain-iterative-no-stack',()=>{const g={nodes:Array.from({length:512},(_,i)=>'T'+i),edges:Array.from({length:511},(_,i)=>({id:'e'+i,from:'T'+i,to:'T'+(i+1),kind:'wr'})),complete:true};const r=call(g);validate(g,r);assert(Object.values(r.graphConstraints).every(s=>s==='acyclic'));});
check('513-node-capacity-invalid',()=>assert.equal(call({nodes:Array.from({length:513},(_,i)=>'T'+i),edges:[],complete:true}).valid,false));
check('original-source-and-parallel-types-retained',()=>{const g={...one,edges:[{...one.edges[0],kind:'rw-predicate',source:{observation:7,key:'a\u0000b'}},{id:'reverse',from:'B',to:'A',kind:'rw-item',source:{observation:9}},{id:'parallel',from:'A',to:'B',kind:'ww',source:{observation:10}}]};const r=call(g);validate(g,r);assert.equal(r.categories['item-rw'].status,'cycle');});
mkdirSync('receipts',{recursive:true});
const receipt={schema:1,passed:!differences.length&&checks.every(x=>x.passed),graphOnly:true,modelCoverageAccepted:false,independentInputs:cases,differences,witnesses,absenceCertificates,checks,coreSha256:hash(readFileSync('dist/capture-core.mjs')),sourceSha256:JSON.parse(readFileSync('dist/build-manifest.json')).sourceSha256,oracleManifestSha256:hash(manifestBytes)};
writeFileSync(process.argv[3]||'receipts/graph-validation.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({...receipt,checks:checks.length}));
if(!receipt.passed)process.exitCode=1;
