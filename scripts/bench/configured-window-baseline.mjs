// Complete configured SDK calls; inputs and outputs remain bound to their bytes.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {cpus,platform,release,arch,totalmem} from 'node:os';
import {parseStaticImports} from './full-sdk/parse-static-imports.mjs';

const sha=x=>createHash('sha256').update(x).digest('hex');
const [planFile,output,childCase,mode]=process.argv.slice(2);
if(!planFile||!output)throw Error('Usage: configured-window-baseline.mjs PLAN.json NEW_OUTPUT_DIR');
const planBytes=readFileSync(planFile),plan=JSON.parse(planBytes);
assert.equal(plan.format,'configured-window-baseline-plan/v1');
assert.match(plan.sourceCommit,/^[0-9a-f]{40}$/);
const runtime=resolve(plan.runtime);
const manifest=JSON.parse(readFileSync(resolve(runtime,'build-manifest.json')));
assert.equal(manifest.version,plan.version);
const inventory=()=>{
 const result={},pending=['sdk.mjs'];
 while(pending.length){
  const name=pending.pop();if(result[name])continue;
  const bytes=readFileSync(resolve(runtime,name));result[name]={bytes:bytes.length,sha256:sha(bytes)};
  pending.push(...parseStaticImports(bytes,name).relativeDependencies.map(x=>x.target));
 }
 return result;
};
const bindings=childCase?JSON.parse(readFileSync(resolve(output,'runtime-bindings.json'))):inventory();
const verifyRuntime=()=>{for(const [name,binding]of Object.entries(bindings))assert.equal(sha(readFileSync(resolve(runtime,name))),binding.sha256);};
verifyRuntime();assert.equal(bindings['core.mjs'].sha256,manifest.coreSha256);
const operations={writerWindow:'verifyConfiguredWriterWindowV4',pointWindow:'analyzeConfiguredPointWindowV4'};
assert.ok(Array.isArray(plan.cases)&&plan.cases.length>0&&plan.cases.length<=32);
assert.equal(new Set(plan.cases.map(x=>x.id)).size,plan.cases.length);
for(const entry of plan.cases){
 assert.match(entry.id,/^[a-z0-9-]{1,64}$/);assert.ok(Object.hasOwn(operations,entry.operation));
 assert.equal(entry.inputs.length,3);
 for(const source of entry.inputs){assert.match(source.sha256,/^[a-f0-9]{64}$/);assert.equal(sha(readFileSync(source.path)),source.sha256);}
}
const percentile=(values,p)=>values.toSorted((a,b)=>a-b)[Math.ceil(values.length*p)-1];
if(childCase){
 const entry=plan.cases.find(x=>x.id===childCase);assert.ok(entry);
 const args=entry.inputs.map(x=>readFileSync(x.path,'utf8'));
 const importStart=performance.now();const sdk=await import(pathToFileURL(resolve(runtime,'sdk.mjs')).href);
 const coldImportMs=performance.now()-importStart;
 const fn=sdk[operations[entry.operation]],samples=[];
 let value,coldCallMs;
 for(let i=0;i<(mode==='memory'?1:35);i++){
  const start=performance.now();value=fn(...args,entry.options??{});const ms=performance.now()-start;
  if(i===0)coldCallMs=ms;if(i>=5)samples.push(ms);
  assert.equal(value.status,entry.expectedStatus);
  if(entry.expectedStatus==='checked-compatible'||entry.expectedStatus==='refuted')assert.equal(value.coverageComplete,true);
 }
 const text=JSON.stringify(value);
 const peakRssKiB=process.resourceUsage().maxRSS;
 verifyRuntime();
 console.log(JSON.stringify({samples,coldImportMs,coldCallMs,peakRssKiB,
  status:value.status,outputBytes:Buffer.byteLength(text),outputSha256:sha(text)}));
}else{
 mkdirSync(output);writeFileSync(resolve(output,'runtime-bindings.json'),JSON.stringify(bindings),{flag:'wx'});const cases=[];
 for(const entry of plan.cases){
  const batches=[],memory=[];
  for(let i=0;i<3;i++)for(const kind of ['timing','memory']){
   const run=spawnSync(process.execPath,[fileURLToPath(import.meta.url),resolve(planFile),resolve(output),entry.id,kind],
    {encoding:'utf8',windowsHide:true,timeout:180000,maxBuffer:1024*1024});
   assert.equal(run.status,0,run.stderr||run.error?.message);
   (kind==='timing'?batches:memory).push(JSON.parse(run.stdout));
  }
  assert.equal(new Set([...batches,...memory].map(x=>x.outputSha256)).size,1);
  const samples=batches.flatMap(x=>x.samples);
  cases.push({id:entry.id,operation:entry.operation,status:batches[0].status,medianMs:percentile(samples,.5),
   p95Ms:percentile(samples,.95),peakRssKiB:Math.max(...memory.map(x=>x.peakRssKiB)),
   outputBytes:batches[0].outputBytes,outputSha256:batches[0].outputSha256,
   inputs:entry.inputs.map(x=>({sha256:x.sha256})),batches,memory});
  console.log(JSON.stringify({completed:entry.id,medianMs:cases.at(-1).medianMs,p95Ms:cases.at(-1).p95Ms}));
 }
 verifyRuntime();
 const receipt={format:'configured-window-baseline/v1',passed:true,comparisonPerformed:false,
  sourceCommit:plan.sourceCommit,version:manifest.version,planSha256:sha(planBytes),build:manifest,runtime:bindings,
  protocol:{warmups:5,samples:30,batches:3,memoryMeasuredInSeparateProcesses:true},
  environment:{node:process.version,platform:platform(),release:release(),arch:arch(),cpu:cpus()[0]?.model,
   logicalCpus:cpus().length,totalMemoryBytes:totalmem()},cases};
 writeFileSync(resolve(output,'baseline.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
}
