import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,copyFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {matrixCases} from './cases.mjs';
const [runtimeArg,outArg,...extra]=process.argv.slice(2);
assert(runtimeArg&&outArg&&!extra.length,'Usage: prepare.mjs DIST NEW_OUTPUT');
const runtime=resolve(runtimeArg),out=resolve(outArg),sha=x=>createHash('sha256').update(x).digest('hex');
mkdirSync(out,{recursive:false});
const api=await import(pathToFileURL(resolve(runtime,'models-v4.mjs')));
const runtimeFiles=['core.mjs','models-v4.mjs','build-manifest.json'];
const runtimeBindings=()=>Object.fromEntries(runtimeFiles.map(n=>[n,sha(readFileSync(resolve(runtime,n)))]));
const before=runtimeBindings();
mkdirSync(resolve(out,'runtime'));
for(const name of runtimeFiles)copyFileSync(resolve(runtime,name),resolve(out,'runtime',name));
const matrix=matrixCases();
assert.deepEqual(matrix.models,api.ELLE_CORE_MODELS_V4);
const keywordTag=Symbol('EDN keyword');
const kw=name=>{assert(/^[a-z-]+$/.test(name));return {[keywordTag]:name};};
const edn=x=>x===null?'nil':typeof x==='string'?JSON.stringify(x):Array.isArray(x)?'['+x.map(edn).join(' ')+']':typeof x==='object'?x[keywordTag]?':'+x[keywordTag]:'{'+Object.entries(x).map(([k,v])=>':'+k+' '+edn(v)).join(' ')+'}':String(x);
function convert(row) {
  const source=row.input,events=source.events,txs=new Map();
  const membership=new Map();
  row.options.clients.forEach((c,i)=>c.transactions.forEach(t=>{assert(!membership.has(t));membership.set(t,i);}));
  for(const event of events){if(event.kind==='begin')txs.set(event.tx,{ops:[],begin:event});else if(event.tx){const tx=txs.get(event.tx);assert(tx);if(['read','write','list_read','append'].includes(event.kind))tx.ops.push(event);else if(['commit_ok','rollback_ok'].includes(event.kind)){assert(!tx.end);tx.end=event;}}}
  const history=[],completion=new Map();
  const initial=events[0].initial;
  for(const e of events){
    if(e.kind==='begin'){history.push({index:history.length,type:kw('invoke'),f:kw('txn'),process:membership.get(e.tx),time:e.time,value:null});}
    if(['commit_ok','rollback_ok'].includes(e.kind)){
      const tx=txs.get(e.tx);
      const value=tx.ops.map(o=>{
        if(o.kind==='read')return [kw('r'),o.key,o.version===initial[o.key]?null:o.version];
        if(o.kind==='write')return [kw('w'),o.key,o.version];
        if(o.kind==='list_read')return [kw('r'),o.key,o.items.map(v=>v.id)];
        return [kw('append'),o.key,o.id];
      });
      completion.set(e.tx,history.length);
      history.push({index:history.length,type:kw(e.kind==='commit_ok'?'ok':'fail'),f:kw('txn'),process:membership.get(e.tx),time:e.time,value});
    }
  }
  // The reference receives only explicit ORIGINAL predecessor facts, never SDK inferences.
  const ww=[];
  if(row.cohort==='explicit-original-order'){
    for(const [to,tx] of txs)for(const op of tx.ops)if(op.kind==='write'&&op.predecessor!==initial[op.key]){
      const writers=[...txs].filter(([,t])=>t.end.kind==='commit_ok'&&t.ops.filter(o=>o.kind==='write'&&o.key===op.key).at(-1)?.version===op.predecessor);
      assert.equal(writers.length,1,'Every external predecessor must identify one committed final writer');
      const producer=writers[0][1].ops.filter(o=>o.kind==='write'&&o.key===op.key).at(-1);
      ww.push([completion.get(writers[0][0]),completion.get(to),JSON.stringify({kind:'original-write-predecessor',operation:op,producer}),writers[0][1].ops.indexOf(producer),tx.ops.indexOf(op)]);
    }
  }
  return edn({id:row.id,'data-model':kw(row.dataModel==='point-register-v1'?'register':'list'),model:kw(row.model),history,'extra-ww':ww});
}
const moon=[],requests=[],failures=[];
for(const row of matrix.cases){
  const source=JSON.stringify(row.input),report=api.classifyModelsV4(source,row.options);
  assert.equal(api.verifyModelsV4(source,report,row.options).valid,true,row.id+' report failed independent recomputation');
  const status=report.models?.find(m=>m.model===row.model)?.status;
  const changed=structuredClone(report);changed.models[0].status=status==='refuted'?'checked-compatible':'refuted';
  assert.equal(api.verifyModelsV4(source,changed,row.options).valid,false,row.id+' altered verdict was accepted');
  const item={id:row.id,inputSha256:sha(source),optionsSha256:sha(JSON.stringify(row.options)),status,sourceProfile:report.sourceProfile,reportSha256:sha(JSON.stringify(report)),verified:true,changedVerdictRejected:true};
  if(row.expected&&status!==row.expected)failures.push({id:row.id,expected:row.expected,actual:status});
  moon.push(item);
  if(row.upstreamEligible)requests.push(convert(row));
}
const write=(name,bytes)=>writeFileSync(resolve(out,name),bytes,{flag:'wx'});
write('matrix.json',JSON.stringify(matrix,null,2)+'\n');
write('moon-results.jsonl',moon.map(x=>JSON.stringify(x)).join('\n')+'\n');
write('requests.edn','[\n'+requests.join('\n')+'\n]\n');
const result={format:'moontxnwitness-shared-model-preparation/v1',passed:!failures.length,cases:moon.length,requiredCases:matrix.cases.filter(c=>c.required).length,upstreamRequests:requests.length,failures,
  sourceRuntime:runtimeBindings(),inputs:Object.fromEntries(['matrix.json','moon-results.jsonl','requests.edn'].map(n=>[n,sha(readFileSync(resolve(out,n)))]))};
assert.deepEqual(result.sourceRuntime,before,'Runtime changed during preparation');
write('preparation.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
if(!result.passed)process.exitCode=1;
